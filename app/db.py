"""SQLite storage for LeadPilot (standard library only)."""
import os
import sqlite3
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.environ.get("LEADPILOT_DB", os.path.join(ROOT, "data", "leadpilot.db"))

DEFAULT_PROFILE = {
    "business_name": "Pixel Peak Digital",
    "services": "Website design and development, SEO, Google and Meta ads, social media management, AI chatbots and automation",
    "contact": "hello@pixelpeak.example",
}

LEAD_FIELDS = ("name", "email", "phone", "company", "need", "budget", "timeline")


def conn():
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    c = sqlite3.connect(PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS profile (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS leads (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session TEXT, source TEXT DEFAULT 'chat',
              name TEXT, email TEXT, phone TEXT, company TEXT,
              need TEXT, budget TEXT, timeline TEXT,
              score INTEGER, tier TEXT, summary TEXT, next_step TEXT,
              email_subject TEXT, email_body TEXT,
              status TEXT DEFAULT 'new', qualified INTEGER DEFAULT 0,
              created REAL, updated REAL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              lead_id INTEGER, role TEXT, content TEXT, ts REAL
            );
            """
        )
        for k, v in DEFAULT_PROFILE.items():
            c.execute("INSERT OR IGNORE INTO profile (k, v) VALUES (?, ?)", (k, v))


def get_profile():
    with conn() as c:
        return {r["k"]: r["v"] for r in c.execute("SELECT k, v FROM profile")}


def set_profile(data: dict):
    with conn() as c:
        for k in DEFAULT_PROFILE:
            if k in data and isinstance(data[k], str):
                c.execute("INSERT OR REPLACE INTO profile (k, v) VALUES (?, ?)", (k, data[k].strip()[:500]))
    return get_profile()


def create_lead(session=None, source="chat", **fields):
    now = time.time()
    cols = ["session", "source", "created", "updated"] + [k for k in fields if k in LEAD_FIELDS]
    vals = [session, source, now, now] + [fields[k] for k in fields if k in LEAD_FIELDS]
    with conn() as c:
        cur = c.execute(f"INSERT INTO leads ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        return cur.lastrowid


def lead_by_session(session):
    with conn() as c:
        r = c.execute("SELECT * FROM leads WHERE session = ?", (session,)).fetchone()
        return dict(r) if r else None


def get_lead(lead_id):
    with conn() as c:
        r = c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(r) if r else None


def update_lead(lead_id, **fields):
    allowed = set(LEAD_FIELDS) | {"score", "tier", "summary", "next_step", "email_subject", "email_body", "status", "qualified"}
    items = [(k, v) for k, v in fields.items() if k in allowed]
    if not items:
        return
    sets = ", ".join(f"{k} = ?" for k, _ in items) + ", updated = ?"
    with conn() as c:
        c.execute(f"UPDATE leads SET {sets} WHERE id = ?", [v for _, v in items] + [time.time(), lead_id])


def add_message(lead_id, role, content):
    with conn() as c:
        c.execute("INSERT INTO messages (lead_id, role, content, ts) VALUES (?, ?, ?, ?)", (lead_id, role, content, time.time()))


def messages(lead_id):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT role, content, ts FROM messages WHERE lead_id = ? ORDER BY id", (lead_id,))]


def list_leads(tier=None):
    q = "SELECT * FROM leads"
    args = []
    if tier in ("hot", "warm", "cold"):
        q += " WHERE tier = ?"
        args.append(tier)
    q += " ORDER BY COALESCE(score, -1) DESC, created DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def delete_lead(lead_id):
    with conn() as c:
        c.execute("DELETE FROM messages WHERE lead_id = ?", (lead_id,))
        c.execute("DELETE FROM leads WHERE id = ?", (lead_id,))


def stats():
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) total,"
            " SUM(CASE WHEN tier='hot' THEN 1 ELSE 0 END) hot,"
            " SUM(CASE WHEN tier='warm' THEN 1 ELSE 0 END) warm,"
            " SUM(CASE WHEN tier='cold' THEN 1 ELSE 0 END) cold,"
            " SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) new,"
            " SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) won FROM leads"
        ).fetchone()
        return {k: (row[k] or 0) for k in row.keys()}
