"""LeadPilot brain: chat with visitors, collect lead info, score the lead, draft the follow-up email.

Live mode uses an LLM (Groq/OpenAI/Gemini). Demo mode (no API key) uses simple rules, so the
whole product still runs end to end.
"""
import json
import os
import re
import time
import urllib.request

from . import db, llm

FIELDS = db.LEAD_FIELDS
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")

CHAT_SYSTEM = """You are the friendly AI receptionist of {business}, a business that offers: {services}.
You are chatting with a visitor on the company website.

Goal: understand what the visitor needs and collect: need, budget, timeline, name, and an email or phone number.
Company is optional.

Rules:
- Ask ONE short question at a time (1-2 sentences). Warm, professional, simple English.
- Never invent prices, discounts, deadlines or promises. If asked for an exact price, say the team will send a quote.
- If the visitor goes off topic, answer briefly and steer back to their project.
- When you have need, budget, timeline, name and a way to contact them, thank them, say a team member will reach out
  shortly, and set "done" to true.

Reply ONLY with JSON in this shape, repeating everything you know so far from the WHOLE conversation:
{{"reply": "your message", "lead": {{"name": null, "email": null, "phone": null, "company": null, "need": null, "budget": null, "timeline": null}}, "done": false}}"""

QUALIFY_SYSTEM = """You are a sales operations assistant for {business} (services: {services}).
You get a lead and the conversation. Score how likely this lead is to become a paying client.
Scoring guide: clear need + realistic budget + short timeline + real contact details = high (70-100).
Some info missing or vague = medium (40-69). Little info, no budget, or just browsing = low (0-39).
Be honest and never invent facts that are not in the data.

Reply ONLY with JSON:
{{"score": 0-100 integer, "summary": "2 sentences about who they are and what they want",
 "next_step": "one concrete action for the sales team",
 "followup_subject": "email subject, max 70 characters",
 "followup_body": "email of 90-130 words, personal, mentions their specific need, no invented prices, one clear call to action (reply or a 15-minute call), signed '{business} Team'"}}"""


def _tier(score: int) -> str:
    return "hot" if score >= 70 else "warm" if score >= 40 else "cold"


def _clean(v):
    if v is None:
        return None
    v = str(v).strip()
    return v[:300] if v and v.lower() not in ("null", "none", "unknown", "n/a") else None


def _merge(lead_id, found: dict):
    current = db.get_lead(lead_id)
    upd = {}
    for k in FIELDS:
        new = _clean((found or {}).get(k))
        if new and new != current.get(k):
            upd[k] = new
    if upd:
        db.update_lead(lead_id, **upd)


# ---------------------------------------------------------------- demo (no API key) mode
DEMO_QUESTIONS = [
    ("need", "Hi! I'm the AI assistant here. What do you need help with: a website, SEO, ads, or something else?"),
    ("budget", "Great. Roughly what budget do you have in mind for this?"),
    ("timeline", "Thanks. When would you like to get started or have it finished?"),
    ("name", "Perfect. May I have your name?"),
    ("email", "Nice to meet you! What is the best email or phone number to reach you on?"),
]


def _demo_chat(lead_id: int, text: str):
    lead = db.get_lead(lead_id)
    upd = {}
    for key, _ in DEMO_QUESTIONS:
        if not lead.get(key) and not (key == "email" and lead.get("phone")):
            if key == "email":
                m = EMAIL_RE.search(text)
                p = PHONE_RE.search(text)
                if m:
                    upd["email"] = m.group(0)
                if p:
                    upd["phone"] = p.group(0).strip()
                if not m and not p:
                    return "That does not look like an email or phone number. Could you type it again?", False
            else:
                upd[key] = text.strip()[:300]
            break
    db.update_lead(lead_id, **upd)
    lead = db.get_lead(lead_id)
    for key, question in DEMO_QUESTIONS:
        if key == "email":
            if not (lead.get("email") or lead.get("phone")):
                return question, False
        elif not lead.get(key):
            return question, False
    return "Thank you! A team member will contact you shortly.", True


