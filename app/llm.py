"""Small LLM client (standard library only). Groq / OpenAI-compatible and Google Gemini.
Same setup as the Website Audit Agent, so the same .env works."""
import json
import os
import time
import urllib.error
import urllib.request

UA = "LeadPilot/1.0 (+https://star-78656.web.app)"


class AgentError(Exception):
    pass


def base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def api_key():
    return os.getenv("OPENAI_API_KEY") or None


def model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def mode() -> str:
    return "live" if api_key() else "demo"


def provider() -> str:
    explicit = os.getenv("AI_PROVIDER", "").lower()
    if explicit:
        return explicit
    return "gemini" if "generativelanguage.googleapis.com" in base_url() else "openai"


def _post(url, body, headers, retries=2):
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA, **headers})
        try:
            with urllib.request.urlopen(req, timeout=int(os.getenv("AI_TIMEOUT", "120"))) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")[:400]
            last = AgentError(f"AI API error {e.code}: {detail}")
            if e.code not in (429, 500, 502, 503):
                raise last
            if e.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = AgentError(f"AI request failed: {e}")
        time.sleep(2 * (attempt + 1))
    raise last


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise AgentError("Model did not return valid JSON.")


def chat_json(system: str, messages: list, temperature: float = 0.4) -> dict:
    """messages = [{"role": "user"|"assistant", "content": str}, ...]"""
    if provider() == "gemini":
        model = model_name().removeprefix("models/")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages]
        data = _post(url, {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        }, {"x-goog-api-key": api_key()})
        try:
            parts = data["candidates"][0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError):
            raise AgentError("Gemini returned no answer.")
        return parse_json(text)
    body = {
        "model": model_name(),
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}] + messages,
    }
    data = _post(base_url() + "/chat/completions", body, {"Authorization": f"Bearer {api_key()}"})
    try:
        return parse_json(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError):
        raise AgentError(f"Unexpected AI response: {str(data)[:300]}")
