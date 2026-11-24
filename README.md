# LeadPilot API

Backend for the LeadPilot frontend demo. It qualifies a lead, scores it from 0 to 100, sorts it into hot, warm or cold, and writes a follow-up email draft. Built with Python, FastAPI and SQLite.

This is a local demo. There is no login, so please use dummy data only.

## Run it

You need Python 3.10 or newer.

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Mac / Linux:  source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

The API is now at `http://127.0.0.1:8002`. Interactive docs are at `http://127.0.0.1:8002/docs`.

Check that it is up: `http://127.0.0.1:8002/api/health`

## Demo mode and live AI

With no key set, the API runs in demo mode (rule-based scoring, no AI service needed). `/api/health` shows `"mode": "demo"`. Everything the frontend needs works in this mode.

For real AI answers, copy `.env.example` to `.env` and put a key in `OPENAI_API_KEY`. Never commit `.env`.

## Sample data

An empty database has no leads. Load the sample leads once:

```bash
curl -X POST http://127.0.0.1:8002/api/seed
```

## Endpoints the frontend uses

| Method | Path | What it does |
|---|---|---|
| POST | `/api/leads` | Send a lead, get it back scored with an email draft |
| GET | `/api/leads` | All leads, best score first (`?tier=hot`, `warm` or `cold`) |
| GET | `/api/leads/{id}` | One lead with its messages |
| PATCH | `/api/leads/{id}` | Change status: `new`, `contacted`, `won`, `lost` |
| POST | `/api/leads/{id}/requalify` | Run the AI again on that lead |
| GET | `/api/stats` | Counts for the header badges |

Full request and response examples are in `docs/LeadPilot_API_Spec.pdf`.

## Field names

Send the backend names when you create a lead:

`name`, `email`, `phone`, `company`, `message`, `budget`, `timeline`, `source`

Fields the API does not know are ignored without an error. So if the form sends `fullName`, the lead is saved without a name. Map your form fields to the names above before you send.

| Form field | Send as |
|---|---|
| Full Name | `name` |
| Monthly Budget | `budget` |
| Service Needed + Project Notes | `message` (join the two) |
| Website | not stored yet |

## Connect from Next.js

Keep the base URL in one place, in `.env.local` of the frontend:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8002
```

```ts
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8002";

const res = await fetch(`${API}/api/leads`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name, email, company, message, budget, timeline }),
});
if (!res.ok) throw new Error((await res.json()).detail);
const lead = await res.json();
```

CORS is open, so a Next.js app on localhost can call the API directly. The scoring call waits for the AI, so show a loading state.

Errors look like `{"detail": "message"}`: `400` bad input, `404` lead not found, `502` the AI service failed.

## Notes

- `created` and `updated` are Unix seconds.
- The `status` field is the pipeline status. For the demo, `new` means "draft ready" and `contacted` means "follow-up sent".
- The database file is created in `data/` on first run and is not part of the repo.