def _demo_qualify(lead: dict, business: str):
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", lead.get("budget") or "") if n.replace(",", "").isdigit()]
    top = max(nums) if nums else 0
    score = 35
    score += 25 if top >= 1000 else 12 if top >= 300 else 0
    score += 15 if re.search(r"asap|now|week|month|urgent|soon", (lead.get("timeline") or "").lower()) else 5
    score += 15 if lead.get("email") else 8 if lead.get("phone") else 0
    score += 8 if lead.get("need") and len(lead["need"]) > 20 else 0
    score = max(0, min(100, score))
    name = (lead.get("name") or "there").split()[0]
    need = lead.get("need") or "your project"
    return {
        "score": score,
        "summary": f"{lead.get('name') or 'A visitor'} is interested in: {need}. Budget: {lead.get('budget') or 'not given'}.",
        "next_step": "Call or email within 24 hours" if score >= 70 else "Send an email and ask for more details",
        "followup_subject": f"Your project: {need[:45]}",
        "followup_body": (
            f"Hi {name},\n\nThanks for reaching out to {business}. We received your request ({need}) and "
            f"we would love to help. Based on your timeline ({lead.get('timeline') or 'flexible'}), we can suggest a "
            f"clear plan and a fixed quote after a short call.\n\nWould a 15-minute call this week work for you? "
            f"Just reply to this email with a time that suits you.\n\nBest regards,\n{business} Team"
        ),
    }


# ---------------------------------------------------------------- public API
def _ctx():
    p = db.get_profile()
    return p["business_name"], p["services"]


def _transcript(lead_id: int) -> str:
    return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in db.messages(lead_id))


def start_chat(session: str):
    lead = db.lead_by_session(session)
    if not lead:
        lead_id = db.create_lead(session=session, source="chat")
        business, _ = _ctx()
        greeting = f"Hi! I'm the AI assistant at {business}. What can I help you with today?"
        db.add_message(lead_id, "assistant", greeting)
        return greeting
    msgs = db.messages(lead["id"])
    return msgs[0]["content"] if msgs else "Hi! How can I help you?"


def history(session: str):
    lead = db.lead_by_session(session)
    return [{"role": m["role"], "content": m["content"]} for m in db.messages(lead["id"])] if lead else []


def chat(session: str, text: str) -> dict:
    text = (text or "").strip()[:1000]
    if not text:
        raise ValueError("Empty message")
    lead = db.lead_by_session(session)
    if not lead:
        start_chat(session)
        lead = db.lead_by_session(session)
    lead_id = lead["id"]
    if lead.get("qualified"):
        db.add_message(lead_id, "user", text)
        reply = "Thanks! Our team already has your details and will contact you shortly."
        db.add_message(lead_id, "assistant", reply)
        return {"reply": reply, "done": True}
    db.add_message(lead_id, "user", text)
    business, services = _ctx()
    done = False
    if llm.mode() == "demo":
        reply, done = _demo_chat(lead_id, text)
    else:
        msgs = [{"role": m["role"], "content": m["content"]} for m in db.messages(lead_id)]
        out = llm.chat_json(CHAT_SYSTEM.format(business=business, services=services), msgs, temperature=0.5)
        reply = (out.get("reply") or "Could you tell me a bit more?").strip()
        _merge(lead_id, out.get("lead") or {})
        done = bool(out.get("done"))
        lead = db.get_lead(lead_id)
        if not done and len([m for m in db.messages(lead_id) if m["role"] == "user"]) >= 9:
            done = True
    db.add_message(lead_id, "assistant", reply)
    if done:
        qualify(lead_id)
    return {"reply": reply, "done": done}


