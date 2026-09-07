"""Minimal Supabase helpers for the FastAPI scheduling service."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schedule_dedupe import dedupe_schedule_entries


ROOT = Path(__file__).resolve().parent.parent
GENERATED_SCHEDULES_FILE = ROOT / "data" / "generated_schedules.json"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.exists():
        return env
    raw = env_path.read_text(encoding="utf-8-sig")
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        env[key.strip()] = value
    return env


ENV = load_env()
SUPABASE_URL = ENV.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = ENV.get("SUPABASE_SECRET_KEY", "")


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SECRET_KEY)


def supabase_rest_get(
    table: str,
    query_string: str,
    *,
    timeout: int = 8,
) -> tuple[list | None, str | None]:
    if not supabase_configured():
        return None, "Supabase not configured"

    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_string}"
    request = Request(
        url,
        headers={
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, list) else [], None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        return None, f"HTTP {err.code}: {detail[:200]}"
    except URLError as err:
        return None, str(err.reason)


def supabase_rpc(
    function_name: str,
    payload: dict[str, Any],
    *,
    timeout: int = 20,
) -> tuple[Any | None, str | None]:
    if not supabase_configured():
        return None, "Supabase not configured"

    url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}, None
            return json.loads(raw), None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        return None, f"HTTP {err.code}: {detail[:300]}"
    except URLError as err:
        return None, str(err.reason)


def parse_supabase_error(error: str | None) -> str | None:
    if not error:
        return None
    match = re.search(r'"message"\s*:\s*"([^"]+)"', error)
    return match.group(1) if match else error


def save_generated_schedules(
    *,
    schedules: list[dict[str, Any]],
    grade_level: str,
    semester_code: str,
    source: str = "ortools",
    merge_strands: set[str] | None = None,
) -> dict[str, Any]:
    """Validate payload shape and persist via Supabase RPC or local JSON fallback."""
    record = {
        "appliedAt": datetime.now().isoformat(),
        "gradeLevel": grade_level,
        "semesterCode": semester_code,
        "schedules": schedules,
        "source": source,
    }

    if supabase_configured() and merge_strands:
        existing, error = supabase_rpc(
            "get_scheduler_existing_schedules",
            {
                "p_grade_level": grade_level,
                "p_semester_code": semester_code,
            },
            timeout=15,
        )
        if not error and isinstance(existing, list):
            merged = [
                item
                for item in existing
                if not (
                    str(item.get("strand") or "").upper() in merge_strands
                    and str(item.get("gradeLevel") or item.get("grade_level") or grade_level) == str(grade_level)
                )
            ]
            merged.extend(schedules)
            record["schedules"] = dedupe_schedule_entries(merged)

    if supabase_configured():
        result, error = supabase_rpc(
            "apply_generated_schedules",
            {"p_payload": record},
            timeout=20,
        )
        if error:
            return {
                "success": False,
                "error": parse_supabase_error(error) or "Failed to save schedules to Supabase.",
            }
        GENERATED_SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_SCHEDULES_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {
            "success": True,
            "source": "supabase",
            "count": len(record["schedules"]),
            **(result or {}),
        }

    GENERATED_SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_SCHEDULES_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {
        "success": True,
        "source": "local_file",
        "path": str(GENERATED_SCHEDULES_FILE.relative_to(ROOT)),
        "count": len(record["schedules"]),
    }
