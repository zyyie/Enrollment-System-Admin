"""Google Gemini free-tier API (cloud fallback — not a local LLM)."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "Geranova-EMS/1.0 (Python; scheduling)"


def call_gemini_json(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 90,
) -> tuple[dict | None, str | None, int | None]:
    """Returns (parsed_json, error_message, retry_after_seconds)."""
    query = urlencode({"key": api_key})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{query}"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as err:
        retry_after = _parse_retry_after(err)
        detail = err.read().decode("utf-8", errors="replace")
        return None, _shorten_gemini_error(err.code, detail), retry_after
    except URLError as err:
        return None, f"Gemini network error: {err.reason}", None
    except json.JSONDecodeError:
        return None, "Gemini returned invalid JSON envelope", None

    text = _extract_gemini_text(raw)
    if not text:
        return None, "Gemini returned an empty response", None

    try:
        parsed = json.loads(text)
        return (parsed if isinstance(parsed, dict) else None), None, None
    except json.JSONDecodeError:
        return None, f"Could not parse JSON from Gemini: {text[:200]}", None


def _extract_gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        return ""
    return (parts[0].get("text") or "").strip()


def _parse_retry_after(err: HTTPError) -> int | None:
    value = err.headers.get("Retry-After") if err.headers else None
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _shorten_gemini_error(code: int, detail: str) -> str:
    if code == 429:
        return "Gemini rate limit (429)"
    try:
        payload = json.loads(detail)
        message = (payload.get("error") or {}).get("message")
        if message:
            return f"Gemini HTTP {code}: {message[:120]}"
    except json.JSONDecodeError:
        pass
    return f"Gemini HTTP {code}: {detail[:120]}"
