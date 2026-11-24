"""LeadPilot API + dashboard + embeddable chat widget. Run: uvicorn app.main:app --port 8002"""
import os
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(os.path.join(ROOT, ".env"))
# Reuse the Website Audit Agent's Groq settings when LeadPilot has no key of its own
_load_env(os.path.join(os.path.dirname(ROOT), "Website_Audit_Agent", ".env"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import agent, db, llm  # noqa: E402

app = FastAPI(title="LeadPilot", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
db.init()


class ChatIn(BaseModel):
    session: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class FormLead(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    message: str = ""
    budget: str = ""
    timeline: str = ""
    source: str = "form"


class StatusIn(BaseModel):
    status: str


class ProfileIn(BaseModel):
    business_name: str | None = None
    services: str | None = None
    contact: str | None = None


@app.get("/")
def home():
    return FileResponse(os.path.join(STATIC, "demo.html"))


@app.get("/dashboard")
def dashboard():
    return FileResponse(os.path.join(STATIC, "dashboard.html"))


@app.get("/widget.js")
def widget():
    return FileResponse(os.path.join(STATIC, "widget.js"), media_type="application/javascript")


@app.get("/api/health")
def health():
    return {"ok": True, "mode": llm.mode(), "model": llm.model_name() if llm.mode() == "live" else None}


@app.post("/api/chat/start")
def chat_start(session: str | None = None):
    sid = session or uuid.uuid4().hex
    greeting = agent.start_chat(sid)
    return {"session": sid, "greeting": greeting, "history": agent.history(sid)}


@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        return agent.chat(body.session, body.message)
    except llm.AgentError as e:
        raise HTTPException(502, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/leads")
def create_lead(body: FormLead):
    """Webhook for website forms, n8n, Zapier: sends the lead in, gets it scored + a follow-up email back."""
    if not (body.email or body.phone or body.message):
        raise HTTPException(400, "Send at least an email, phone or message")
    try:
        return agent.from_form(body.model_dump())
    except llm.AgentError as e:
        raise HTTPException(502, str(e))


@app.get("/api/leads")
def leads(tier: str | None = None):
    return db.list_leads(tier)


@app.get("/api/leads/{lead_id}")
def lead(lead_id: int):
    row = db.get_lead(lead_id)
    if not row:
        raise HTTPException(404, "Lead not found")
    row["messages"] = db.messages(lead_id)
    return row


@app.patch("/api/leads/{lead_id}")
def set_status(lead_id: int, body: StatusIn):
    if body.status not in ("new", "contacted", "won", "lost"):
        raise HTTPException(400, "Bad status")
    if not db.get_lead(lead_id):
        raise HTTPException(404, "Lead not found")
    db.update_lead(lead_id, status=body.status)
    return db.get_lead(lead_id)


@app.delete("/api/leads/{lead_id}")
def remove(lead_id: int):
    db.delete_lead(lead_id)
    return {"ok": True}


@app.post("/api/leads/{lead_id}/requalify")
def requalify(lead_id: int):
    if not db.get_lead(lead_id):
        raise HTTPException(404, "Lead not found")
    try:
        return agent.qualify(lead_id)
    except llm.AgentError as e:
        raise HTTPException(502, str(e))


@app.get("/api/stats")
def stats():
    return db.stats()


@app.get("/api/profile")
def get_profile():
    return db.get_profile()


@app.put("/api/profile")
def put_profile(body: ProfileIn):
    return db.set_profile(body.model_dump(exclude_none=True))


@app.post("/api/seed")
def seed():
    return {"added": agent.seed_samples()}