def qualify(lead_id: int) -> dict:
    lead = db.get_lead(lead_id)
    business, services = _ctx()
    if llm.mode() == "demo":
        res = _demo_qualify(lead, business)
    else:
        user = f"Lead data: {json.dumps({k: lead.get(k) for k in FIELDS}, ensure_ascii=False)}\n\nConversation:\n{_transcript(lead_id) or '(none)'}"
        res = llm.chat_json(QUALIFY_SYSTEM.format(business=business, services=services), [{"role": "user", "content": user}], temperature=0.3)
    try:
        score = max(0, min(100, int(res.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    db.update_lead(
        lead_id, score=score, tier=_tier(score), qualified=1,
        summary=_clean(res.get("summary")) or "", next_step=_clean(res.get("next_step")) or "",
        email_subject=_clean(res.get("followup_subject")) or "", email_body=(res.get("followup_body") or "").strip(),
    )
    _webhook(db.get_lead(lead_id))
    return db.get_lead(lead_id)


def from_form(data: dict) -> dict:
    """Lead arrives from a website form / n8n / Zapier instead of the chat widget."""
    fields = {k: _clean(data.get(k)) for k in FIELDS}
    message = _clean(data.get("message"))
    if message and not fields.get("need"):
        fields["need"] = message
    lead_id = db.create_lead(source=_clean(data.get("source")) or "form", **{k: v for k, v in fields.items() if v})
    if message:
        db.add_message(lead_id, "user", message)
    return qualify(lead_id)


def _webhook(lead: dict):
    url = os.getenv("LEAD_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=json.dumps(lead).encode(), method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass  # a broken webhook must never break lead capture


# ---------------------------------------------------------------- sample data for demos
SAMPLES = [
    dict(name="Sarah Mitchell", email="sarah@greenleafcafe.com", company="Greenleaf Cafe", need="New website with online ordering for our 3 cafes", budget="$4,000 - $6,000", timeline="Launch in 6 weeks", score=91, source="chat",
         summary="Sarah runs a 3-location cafe group and needs a website with online ordering. Budget and timeline are clear.",
         next_step="Call today and book a discovery meeting", status="new",
         chat=[("assistant", "Hi! I'm the AI assistant at Pixel Peak Digital. What can I help you with today?"), ("user", "We need a new website with online ordering for our cafes"), ("assistant", "Sounds great! Roughly what budget do you have in mind?"), ("user", "Around 4 to 6 thousand dollars"), ("assistant", "And when would you like it live?"), ("user", "In about 6 weeks, we have a new menu launching")]),
    dict(name="Daniel Okoye", email="daniel@brightpath.io", company="BrightPath Logistics", need="SEO and Google Ads for freight quotes", budget="$1,500 per month", timeline="Start this month", score=84, source="chat",
         summary="Daniel's logistics company wants more quote requests from search. Ready to start this month with a monthly budget.",
         next_step="Send a proposal for SEO plus ads within 24 hours", status="contacted",
         chat=[("assistant", "Hi! I'm the AI assistant at Pixel Peak Digital. What can I help you with today?"), ("user", "Looking for SEO and Google ads, we want more freight quote requests"), ("assistant", "Got it. What monthly budget are you considering?"), ("user", "1500 a month")]),
    dict(name="Priya Nair", email="priya.nair@lumenskin.co", company="Lumen Skin", need="Social media management for a skincare brand", budget="$800 per month", timeline="Next quarter", score=63, source="form",
         summary="Priya's skincare brand wants social media help. Budget is modest and timing is a quarter away.",
         next_step="Email a package overview and ask about content needs", status="new", chat=[("user", "Hi, we are a skincare brand and want help with Instagram and TikTok next quarter.")]),
    dict(name="Tom Reyes", email="tom@reyesplumbing.com", company="Reyes Plumbing", need="Update our old website", budget="Not sure yet", timeline="No rush", score=41, source="chat",
         summary="Tom owns a small plumbing company with an outdated website. No budget or deadline yet.",
         next_step="Send a short case study and check back in 2 weeks", status="new",
         chat=[("assistant", "Hi! I'm the AI assistant at Pixel Peak Digital. What can I help you with today?"), ("user", "My website is old, maybe update it"), ("assistant", "What budget are you thinking about?"), ("user", "Not sure yet")]),
    dict(name="Alex", email="", company="", need="Just looking around", budget="", timeline="", score=18, source="chat",
         summary="Visitor browsed but shared no budget, timeline or contact details.",
         next_step="No action needed unless they return", status="new", chat=[("assistant", "Hi! I'm the AI assistant at Pixel Peak Digital. What can I help you with today?"), ("user", "just looking")]),
]


def seed_samples():
    business = db.get_profile()["business_name"]
    for s in SAMPLES:
        s = dict(s)
        chat = s.pop("chat")
        score, summary, nxt, status = s.pop("score"), s.pop("summary"), s.pop("next_step"), s.pop("status")
        first = (s.get("name") or "there").split()[0]
        lead_id = db.create_lead(**{k: v for k, v in s.items() if k in FIELDS or k == "source"})
        for role, content in chat:
            db.add_message(lead_id, role, content)
        body = (
            f"Hi {first},\n\nThanks for getting in touch with {business}. I read about {s.get('need', 'your project').lower()} "
            f"and we would love to help. After a short call we can share a clear plan and a fixed quote.\n\n"
            f"Would a 15-minute call this week work? Just reply with a time that suits you.\n\nBest regards,\n{business} Team"
        )
        db.update_lead(lead_id, score=score, tier=_tier(score), qualified=1, summary=summary, next_step=nxt,
                       email_subject=f"Your project: {s.get('need', '')[:40]}", email_body=body, status=status)
    return len(SAMPLES)
