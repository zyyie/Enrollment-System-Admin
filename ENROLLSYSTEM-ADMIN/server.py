"""
Enrollment System - Local Development Server
Run: python server.py
"""

import base64
import http.server
import json
import os
import re
import smtplib
import socketserver
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from email import encoders
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

from shared.services.email_templates import (
    APPLICANT_EMAIL_VERSION,
    build_admission_rejection_email,
    build_applicant_confirmation_email,
)
from shared.services.admission_schedules import resolve_subject_schedule_details
from shared.services.storage import (
    find_local_document,
    admin_document_view_url,
    load_admission_file_content,
    resolve_document_view_url,
    upload_admission_files_to_supabase,
)
from shared.validation.admission import validate_admission_fields, validate_admission_files

PORT = 8001
ROOT = Path(__file__).parent
UPLOADS_DIR = ROOT / "uploads" / "admissions"
LOCAL_ADMISSIONS_FILE = ROOT / "data" / "admissions.json"


def load_env():
    env = {}
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


def normalize_gmail_password(password):
    return re.sub(r"\s+", "", password or "")


ENV = load_env()
SUPABASE_URL = ENV.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = ENV.get("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = ENV.get("SUPABASE_SECRET_KEY", "")
GMAIL_USER = ENV.get("GMAIL_USER", "").strip().lower()
GMAIL_APP_PASSWORD = normalize_gmail_password(ENV.get("GMAIL_APP_PASSWORD", ""))
ADMIN_EMAIL = (ENV.get("ADMIN_EMAIL") or GMAIL_USER).strip().lower()
SCHOOL_NAME = ENV.get("SCHOOL_NAME", "Geranova Senior High School")
REMOVED_STRAND_CODES = {"GAS", "CSS", "HE", "INDARTS", "OTHER"}
LEGACY_FACULTY_IDS = {
    "FAC-CK-01", "FAC-CSS-01", "FAC-GAS-01", "FAC-HE-01", "FAC-HUM-01", "FAC-IA-01",
}
PAYMONGO_SECRET_KEY = ENV.get("PAYMONGO_SECRET_KEY", "")
ENROLLMENT_FEE = float(ENV.get("ENROLLMENT_FEE", "2500"))
GCASH_MERCHANT_NAME = ENV.get("GCASH_MERCHANT_NAME", SCHOOL_NAME)
GCASH_MERCHANT_NUMBER = ENV.get("GCASH_MERCHANT_NUMBER", "0945 661 0582")
GCASH_QR_IMAGE = ENV.get("GCASH_QR_IMAGE", "assets/gcash-qr.png")
GROQ_API_KEY = ENV.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = ENV.get("GROQ_MODEL", "llama-3.1-8b-instant").strip()
OPENROUTER_API_KEY = ENV.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = ENV.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free").strip()
GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = ENV.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
AI_ENABLE_OPENROUTER = ENV.get("AI_ENABLE_OPENROUTER", "").strip().lower() in ("1", "true", "yes")

PAYMENT_SESSIONS_FILE = ROOT / "data" / "payment_sessions.json"
GENERATED_SCHEDULES_FILE = ROOT / "data" / "generated_schedules.json"

_scheduler_service = None
_env_mtime: float | None = None


def reload_runtime_env(force: bool = False) -> bool:
    """Reload .env when the file changes so AI keys apply without a full restart."""
    global ENV, GROQ_API_KEY, GROQ_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODEL
    global GEMINI_API_KEY, GEMINI_MODEL, AI_ENABLE_OPENROUTER, _env_mtime, _scheduler_service

    env_path = ROOT / ".env"
    try:
        mtime = env_path.stat().st_mtime if env_path.exists() else None
    except OSError:
        mtime = None

    if not force and mtime == _env_mtime:
        return False

    ENV = load_env()
    GROQ_API_KEY = ENV.get("GROQ_API_KEY", "").strip()
    GROQ_MODEL = ENV.get("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    OPENROUTER_API_KEY = ENV.get("OPENROUTER_API_KEY", "").strip()
    OPENROUTER_MODEL = ENV.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free").strip()
    GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = ENV.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
    AI_ENABLE_OPENROUTER = ENV.get("AI_ENABLE_OPENROUTER", "").strip().lower() in ("1", "true", "yes")
    _env_mtime = mtime
    _scheduler_service = None
    return True


def effective_openrouter_api_key() -> str:
    """OpenRouter free tier is gone — only use when explicitly enabled."""
    if not AI_ENABLE_OPENROUTER:
        return ""
    return OPENROUTER_API_KEY


def get_scheduler_service():
    global _scheduler_service
    reload_runtime_env()
    if _scheduler_service is None:
        from scheduling.scheduler_service import SchedulerService

        def rest_get(table, query_string):
            return supabase_rest_get(table, query_string, use_secret=True, timeout=8)

        _scheduler_service = SchedulerService(
            groq_api_key=GROQ_API_KEY,
            groq_model=GROQ_MODEL,
            openrouter_api_key=effective_openrouter_api_key(),
            openrouter_model=OPENROUTER_MODEL,
            gemini_api_key=GEMINI_API_KEY,
            gemini_model=GEMINI_MODEL,
            rest_get=rest_get if supabase_configured() else None,
        )
    return _scheduler_service

REQUIRED_DOCS = {
    "form_138": "Original Copy of Form 138 (Report Card) signed by the Principal",
    "form_137": "Original Copy of Form 137",
    "good_moral": "Original Copy of Certificate of Good Moral Character",
    "birth_certificate": "Photocopy of Birth Certificate issued by PSA",
    "high_school_diploma": "High School Diploma",
}


def build_full_address(fields):
    parts = [
        fields.get("houseNumber", "").strip(),
        fields.get("street", "").strip(),
        fields.get("barangay", "").strip(),
        fields.get("city", "").strip(),
        fields.get("province", "").strip(),
    ]
    full = ", ".join(part for part in parts if part)
    return full or fields.get("address", "").strip()


def parse_address_breakdown(record):
    """Fill addr_* fields from a comma-separated address when columns are empty."""
    if not isinstance(record, dict):
        return record

    existing = [
        record.get("houseNumber") or record.get("addr_house_number"),
        record.get("street") or record.get("addr_street"),
        record.get("barangay") or record.get("addr_barangay"),
        record.get("city") or record.get("addr_city"),
        record.get("province") or record.get("addr_province"),
    ]
    if any(str(v or "").strip() for v in existing):
        return record

    address = str(record.get("address") or "").strip()
    if not address:
        return record

    parts = [part.strip() for part in address.split(",") if part.strip()]
    if len(parts) >= 5:
        record.setdefault("houseNumber", parts[0])
        record.setdefault("street", parts[1])
        record.setdefault("barangay", parts[2])
        record.setdefault("city", parts[3])
        record.setdefault("province", parts[4])
    elif len(parts) == 4:
        record.setdefault("street", parts[0])
        record.setdefault("barangay", parts[1])
        record.setdefault("city", parts[2])
        record.setdefault("province", parts[3])
    return record


def load_payment_sessions():
    if not PAYMENT_SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(PAYMENT_SESSIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_payment_sessions(sessions):
    PAYMENT_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAYMENT_SESSIONS_FILE.write_text(json.dumps(sessions, indent=2), encoding="utf-8")


def get_base_url(handler):
    host = handler.headers.get("Host", f"localhost:{PORT}")
    return f"http://{host}"


def create_paymongo_checkout(handler, session_id, amount_php):
    amount_centavos = int(round(amount_php * 100))
    base_url = get_base_url(handler)
    payload = {
        "data": {
            "attributes": {
                "send_email_receipt": False,
                "show_description": True,
                "show_line_items": True,
                "line_items": [{
                    "currency": "PHP",
                    "amount": amount_centavos,
                    "name": f"{SCHOOL_NAME} — Enrollment Fee",
                    "quantity": 1,
                }],
                "payment_method_types": ["gcash"],
                "success_url": f"{base_url}/payment-success.html?session_id={session_id}",
                "cancel_url": f"{base_url}/enroll.html?payment=cancelled",
                "description": f"{SCHOOL_NAME} Enrollment Fee",
            }
        }
    }
    auth = base64.b64encode(f"{PAYMONGO_SECRET_KEY}:".encode()).decode()
    request = Request(
        "https://api.paymongo.com/v1/checkout_sessions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    attrs = data["data"]["attributes"]
    checkout_url = attrs.get("checkout_url")
    paymongo_id = data["data"]["id"]
    return checkout_url, paymongo_id


def fetch_paymongo_session(paymongo_session_id):
    auth = base64.b64encode(f"{PAYMONGO_SECRET_KEY}:".encode()).decode()
    request = Request(
        f"https://api.paymongo.com/v1/checkout_sessions/{paymongo_session_id}",
        headers={"Authorization": f"Basic {auth}"},
        method="GET",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def handle_create_gcash_payment(handler):
    body = read_json_body(handler)
    session_id = str(uuid.uuid4())
    amount = ENROLLMENT_FEE
    sessions = load_payment_sessions()

    if PAYMONGO_SECRET_KEY:
        try:
            checkout_url, paymongo_id = create_paymongo_checkout(handler, session_id, amount)
            sessions[session_id] = {
                "mode": "paymongo",
                "status": "pending",
                "amount": amount,
                "paymongoId": paymongo_id,
                "reference": None,
                "createdAt": datetime.now().isoformat(),
            }
            save_payment_sessions(sessions)
            json_response(handler, 200, {
                "success": True,
                "mode": "paymongo",
                "sessionId": session_id,
                "checkoutUrl": checkout_url,
                "amount": amount,
            })
            return
        except (HTTPError, URLError, KeyError, ValueError) as err:
            detail = str(err)
            if isinstance(err, HTTPError):
                detail = err.read().decode("utf-8", errors="ignore")
            json_response(handler, 500, {
                "success": False,
                "error": f"PayMongo error: {detail}",
            })
            return

    sessions[session_id] = {
        "mode": "demo",
        "status": "pending",
        "amount": amount,
        "reference": None,
        "createdAt": datetime.now().isoformat(),
    }
    save_payment_sessions(sessions)
    json_response(handler, 200, {
        "success": True,
        "mode": "demo",
        "sessionId": session_id,
        "amount": amount,
    })


def handle_verify_gcash_payment(handler, session_id):
    if not session_id:
        json_response(handler, 400, {"success": False, "error": "Session ID required"})
        return

    sessions = load_payment_sessions()
    session = sessions.get(session_id)
    if not session:
        json_response(handler, 404, {"success": False, "error": "Payment session not found"})
        return

    if session.get("mode") == "paymongo" and session.get("status") != "paid":
        paymongo_id = session.get("paymongoId")
        if paymongo_id and PAYMONGO_SECRET_KEY:
            try:
                data = fetch_paymongo_session(paymongo_id)
                attrs = data.get("data", {}).get("attributes", {})
                payments = attrs.get("payments") or []
                paid = attrs.get("status") == "paid" or any(
                    p.get("attributes", {}).get("status") == "paid" for p in payments
                )
                if paid:
                    reference = None
                    if payments:
                        reference = payments[0].get("attributes", {}).get("source", {}).get("id")
                    session["status"] = "paid"
                    session["reference"] = reference or f"PM-{paymongo_id[-8:].upper()}"
                    session["paidAt"] = datetime.now().isoformat()
                    sessions[session_id] = session
                    save_payment_sessions(sessions)
            except (HTTPError, URLError, KeyError):
                pass

    paid = session.get("status") == "paid"
    json_response(handler, 200, {
        "success": True,
        "paid": paid,
        "reference": session.get("reference"),
        "amount": session.get("amount"),
        "sessionId": session_id,
    })


def handle_complete_demo_gcash_payment(handler):
    body = read_json_body(handler)
    session_id = body.get("sessionId")
    mobile = body.get("mobileNumber", "")

    if not session_id:
        json_response(handler, 400, {"success": False, "error": "Session ID required"})
        return

    sessions = load_payment_sessions()
    session = sessions.get(session_id)
    if not session:
        json_response(handler, 404, {"success": False, "error": "Payment session not found"})
        return

    reference = f"GCASH-{datetime.now().strftime('%Y%m%d')}-{mobile[-4:]}"
    session["status"] = "paid"
    session["reference"] = reference
    session["mobile"] = mobile
    session["paidAt"] = datetime.now().isoformat()
    sessions[session_id] = session
    save_payment_sessions(sessions)

    json_response(handler, 200, {
        "success": True,
        "paid": True,
        "reference": reference,
        "amount": session.get("amount"),
        "sessionId": session_id,
    })


def handle_gcash_config(handler):
    json_response(handler, 200, {
        "success": True,
        "merchantName": GCASH_MERCHANT_NAME,
        "merchantNumber": GCASH_MERCHANT_NUMBER,
        "qrImage": GCASH_QR_IMAGE,
        "amount": ENROLLMENT_FEE,
        "schoolName": SCHOOL_NAME,
    })


def build_config_js():
    enabled = bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY)
    config = {
        "url": SUPABASE_URL,
        "publishableKey": SUPABASE_PUBLISHABLE_KEY,
        "enabled": enabled,
        "enrollmentFee": ENROLLMENT_FEE,
    }
    return "window.SUPABASE_CONFIG = " + json.dumps(config) + ";\n"


def json_response(handler, status, payload):
    content = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def parse_multipart_form(handler):
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        return None

    boundary_match = re.search(r"boundary=(.+)", content_type)
    if not boundary_match:
        return None

    boundary = boundary_match.group(1).strip().strip('"')
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length)

    parts = body.split(f"--{boundary}".encode())
    fields = {}
    files = {}

    for part in parts:
        if not part or part in (b"--\r\n", b"--"):
            continue
        if b"\r\n\r\n" not in part:
            continue

        header_block, content = part.split(b"\r\n\r\n", 1)
        content = content.rstrip(b"\r\n")
        if not content:
            continue

        header_text = header_block.decode("utf-8", errors="ignore")
        name_match = re.search(r'name="([^"]+)"', header_text)
        if not name_match:
            continue

        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', header_text)

        if filename_match and filename_match.group(1):
            files[name] = {
                "filename": filename_match.group(1),
                "content": content,
            }
        else:
            fields[name] = content.decode("utf-8", errors="ignore")

    return {"fields": fields, "files": files}


def supabase_configured():
    return bool(SUPABASE_URL and (SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY))


def parse_supabase_error(error):
    if not error:
        return "Unknown Supabase error"
    try:
        data = json.loads(error)
        message = data.get("message") or data.get("error") or data.get("hint")
        if message:
            return str(message)
    except (json.JSONDecodeError, TypeError):
        pass
    return str(error)[:500]


def friendly_user_error(message, fallback="Something went wrong. Please try again or contact the system administrator."):
    """Return a safe message for end users — never expose DB or setup instructions."""
    if not message:
        return fallback
    text = str(message).strip()
    if not text:
        return fallback
    lower = text.lower()
    blocked = (
        "supabase", "sql editor", ".sql", "run supabase", "re-run",
        "migration", "service_role", "publishable", ".env",
        "postgresql", "permission denied", "rpc ", "schema ",
        "column ", "violates", "foreign key", "does not exist",
        "failed to fetch", "typeerror", "pgrst", "rest/v1",
        "enrollment-workflow", "schedule-sync", "fix-student-login",
        "fix-approve-review", "faculty-strands-rooms", "publish-schedules",
    )
    if any(token in lower for token in blocked):
        return fallback
    if len(text) > 280:
        return fallback
    return text


def supabase_rpc(function_name, params=None, use_secret=True, timeout=6):
    if not SUPABASE_URL:
        return None, "Supabase URL is not configured"

    key = SUPABASE_SECRET_KEY if use_secret and SUPABASE_SECRET_KEY else SUPABASE_PUBLISHABLE_KEY
    if not key:
        return None, "Supabase API key is not configured"

    url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"
    payload = json.dumps(params or {}).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def normalize_rpc_json_array(result):
    """RPC functions that RETURN JSON may arrive as list, JSON string, or null."""
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
        return []
    return []


DEFAULT_FACULTY = {
    "faculty_id": "FAC-2026-0001",
    "last_name": "DELA CRUZ",
    "first_name": "JUAN",
    "middle_name": "MARTINEZ",
    "role": "Registrar",
    "department": "Registrar Office",
    "password": "faculty123",
    "is_active": True,
}


def supabase_rest_get(table, query_string, use_secret=True, timeout=6):
    if not SUPABASE_URL:
        return None, "Supabase URL is not configured"

    key = SUPABASE_SECRET_KEY if use_secret and SUPABASE_SECRET_KEY else SUPABASE_PUBLISHABLE_KEY
    if not key:
        return None, "Supabase API key is not configured"

    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_string}"
    request = Request(
        url,
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return (json.loads(raw) if raw else []), None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def supabase_rest_upsert(table, rows, on_conflict):
    if not SUPABASE_URL:
        return None, "Supabase URL is not configured"

    key = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
    if not key:
        return None, "Supabase API key is not configured"

    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"
    payload = json.dumps(rows if isinstance(rows, list) else [rows]).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return (json.loads(raw) if raw else {"success": True}), None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def supabase_rest_insert(table, row, return_representation=False):
    if not SUPABASE_URL:
        return None, "Supabase URL is not configured"

    key = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
    if not key:
        return None, "Supabase API key is not configured"

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    payload = json.dumps(row if isinstance(row, dict) else row).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if return_representation:
        headers["Prefer"] = "return=representation"

    request = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if return_representation and raw:
                parsed = json.loads(raw)
                return (parsed[0] if isinstance(parsed, list) and parsed else parsed), None
            return ({"success": True}), None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def supabase_rest_patch(table, query_string, payload):
    if not SUPABASE_URL:
        return None, "Supabase URL is not configured"

    key = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
    if not key:
        return None, "Supabase API key is not configured"

    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_string}"
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return {"success": True}, None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def supabase_rest_delete(table, query_string):
    if not SUPABASE_URL:
        return None, "Supabase URL is not configured"

    key = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
    if not key:
        return None, "Supabase API key is not configured"

    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_string}"
    request = Request(
        url,
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return {"success": True}, None
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        return None, detail or err.reason
    except URLError as err:
        return None, str(err.reason)


def require_supabase_api(handler):
    if not supabase_configured():
        json_response(handler, 503, {
            "success": False,
            "error": "Supabase is not configured.",
            "hint": "Add SUPABASE_URL and SUPABASE_SECRET_KEY to .env",
        })
        return False
    return True


def parse_supabase_error(raw):
    text = str(raw or "")
    if "faculty_strands" in text:
        return "This action is temporarily unavailable. Please contact the system administrator."
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            hint = data.get("hint") or ""
            message = data.get("message") or data.get("error") or ""
            if "permission denied" in message.lower() and "service_role" in hint.lower():
                return "This action is temporarily unavailable. Please contact the system administrator."
            return message or hint or text[:240]
    except (json.JSONDecodeError, TypeError):
        pass
    if "permission denied" in text.lower():
        return "Database permissions missing. Re-run supabase/faculty-strands-rooms.sql in Supabase SQL Editor."
    return text[:240] or "Database request failed."


def normalize_teacher_row(row):
    strand_links = row.pop("faculty_strands", None) or []
    strands = []
    for link in strand_links:
        strand = link.get("strands") if isinstance(link, dict) else None
        if isinstance(strand, dict) and strand.get("code"):
            code = strand["code"].upper()
            if code not in REMOVED_STRAND_CODES:
                strands.append(code)
    row["strands"] = sorted(set(strands))
    row["name"] = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
    password = (row.get("password") or "").strip()
    row["password"] = password or "teacher123"
    return row


def is_removed_faculty(teacher):
    faculty_id = (teacher.get("faculty_id") or "").upper()
    if faculty_id in LEGACY_FACULTY_IDS:
        return True
    department = (teacher.get("department") or "").upper().strip()
    strands = [(s or "").upper() for s in (teacher.get("strands") or [])]

    for code in REMOVED_STRAND_CODES:
        if code in strands:
            return True
        if faculty_id.startswith(f"FAC-{code}-") or f"-{code}-" in faculty_id:
            return True
        if department.startswith(f"{code} DEPARTMENT") or department == code:
            return True
    return False


def filter_active_teachers(teachers):
    return [
        t for t in teachers
        if t.get("is_active", True) and not is_removed_faculty(t)
    ]


def deactivate_removed_strand_faculty():
    if not supabase_configured():
        return
    for code in REMOVED_STRAND_CODES:
        dept_pattern = quote(f"{code} Department%", safe="%")
        supabase_rest_patch(
            "faculty",
            f"role=eq.Teacher&or=(faculty_id.ilike.FAC-{code}-%,department.ilike.{dept_pattern})",
            {"is_active": False},
        )
        removed_strands, _ = supabase_rest_get(
            "strands",
            f"code=eq.{code}&select=id",
            use_secret=True,
        )
        if removed_strands:
            strand_id = removed_strands[0].get("id")
            if strand_id:
                supabase_rest_delete("faculty_strands", f"strand_id=eq.{strand_id}")


def fetch_teacher_detail(teacher_id):
    if not teacher_id:
        return None, "Teacher id required"

    query = (
        f"id=eq.{teacher_id}&role=eq.Teacher"
        "&select=id,faculty_id,first_name,last_name,middle_name,department,email,password,"
        "max_load_units,is_active,role,last_login,faculty_strands(strands(code,name))"
    )
    rows, error = supabase_rest_get("faculty", query, use_secret=True)
    if error and "faculty_strands" in str(error):
        rows, error = supabase_rest_get(
            "faculty",
            f"id=eq.{teacher_id}&role=eq.Teacher"
            "&select=id,faculty_id,first_name,last_name,middle_name,department,email,password,"
            "max_load_units,is_active,role,last_login",
            use_secret=True,
        )
    if error:
        return None, parse_supabase_error(error)
    if not rows:
        return None, "Teacher not found"
    teacher = normalize_teacher_row(dict(rows[0]))
    if is_removed_faculty(teacher):
        return None, "Teacher not found"
    return teacher, None


def handle_get_teacher_detail(handler):
    if not require_supabase_api(handler):
        return
    params = parse_qs(urlparse(handler.path).query)
    teacher_id = (params.get("id") or [""])[0].strip()
    teacher, error = fetch_teacher_detail(teacher_id)
    if error:
        json_response(handler, 404 if error == "Teacher not found" else 502, {
            "success": False,
            "error": error,
        })
        return
    json_response(handler, 200, {"success": True, "data": teacher})


def sync_teacher_strands(faculty_uuid, strand_codes):
    _, del_err = supabase_rest_delete("faculty_strands", f"faculty_id=eq.{faculty_uuid}")
    if del_err:
        return False, parse_supabase_error(del_err)

    for code in strand_codes or []:
        strand_id = get_supabase_strand_id(code)
        if not strand_id:
            continue
        _, ins_err = supabase_rest_insert("faculty_strands", {
            "faculty_id": faculty_uuid,
            "strand_id": strand_id,
        })
        if ins_err:
            return False, parse_supabase_error(ins_err)
    return True, None


def handle_list_teachers(handler):
    if not require_supabase_api(handler):
        return
    query = (
        "select=id,faculty_id,first_name,last_name,middle_name,department,email,password,"
        "max_load_units,is_active,role,faculty_strands(strands(code,name))"
        "&role=eq.Teacher&order=last_name.asc"
    )
    rows, error = supabase_rest_get("faculty", query, use_secret=True, timeout=20)
    if error and "faculty_strands" in str(error):
        rows, error = supabase_rest_get(
            "faculty",
            "select=id,faculty_id,first_name,last_name,middle_name,department,email,password,"
            "max_load_units,is_active,role&role=eq.Teacher&order=last_name.asc",
            use_secret=True,
            timeout=20,
        )
    if error:
        json_response(handler, 502, {
            "success": False,
            "error": parse_supabase_error(error),
            "hint": "Run supabase/faculty-strands-rooms.sql in Supabase SQL Editor.",
        })
        return
    try:
        deactivate_removed_strand_faculty()
    except Exception:
        pass
    teachers = filter_active_teachers([
        normalize_teacher_row(dict(row)) for row in (rows or [])
    ])
    json_response(handler, 200, {"success": True, "data": teachers})


def generate_teacher_faculty_id(strand_codes=None):
    rows, _ = supabase_rest_get(
        "faculty",
        "select=faculty_id",
        use_secret=True,
        timeout=20,
    )
    existing = {str(row.get("faculty_id") or "").upper() for row in (rows or [])}

    codes = [str(code or "").strip().upper() for code in (strand_codes or []) if str(code or "").strip()]
    for code in codes:
        prefix = f"FAC-{code}-"
        nums = []
        for faculty_id in existing:
            if not faculty_id.startswith(prefix):
                continue
            suffix = faculty_id[len(prefix):]
            if suffix.isdigit():
                nums.append(int(suffix))
        candidate = f"{prefix}{(max(nums, default=0) + 1):02d}"
        if candidate not in existing:
            return candidate

    year = datetime.now().strftime("%Y")
    prefix = f"FAC-{year}-"
    nums = []
    for faculty_id in existing:
        if not faculty_id.startswith(prefix):
            continue
        suffix = faculty_id[len(prefix):]
        if suffix.isdigit():
            nums.append(int(suffix))
    next_seq = max(nums, default=0) + 1
    candidate = f"{prefix}{next_seq:04d}"
    while candidate in existing:
        next_seq += 1
        candidate = f"{prefix}{next_seq:04d}"
    return candidate


def generate_next_student_id():
    year = datetime.now().strftime("%Y")
    rows, _ = supabase_rest_get(
        "students",
        f"student_id=like.{year}-%&select=student_id&order=student_id.desc&limit=1",
        use_secret=True,
    )
    next_seq = 1
    if isinstance(rows, list) and rows:
        existing = rows[0].get("student_id") or ""
        try:
            next_seq = int(existing.split("-")[1]) + 1
        except (ValueError, IndexError):
            next_seq = 1
    return f"{year}-{next_seq:05d}-SHS-0"


DEFAULT_STRAND_ROWS = [
    {"code": "STEM", "name": "STEM - Science, Technology, Engineering, and Mathematics", "track": "Academic"},
    {"code": "ABM", "name": "Accountancy, Business & Management", "track": "Academic"},
    {"code": "HUMSS", "name": "Humanities & Social Sciences", "track": "Academic"},
    {"code": "ICT", "name": "Information and Communications Technology", "track": "TechPro"},
    {"code": "COOKERY", "name": "Cookery", "track": "TechPro"},
    {"code": "EIM", "name": "Electrical Installation and Maintenance", "track": "TechPro"},
]

DEFAULT_STRAND_CODE = "STEM"


def filter_active_strand_rows(rows):
    return [r for r in (rows or []) if (r.get("code") or "").upper() not in REMOVED_STRAND_CODES]


def deactivate_removed_strands():
    if not supabase_configured():
        return
    for code in REMOVED_STRAND_CODES:
        supabase_rest_patch("strands", f"code=eq.{code}", {"is_active": False})


def deactivate_removed_strand_subjects():
    if not supabase_configured():
        return
    deactivate_removed_strands()
    for code in REMOVED_STRAND_CODES:
        removed_strands, _ = supabase_rest_get(
            "strands",
            f"code=eq.{code}&select=id",
            use_secret=True,
        )
        if removed_strands:
            strand_id = removed_strands[0].get("id")
            if strand_id:
                supabase_rest_patch("subjects", f"strand_id=eq.{strand_id}", {"is_active": False})
    deprecated_code_filter = ",".join(
        f"code.ilike.{pattern}"
        for pattern in (
            "G11-CSS-%", "G12-CSS-%", "CSS-%",
            "G11-GAS-%", "G12-GAS-%", "GAS-%",
            "G11-HE-%", "G12-HE-%", "HE-%",
            "G11-IA-%", "G12-IA-%", "IA-%", "INDARTS-%",
        )
    )
    supabase_rest_patch("subjects", f"or=({deprecated_code_filter})", {"is_active": False})


def is_removed_subject_code(subject_code):
    code = (subject_code or "").upper()
    if not code:
        return False
    for removed in REMOVED_STRAND_CODES:
        if code.startswith(f"{removed}-"):
            return True
        if re.search(rf"^G1[12]-{re.escape(removed)}-", code):
            return True
    if re.search(r"^G1[12]-(CSS|GAS|HE|IA)-", code):
        return True
    if code.startswith("IA-") or code.startswith("INDARTS-"):
        return True
    return False


def is_removed_subject_row(row):
    strand = row.get("strands") or {}
    strand_code = (strand.get("code") or "").upper()
    if strand_code in REMOVED_STRAND_CODES:
        return True
    return is_removed_subject_code(row.get("code"))


def _validate_local_python_modules():
    import py_compile

    for name in ("enrollment_curriculum.py",):
        path = ROOT / name
        if not path.exists():
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            raise SystemExit(
                f"\n{path.name} has invalid Python syntax and the admin server cannot start.\n"
                f"{exc}\n"
                f"Fix the indentation/syntax in that file, or copy "
                f"ENROLLSYSTEM/enrollment_curriculum.py to ENROLLSYSTEM-ADMIN/.\n"
            ) from exc


def build_subject_semester_map():
    mapping = {}
    try:
        from enrollment_curriculum import ENROLLMENT_CURRICULUM
    except ImportError:
        return mapping
    for grade_level, semesters in ENROLLMENT_CURRICULUM.items():
        for semester, config in semesters.items():
            for bucket in ("core", "applied"):
                for item in config.get(bucket, []):
                    mapping[(item.get("code") or "").upper()] = semester
            for strand, specs in config.get("specialized", {}).items():
                if (strand or "").upper() in REMOVED_STRAND_CODES:
                    continue
                for spec in specs:
                    mapping[(spec.get("code") or "").upper()] = semester
    return mapping


_validate_local_python_modules()
SUBJECT_SEMESTER_MAP = build_subject_semester_map()


def fetch_active_strand_codes():
    if not supabase_configured():
        return [row["code"] for row in DEFAULT_STRAND_ROWS]
    deactivate_removed_strands()
    rows, error = supabase_rest_get(
        "strands",
        "select=code&is_active=eq.true&order=code.asc",
        use_secret=True,
    )
    if error or not rows:
        return [row["code"] for row in DEFAULT_STRAND_ROWS]
    return [r["code"] for r in filter_active_strand_rows(rows)]


def fetch_active_strand_count():
    return len(fetch_active_strand_codes())


def curriculum_fallback_strands():
    return [
        {**row, "id": None, "is_active": True, "source": "curriculum_fallback"}
        for row in DEFAULT_STRAND_ROWS
    ]


def ensure_default_strands():
    errors = []
    for row in DEFAULT_STRAND_ROWS:
        _, error = supabase_rest_upsert(
            "strands",
            {**row, "is_active": True},
            "code",
        )
        if error:
            errors.append(parse_supabase_error(error))
            break
    return not errors, errors[0] if errors else None


def handle_list_strands(handler):
    if not require_supabase_api(handler):
        return

    ensure_default_strands()
    deactivate_removed_strands()
    rows, error = supabase_rest_get(
        "strands",
        "select=id,code,name,track,is_active&is_active=eq.true&order=code.asc",
        use_secret=True,
    )
    if error:
        json_response(handler, 200, {
            "success": True,
            "data": curriculum_fallback_strands(),
            "warning": parse_supabase_error(error),
            "source": "curriculum_fallback",
        })
        return

    if not rows:
        ensure_default_strands()
        deactivate_removed_strands()
        rows, error = supabase_rest_get(
            "strands",
            "select=id,code,name,track,is_active&is_active=eq.true&order=code.asc",
            use_secret=True,
        )

    rows = filter_active_strand_rows(rows)
    json_response(handler, 200, {
        "success": True,
        "data": rows or curriculum_fallback_strands(),
        "source": "supabase" if rows else "curriculum_fallback",
    })


def normalize_subject_row(row):
    strand = row.get("strands") or {}
    code = (strand.get("code") or "").upper()
    subject_code = (row.get("code") or "").upper()
    semester_code = row.get("semester_code") or SUBJECT_SEMESTER_MAP.get(subject_code)
    return {
        "id": row.get("id"),
        "code": row.get("code"),
        "name": row.get("name"),
        "description": row.get("description"),
        "gradeLevel": row.get("grade_level"),
        "semesterCode": semester_code,
        "semesterLabel": "1st Semester" if semester_code == "1st" else "2nd Semester" if semester_code == "2nd" else "—",
        "lecHours": row.get("lec_hours") or 0,
        "labHours": row.get("lab_hours") or 0,
        "units": row.get("units") or 0,
        "strand": code or "All Strands",
        "strandCode": code or None,
        "isActive": row.get("is_active", True),
    }


def handle_list_subjects(handler):
    if not require_supabase_api(handler):
        return
    deactivate_removed_strand_subjects()
    rows, error = supabase_rest_get(
        "subjects",
        "select=id,code,name,description,grade_level,semester_code,lec_hours,lab_hours,units,is_active,"
        "strands(code,name)&is_active=eq.true&order=grade_level.asc,code.asc",
        use_secret=True,
    )
    if error:
        json_response(handler, 502, {
            "success": False,
            "error": parse_supabase_error(error),
            "hint": "Run supabase/faculty-strands-rooms.sql in Supabase SQL Editor.",
        })
        return
    subjects = [
        normalize_subject_row(dict(row))
        for row in (rows or [])
        if not is_removed_subject_row(dict(row))
    ]
    json_response(handler, 200, {"success": True, "data": subjects})


def handle_save_subject(handler):
    if not require_supabase_api(handler):
        return
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    subject_id = body.get("id")
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    description = (body.get("description") or name).strip()
    grade_level = body.get("gradeLevel") or "Grade 12"
    units = int(body.get("units") or 3)
    lec_hours = int(body.get("lecHours") if body.get("lecHours") is not None else units)
    lab_hours = int(body.get("labHours") or 0)
    strand_code = (body.get("strandCode") or body.get("strand") or "").strip().upper()
    semester_code = (body.get("semesterCode") or body.get("semester") or "").strip().lower()
    is_active = body.get("isActive", True)

    if not code or not name:
        json_response(handler, 400, {"success": False, "error": "Subject code and name are required."})
        return
    if is_removed_subject_code(code):
        json_response(handler, 400, {
            "success": False,
            "error": "This subject belongs to a removed strand (CSS, GAS, HE, INDARTS) and cannot be saved.",
        })
        return
    if strand_code in REMOVED_STRAND_CODES:
        json_response(handler, 400, {
            "success": False,
            "error": f"Strand '{strand_code}' is no longer offered.",
        })
        return
    if grade_level not in ("Grade 11", "Grade 12"):
        json_response(handler, 400, {"success": False, "error": "Invalid grade level."})
        return

    payload = {
        "code": code,
        "name": name,
        "description": description,
        "grade_level": grade_level,
        "lec_hours": lec_hours,
        "lab_hours": lab_hours,
        "units": units,
        "is_active": bool(is_active),
    }
    if semester_code in ("1st", "2nd"):
        payload["semester_code"] = semester_code
    elif SUBJECT_SEMESTER_MAP.get(code):
        payload["semester_code"] = SUBJECT_SEMESTER_MAP[code]

    if strand_code and strand_code not in ("ALL", "ALL STRANDS", "—"):
        ensure_default_strands()
        strand_id = get_supabase_strand_id(strand_code)
        if not strand_id:
            json_response(handler, 400, {
                "success": False,
                "error": f"Strand '{strand_code}' not found. Add it under Strands first or run the SQL seed.",
            })
            return
        payload["strand_id"] = strand_id
    else:
        payload["strand_id"] = None

    if subject_id:
        _, error = supabase_rest_patch("subjects", f"id=eq.{subject_id}", payload)
        if error:
            json_response(handler, 502, {"success": False, "error": parse_supabase_error(error)})
            return
        json_response(handler, 200, {"success": True, "message": "Subject updated."})
        return

    _, error = supabase_rest_upsert("subjects", payload, "code")
    if error:
        json_response(handler, 502, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "message": "Subject saved to database."})


def handle_save_teacher(handler):
    if not require_supabase_api(handler):
        return
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    teacher_id = body.get("id")
    first_name = (body.get("firstName") or "").strip().upper()
    last_name = (body.get("lastName") or "").strip().upper()
    middle_name = (body.get("middleName") or "").strip().upper() or None
    email = (body.get("email") or "").strip() or None
    department = (body.get("department") or "").strip() or None
    max_load = int(body.get("maxLoadUnits") or 3)
    password = (body.get("password") or "teacher123").strip()
    strand_codes = [s.upper() for s in (body.get("strands") or []) if s]
    is_active = body.get("isActive", True)

    if not first_name or not last_name:
        json_response(handler, 400, {"success": False, "error": "First and last name are required."})
        return
    if not strand_codes:
        json_response(handler, 400, {"success": False, "error": "Select at least one strand the teacher handles."})
        return

    if teacher_id:
        _, error = supabase_rest_patch(
            "faculty",
            f"id=eq.{teacher_id}",
            {
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "email": email,
                "department": department,
                "max_load_units": max_load,
                "is_active": bool(is_active),
                "updated_at": datetime.utcnow().isoformat() + "Z",
            },
        )
        if error:
            json_response(handler, 502, {"success": False, "error": error})
            return
        if body.get("password"):
            supabase_rest_patch("faculty", f"id=eq.{teacher_id}", {"password": password})
        ok, sync_err = sync_teacher_strands(teacher_id, strand_codes)
        if not ok:
            json_response(handler, 502, {"success": False, "error": sync_err})
            return
        json_response(handler, 200, {"success": True, "message": "Teacher updated."})
        return

    faculty_code = (body.get("facultyId") or generate_teacher_faculty_id(strand_codes)).strip().upper()
    row, error = supabase_rest_insert("faculty", {
        "faculty_id": faculty_code,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "email": email,
        "department": department,
        "role": "Teacher",
        "password": password,
        "max_load_units": max_load,
        "is_active": bool(is_active),
    }, return_representation=True)
    if error or not row:
        json_response(handler, 502, {"success": False, "error": parse_supabase_error(error or "Could not save teacher.")})
        return
    faculty_uuid = row.get("id")
    ok, sync_err = sync_teacher_strands(faculty_uuid, strand_codes)
    if not ok:
        json_response(handler, 502, {"success": False, "error": sync_err})
        return
    json_response(handler, 200, {
        "success": True,
        "message": "Teacher saved to database.",
        "facultyId": faculty_code,
        "id": faculty_uuid,
    })


def handle_list_rooms(handler):
    if not require_supabase_api(handler):
        return
    rows, error = supabase_rest_get(
        "rooms",
        "select=id,name,capacity,room_type,is_active&order=name.asc",
        use_secret=True,
    )
    if error:
        json_response(handler, 502, {"success": False, "error": error})
        return
    json_response(handler, 200, {"success": True, "data": rows or []})


def handle_list_section_quotas(handler):
    if not require_supabase_api(handler):
        return
    result, error = supabase_rpc("get_section_quota_overview", timeout=10)
    if error:
        json_response(handler, 502, {"success": False, "error": error})
        return
    json_response(handler, 200, {"success": True, "data": result or []})


def handle_update_section_quota(handler):
    if not require_supabase_api(handler):
        return
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    section_id = (body.get("id") or "").strip()
    try:
        max_students = int(body.get("maxStudents") or 40)
    except (TypeError, ValueError):
        json_response(handler, 400, {"success": False, "error": "Invalid quota value."})
        return

    if not section_id:
        json_response(handler, 400, {"success": False, "error": "Section id is required."})
        return
    if max_students < 1:
        json_response(handler, 400, {"success": False, "error": "Quota must be at least 1."})
        return

    _, error = supabase_rest_patch(
        "sections",
        f"id=eq.{section_id}",
        {"max_students": max_students},
    )
    if error:
        json_response(handler, 502, {"success": False, "error": error})
        return

    json_response(handler, 200, {
        "success": True,
        "message": f"Section quota updated to {max_students} students.",
    })


def handle_save_room(handler):
    if not require_supabase_api(handler):
        return
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    room_id = body.get("id")
    name = (body.get("name") or "").strip().upper()
    capacity = int(body.get("capacity") or 40)
    room_type = (body.get("roomType") or "classroom").strip().lower()
    is_active = body.get("isActive", True)

    if not name:
        json_response(handler, 400, {"success": False, "error": "Room name is required."})
        return
    if room_type not in ("classroom", "laboratory"):
        room_type = "classroom"

    payload = {
        "name": name,
        "capacity": capacity,
        "room_type": room_type,
        "is_active": bool(is_active),
    }

    if room_id:
        _, error = supabase_rest_patch("rooms", f"id=eq.{room_id}", payload)
        if error:
            json_response(handler, 502, {"success": False, "error": error})
            return
        json_response(handler, 200, {"success": True, "message": "Room updated."})
        return

    _, error = supabase_rest_insert("rooms", payload)
    if error:
        json_response(handler, 502, {"success": False, "error": error})
        return
    json_response(handler, 200, {"success": True, "message": "Room saved to database."})


def handle_list_students_api(handler):
    if not require_supabase_api(handler):
        return
    rows, error = supabase_rest_get(
        "students",
        "select=id,student_id,first_name,last_name,middle_name,grade_level,admission_status,"
        "is_active,gender,contact_number,birthdate,strands(code,name),sections(name)"
        "&order=last_name.asc",
        use_secret=True,
    )
    if error:
        json_response(handler, 502, {"success": False, "error": error})
        return

    students = []
    for row in rows or []:
        strand = row.get("strands") or {}
        section = row.get("sections") or {}
        students.append({
            "id": row.get("id"),
            "studentId": row.get("student_id"),
            "firstName": row.get("first_name"),
            "lastName": row.get("last_name"),
            "middleName": row.get("middle_name"),
            "name": f"{row.get('last_name', '')}, {row.get('first_name', '')} {row.get('middle_name') or ''}".strip(),
            "gradeLevel": row.get("grade_level"),
            "strand": strand.get("code") or "—",
            "strandName": strand.get("name"),
            "section": section.get("name") or "—",
            "status": "Enrolled" if row.get("is_active") else "Inactive",
            "admissionStatus": row.get("admission_status"),
            "gender": row.get("gender"),
            "contactNumber": row.get("contact_number"),
            "birthdate": str(row.get("birthdate") or "")[:10],
        })
    json_response(handler, 200, {"success": True, "data": students})


def handle_save_student_api(handler):
    if not require_supabase_api(handler):
        return
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    first_name = (body.get("firstName") or "").strip().upper()
    last_name = (body.get("lastName") or "").strip().upper()
    middle_name = (body.get("middleName") or "").strip().upper() or None
    student_id = (body.get("studentId") or generate_next_student_id()).strip().upper()
    grade_level = body.get("gradeLevel") or "Grade 11"
    strand_code = (body.get("strand") or body.get("strandCode") or "").strip().upper()
    birthdate = str(body.get("birthdate") or "2008-01-01")[:10]
    password = (body.get("password") or "student123").strip()
    gender = body.get("gender")
    contact_number = body.get("contactNumber")
    admission_type = (body.get("admissionType") or "continuing").lower()

    if not first_name or not last_name:
        json_response(handler, 400, {"success": False, "error": "First and last name are required."})
        return
    if grade_level not in ("Grade 11", "Grade 12"):
        json_response(handler, 400, {"success": False, "error": "Invalid grade level."})
        return

    strand_id = get_supabase_strand_id(strand_code) if strand_code else None
    row = {
        "student_id": student_id,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "birthdate": birthdate,
        "password": password,
        "gender": gender,
        "contact_number": contact_number,
        "admission_type": admission_type if admission_type in ("new", "continuing", "transferee", "returnee") else "continuing",
        "admission_status": "enrolled",
        "grade_level": grade_level,
        "scholastic_status": "Regular",
        "track": "Academic",
        "is_active": True,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if strand_id:
        row["strand_id"] = strand_id

    _, error = supabase_rest_upsert("students", row, "student_id")
    if error:
        json_response(handler, 502, {"success": False, "error": error})
        return
    json_response(handler, 200, {
        "success": True,
        "message": "Student saved to database.",
        "studentId": student_id,
    })


def seed_default_faculty():
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        return False, "Skipped — add SUPABASE_SECRET_KEY to .env for auto-seed"

    result, error = supabase_rpc("seed_default_faculty", use_secret=True)
    if not error and result and result.get("success"):
        return True, None

    result, error = supabase_rest_upsert("faculty", DEFAULT_FACULTY, "faculty_id")
    if not error:
        return True, None

    if error and "password" in error and "schema cache" in error:
        return False, "Run supabase/seed-faculty.sql in Supabase SQL Editor first"
    return False, error or "Faculty seed failed"


def handle_seed_faculty(handler):
    ok, error = seed_default_faculty()
    if ok:
        json_response(handler, 200, {
            "success": True,
            "facultyId": DEFAULT_FACULTY["faculty_id"],
            "message": "Default faculty account saved to Supabase.",
        })
    else:
        json_response(handler, 500, {"success": False, "error": error})


def local_faculty_login(faculty_id, password):
    if (
        faculty_id == DEFAULT_FACULTY["faculty_id"]
        and password == DEFAULT_FACULTY["password"]
    ):
        return {
            "id": DEFAULT_FACULTY["faculty_id"],
            "lastName": DEFAULT_FACULTY["last_name"],
            "firstName": DEFAULT_FACULTY["first_name"],
            "middleName": DEFAULT_FACULTY["middle_name"],
            "role": DEFAULT_FACULTY["role"],
            "department": DEFAULT_FACULTY["department"],
            "lastLogin": datetime.now().strftime("%b %d, %Y %I:%M %p"),
        }
    return None


def handle_faculty_login(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body."})
        return

    faculty_id = (body.get("facultyId") or "").strip().upper()
    password = body.get("password") or ""

    if not faculty_id or not password:
        json_response(handler, 400, {"success": False, "error": "Faculty ID and password are required."})
        return

    faculty = None

    if SUPABASE_URL and (SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY):
        result, error = supabase_rpc("authenticate_faculty", {
            "p_faculty_id": faculty_id,
            "p_password": password,
        })
        if not error and isinstance(result, dict) and result.get("id"):
            faculty = result

    if not faculty:
        faculty = local_faculty_login(faculty_id, password)

    if faculty:
        role = (faculty.get("role") or "").strip().lower()
        if role == "teacher":
            json_response(handler, 403, {
                "success": False,
                "error": "Teacher accounts use the Faculty Portal at http://localhost:8003/login.html",
            })
            return
        json_response(handler, 200, {"success": True, "faculty": faculty})
        return

    json_response(handler, 401, {"success": False, "error": "Invalid Faculty ID or password."})


def build_student_session_from_admission(app):
    birthdate = str(app.get("birthdate") or "2000-01-01")[:10]
    year, month, day = birthdate.split("-")
    strand_code = app.get("strandCode") or app.get("strand") or DEFAULT_STRAND_CODE
    return {
        "id": app.get("student_id_generated"),
        "lastName": (app.get("lastName") or "").upper(),
        "firstName": (app.get("firstName") or "").upper(),
        "middleName": app.get("middleName") or "",
        "birthMonth": str(int(month)),
        "birthDay": str(int(day)),
        "birthYear": str(int(year)),
        "gradeLevel": app.get("gradeLevel") or "Grade 11",
        "strand": strand_code,
        "strandFull": strand_code,
        "section": "",
        "track": "Academic",
        "admissionStatus": "New",
        "scholasticStatus": "Regular",
        "schoolYear": "2026-2027",
        "semester": "First Semester",
        "voucherQualified": False,
    }


def local_student_login(student_id, birth_month, birth_day, birth_year, password):
    student_id = (student_id or "").strip().upper()
    password = (password or "").strip()
    if not student_id or not password:
        return None

    for app in load_local_admissions():
        if (app.get("status") or "").lower() != "approved":
            continue
        sid = (app.get("student_id_generated") or "").strip().upper()
        if sid != student_id:
            continue
        stored_password = (app.get("temp_password") or app.get("tempPassword") or "").strip()
        if stored_password != password:
            continue
        birthdate = str(app.get("birthdate") or "")[:10]
        if birthdate:
            try:
                y, m, d = [int(part) for part in birthdate.split("-")]
                if int(birth_year) != y or int(birth_month) != m or int(birth_day) != d:
                    continue
            except (TypeError, ValueError):
                continue
        return build_student_session_from_admission(app)
    return None


def get_supabase_strand_id(code):
    if not code or not SUPABASE_URL:
        return None
    data, error = supabase_rest_get(
        "strands",
        f"code=eq.{code}&select=id&limit=1",
        use_secret=True,
    )
    if error or not isinstance(data, list) or not data:
        return None
    return data[0].get("id")


def sync_student_to_supabase(app, student_id, temp_password):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        return False, "Supabase secret key not configured"

    strand_code = app.get("strandCode") or app.get("strand") or DEFAULT_STRAND_CODE
    strand_id = app.get("strandId") or get_supabase_strand_id(strand_code)
    admission_type = (app.get("admissionType") or "new").lower()
    if admission_type not in ("new", "continuing", "transferee", "returnee"):
        admission_type = "new"

    row = {
        "student_id": student_id,
        "last_name": app.get("lastName", ""),
        "first_name": app.get("firstName", ""),
        "middle_name": app.get("middleName"),
        "birthdate": str(app.get("birthdate") or "2000-01-01")[:10],
        "password": temp_password,
        "gender": app.get("gender"),
        "address": app.get("address"),
        "contact_number": app.get("contactNumber"),
        "admission_type": admission_type,
        "admission_status": "approved",
        "grade_level": app.get("gradeLevel") or "Grade 11",
        "scholastic_status": "Regular",
        "track": "Academic",
        "is_active": True,
    }
    if strand_id:
        row["strand_id"] = strand_id

    _, error = supabase_rest_upsert("students", row, "student_id")
    if error:
        return False, error
    return True, None


def sync_approved_student_credentials(result, app_detail=None):
    """Keep students.password in sync with the temp password emailed on approval."""
    student_id = (
        result.get("studentId")
        or result.get("student_id")
        or (app_detail or {}).get("studentId")
        or (app_detail or {}).get("student_id_generated")
        or ""
    ).strip().upper()
    temp_password = (
        result.get("tempPassword")
        or result.get("temp_password")
        or (app_detail or {}).get("tempPassword")
        or (app_detail or {}).get("temp_password")
        or ""
    ).strip()
    if not student_id or not temp_password:
        print("[Student sync] Skipped — missing studentId or tempPassword from approval result")
        return False, "Missing studentId or tempPassword"

    detail = app_detail or {}
    app = {
        "lastName": result.get("lastName") or detail.get("lastName") or detail.get("last_name") or "",
        "firstName": result.get("firstName") or detail.get("firstName") or detail.get("first_name") or "",
        "middleName": result.get("middleName") or detail.get("middleName") or detail.get("middle_name") or "",
        "birthdate": detail.get("birthdate") or result.get("birthdate"),
        "gender": detail.get("gender"),
        "address": detail.get("address"),
        "contactNumber": detail.get("contactNumber") or detail.get("contact_number"),
        "strandCode": detail.get("strandCode") or detail.get("strand") or detail.get("strand_code"),
        "strandId": detail.get("strandId") or detail.get("strand_id"),
        "gradeLevel": detail.get("gradeLevel") or detail.get("grade_level"),
        "admissionType": detail.get("admissionType") or detail.get("admission_type") or "new",
    }
    ok, err = sync_student_to_supabase(app, student_id, temp_password)
    if ok:
        print(f"[Student sync] Credentials synced for {student_id}")
    else:
        print(f"[Student sync] Failed for {student_id}: {err}")
    return ok, err


def birthdate_matches(stored, birth_month, birth_day, birth_year):
    if not stored:
        return False
    try:
        parts = str(stored)[:10].split("-")
        if len(parts) != 3:
            return False
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return (
            y == int(birth_year)
            and m == int(birth_month)
            and d == int(birth_day)
        )
    except (TypeError, ValueError):
        return False


def build_student_session_from_supabase_row(row, strand_code=None, strand_name=None):
    birthdate = str(row.get("birthdate") or "2000-01-01")[:10]
    year, month, day = birthdate.split("-")
    strands = row.get("strands") if isinstance(row.get("strands"), dict) else {}
    code = strand_code or strands.get("code") or "STEM"
    name = strand_name or strands.get("name") or code
    sections = row.get("sections") if isinstance(row.get("sections"), dict) else {}
    return {
        "id": row.get("student_id"),
        "supabaseId": row.get("id"),
        "lastName": row.get("last_name") or "",
        "firstName": row.get("first_name") or "",
        "middleName": row.get("middle_name") or "",
        "birthMonth": str(int(month)),
        "birthDay": str(int(day)),
        "birthYear": str(int(year)),
        "gradeLevel": row.get("grade_level") or "Grade 11",
        "strand": code,
        "strandFull": name,
        "section": sections.get("name") or "",
        "track": row.get("track") or "Academic",
        "admissionStatus": row.get("admission_status") or "approved",
        "scholasticStatus": row.get("scholastic_status") or "Regular",
        "accountStatus": row.get("account_status") or "active",
        "progressionStatus": row.get("progression_status") or "in_progress",
        "grade11Completed": bool(row.get("grade11_completed")),
        "schoolYear": "2026-2027",
        "semester": "First Semester",
        "semesterCode": "1st",
        "enrollmentOpen": False,
        "voucherQualified": bool(row.get("voucher_qualified")),
    }


def supabase_student_auth_fallback(student_id, birth_month, birth_day, birth_year, password):
    """REST fallback when authenticate_student RPC is outdated or returns null."""
    if not supabase_configured():
        return None

    student_id = (student_id or "").strip().upper()
    password = (password or "").strip()
    if not student_id or not password:
        return None

    from urllib.parse import quote

    students, err = supabase_rest_get(
        "students",
        f"student_id=eq.{quote(student_id)}&select=*,strands(code,name),sections(name)",
        use_secret=True,
        timeout=10,
    )
    admissions, err2 = supabase_rest_get(
        "admission_applications",
        (
            f"status=eq.approved&student_id_generated=eq.{quote(student_id)}"
            "&select=*,strands(code,name)"
        ),
        use_secret=True,
        timeout=10,
    )
    admission_list = admissions if isinstance(admissions, list) else []
    stale_student_row = None

    if isinstance(students, list):
        for row in students:
            stored_password = (row.get("password") or "").strip()
            if stored_password != password:
                if birthdate_matches(row.get("birthdate"), birth_month, birth_day, birth_year):
                    stale_student_row = row
                continue
            if not birthdate_matches(row.get("birthdate"), birth_month, birth_day, birth_year):
                continue
            if row.get("is_active") is False:
                continue
            status = (row.get("account_status") or "active").lower()
            if status == "frozen":
                return {
                    "error": "ACCOUNT_FROZEN",
                    "message": (
                        "Your account has been frozen due to non-enrollment during "
                        "the official registration period. Please contact the registrar's office."
                    ),
                }
            if status == "inactive":
                return {
                    "error": "ACCOUNT_INACTIVE",
                    "message": "Your account is inactive. Please contact the registrar's office.",
                }
            return build_student_session_from_supabase_row(row)

    for app in admission_list:
        stored_password = (app.get("temp_password") or "").strip()
        if stored_password != password:
            continue
        if not birthdate_matches(app.get("birthdate"), birth_month, birth_day, birth_year):
            continue
        strands = app.get("strands") if isinstance(app.get("strands"), dict) else {}
        session = build_student_session_from_admission({
            **app,
            "student_id_generated": app.get("student_id_generated"),
            "lastName": app.get("last_name"),
            "firstName": app.get("first_name"),
            "middleName": app.get("middle_name"),
            "strandCode": strands.get("code") or "STEM",
            "strand": strands.get("code") or "STEM",
            "gradeLevel": app.get("grade_level"),
        })
        sync_student_to_supabase(
            {
                **app,
                "lastName": app.get("last_name"),
                "firstName": app.get("first_name"),
                "middleName": app.get("middle_name"),
                "strandCode": strands.get("code") or "STEM",
                "strandId": app.get("strand_id"),
                "birthdate": app.get("birthdate"),
                "gender": app.get("gender"),
                "address": app.get("address"),
                "contactNumber": app.get("contact_number"),
                "admissionType": app.get("admission_type"),
                "gradeLevel": app.get("grade_level"),
            },
            student_id,
            stored_password,
        )
        return session

    if stale_student_row and admission_list:
        for app in admission_list:
            stored_password = (app.get("temp_password") or "").strip()
            if stored_password != password:
                continue
            sync_student_to_supabase(
                {
                    **app,
                    "lastName": app.get("last_name"),
                    "firstName": app.get("first_name"),
                    "middleName": app.get("middle_name"),
                    "strandCode": (app.get("strands") or {}).get("code") or "STEM",
                    "strandId": app.get("strand_id"),
                    "birthdate": app.get("birthdate"),
                    "gender": app.get("gender"),
                    "address": app.get("address"),
                    "contactNumber": app.get("contact_number"),
                    "admissionType": app.get("admission_type"),
                    "gradeLevel": app.get("grade_level"),
                },
                student_id,
                stored_password,
            )
            return build_student_session_from_supabase_row(stale_student_row)

    return None


def handle_student_login(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body."})
        return

    student_id = (body.get("studentId") or "").strip().upper()
    password = (body.get("password") or "").strip()
    try:
        birth_month = int(body.get("birthMonth") or 0)
        birth_day = int(body.get("birthDay") or 0)
        birth_year = int(body.get("birthYear") or 0)
    except (TypeError, ValueError):
        birth_month = birth_day = birth_year = 0

    if not student_id or not password or not birth_month or not birth_day or not birth_year:
        json_response(handler, 400, {
            "success": False,
            "error": "Student ID, birthdate, and password are required.",
        })
        return

    student = None

    if supabase_configured():
        result, error = supabase_rpc("authenticate_student", {
            "p_student_id": student_id,
            "p_birth_month": birth_month,
            "p_birth_day": birth_day,
            "p_birth_year": birth_year,
            "p_password": password,
        }, timeout=10)
        if error:
            print(f"[Supabase auth error] {parse_supabase_error(error)}")
        elif isinstance(result, dict) and result.get("error") == "ACCOUNT_FROZEN":
            json_response(handler, 403, {
                "success": False,
                "error": result.get("message") or "Account frozen.",
                "code": "ACCOUNT_FROZEN",
            })
            return
        elif isinstance(result, dict) and result.get("error") == "ACCOUNT_INACTIVE":
            json_response(handler, 403, {
                "success": False,
                "error": result.get("message") or "Account inactive.",
                "code": "ACCOUNT_INACTIVE",
            })
            return
        elif isinstance(result, dict) and result.get("id"):
            student = result

        if not student:
            student = supabase_student_auth_fallback(
                student_id, birth_month, birth_day, birth_year, password,
            )
            if isinstance(student, dict) and student.get("error") == "ACCOUNT_FROZEN":
                json_response(handler, 403, {
                    "success": False,
                    "error": student.get("message") or "Account frozen.",
                    "code": "ACCOUNT_FROZEN",
                })
                return
            if isinstance(student, dict) and student.get("error") == "ACCOUNT_INACTIVE":
                json_response(handler, 403, {
                    "success": False,
                    "error": student.get("message") or "Account inactive.",
                    "code": "ACCOUNT_INACTIVE",
                })
                return

    if not student and not supabase_configured():
        student = local_student_login(student_id, birth_month, birth_day, birth_year, password)

    if student:
        json_response(handler, 200, {"success": True, "student": student})
        return

    json_response(handler, 401, {
        "success": False,
        "error": "Invalid Student ID, birthdate, or password.",
        "hint": (
            "Use the exact Student ID and Temporary Password from your approval email. "
            "Birthdate must match your enrollment form. "
            "If you still cannot sign in, contact the registrar office."
        ) if supabase_configured() else None,
    })


def load_local_admissions():
    if not LOCAL_ADMISSIONS_FILE.exists():
        return []
    try:
        return json.loads(LOCAL_ADMISSIONS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_local_admissions(records):
    LOCAL_ADMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_ADMISSIONS_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")


def upsert_local_admission(application_id, app_number, payload, fields, status="pending"):
    """Keep a local copy so the admin portal always sees new enrollments."""
    records = load_local_admissions()
    record = {
        "id": application_id,
        "applicationNumber": app_number,
        "status": status,
        "tempPassword": None,
        "student_id_generated": None,
        **payload,
        "strandCode": fields.get("strandCode", payload.get("strandCode", "")),
        "createdAt": datetime.now().isoformat(),
    }
    idx = find_local_admission_index(records, application_id, app_number)
    if idx is not None:
        existing = records[idx]
        record["createdAt"] = existing.get("createdAt") or record["createdAt"]
        records[idx] = {**existing, **record}
    else:
        records.append(record)
    save_local_admissions(records)
    return record


def find_local_admission_index(records, application_id, app_number=None):
    target_id = str(application_id or "").strip()
    target_no = str(app_number or application_id or "").strip()
    for i, record in enumerate(records):
        record_id = str(record.get("id") or "").strip()
        record_no = str(record.get("applicationNumber") or "").strip()
        if target_id and record_id == target_id:
            return i
        if target_no and record_no == target_no:
            return i
    return None


def documents_list_to_dict(documents):
    if isinstance(documents, dict):
        return documents
    result = {}
    for doc in documents or []:
        if isinstance(doc, dict) and doc.get("key") and doc.get("path"):
            result[doc["key"]] = doc["path"]
    return result


def sync_admission_detail_to_local(detail):
    """Materialize a remote/cached admission detail into local admissions.json."""
    normalized = normalize_admission_input(detail)
    records = load_local_admissions()
    app_id = normalized.get("id")
    app_number = normalized.get("applicationNumber")
    idx = find_local_admission_index(records, app_id, app_number)

    record = {
        "id": app_id,
        "applicationNumber": app_number,
        "status": (normalized.get("status") or "pending").lower(),
        "lastName": normalized.get("lastName", ""),
        "firstName": normalized.get("firstName", ""),
        "middleName": normalized.get("middleName", ""),
        "birthdate": normalized.get("birthdate", ""),
        "gender": normalized.get("gender", ""),
        "address": normalized.get("address", ""),
        "contactNumber": normalized.get("contactNumber", ""),
        "email": normalized.get("email", ""),
        "gradeLevel": normalized.get("gradeLevel", ""),
        "strandCode": normalized.get("strandCode", ""),
        "strandId": normalized.get("strandId", ""),
        "admissionType": normalized.get("admissionType", "new"),
        "paymentMode": normalized.get("paymentMode", "cashier"),
        "bankCode": normalized.get("bankCode", ""),
        "bankReference": normalized.get("bankReference", ""),
        "bankSenderName": normalized.get("bankSenderName", ""),
        "bankProofPath": normalized.get("bankProofPath", ""),
        "gcashReference": normalized.get("gcashReference", ""),
        "gcashSenderName": normalized.get("gcashSenderName", ""),
        "gcashProofPath": normalized.get("gcashProofPath", ""),
        "paymentStatus": normalized.get("paymentStatus", ""),
        "paymentAmount": normalized.get("paymentAmount", ""),
        "documents": documents_list_to_dict(detail.get("documents")),
        "docForm138Path": normalized.get("docForm138Path"),
        "docForm137Path": normalized.get("docForm137Path"),
        "docGoodMoralPath": normalized.get("docGoodMoralPath"),
        "docBirthCertificatePath": normalized.get("docBirthCertificatePath"),
        "docHighSchoolDiplomaPath": normalized.get("docHighSchoolDiplomaPath"),
        "student_id_generated": normalized.get("student_id_generated"),
        "reviewed_at": normalized.get("reviewed_at"),
        "rejection_reason": normalized.get("rejection_reason"),
        "createdAt": normalized.get("createdAt") or datetime.now().isoformat(),
    }

    if idx is not None:
        existing = records[idx]
        record["createdAt"] = existing.get("createdAt") or record["createdAt"]
        records[idx] = {**existing, **record}
    else:
        records.append(record)
    save_local_admissions(records)
    return records[idx if idx is not None else -1], records


def ensure_pending_admission_for_review(application_id):
    records = load_local_admissions()
    idx = find_local_admission_index(records, application_id)
    if idx is not None:
        app = records[idx]
        if (app.get("status") or "pending").lower() == "pending":
            return idx, app, records

    detail = get_admission_by_id(application_id)
    if not detail:
        return None, None, records
    if (detail.get("status") or "pending").lower() != "pending":
        return None, None, records

    app, records = sync_admission_detail_to_local(detail)
    idx = find_local_admission_index(records, application_id, app.get("applicationNumber"))
    return idx, records[idx], records


def update_local_admission_review(app, records, action, reason=None, student_id=None, temp_password=None):
    idx = find_local_admission_index(records, app.get("id"), app.get("applicationNumber"))
    if idx is None:
        return app

    reviewed_at = datetime.now().isoformat()
    if action == "approve":
        records[idx]["status"] = "approved"
        records[idx]["student_id_generated"] = student_id
        records[idx]["temp_password"] = temp_password
        records[idx]["reviewed_at"] = reviewed_at
    else:
        records[idx]["status"] = "rejected"
        records[idx]["rejection_reason"] = reason
        records[idx]["reviewed_at"] = reviewed_at

    save_local_admissions(records)
    return records[idx]


def format_applicant_name(record):
    return f"{record.get('lastName', '')}, {record.get('firstName', '')} {record.get('middleName', '')}".strip()


def normalize_admission_input(record):
    """Normalize camelCase/snake_case admission records from local JSON or Supabase."""
    if not record:
        return {}

    def pick(*keys):
        for key in keys:
            val = record.get(key)
            if val is not None and str(val).strip() != "":
                return val
        return ""

    address = pick("address")
    if not address:
        address = build_full_address({
            "houseNumber": pick("houseNumber", "addr_house_number", "addrHouseNumber"),
            "street": pick("street", "addr_street", "addrStreet"),
            "barangay": pick("barangay", "addr_barangay", "addrBarangay"),
            "city": pick("city", "addr_city", "addrCity"),
            "province": pick("province", "addr_province", "addrProvince"),
        })

    birthdate = pick("birthdate", "birth_date")
    if birthdate:
        birthdate = str(birthdate)[:10]

    created = pick("createdAt", "created_at", "submittedAt")
    payment_amount = pick("paymentAmount", "payment_amount")
    if payment_amount != "":
        payment_amount = str(payment_amount)

    documents = record.get("documents") or {}
    if isinstance(documents, str):
        try:
            documents = json.loads(documents)
        except (json.JSONDecodeError, TypeError):
            documents = {}
    if not isinstance(documents, dict):
        documents = {}

    normalized = {
        "id": pick("id"),
        "applicationNumber": pick("applicationNumber", "application_number"),
        "lastName": pick("lastName", "last_name"),
        "firstName": pick("firstName", "first_name"),
        "middleName": pick("middleName", "middle_name"),
        "birthdate": birthdate,
        "gender": pick("gender"),
        "address": address,
        "contactNumber": pick("contactNumber", "contact_number"),
        "email": pick("email"),
        "gradeLevel": pick("gradeLevel", "grade_level", "grade"),
        "strandCode": pick("strandCode", "strand"),
        "admissionType": pick("admissionType", "admission_type") or "new",
        "previousSchool": pick("previousSchool", "previous_school"),
        "paymentMode": pick("paymentMode", "payment_mode") or "cashier",
        "bankCode": pick("bankCode", "bank_code"),
        "bankReference": pick("bankReference", "bank_reference"),
        "bankSenderName": pick("bankSenderName", "bank_sender_name"),
        "bankProofPath": pick("bankProofPath", "bank_proof_path"),
        "gcashReference": pick("gcashReference", "gcash_reference"),
        "gcashSenderName": pick("gcashSenderName", "gcash_sender_name"),
        "gcashProofPath": pick("gcashProofPath", "gcash_proof_path"),
        "paymentStatus": pick("paymentStatus", "payment_status"),
        "paymentAmount": payment_amount,
        "status": (pick("status") or "pending").lower(),
        "createdAt": created,
        "student_id_generated": pick("student_id_generated", "studentId", "student_id_generated"),
        "reviewed_at": pick("reviewed_at", "reviewedAt"),
        "rejection_reason": pick("rejection_reason", "rejectionReason"),
        "documents": documents,
        "docForm138Path": pick("docForm138Path", "doc_form_138_path"),
        "docForm137Path": pick("docForm137Path", "doc_form_137_path"),
        "docGoodMoralPath": pick("docGoodMoralPath", "doc_good_moral_path"),
        "docBirthCertificatePath": pick("docBirthCertificatePath", "doc_birth_certificate_path"),
        "docHighSchoolDiplomaPath": pick("docHighSchoolDiplomaPath", "doc_high_school_diploma_path"),
        "profilePhotoUploadPath": pick(
            "profilePhotoUploadPath",
            "profile_photo_upload_path",
        ),
        "profilePhotoCameraPath": pick(
            "profilePhotoCameraPath",
            "profile_photo_camera_path",
        ),
        "preferredSubjectSchedules": record.get("preferredSubjectSchedules")
        or record.get("preferred_subject_schedules")
        or {},
        "subjectScheduleDetails": record.get("subjectScheduleDetails")
        or record.get("subject_schedule_details")
        or [],
        "houseNumber": pick("houseNumber", "addr_house_number", "addrHouseNumber"),
        "street": pick("street", "addr_street", "addrStreet"),
        "barangay": pick("barangay", "addr_barangay", "addrBarangay"),
        "city": pick("city", "addr_city", "addrCity"),
        "province": pick("province", "addr_province", "addrProvince"),
    }

    if not normalized["profilePhotoUploadPath"]:
        normalized["profilePhotoUploadPath"] = documents.get("profile_upload") or ""
    if not normalized["profilePhotoCameraPath"]:
        normalized["profilePhotoCameraPath"] = documents.get("profile_camera") or ""

    for doc_key, path_key in (
        ("form_138", "docForm138Path"),
        ("form_137", "docForm137Path"),
        ("good_moral", "docGoodMoralPath"),
        ("birth_certificate", "docBirthCertificatePath"),
        ("high_school_diploma", "docHighSchoolDiplomaPath"),
    ):
        if not documents.get(doc_key) and normalized.get(path_key):
            documents[doc_key] = normalized[path_key]

    normalized["documents"] = documents
    return normalized


def merge_admission_fields(base, update):
    result = dict(base or {})
    for key, value in (update or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() in ("", "—"):
            continue
        if key not in result or result[key] in (None, "", "—"):
            result[key] = value
        elif key == "documents" and isinstance(value, dict):
            merged_docs = dict(result.get("documents") or {})
            merged_docs.update({k: v for k, v in value.items() if v})
            result["documents"] = merged_docs
    return result


def build_admission_detail(record):
    record = parse_address_breakdown(normalize_admission_input(record))
    documents = record.get("documents") or {}
    doc_list = []
    for key, label in REQUIRED_DOCS.items():
        path = documents.get(key)
        if path:
            path = str(path).replace("\\", "/")
        doc_list.append({
            "key": key,
            "label": label,
            "path": path,
            "url": document_view_url(path),
            "uploaded": bool(path),
        })
    gcash_path = record.get("gcashProofPath")
    if record.get("paymentMode") == "gcash" and gcash_path:
        gcash_path = str(gcash_path).replace("\\", "/")
        doc_list.append({
            "key": "gcash_proof",
            "label": "GCash Payment Receipt",
            "path": gcash_path,
            "url": document_view_url(gcash_path),
            "uploaded": True,
        })
    bank_path = record.get("bankProofPath")
    if record.get("paymentMode") == "bank" and bank_path:
        bank_path = str(bank_path).replace("\\", "/")
        doc_list.append({
            "key": "bank_proof",
            "label": "Bank Payment Receipt",
            "path": bank_path,
            "url": document_view_url(bank_path),
            "uploaded": True,
        })
    created = record.get("createdAt") or record.get("created_at") or ""
    student_name = format_applicant_name(record) or record.get("student") or ""

    profile_upload = record.get("profilePhotoUploadPath") or documents.get("profile_upload")
    profile_camera = record.get("profilePhotoCameraPath") or documents.get("profile_camera")
    profile_path = profile_upload or profile_camera

    schedule_details = resolve_subject_schedule_details(
        record,
        rest_get_fn=supabase_rest_get if supabase_configured() else None,
    )

    return {
        "id": record.get("id"),
        "applicationNumber": record.get("applicationNumber"),
        "status": (record.get("status") or "pending").lower(),
        "student": student_name,
        "lastName": record.get("lastName", ""),
        "firstName": record.get("firstName", ""),
        "middleName": record.get("middleName", ""),
        "birthdate": record.get("birthdate", ""),
        "gender": record.get("gender", ""),
        "address": record.get("address", ""),
        "houseNumber": record.get("houseNumber", ""),
        "street": record.get("street", ""),
        "barangay": record.get("barangay", ""),
        "city": record.get("city", ""),
        "province": record.get("province", ""),
        "contactNumber": record.get("contactNumber", ""),
        "email": record.get("email", ""),
        "gradeLevel": record.get("gradeLevel") or record.get("grade", ""),
        "strandCode": record.get("strandCode") or record.get("strand", ""),
        "admissionType": record.get("admissionType", "new"),
        "previousSchool": record.get("previousSchool", ""),
        "paymentMode": record.get("paymentMode", "cashier"),
        "bankCode": record.get("bankCode", ""),
        "bankReference": record.get("bankReference", ""),
        "bankSenderName": record.get("bankSenderName", ""),
        "gcashReference": record.get("gcashReference", ""),
        "gcashSenderName": record.get("gcashSenderName", ""),
        "paymentStatus": record.get("paymentStatus", ""),
        "paymentAmount": record.get("paymentAmount", ""),
        "submittedAt": created,
        "date": created[:10] if created else "",
        "documents": doc_list,
        "profilePhotoUploadPath": profile_upload,
        "profilePhotoCameraPath": profile_camera,
        "profilePhotoUrl": document_view_url(profile_path),
        "preferredSubjectSchedules": record.get("preferredSubjectSchedules") or {},
        "subjectScheduleDetails": schedule_details if isinstance(schedule_details, list) else [],
        "studentId": record.get("student_id_generated") or record.get("studentId"),
        "reviewedAt": record.get("reviewed_at"),
        "rejectionReason": record.get("rejection_reason"),
    }


def normalize_local_admission(record):
    detail = build_admission_detail(record)
    detail["strand"] = detail.get("strandCode") or "—"
    detail["grade"] = detail.get("gradeLevel") or "—"
    detail["source"] = "local"
    return detail


def fetch_supabase_pending_admissions():
    if not supabase_configured():
        return []
    data, error = supabase_rpc("get_pending_admissions", timeout=10)
    if error or not data:
        if error:
            print(f"[Supabase] get_pending_admissions: {parse_supabase_error(error)}")
        return []
    if not isinstance(data, list):
        return []
    return [
        {**normalize_local_admission(item), "source": "supabase"}
        if isinstance(item, dict) else item
        for item in data
    ]


def fetch_supabase_admission_history():
    if not supabase_configured():
        return []
    data, error = supabase_rpc("get_admission_history", timeout=10)
    if error or not data:
        if error:
            print(f"[Supabase] get_admission_history: {parse_supabase_error(error)}")
        return []
    return data if isinstance(data, list) else []


def merge_admission_records(remote_items, local_items):
    merged = {}
    for item in local_items + remote_items:
        key = item.get("id") or item.get("applicationNumber")
        if not key:
            continue
        if key in merged:
            merged[key] = merge_admission_fields(merged[key], item)
        else:
            merged[key] = item

    by_app_no = {}
    for item in merged.values():
        app_no = item.get("applicationNumber")
        if app_no and app_no in by_app_no:
            by_app_no[app_no] = merge_admission_fields(by_app_no[app_no], item)
        elif app_no:
            by_app_no[app_no] = item

    if by_app_no:
        final = {}
        for item in merged.values():
            app_no = item.get("applicationNumber")
            key = item.get("id") or app_no
            final[key] = by_app_no.get(app_no, item) if app_no else item
        return list(final.values())

    return list(merged.values())


def get_all_pending_admissions(include_remote=True):
    if supabase_configured():
        return fetch_supabase_pending_admissions()
    return [
        normalize_local_admission(r)
        for r in load_local_admissions()
        if (r.get("status") or "pending").lower() == "pending"
    ]


def get_all_admission_history(include_remote=True):
    if supabase_configured():
        return fetch_supabase_admission_history()
    return [
        {
            "id": r.get("applicationNumber") or r.get("id"),
            "applicationId": r.get("id"),
            "student": format_applicant_name(r),
            "studentId": r.get("student_id_generated") or "—",
            "strand": r.get("strandCode") or "—",
            "grade": r.get("gradeLevel") or "—",
            "status": (r.get("status") or "pending").capitalize(),
            "date": (r.get("reviewed_at") or r.get("createdAt") or "")[:10],
            "email": r.get("email", ""),
            "applicationNumber": r.get("applicationNumber"),
        }
        for r in load_local_admissions()
        if (r.get("status") or "pending").lower() in ("approved", "rejected")
    ]


def build_local_dashboard_payload():
    """Fast dashboard using local files only — no Supabase wait."""
    local_records = load_local_admissions()
    pending = [
        normalize_local_admission(r)
        for r in local_records
        if (r.get("status") or "pending").lower() == "pending"
    ]
    history = [
        {
            "id": r.get("applicationNumber") or r.get("id"),
            "applicationId": r.get("id"),
            "student": format_applicant_name(r),
            "studentId": r.get("student_id_generated") or "—",
            "strand": r.get("strandCode") or "—",
            "grade": r.get("gradeLevel") or "—",
            "status": (r.get("status") or "pending").capitalize(),
            "date": (r.get("reviewed_at") or r.get("createdAt") or "")[:10],
            "email": r.get("email", ""),
            "applicationNumber": r.get("applicationNumber"),
        }
        for r in local_records
        if (r.get("status") or "pending").lower() in ("approved", "rejected")
    ]

    approved_count = sum(1 for r in local_records if (r.get("status") or "").lower() == "approved")
    rejected_count = sum(1 for r in local_records if (r.get("status") or "").lower() == "rejected")
    pending_count = len(pending)

    strand_counts = {}
    for record in local_records + pending:
        code = record.get("strand") or record.get("strandCode") or "—"
        if code and code != "—":
            strand_counts[code] = strand_counts.get(code, 0) + 1

    recent_activity = []
    for app in pending:
        recent_activity.append({
            "id": app.get("id"),
            "type": "admission",
            "student": app.get("student"),
            "strand": f"{app.get('strand', '—')} · {app.get('grade', '—')}",
            "subject": app.get("applicationNumber") or "New Admission",
            "date": app.get("date") or "—",
            "status": "Pending",
        })
    for item in sorted(history, key=lambda x: x.get("date") or "", reverse=True)[:8]:
        recent_activity.append({
            "id": item.get("applicationId") or item.get("id"),
            "type": "admission",
            "student": item.get("student"),
            "strand": f"{item.get('strand', '—')} · {item.get('grade', '—')}",
            "subject": item.get("applicationNumber") or item.get("id") or "Admission",
            "date": item.get("date") or "—",
            "status": item.get("status") or "Processed",
        })

    strand_codes = fetch_active_strand_codes()

    return {
        "totalStudents": max(approved_count, 1 if approved_count else 0),
        "totalStrands": len(strand_codes),
        "pendingEnrollments": pending_count,
        "pendingAdmissionCount": pending_count,
        "totalAdmissions": len(local_records),
        "enrollmentStats": {
            "approved": approved_count,
            "pending": pending_count,
            "rejected": rejected_count,
        },
        "recentActivity": recent_activity[:10],
        "pendingAdmissions": pending,
        "strandDistribution": [
            {
                "name": code,
                "grade": "Grade 11 & 12",
                "applicants": strand_counts.get(code, 0),
            }
            for code in strand_codes
        ],
        "pendingRequests": [
            {
                "id": app.get("id"),
                "student": app.get("student"),
                "studentId": app.get("applicationNumber") or app.get("id"),
                "strand": app.get("strand"),
                "grade": app.get("grade"),
                "email": app.get("email"),
            }
            for app in pending
        ],
    }


def build_supabase_dashboard_payload():
    pending = fetch_supabase_pending_admissions()
    history = fetch_supabase_admission_history()

    approved_count = sum(1 for h in history if (h.get("status") or "").lower() == "approved")
    rejected_count = sum(1 for h in history if (h.get("status") or "").lower() == "rejected")
    pending_count = len(pending)

    strand_counts = {}
    for record in pending + history:
        code = record.get("strand") or record.get("strandCode") or "—"
        if code and code != "—":
            strand_counts[code] = strand_counts.get(code, 0) + 1

    recent_activity = []
    for app in pending:
        recent_activity.append({
            "id": app.get("id"),
            "type": "admission",
            "student": app.get("student"),
            "strand": f"{app.get('strand', '—')} · {app.get('grade', '—')}",
            "subject": app.get("applicationNumber") or "New Admission",
            "date": app.get("date") or "—",
            "status": "Pending",
        })
    for item in sorted(history, key=lambda x: x.get("date") or "", reverse=True)[:8]:
        recent_activity.append({
            "id": item.get("applicationId") or item.get("id"),
            "type": "admission",
            "student": item.get("student"),
            "strand": f"{item.get('strand', '—')} · {item.get('grade', '—')}",
            "subject": item.get("applicationNumber") or item.get("id") or "Admission",
            "date": item.get("date") or "—",
            "status": item.get("status") or "Processed",
        })

    strand_codes = fetch_active_strand_codes()

    return {
        "totalStudents": approved_count,
        "totalStrands": len(strand_codes),
        "pendingEnrollments": pending_count,
        "pendingAdmissionCount": pending_count,
        "totalAdmissions": approved_count + pending_count + rejected_count,
        "enrollmentStats": {
            "approved": approved_count,
            "pending": pending_count,
            "rejected": rejected_count,
        },
        "recentActivity": recent_activity[:10],
        "pendingAdmissions": pending,
        "storage": "supabase",
        "strandDistribution": [
            {
                "name": code,
                "grade": "Grade 11 & 12",
                "applicants": strand_counts.get(code, 0),
            }
            for code in strand_codes
        ],
        "pendingRequests": [
            {
                "id": app.get("id"),
                "student": app.get("student"),
                "studentId": app.get("applicationNumber") or app.get("id"),
                "strand": app.get("strand"),
                "grade": app.get("grade"),
                "email": app.get("email"),
            }
            for app in pending
        ],
    }


def build_faculty_dashboard_payload(include_remote=True):
    if supabase_configured():
        return build_supabase_dashboard_payload()
    return build_local_dashboard_payload()


def handle_faculty_dashboard(handler):
    payload = build_faculty_dashboard_payload()
    json_response(handler, 200, {"success": True, "data": payload})


def generate_local_app_number(records):
    year = datetime.now().strftime("%Y")
    count = len(records) + 1
    return f"APP-{year}-{count:05d}"


def generate_local_student_id(records):
    year = datetime.now().strftime("%Y")
    existing = [r.get("student_id_generated") for r in records if r.get("student_id_generated")]
    max_seq = 145
    for sid in existing:
        try:
            seq = int(sid.split("-")[1])
            max_seq = max(max_seq, seq)
        except (IndexError, ValueError):
            pass
    return f"{year}-{max_seq + 1:05d}-SHS-0"


def save_uploaded_files(application_id, files):
    app_dir = UPLOADS_DIR / application_id
    app_dir.mkdir(parents=True, exist_ok=True)
    saved = {}

    for field, info in files.items():
        filename = Path(info["filename"]).name
        safe_name = re.sub(r"[^\w.\-]", "_", filename) or f"{field}.bin"
        target = app_dir / f"{field}_{safe_name}"
        target.write_bytes(info["content"])
        saved[field] = str(target.relative_to(ROOT)).replace("\\", "/")

    return saved


def persist_admission_documents(application_id, files):
    local_paths = save_uploaded_files(application_id, files)
    return local_paths, local_paths


def patch_admission_document_paths(application_id, doc_paths):
    if not supabase_configured() or not application_id:
        return
    payload = {
        "docForm138Path": doc_paths.get("form_138"),
        "docForm137Path": doc_paths.get("form_137"),
        "docGoodMoralPath": doc_paths.get("good_moral"),
        "docBirthCertificatePath": doc_paths.get("birth_certificate"),
        "docHighSchoolDiplomaPath": doc_paths.get("high_school_diploma"),
        "gcashProofPath": doc_paths.get("gcash_proof"),
        "bankProofPath": doc_paths.get("bank_proof"),
        "documents": doc_paths,
    }
    _, error = supabase_rest_patch(
        "admission_applications",
        f"id=eq.{application_id}",
        payload,
    )
    if error:
        print(f"[Supabase patch doc paths] {error}")


def enrich_app_data_with_profile_photo_urls(app_data, doc_paths, files=None):
    """Prepare profile photo for email using CID inline attachment (Gmail-safe)."""
    import mimetypes

    from shared.services.email_templates import PROFILE_PHOTO_CID

    enriched = dict(app_data or {})
    image_ext = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    content = None
    filename = "profile.jpg"

    if files:
        primary = files.get("profile_upload") or files.get("profile_photo") or files.get("profile_camera")
        if primary and primary.get("content"):
            content = primary["content"]
            filename = primary.get("filename") or filename

    if content is None:
        path = (doc_paths or {}).get("profile_upload") or enriched.get("profilePhotoUploadPath")
        local_file = find_local_document(path, admission_file_roots())
        if local_file and local_file.suffix.lower() in image_ext:
            content = local_file.read_bytes()
            filename = local_file.name

    if content:
        enriched["profilePhotoInlineCid"] = PROFILE_PHOTO_CID
        enriched["profilePhotoInlineContent"] = content
        enriched["profilePhotoFilename"] = filename
        enriched["profilePhotoInlineMime"] = mimetypes.guess_type(filename)[0] or "image/jpeg"
    return enriched


def _profile_photo_inline_attachment(app_data: dict) -> dict | None:
    content = app_data.get("profilePhotoInlineContent")
    cid = app_data.get("profilePhotoInlineCid")
    if not content or not cid:
        return None
    filename = app_data.get("profilePhotoFilename") or "profile.jpg"
    return {
        "content": content,
        "name": filename,
        "mime": app_data.get("profilePhotoInlineMime") or "image/jpeg",
        "inline_cid": cid,
        "inline_only": True,
    }


def run_admission_post_submit(application_id, files, local_doc_paths, app_data, gcash_proof_path, app_number):
    """Send confirmation emails first, then upload documents to Supabase storage."""
    try:
        _send_submission_emails(app_data, local_doc_paths, gcash_proof_path, app_number, files)
    except Exception as err:
        print(f"[Email post-submit] Failed to send confirmation emails: {err}")
        import traceback
        traceback.print_exc()

    try:
        if supabase_configured() and SUPABASE_SECRET_KEY:
            stored_paths = upload_admission_files_to_supabase(
                SUPABASE_URL,
                SUPABASE_SECRET_KEY,
                application_id,
                files,
                local_doc_paths,
            )
            patch_admission_document_paths(application_id, stored_paths)
    except Exception as err:
        print(f"[Storage post-submit] Upload failed (application saved): {err}")
        import traceback
        traceback.print_exc()


def admission_file_roots():
    roots = [ROOT]
    sibling = ROOT.parent / ("ENROLLSYSTEM" if ROOT.name == "ENROLLSYSTEM-ADMIN" else "ENROLLSYSTEM-ADMIN")
    if sibling.is_dir():
        roots.append(sibling)
    return roots


def document_view_url(path):
    return admin_document_view_url(path)


def handle_admission_file(handler):
    import mimetypes

    query = handler.path.split("?", 1)[1] if "?" in handler.path else ""
    file_path = ""
    for part in query.split("&"):
        if part.startswith("path="):
            file_path = unquote(part.split("=", 1)[1])
            break

    if not file_path:
        json_response(handler, 400, {"success": False, "error": "Missing file path"})
        return

    content, filename, local_file = load_admission_file_content(
        file_path,
        local_roots=admission_file_roots(),
        supabase_url=SUPABASE_URL,
        secret_key=SUPABASE_SECRET_KEY,
    )
    if content is None:
        handler.send_error(404, "File not found")
        return

    if local_file:
        mime, _ = mimetypes.guess_type(str(local_file))
        download_name = local_file.name
    else:
        mime, _ = mimetypes.guess_type(filename or file_path)
        download_name = filename or Path(file_path).name

    handler.send_response(200)
    handler.send_header("Content-Type", mime or "application/octet-stream")
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("Content-Disposition", f'inline; filename="{download_name}"')
    handler.end_headers()
    handler.wfile.write(content)


def send_email(to_addr, subject, html_body, attachments=None):
    to_addr = (to_addr or "").strip()
    if not to_addr:
        return False, "Missing recipient email address"

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print(f"[Email skipped - Gmail not configured] To: {to_addr} | {subject}")
        return False, "Gmail is not configured in .env (GMAIL_USER + GMAIL_APP_PASSWORD)"

    attachment_list = list(attachments or [])
    inline_items = [item for item in attachment_list if item.get("inline_cid")]
    other_items = [item for item in attachment_list if not item.get("inline_cid")]

    if inline_items:
        msg = MIMEMultipart("mixed")
        related = MIMEMultipart("related")
        related.attach(MIMEText(html_body, "html"))
        for attachment in inline_items:
            filename = attachment.get("name", "inline.jpg")
            data = attachment.get("content")
            if data is None:
                path = ROOT / attachment["path"]
                if not path.exists():
                    print(f"[Email inline attachment missing] {attachment.get('path')}")
                    continue
                data = path.read_bytes()
                filename = attachment.get("name", path.name)
            subtype = "jpeg"
            if filename.lower().endswith(".png"):
                subtype = "png"
            elif filename.lower().endswith(".gif"):
                subtype = "gif"
            elif filename.lower().endswith(".webp"):
                subtype = "webp"
            inline_part = MIMEImage(data, _subtype=subtype)
            inline_part.add_header("Content-ID", f"<{attachment['inline_cid']}>")
            inline_part.add_header("Content-Disposition", "inline", filename=filename)
            related.attach(inline_part)
        msg.attach(related)
    else:
        msg = MIMEMultipart()
        msg.attach(MIMEText(html_body, "html"))

    msg["From"] = f"{SCHOOL_NAME} <{GMAIL_USER}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    domain = GMAIL_USER.split("@", 1)[-1] if "@" in GMAIL_USER else "localhost"
    message_id = f"{uuid.uuid4().hex}@{domain}"
    msg["Message-ID"] = f"<{message_id}>"
    msg["X-Entity-Ref-ID"] = message_id

    for attachment in other_items:
        filename = attachment.get("name", "attachment")
        if attachment.get("content") is not None:
            data = attachment["content"]
        else:
            path = ROOT / attachment["path"]
            if not path.exists():
                print(f"[Email attachment missing] {attachment.get('path')}")
                continue
            data = path.read_bytes()
            filename = attachment.get("name", path.name)

        lower_name = filename.lower()
        if "registration" in lower_name and lower_name.endswith((".html", ".htm")):
            print(
                f"[Email] BLOCKED legacy HTML registration attachment ({filename}). "
                "Restart the server and approve again to send Registration_Certificate_*.pdf."
            )
            continue

        if filename.lower().endswith(".pdf") or attachment.get("mime") == "application/pdf":
            part = MIMEBase("application", "pdf")
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
            continue

        if str(attachment.get("mime", "")).startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            subtype = "png"
            if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
                subtype = "jpeg"
            elif "." in filename:
                subtype = filename.rsplit(".", 1)[-1].lower()
                if subtype == "jpg":
                    subtype = "jpeg"
            inline_cid = attachment.get("inline_cid")
            if inline_cid:
                inline_part = MIMEImage(data, _subtype=subtype)
                inline_part.add_header("Content-ID", f"<{inline_cid}>")
                inline_part.add_header("Content-Disposition", "inline", filename=filename)
                msg.attach(inline_part)
                if not attachment.get("inline_only"):
                    attach_part = MIMEImage(data, _subtype=subtype)
                    attach_part.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(attach_part)
                continue
            attach_part = MIMEImage(data, _subtype=subtype)
            attach_part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(attach_part)
            continue

        if filename.lower().endswith((".html", ".htm")) or attachment.get("mime") == "text/html":
            part = MIMEText(data.decode("utf-8") if isinstance(data, bytes) else data, "html", "utf-8")
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)
            continue

        part = MIMEBase("application", "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    method, err = _deliver_smtp_message(msg, to_addr)
    if method:
        print(f"[Email sent via {method}] To: {to_addr} | {subject}")
        return True, None
    if err:
        print(f"[Email error] {err}")
    return False, err or "Unknown SMTP error"


def _send_submission_emails(app_data, doc_paths, gcash_proof_path, app_number, files=None):
    import importlib
    from shared.services import email_templates as email_mod

    importlib.reload(email_mod)
    email_app_data = enrich_app_data_with_profile_photo_urls(app_data, doc_paths, files)
    html_body = email_mod.build_applicant_confirmation_email(email_app_data, SCHOOL_NAME)
    has_summary = "Personal Information" in html_body
    print(
        f"[Email applicant template] version={email_mod.APPLICANT_EMAIL_VERSION} "
        f"full_summary={has_summary} to={app_data.get('email')}"
    )
    inline_attachments = []
    photo_attachment = _profile_photo_inline_attachment(email_app_data)
    if photo_attachment:
        inline_attachments.append(photo_attachment)
        print(f"[Email applicant] inline profile photo cid={photo_attachment['inline_cid']}")
    ok, err = send_email(
        app_data["email"],
        f"Application Received — {app_number} — {SCHOOL_NAME}",
        html_body,
        inline_attachments,
    )
    print(f"[Email applicant] sent={ok} error={err}")

    time.sleep(3.0)

    attachments = [{"path": path, "name": Path(path).name} for path in doc_paths.values()]
    if gcash_proof_path and gcash_proof_path not in doc_paths.values():
        attachments.append({"path": gcash_proof_path, "name": Path(gcash_proof_path).name})
    bank_proof_path = doc_paths.get("bank_proof")
    if bank_proof_path and bank_proof_path not in doc_paths.values():
        attachments.append({"path": bank_proof_path, "name": Path(bank_proof_path).name})

    admin_target = ADMIN_EMAIL or GMAIL_USER
    if admin_target:
        ok, err = send_email(
            admin_target,
            f"[{SCHOOL_NAME}] New Admission — {app_number}",
            build_admin_submission_email(app_data, doc_paths),
            attachments,
        )
        print(f"[Email admin] sent={ok} error={err}")


def dispatch_submission_emails(app_data, doc_paths, gcash_proof_path, app_number):
    """Send confirmation emails in the background so submit responds immediately."""
    def _worker():
        try:
            _send_submission_emails(app_data, doc_paths, gcash_proof_path, app_number)
        except Exception as err:
            print(f"[Email background] Failed: {err}")
            import traceback
            traceback.print_exc()

    threading.Thread(target=_worker, daemon=True).start()


_smtp_send_lock = threading.Lock()


def _deliver_smtp_message(msg, to_addr):
    """Serialize once, send with lock + retries to avoid Gmail 'Server not connected' drops."""
    recipients = [addr.strip() for addr in str(to_addr or "").split(",") if addr.strip()]
    if not recipients:
        return None, "Missing recipient email address"

    payload = msg.as_string()
    from_addr = GMAIL_USER
    errors = []

    def send_ssl():
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(from_addr, recipients, payload)

    def send_tls():
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(from_addr, recipients, payload)

    with _smtp_send_lock:
        for attempt in range(1, 4):
            for label, sender in (("SMTP_SSL:465", send_ssl), ("STARTTLS:587", send_tls)):
                try:
                    sender()
                    return label, None
                except Exception as err:
                    errors.append(f"{label}(try{attempt}): {err}")
            if attempt < 3:
                time.sleep(attempt * 0.75)

    return None, " | ".join(errors[-6:])


def _send_via_smtp_ssl(msg):
    method, err = _deliver_smtp_message(msg, msg.get("To", ""))
    if err:
        raise RuntimeError(err)


def _send_via_starttls(msg):
    method, err = _deliver_smtp_message(msg, msg.get("To", ""))
    if err:
        raise RuntimeError(err)


def gmail_configured():
    return bool(GMAIL_USER and GMAIL_APP_PASSWORD)


def mask_email(email):
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * (len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"


def build_admin_submission_email(app_data, doc_paths):
    docs_html = "".join(
        f"<li><strong>{REQUIRED_DOCS.get(key, key)}</strong></li>"
        for key in REQUIRED_DOCS
        if key in doc_paths
    )
    payment = app_data.get("paymentMode", "")
    if payment == "gcash":
        payment_detail = (
            f"GCash — Ref: {app_data.get('gcashReference', 'N/A')} · "
            f"Sender: {app_data.get('gcashSenderName', 'N/A')} · "
            f"PHP {app_data.get('paymentAmount', ENROLLMENT_FEE)}"
        )
    elif payment == "bank":
        bank_names = {"bpi": "BPI", "unionbank": "UnionBank"}
        bank_label = bank_names.get(app_data.get("bankCode", ""), app_data.get("bankCode", "Bank"))
        payment_detail = (
            f"{bank_label} — Ref: {app_data.get('bankReference', 'N/A')} · "
            f"Sender: {app_data.get('bankSenderName', 'N/A')} · "
            f"PHP {app_data.get('paymentAmount', ENROLLMENT_FEE)}"
        )
    else:
        payment_detail = "Pay in person at the Cashier"

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;">
      <h2 style="color:#1a3a6b;">New Admission Application — {SCHOOL_NAME}</h2>
      <p><strong>Application No:</strong> {app_data.get('applicationNumber')}</p>
      <p><strong>Name:</strong> {app_data.get('lastName')}, {app_data.get('firstName')} {app_data.get('middleName', '')}</p>
      <p><strong>Email:</strong> {app_data.get('email')}</p>
      <p><strong>Contact:</strong> {app_data.get('contactNumber')}</p>
      <p><strong>Grade Level:</strong> {app_data.get('gradeLevel')}</p>
      <p><strong>Strand:</strong> {app_data.get('strandCode', 'N/A')}</p>
      <p><strong>Payment:</strong> {payment_detail}</p>
      <h3>Submitted Documents</h3>
      <ul>{docs_html}</ul>
      <p>Please review this application in the Faculty Portal.</p>
    </div>
    """


def build_approval_email(result, app_detail=None):
    from shared.services.registration_form import build_approval_email_html, prepare_form_data

    form_data = prepare_form_data(
        result,
        app_detail,
        rest_get_fn=supabase_rest_get if supabase_configured() else None,
    )
    return build_approval_email_html(result, form_data, SCHOOL_NAME)


def send_admission_credentials_email(result, app_detail=None):
    """Send Student ID + temp password after admission approval — no Registration Form."""
    from shared.services.email_templates import build_admission_approval_email

    merged = {**(app_detail or {}), **(result or {})}
    email = (merged.get("email") or "").strip().lower()
    if not email:
        return False, "Student email address not found."

    form_data = {
        "firstName": merged.get("firstName") or merged.get("first_name"),
        "studentId": merged.get("studentId") or merged.get("student_id_generated"),
        "tempPassword": merged.get("tempPassword") or merged.get("temp_password"),
        "applicationNumber": merged.get("applicationNumber") or merged.get("application_number"),
    }
    app_number = form_data.get("applicationNumber") or "Application"
    subject = f"Enrollment Approved — {app_number} — {SCHOOL_NAME}"
    try:
        html_body = build_admission_approval_email(result, form_data, SCHOOL_NAME)
    except Exception as err:
        print(f"[Email approval] Template error: {err}")
        return False, f"Could not build approval email: {err}"

    ok, err = send_email(email, subject, html_body)
    if ok:
        print(f"[Email approval] Sent to {email} | {app_number} | student={form_data.get('studentId')}")
    else:
        print(f"[Email approval] FAILED to {email} | {app_number} | {err}")
    return ok, err


_registration_form_send_locks: dict[str, threading.Lock] = {}
_registration_form_send_guard = threading.Lock()


def _registration_form_send_lock(enrollment_id: str) -> threading.Lock:
    key = str(enrollment_id or "").strip()
    with _registration_form_send_guard:
        if key not in _registration_form_send_locks:
            _registration_form_send_locks[key] = threading.Lock()
        return _registration_form_send_locks[key]


def send_registration_form_email(enrollment_id: str, payment_result: dict, *, force_resend: bool = False):
    """Send Registration Certificate PDF after tuition payment approval."""
    from shared.services.email_templates import build_registration_form_delivery_email
    from shared.services.registration_form import (
        build_registration_certificate_email_attachment,
        prepare_form_data,
    )

    if not force_resend and payment_result.get("registrationFormEmailSent"):
        return True, None

    email = (payment_result.get("email") or "").strip()
    if not email:
        return False, "Student email address not found."

    student_id = payment_result.get("studentId") or payment_result.get("student_id")
    if not student_id:
        return False, "Student ID not found for registration form."

    lock = _registration_form_send_lock(str(enrollment_id))
    if not lock.acquire(blocking=False):
        return False, "Registration form email is already being sent for this enrollment."

    try:
        if not force_resend and payment_result.get("registrationFormEmailSent"):
            return True, None

        app_detail = find_admission_by_student_id(student_id) or {}
        result = {
            "studentId": student_id,
            "email": email,
            "firstName": payment_result.get("firstName") or app_detail.get("firstName"),
            "lastName": payment_result.get("lastName") or app_detail.get("lastName"),
            "middleName": payment_result.get("middleName") or app_detail.get("middleName"),
            "applicationNumber": payment_result.get("applicationNumber") or app_detail.get("applicationNumber"),
            "applicationId": app_detail.get("id") or payment_result.get("applicationId"),
            "gradeLevel": payment_result.get("gradeLevel") or app_detail.get("gradeLevel"),
            "strandCode": payment_result.get("strandCode") or app_detail.get("strandCode"),
            "schoolYear": payment_result.get("schoolYear"),
            "semester": payment_result.get("semester"),
        }

        schedule_source = dict(app_detail)
        if supabase_configured() and not (
            schedule_source.get("subjectScheduleDetails")
            or schedule_source.get("preferredSubjectSchedules")
        ):
            lookup_id = str(
                result.get("applicationId")
                or result.get("applicationNumber")
                or ""
            ).strip()
            if lookup_id:
                raw = find_supabase_admission(lookup_id)
                if raw:
                    schedule_source = {**schedule_source, **raw}

        form_data = prepare_form_data(
            result,
            schedule_source,
            rest_get_fn=supabase_rest_get if supabase_configured() else None,
        )
        sibling = ROOT.parent / ("ENROLLSYSTEM" if ROOT.name == "ENROLLSYSTEM-ADMIN" else "ENROLLSYSTEM-ADMIN")
        attachments = [
            build_registration_certificate_email_attachment(
                result,
                form_data,
                SCHOOL_NAME,
                ROOT,
                sibling_roots=[sibling],
            ),
        ]
        subject_ref = result.get("applicationNumber") or student_id
        return send_email(
            email,
            f"Registration Certificate — {subject_ref} — {SCHOOL_NAME}",
            build_registration_form_delivery_email(result, form_data, SCHOOL_NAME),
            attachments,
        )
    finally:
        lock.release()


def send_admission_approval_email(result, app_detail=None):
    """Deprecated alias — credentials only; Registration Form is sent after payment approval."""
    return send_admission_credentials_email(result, app_detail)


def build_rejection_email(result, reason):
    return build_admission_rejection_email(result, reason, SCHOOL_NAME)


def handle_admission_submit(handler):
    parsed = parse_multipart_form(handler)
    if not parsed:
        json_response(handler, 400, {"success": False, "error": "Invalid form data"})
        return

    fields = parsed["fields"]
    files = parsed["files"]

    missing_fields = [
        key for key in (
            "lastName", "firstName", "birthdate", "email", "contactNumber",
            "gender", "gradeLevel", "paymentMode"
        )
        if not fields.get(key, "").strip()
    ]
    if missing_fields:
        json_response(handler, 400, {
            "success": False,
            "error": f"Missing required fields: {', '.join(missing_fields)}",
        })
        return

    field_error = validate_admission_fields(fields)
    if field_error:
        json_response(handler, 400, {"success": False, "error": field_error})
        return

    if not fields.get("strandCode", fields.get("strandId", "")).strip():
        json_response(handler, 400, {"success": False, "error": "Preferred strand is required."})
        return

    address_fields = ("houseNumber", "street", "barangay", "city", "province")
    if not all(fields.get(key, "").strip() for key in address_fields):
        json_response(handler, 400, {"success": False, "error": "Please complete all address fields."})
        return

    if not fields.get("previousSchool", "").strip():
        json_response(handler, 400, {"success": False, "error": "Previous school is required."})
        return

    missing_docs = [key for key in REQUIRED_DOCS if key not in files]
    if missing_docs:
        json_response(handler, 400, {
            "success": False,
            "error": "Please upload all required documents.",
            "missingDocuments": missing_docs,
        })
        return

    if fields.get("paymentMode") == "gcash":
        if not fields.get("gcashReference", "").strip():
            json_response(handler, 400, {"success": False, "error": "GCash reference number is required."})
            return
        if not fields.get("gcashSenderName", "").strip():
            json_response(handler, 400, {"success": False, "error": "GCash sender name is required."})
            return
        if not fields.get("paymentAmount", "").strip():
            json_response(handler, 400, {"success": False, "error": "Payment amount is required."})
            return
        if "gcash_proof" not in files:
            json_response(handler, 400, {"success": False, "error": "Please upload your GCash payment receipt."})
            return

    if fields.get("paymentMode") == "bank":
        if not fields.get("bankCode", "").strip():
            json_response(handler, 400, {"success": False, "error": "Bank selection is required."})
            return
        if not fields.get("bankReference", "").strip():
            json_response(handler, 400, {"success": False, "error": "Bank reference number is required."})
            return
        if not fields.get("bankSenderName", "").strip():
            json_response(handler, 400, {"success": False, "error": "Bank account holder name is required."})
            return
        if not fields.get("paymentAmount", "").strip():
            json_response(handler, 400, {"success": False, "error": "Payment amount is required."})
            return
        if "bank_proof" not in files:
            json_response(handler, 400, {"success": False, "error": "Please upload your bank payment receipt."})
            return

    file_error = validate_admission_files(files, payment_mode=fields.get("paymentMode", ""))
    if file_error:
        json_response(handler, 400, {"success": False, "error": file_error})
        return

    application_id = str(uuid.uuid4())
    doc_paths, local_doc_paths = persist_admission_documents(application_id, files)
    gcash_proof_path = doc_paths.get("gcash_proof")
    bank_proof_path = doc_paths.get("bank_proof")

    gcash_ref = fields.get("gcashReference", "").strip()

    full_address = build_full_address(fields)

    payload = {
        "lastName": fields["lastName"].strip(),
        "firstName": fields["firstName"].strip(),
        "middleName": fields.get("middleName", "").strip(),
        "birthdate": fields["birthdate"].strip(),
        "gender": fields.get("gender", "").strip(),
        "houseNumber": fields.get("houseNumber", "").strip(),
        "street": fields.get("street", "").strip(),
        "barangay": fields.get("barangay", "").strip(),
        "city": fields.get("city", "").strip(),
        "province": fields.get("province", "").strip(),
        "address": full_address,
        "contactNumber": fields["contactNumber"].strip(),
        "email": fields["email"].strip().lower(),
        "gradeLevel": fields["gradeLevel"].strip(),
        "strandCode": fields.get("strandCode", fields.get("strandId", "")).strip(),
        "strandId": "",
        "admissionType": fields.get("admissionType", "new").strip() or "new",
        "previousSchool": fields.get("previousSchool", "").strip(),
        "paymentMode": fields["paymentMode"].strip(),
        "bankCode": fields.get("bankCode", "").strip(),
        "bankReference": fields.get("bankReference", "").strip(),
        "bankSenderName": fields.get("bankSenderName", "").strip(),
        "bankProofPath": bank_proof_path,
        "gcashReference": gcash_ref,
        "gcashSenderName": fields.get("gcashSenderName", "").strip(),
        "gcashProofPath": gcash_proof_path,
        "paymentStatus": fields.get("paymentStatus", "submitted").strip() or "submitted",
        "paymentAmount": fields.get("paymentAmount", str(ENROLLMENT_FEE)).strip(),
        "documents": doc_paths,
        "docForm138Path": doc_paths.get("form_138"),
        "docForm137Path": doc_paths.get("form_137"),
        "docGoodMoralPath": doc_paths.get("good_moral"),
        "docBirthCertificatePath": doc_paths.get("birth_certificate"),
        "docHighSchoolDiplomaPath": doc_paths.get("high_school_diploma"),
    }

    app_number = None
    supabase_id = application_id

    if supabase_configured():
        result, error = supabase_rpc(
            "submit_admission_application",
            {"p_payload": payload},
            timeout=15,
        )
        if error:
            print(f"[Supabase error] submit_admission_application: {error}")
            json_response(handler, 500, {
                "success": False,
                "error": "Failed to save application to Supabase.",
                "details": parse_supabase_error(error),
                "hint": (
                    "Open Supabase SQL Editor and run "
                    "supabase/supabase-primary-migration.sql, then restart the server."
                ),
            })
            return

        app_number = result.get("applicationNumber")
        supabase_id = result.get("applicationId", application_id)
        print(f"[Supabase] Saved admission {app_number}")
    else:
        records = load_local_admissions()
        app_number = generate_local_app_number(records)
        upsert_local_admission(application_id, app_number, payload, fields, "pending")
        print("[Info] Supabase not configured — saved to local data/admissions.json")

    app_data = {**payload, "applicationNumber": app_number, "strandCode": fields.get("strandCode", "")}

    response = {
        "success": True,
        "applicationNumber": app_number,
        "applicationId": supabase_id,
        "storage": "supabase" if supabase_configured() else "local",
        "emailsQueued": gmail_configured(),
    }
    if not gmail_configured():
        response["emailWarning"] = (
            "Your application was saved successfully. A confirmation email could not be sent at this time. "
            "Please contact the Registrar's Office if you do not receive an update within a few business days."
        )
    json_response(handler, 200, response)

    threading.Thread(
        target=run_admission_post_submit,
        args=(supabase_id, files, local_doc_paths, app_data, gcash_proof_path, app_number),
        daemon=True,
    ).start()


def handle_admission_review(handler):
    body = read_json_body(handler)
    application_id = body.get("applicationId")
    action = (body.get("action") or "").lower()
    faculty_id = body.get("facultyId", "")
    reason = body.get("reason")

    if not application_id or action not in ("approve", "reject"):
        json_response(handler, 400, {"success": False, "error": "Invalid request"})
        return

    if supabase_configured():
        detail = get_admission_by_id(application_id)
        if not detail:
            json_response(handler, 404, {
                "success": False,
                "error": "Application not found in Supabase.",
                "hint": (
                    "Refresh the review list and open the application again. "
                    "If this keeps happening, run supabase/fix-approve-review.sql in Supabase SQL Editor."
                ),
            })
            return
        if (detail.get("status") or "pending").lower() != "pending":
            json_response(handler, 404, {
                "success": False,
                "error": "Application already processed.",
            })
            return

        review_id = detail.get("id") or application_id
        result, error = supabase_rpc("review_admission_application", {
            "p_application_id": review_id,
            "p_faculty_id": faculty_id,
            "p_action": action,
            "p_reason": reason,
        }, timeout=15)

        if error or not isinstance(result, dict) or not result.get("email"):
            print(f"[Supabase review error] {error}")
            json_response(handler, 500, {
                "success": False,
                "error": "Failed to process review in Supabase.",
                "details": parse_supabase_error(error),
                "hint": (
                    "Run supabase/fix-approve-review.sql in Supabase SQL Editor "
                    "(adds missing students columns + fixes review RPC), then restart the server."
                ),
            })
            return

        email_ok = False
        email_err = None
        if action == "approve":
            sync_approved_student_credentials(result, detail)
            app_ref = (
                result.get("applicationNumber")
                or detail.get("applicationNumber")
                or review_id
                or application_id
            )
            email_ok, email_err = dispatch_admission_credentials_email(app_ref, result, detail)
            result["emailQueued"] = True
        else:
            email_ok, email_err = send_email(
                result["email"],
                f"Admission Update — {result.get('applicationNumber') or 'Application'} — {SCHOOL_NAME}",
                build_rejection_email(result, reason),
            )
        result["success"] = True
        result["emailSent"] = email_ok
        if email_err:
            result["emailError"] = email_err
        json_response(handler, 200, result)
        return

    idx, app, records = ensure_pending_admission_for_review(application_id)
    if app is None:
        json_response(handler, 404, {"success": False, "error": "Application not found or already processed"})
        return

    if action == "approve":
        student_id = generate_local_student_id(records)
        temp_password = f"Shs{datetime.now().strftime('%m%d')}"
        update_local_admission_review(app, records, "approve", student_id=student_id, temp_password=temp_password)
        result = {
            "success": True,
            "status": "approved",
            "studentId": student_id,
            "tempPassword": temp_password,
            "email": app["email"],
            "firstName": app["firstName"],
            "applicationNumber": app.get("applicationNumber"),
        }
        sync_approved_student_credentials(result, app)
        app_ref = result.get("applicationNumber") or app.get("applicationNumber") or application_id
        ok, err = dispatch_admission_credentials_email(app_ref, result, app)
        result["emailQueued"] = True
        result["emailSent"] = ok
        if err:
            result["emailError"] = err
    else:
        update_local_admission_review(app, records, "reject", reason=reason)
        result = {
            "success": True,
            "status": "rejected",
            "email": app["email"],
            "firstName": app["firstName"],
            "applicationNumber": app.get("applicationNumber"),
        }
        ok, err = send_email(
            app["email"],
            f"Admission Update — {app.get('applicationNumber') or result.get('applicationNumber') or 'Application'} — {SCHOOL_NAME}",
            build_rejection_email(result, reason),
        )
        result["emailSent"] = ok
        if err:
            result["emailError"] = err

    json_response(handler, 200, result)


def handle_resend_admission_credentials(handler):
    body = read_json_body(handler)
    application_id = body.get("applicationId") or body.get("applicationNumber") or body.get("id")
    if not application_id:
        json_response(handler, 400, {"success": False, "error": "applicationId is required"})
        return

    creds = fetch_admission_credentials(application_id)
    if not creds:
        json_response(handler, 404, {"success": False, "error": "Application not found"})
        return
    if (creds.get("status") or "").lower() != "approved":
        json_response(handler, 400, {"success": False, "error": "Application must be approved first."})
        return

    email_ok, email_err = deliver_admission_credentials_email(application_id)
    if email_ok:
        json_response(handler, 200, {
            "success": True,
            "emailSent": True,
            "email": creds.get("email"),
            "message": f"Approval email resent to {creds.get('email')}.",
        })
        return

    json_response(handler, 500, {
        "success": False,
        "emailSent": False,
        "email": creds.get("email"),
        "error": email_err or "Could not send approval email.",
    })


def handle_resend_registration_certificate(handler):
    body = read_json_body(handler)
    enrollment_id = body.get("enrollmentId")
    application_id = body.get("applicationId") or body.get("applicationNumber")

    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return

    if enrollment_id:
        rows, rest_error = supabase_rest_get(
            "enrollment_payments",
            (
                f"enrollment_id=eq.{enrollment_id}"
                "&select=*,enrollments(status,students(student_id,first_name,last_name,middle_name,grade_level,strands(code)),semesters(name,school_years(label)))"
            ),
            use_secret=True,
        )
        if rest_error or not rows:
            json_response(handler, 404, {"success": False, "error": "Payment record not found for this enrollment."})
            return
        row = rows[0]
        enrollment = row.get("enrollments") or {}
        student = enrollment.get("students") or {}
        semester = enrollment.get("semesters") or {}
        school_year = semester.get("school_years") or {}
        if (enrollment.get("status") or "").lower() != "enrolled":
            json_response(handler, 400, {"success": False, "error": "Enrollment must be approved before resending the Registration Form."})
            return
        if (row.get("status") or "").lower() != "approved":
            json_response(handler, 400, {"success": False, "error": "Payment must be approved before resending the Registration Form."})
            return
        student_id = student.get("student_id")
        app_detail = find_admission_by_student_id(student_id) if student_id else None
        payment_result = {
            "studentId": student_id,
            "firstName": student.get("first_name"),
            "lastName": student.get("last_name"),
            "middleName": student.get("middle_name"),
            "gradeLevel": student.get("grade_level"),
            "strandCode": (student.get("strands") or {}).get("code"),
            "schoolYear": school_year.get("label"),
            "semester": semester.get("name"),
            "email": (app_detail or {}).get("email"),
            "applicationNumber": (app_detail or {}).get("applicationNumber"),
            "registrationFormEmailSent": row.get("registration_form_email_sent"),
        }
    elif application_id:
        detail = get_admission_by_id(application_id)
        if not detail:
            json_response(handler, 404, {"success": False, "error": "Application not found"})
            return
        if (detail.get("status") or "").lower() != "approved":
            json_response(handler, 400, {"success": False, "error": "Application must be approved."})
            return
        student_id = detail.get("studentId") or detail.get("student_id_generated")
        pay_rows, pay_error = supabase_rest_get(
            "enrollment_payments",
            (
                "select=*,enrollments!inner(status,students!inner(student_id))"
                f"&enrollments.students.student_id=eq.{quote(str(student_id or '').upper())}"
                "&enrollments.status=eq.enrolled"
                "&status=eq.approved"
                "&order=updated_at.desc&limit=1"
            ),
            use_secret=True,
        )
        if pay_error or not pay_rows:
            json_response(handler, 400, {
                "success": False,
                "error": "Payment must be approved before resending the Registration Form.",
            })
            return
        enrollment_id = pay_rows[0].get("enrollment_id")
        payment_result = {
            "studentId": student_id,
            "email": detail.get("email"),
            "firstName": detail.get("firstName"),
            "applicationNumber": detail.get("applicationNumber"),
            "registrationFormEmailSent": pay_rows[0].get("registration_form_email_sent"),
        }
    else:
        json_response(handler, 400, {"success": False, "error": "enrollmentId or applicationId is required"})
        return

    if not payment_result.get("email"):
        json_response(handler, 400, {"success": False, "error": "Student email not found."})
        return

    email_ok, email_err = send_registration_form_email(
        str(enrollment_id),
        payment_result,
        force_resend=True,
    )
    if email_ok:
        mark_result, mark_error = supabase_rpc(
            "mark_registration_form_email_sent",
            {"p_enrollment_id": enrollment_id},
            timeout=10,
        )
        if mark_error:
            print(f"[Registration form email] mark sent failed: {mark_error}")
    elif enrollment_id:
        supabase_rpc(
            "mark_registration_form_email_failed",
            {"p_enrollment_id": enrollment_id, "p_error": email_err or "Email delivery failed"},
            timeout=10,
        )

    json_response(handler, 200, {
        "success": email_ok,
        "emailSent": email_ok,
        "emailError": email_err,
        "enrollmentId": enrollment_id,
    })


def find_admission_by_student_id(student_id):
    sid = str(student_id or "").strip().upper()
    if not sid or not supabase_configured():
        return None

    rows, error = supabase_rest_get(
        "admission_applications",
        (
            f"student_id_generated=eq.{sid}&status=eq.approved"
            "&select=application_number&order=reviewed_at.desc&limit=1"
        ),
        use_secret=True,
    )
    if error or not rows:
        return None

    app_number = rows[0].get("application_number")
    if not app_number:
        return None
    return get_admission_by_id(app_number)


def handle_serve_registration_certificate(handler, student_id: str) -> bool:
    from shared.services.registration_form import (
        COR_PDF_LAYOUT_VERSION,
        build_registration_certificate_for_student,
        write_registration_certificate_http,
    )

    detail = find_admission_by_student_id(student_id)
    if not detail:
        return False

    pdf_bytes = build_registration_certificate_for_student(
        student_id,
        SCHOOL_NAME,
        admission_detail=detail,
        rest_get_fn=supabase_rest_get if supabase_configured() else None,
    )
    if not pdf_bytes:
        return False

    write_registration_certificate_http(handler, pdf_bytes, student_id, inline=True)
    print(f"[COR] Served dynamic PDF ({COR_PDF_LAYOUT_VERSION}) for {student_id}")
    return True


def handle_preview_registration_certificate(handler):
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(handler.path).query)
    application_id = (query.get("id") or query.get("applicationId") or [""])[0]
    if not application_id:
        json_response(handler, 400, {"success": False, "error": "id query parameter is required"})
        return

    detail = get_admission_by_id(application_id)
    if not detail:
        json_response(handler, 404, {"success": False, "error": "Application not found"})
        return

    if (detail.get("status") or "").lower() != "approved":
        json_response(handler, 400, {
            "success": False,
            "error": "COR preview is only available for approved applications.",
        })
        return

    student_id = detail.get("studentId") or application_id
    from shared.services.registration_form import (
        build_registration_certificate_for_student,
        write_registration_certificate_http,
    )

    pdf_bytes = build_registration_certificate_for_student(
        student_id,
        SCHOOL_NAME,
        admission_detail=detail,
        rest_get_fn=supabase_rest_get if supabase_configured() else None,
    )
    if not pdf_bytes:
        json_response(handler, 500, {"success": False, "error": "Failed to generate COR PDF"})
        return

    write_registration_certificate_http(handler, pdf_bytes, student_id, inline=True)


def find_supabase_admission(application_id):
    """Look up an admission in Supabase by UUID or application number."""
    target = str(application_id or "").strip()
    if not target or not supabase_configured():
        return None

    result, error = supabase_rpc("get_admission_detail", {
        "p_application_id": target,
    }, timeout=10)
    if not error and isinstance(result, dict) and result.get("id"):
        return result

    if error:
        print(f"[Supabase] get_admission_detail({target}): {parse_supabase_error(error)}")

    for item in fetch_supabase_pending_admissions():
        item_id = str(item.get("id") or "")
        item_no = str(item.get("applicationNumber") or "")
        if target in (item_id, item_no):
            return item

    for item in fetch_supabase_admission_history():
        item_id = str(item.get("applicationId") or item.get("id") or "")
        item_no = str(item.get("applicationNumber") or "")
        if target in (item_id, item_no):
            return item

    return None


def fetch_admission_credentials(application_id: str) -> dict | None:
    """Load Student ID + password for resend (admin secret REST — not exposed in public RPC)."""
    target = str(application_id or "").strip()
    if not target:
        return None

    if supabase_configured():
        row = None
        for filt in (
            f"application_number=eq.{quote(target)}",
            f"id=eq.{quote(target)}",
        ):
            rows, err = supabase_rest_get(
                "admission_applications",
                (
                    "select=id,application_number,email,first_name,status,"
                    "student_id_generated,temp_password"
                    f"&{filt}&limit=1"
                ),
                use_secret=True,
            )
            if err:
                print(f"[Credentials lookup] {err}")
                continue
            if rows:
                row = rows[0]
                break
        if not row:
            return None

        student_id = row.get("student_id_generated")
        temp_password = row.get("temp_password")
        if student_id and not temp_password:
            student_rows, err = supabase_rest_get(
                "students",
                f"select=password&student_id=eq.{quote(str(student_id).upper())}&limit=1",
                use_secret=True,
            )
            if not err and student_rows:
                temp_password = student_rows[0].get("password")

        return {
            "studentId": student_id,
            "tempPassword": temp_password,
            "email": row.get("email"),
            "firstName": row.get("first_name"),
            "applicationNumber": row.get("application_number"),
            "status": row.get("status"),
        }

    for record in load_local_admissions():
        if record.get("id") == target or record.get("applicationNumber") == target:
            return {
                "studentId": record.get("student_id_generated") or record.get("studentId"),
                "tempPassword": record.get("temp_password") or record.get("tempPassword"),
                "email": record.get("email"),
                "firstName": record.get("firstName"),
                "applicationNumber": record.get("applicationNumber"),
                "status": record.get("status"),
            }
    return None


def deliver_admission_credentials_email(application_ref, fallback_result=None, fallback_detail=None):
    """Send approval credentials — RPC payload first, then DB lookup (resend path)."""
    merged = {**(fallback_detail or {}), **(fallback_result or {})}
    email = (merged.get("email") or "").strip().lower()
    student_id = merged.get("studentId") or merged.get("student_id_generated")
    temp_password = merged.get("tempPassword") or merged.get("temp_password")
    if email and student_id and temp_password:
        payload = {
            "studentId": student_id,
            "tempPassword": temp_password,
            "email": email,
            "firstName": merged.get("firstName") or merged.get("first_name"),
            "applicationNumber": merged.get("applicationNumber") or merged.get("application_number"),
        }
        ok, err = send_admission_credentials_email(payload, merged)
        if ok:
            return ok, err
        print(f"[Email approval] Direct RPC payload send failed: {err}")

    ref = str(application_ref or "").strip()
    creds = fetch_admission_credentials(ref) if ref else None
    if creds and creds.get("studentId") and creds.get("tempPassword") and creds.get("email"):
        payload = {
            "studentId": creds["studentId"],
            "tempPassword": creds["tempPassword"],
            "email": creds["email"],
            "firstName": creds.get("firstName"),
            "applicationNumber": creds.get("applicationNumber"),
        }
        return send_admission_credentials_email(payload, creds)

    if email and student_id and temp_password:
        payload = {
            "studentId": student_id,
            "tempPassword": temp_password,
            "email": email,
            "firstName": merged.get("firstName") or merged.get("first_name"),
            "applicationNumber": merged.get("applicationNumber") or merged.get("application_number"),
        }
        return send_admission_credentials_email(payload, merged)

    return False, "Approved credentials not found."


def dispatch_admission_credentials_email(application_ref, fallback_result=None, fallback_detail=None):
    """
    Queue approval email in background with delay + retries.
    Avoids Gmail 'Server not connected' when submit confirmation is still sending.
    """
    app_ref = str(application_ref or "").strip()
    fb_result = dict(fallback_result or {})
    fb_detail = dict(fallback_detail or {}) if fallback_detail else None
    target = (
        fb_result.get("email")
        or (fb_detail or {}).get("email")
        or "?"
    )

    def worker():
        time.sleep(4.0)
        for attempt in range(1, 8):
            ok, err = deliver_admission_credentials_email(app_ref, fb_result, fb_detail)
            if ok:
                print(f"[Email approval] Delivered to {target} on attempt {attempt}")
                return
            print(f"[Email approval] Attempt {attempt}/7 failed for {target}: {err}")
            time.sleep(min(attempt * 1.5, 10.0))
        print(f"[Email approval] All attempts failed for {target}")

    threading.Thread(target=worker, daemon=True).start()
    return True, None


def get_admission_by_id(application_id):
    if not application_id:
        return None

    if supabase_configured():
        record = find_supabase_admission(application_id)
        if record:
            return build_admission_detail(record)
        return None

    for record in load_local_admissions():
        if record.get("id") == application_id or record.get("applicationNumber") == application_id:
            return build_admission_detail(record)

    return None


def handle_get_admission_detail(handler):
    query = handler.path.split("?", 1)[1] if "?" in handler.path else ""
    app_id = ""
    for part in query.split("&"):
        if part.startswith("id="):
            app_id = unquote(part.split("=", 1)[1])
    if not app_id:
        json_response(handler, 400, {"success": False, "error": "Missing application id"})
        return
    detail = get_admission_by_id(app_id)
    if not detail:
        json_response(handler, 404, {"success": False, "error": "Application not found"})
        return
    json_response(handler, 200, {"success": True, "data": detail})


def handle_get_pending_admissions(handler):
    pending = get_all_pending_admissions()
    json_response(handler, 200, {"success": True, "data": pending})


def handle_get_admission_history(handler):
    history = get_all_admission_history()
    json_response(handler, 200, {"success": True, "data": history})


def handle_get_pending_subject_enrollments(handler):
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = supabase_rpc("get_pending_enrollments", {}, timeout=15)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    pending = normalize_rpc_json_array(result)
    json_response(handler, 200, {"success": True, "data": pending, "count": len(pending)})


def handle_get_subject_enrollment_history(handler):
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = supabase_rpc("get_enrollment_history", {}, timeout=15)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    history = normalize_rpc_json_array(result)
    json_response(handler, 200, {"success": True, "data": history, "count": len(history)})


def enrich_enrollment_detail_payload(detail):
    if not isinstance(detail, dict):
        return detail
    payment = detail.get("payment")
    if isinstance(payment, dict):
        proof_path = payment.get("gcashProofPath")
        if proof_path:
            payment["gcashProofUrl"] = admin_document_view_url(proof_path)
        detail["payment"] = payment
    return detail


def handle_get_subject_enrollment_detail(handler):
    query = handler.path.split("?", 1)[-1] if "?" in handler.path else ""
    enrollment_id = None
    for part in query.split("&"):
        if part.startswith("id="):
            enrollment_id = unquote(part.split("=", 1)[1])
    if not enrollment_id and "/detail/" in handler.path:
        enrollment_id = unquote(handler.path.rsplit("/", 1)[-1])
    if not enrollment_id:
        json_response(handler, 400, {"success": False, "error": "Enrollment id required"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = supabase_rpc("get_enrollment_detail", {"p_enrollment_id": enrollment_id}, timeout=15)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    if not result:
        json_response(handler, 404, {"success": False, "error": "Enrollment not found"})
        return
    json_response(handler, 200, {"success": True, "data": enrich_enrollment_detail_payload(result)})


def handle_subject_enrollment_review(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return
    enrollment_id = body.get("enrollmentId")
    action = (body.get("action") or "").lower()
    faculty_id = body.get("facultyId", "")
    reason = body.get("reason")
    if not enrollment_id or action not in ("approve", "reject"):
        json_response(handler, 400, {"success": False, "error": "Invalid request"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = supabase_rpc("review_enrollment", {
        "p_enrollment_id": enrollment_id,
        "p_faculty_id": faculty_id,
        "p_action": action,
        "p_reason": reason,
    }, timeout=15)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "data": result})


def _rest_current_school_year():
    rows, error = supabase_rest_get(
        "school_years",
        "is_current=eq.true&select=id,label,code,enrollment_open&limit=1",
        timeout=10,
    )
    if error:
        return None, error
    if rows:
        return rows[0], None

    rows, error = supabase_rest_get(
        "school_years",
        "code=eq.2627&select=id,label,code,enrollment_open&limit=1",
        timeout=10,
    )
    if error:
        return None, error
    if rows:
        sy = rows[0]
        supabase_rest_patch("school_years", f"id=eq.{sy['id']}", {"is_current": True})
        return sy, None

    created, error = supabase_rest_insert(
        "school_years",
        {"label": "2026-2027", "code": "2627", "is_current": True, "enrollment_open": False},
        return_representation=True,
    )
    if error:
        return None, error
    return created, None


def _rest_semester_select_fields():
    return "id,name,code,is_current,enrollment_open,start_date,end_date"


def _rest_get_semesters(sy_id):
    fields = _rest_semester_select_fields()
    rows, error = supabase_rest_get(
        "semesters",
        f"school_year_id=eq.{sy_id}&select={fields},target_grade_level&order=code.asc",
        timeout=10,
    )
    if error and "target_grade_level" in str(error).lower():
        rows, error = supabase_rest_get(
            "semesters",
            f"school_year_id=eq.{sy_id}&select={fields}&order=code.asc",
            timeout=10,
        )
    return rows, error


def _rest_ensure_semesters(sy_id):
    sem_rows, error = _rest_get_semesters(sy_id)
    if error:
        return None, error

    existing = {row.get("code"): row for row in (sem_rows or []) if row.get("code")}
    defaults = [
        {
            "school_year_id": sy_id,
            "name": "First Semester",
            "code": "1st",
            "is_current": True,
            "enrollment_open": False,
            "start_date": "2026-08-01",
            "end_date": "2026-12-15",
        },
        {
            "school_year_id": sy_id,
            "name": "Second Semester",
            "code": "2nd",
            "is_current": False,
            "enrollment_open": False,
            "start_date": "2027-01-05",
            "end_date": "2027-05-30",
        },
    ]
    for item in defaults:
        if item["code"] not in existing:
            _, insert_error = supabase_rest_insert("semesters", item)
            if insert_error and "target_grade_level" in str(insert_error).lower():
                item.pop("target_grade_level", None)
                _, insert_error = supabase_rest_insert("semesters", item)
            if insert_error and "duplicate" not in str(insert_error).lower():
                return None, insert_error

    sem_rows, error = _rest_get_semesters(sy_id)
    if error:
        return None, error
    if not sem_rows:
        return None, "No semesters configured for the current school year"

    if not any(row.get("is_current") for row in sem_rows):
        first_id = sem_rows[0]["id"]
        supabase_rest_patch("semesters", f"school_year_id=eq.{sy_id}", {"is_current": False})
        supabase_rest_patch("semesters", f"id=eq.{first_id}", {"is_current": True})
        sem_rows[0]["is_current"] = True

    return sem_rows, None


def _format_enrollment_period_payload(sy, sem_rows):
    current = next((row for row in sem_rows if row.get("is_current")), sem_rows[0])
    ordered = sorted(
        sem_rows,
        key=lambda row: 0 if row.get("code") == "1st" else 1 if row.get("code") == "2nd" else 2,
    )
    return {
        "schoolYearId": sy.get("id"),
        "schoolYear": sy.get("label"),
        "schoolYearCode": sy.get("code"),
        "schoolYearOpen": sy.get("enrollment_open"),
        "semesterId": current.get("id"),
        "semester": current.get("name"),
        "semesterCode": current.get("code"),
        "enrollmentOpen": current.get("enrollment_open"),
        "targetGradeLevel": current.get("target_grade_level"),
        "startDate": current.get("start_date"),
        "endDate": current.get("end_date"),
        "isCurrent": current.get("is_current"),
        "semesters": [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "code": row.get("code"),
                "enrollmentOpen": row.get("enrollment_open"),
                "targetGradeLevel": row.get("target_grade_level"),
                "startDate": row.get("start_date"),
                "endDate": row.get("end_date"),
                "isCurrent": row.get("is_current"),
            }
            for row in ordered
        ],
    }


def fetch_enrollment_period_data():
    sy, error = _rest_current_school_year()
    if error or not sy:
        result, rpc_error = supabase_rpc("get_enrollment_period", {}, timeout=10)
        if rpc_error:
            return None, error or rpc_error
        return result or {}, None

    sem_rows, error = _rest_ensure_semesters(sy["id"])
    if error or not sem_rows:
        result, rpc_error = supabase_rpc("get_enrollment_period", {}, timeout=10)
        if rpc_error:
            return None, error or rpc_error
        return result or {}, None

    return _format_enrollment_period_payload(sy, sem_rows), None


def switch_enrollment_semester_data(semester_code):
    semester_code = (semester_code or "").strip().lower()
    if semester_code not in ("1st", "2nd"):
        return None, "semesterCode must be 1st or 2nd"

    sy, error = _rest_current_school_year()
    if error or not sy:
        return None, error or "School year not found"

    sem_rows, error = _rest_ensure_semesters(sy["id"])
    if error:
        return None, error

    target = next((row for row in sem_rows if row.get("code") == semester_code), None)
    if not target:
        return None, f"Semester {semester_code} not found"

    _, error = supabase_rest_patch("semesters", f"school_year_id=eq.{sy['id']}", {"is_current": False})
    if error:
        return None, error
    _, error = supabase_rest_patch("semesters", f"id=eq.{target['id']}", {"is_current": True})
    if error:
        return None, error

    refreshed, error = fetch_enrollment_period_data()
    return refreshed, error


def _rest_freeze_inactive_students(semester_id):
    students, error = supabase_rest_get(
        "students",
        "is_active=eq.true&account_status=eq.active"
        "&select=id,admission_status",
        timeout=15,
    )
    if error or not students:
        return 0

    enrolled_rows, _ = supabase_rest_get(
        "enrollments",
        f"semester_id=eq.{semester_id}&status=in.(pending,approved,enrolled)&select=student_id",
        timeout=15,
    )
    enrolled_ids = {row.get("student_id") for row in (enrolled_rows or []) if row.get("student_id")}

    frozen = 0
    for student in students:
        student_id = student.get("id")
        if not student_id or student_id in enrolled_ids:
            continue
        if (student.get("admission_status") or "") not in ("approved", "enrolled"):
            continue
        _, patch_error = supabase_rest_patch(
            "students",
            f"id=eq.{student_id}",
            {"account_status": "frozen"},
        )
        if not patch_error:
            frozen += 1
    return frozen


def _rest_close_semester_enrollment(semester_id):
    pending_rows, _ = supabase_rest_get(
        "enrollments",
        f"semester_id=eq.{semester_id}&status=eq.pending&select=id",
        timeout=15,
    )
    rejected = len(pending_rows or [])
    if rejected:
        supabase_rest_patch(
            "enrollments",
            f"semester_id=eq.{semester_id}&status=eq.pending",
            {
                "status": "rejected",
                "rejection_reason": "Enrollment period closed by the registrar.",
            },
        )

    frozen = 0
    freeze_result, freeze_error = supabase_rpc("freeze_inactive_students", {}, timeout=15)
    if not freeze_error and isinstance(freeze_result, dict):
        frozen = int(freeze_result.get("frozenCount") or 0)
    else:
        frozen = _rest_freeze_inactive_students(semester_id)

    return {"rejectedPending": rejected, "frozenStudents": frozen}


def set_enrollment_period_data(enrollment_open, target_grade_level=None, semester_code=None):
    sy, error = _rest_current_school_year()
    if error or not sy:
        return None, error or "School year not found"

    if semester_code:
        _, error = switch_enrollment_semester_data(semester_code)
        if error:
            return None, error

    period, error = fetch_enrollment_period_data()
    if error or not period:
        return None, error or "Could not load enrollment period"

    semester_id = period.get("semesterId")
    if not semester_id:
        return None, "Active semester not found"

    semester_patch = {"enrollment_open": bool(enrollment_open)}
    if target_grade_level is not None:
        semester_patch["target_grade_level"] = target_grade_level or None

    _, error = supabase_rest_patch("semesters", f"id=eq.{semester_id}", semester_patch)
    if error and "target_grade_level" in str(error).lower():
        semester_patch.pop("target_grade_level", None)
        _, error = supabase_rest_patch("semesters", f"id=eq.{semester_id}", semester_patch)
    if error:
        return None, error

    supabase_rest_patch(
        "school_years",
        f"id=eq.{sy['id']}",
        {"enrollment_open": bool(enrollment_open)},
    )

    close_summary = None
    if not enrollment_open:
        close_summary = _rest_close_semester_enrollment(semester_id)

    refreshed, error = fetch_enrollment_period_data()
    if error:
        return None, error

    return {
        "success": True,
        "enrollmentOpen": bool(enrollment_open),
        "targetGradeLevel": target_grade_level or None,
        "semesterCode": refreshed.get("semesterCode"),
        "closeSummary": close_summary,
        "period": refreshed,
    }, None


def handle_get_enrollment_period(handler):
    if not supabase_configured():
        json_response(handler, 200, {"success": True, "data": {"enrollmentOpen": True}})
        return
    result, error = fetch_enrollment_period_data()
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "data": result or {}})


def handle_set_enrollment_period(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    if body.get("switchOnly"):
        result, error = switch_enrollment_semester_data(body.get("semesterCode"))
    else:
        result, error = set_enrollment_period_data(
            bool(body.get("enrollmentOpen")),
            body.get("targetGradeLevel"),
            body.get("semesterCode"),
        )
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "data": result or {}})


def handle_switch_enrollment_semester(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = switch_enrollment_semester_data(body.get("semesterCode"))
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "data": result or {}})


def _fetch_students_for_grading_rest(grade_level=None, strand_code=None):
    sem_rows, sem_error = supabase_rest_get(
        "semesters",
        "is_current=eq.true&select=id,name&limit=1",
    )
    if sem_error or not sem_rows:
        return []

    sem = sem_rows[0]
    rows, error = supabase_rest_get(
        "enrollments",
        f"status=eq.enrolled&semester_id=eq.{sem['id']}"
        "&select=id,students(student_id,last_name,first_name,grade_level,strands(code))",
    )
    if error or not rows:
        return []

    students = []
    for row in rows:
        st = row.get("students") or {}
        strand = (st.get("strands") or {}).get("code") or ""
        gl = st.get("grade_level") or ""
        if grade_level and gl != grade_level:
            continue
        if strand_code and strand.upper() != strand_code.upper():
            continue
        students.append({
            "studentId": st.get("student_id") or "",
            "student": f"{st.get('last_name', '')}, {st.get('first_name', '')}".strip(", "),
            "gradeLevel": gl,
            "strand": strand,
            "enrollmentId": row.get("id"),
            "semester": sem.get("name") or "",
        })

    students.sort(key=lambda s: s.get("student") or "")
    return students


def handle_get_students_for_grading(handler):
    query = handler.path.split("?", 1)[-1] if "?" in handler.path else ""
    params = {}
    for part in query.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[unquote(k)] = unquote(v)
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    grade_level = params.get("gradeLevel") or None
    strand_code = params.get("strand") or None
    result, error = supabase_rpc("get_students_for_grading", {
        "p_grade_level": grade_level,
        "p_strand_code": strand_code,
    }, timeout=15)
    if error:
        students = _fetch_students_for_grading_rest(grade_level, strand_code)
        if not students:
            json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
            return
        json_response(handler, 200, {"success": True, "data": students})
        return
    json_response(handler, 200, {"success": True, "data": result if isinstance(result, list) else []})


def handle_get_grades_sheet(handler):
    query = handler.path.split("?", 1)[-1] if "?" in handler.path else ""
    enrollment_id = None
    for part in query.split("&"):
        if part.startswith("enrollmentId="):
            enrollment_id = unquote(part.split("=", 1)[1])
    if not enrollment_id:
        json_response(handler, 400, {"success": False, "error": "enrollmentId required"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = supabase_rpc("get_enrollment_grades_sheet", {
        "p_enrollment_id": enrollment_id,
    }, timeout=15)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "data": result if isinstance(result, list) else []})


def handle_save_grades(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    result, error = supabase_rpc("save_student_grades", {
        "p_enrollment_id": body.get("enrollmentId"),
        "p_faculty_id": body.get("facultyId", ""),
        "p_grades": body.get("grades") or [],
    }, timeout=20)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return
    json_response(handler, 200, {"success": True, "data": result})


def handle_list_enrollment_payments(handler):
    query = handler.path.split("?", 1)[-1] if "?" in handler.path else ""
    status = None
    scope = "needs_action"
    for part in query.split("&"):
        if part.startswith("status="):
            status = unquote(part.split("=", 1)[1]).strip() or None
        if part.startswith("scope="):
            scope = unquote(part.split("=", 1)[1]).strip() or "needs_action"
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return

    result, error = supabase_rpc(
        "list_enrollment_payments",
        {"p_status": status, "p_scope": scope},
        timeout=15,
    )
    if error:
        fallback, fb_error = supabase_rpc(
            "list_enrollment_payments",
            {"p_status": status},
            timeout=15,
        )
        if fb_error:
            json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
            return
        if scope == "needs_action":
            json_response(handler, 200, {
                "success": True,
                "data": fallback if isinstance(fallback, list) else [],
                "warning": (
                    "Run supabase/fix-payment-list-all-terms.sql in Supabase SQL Editor "
                    "to show previous-term payments that block next enrollment."
                ),
            })
            return
        result = fallback
        error = None

    json_response(handler, 200, {"success": True, "data": result if isinstance(result, list) else []})


def handle_approve_enrollment_payment(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return
    enrollment_id = body.get("enrollmentId")
    if not enrollment_id:
        json_response(handler, 400, {"success": False, "error": "enrollmentId required"})
        return
    if not supabase_configured():
        json_response(handler, 503, {"success": False, "error": "Supabase not configured"})
        return
    user = body.get("facultyId") or body.get("adminId") or ""
    result, error = supabase_rpc("approve_enrollment_payment", {
        "p_enrollment_id": enrollment_id,
        "p_faculty_id": user,
        "p_amount_paid": body.get("amountPaid"),
        "p_or_number": body.get("orNumber") or "",
        "p_payment_mode": body.get("paymentMode") or "cashier",
        "p_notes": body.get("notes") or "",
    }, timeout=20)
    if error:
        json_response(handler, 500, {"success": False, "error": parse_supabase_error(error)})
        return

    data = result if isinstance(result, dict) else {}
    response = {
        "success": True,
        "data": data,
        "paymentApproved": (data.get("paymentStatus") or data.get("status")) == "approved",
        "alreadyApproved": bool(data.get("alreadyApproved")),
        "registrationFormEmailSent": bool(data.get("registrationFormEmailSent")),
    }

    if not response["paymentApproved"]:
        json_response(handler, 200, response)
        return

    if data.get("registrationFormEmailSent"):
        response["message"] = "Payment is already approved. Registration form was previously emailed."
        json_response(handler, 200, response)
        return

    email_ok, email_err = send_registration_form_email(str(enrollment_id), data)
    if email_ok:
        mark_result, mark_error = supabase_rpc(
            "mark_registration_form_email_sent",
            {"p_enrollment_id": enrollment_id},
            timeout=10,
        )
        marked = isinstance(mark_result, dict) and mark_result.get("marked")
        response["registrationFormEmailSent"] = bool(marked)
        response["emailSent"] = True
        response["message"] = "Payment approved and registration form emailed successfully."
        if not marked:
            response["message"] = (
                "Payment approved. Registration form email was sent, but the sent flag could not be updated."
            )
    else:
        supabase_rpc(
            "mark_registration_form_email_failed",
            {"p_enrollment_id": enrollment_id, "p_error": email_err or "Email delivery failed"},
            timeout=10,
        )
        response["registrationFormEmailSent"] = False
        response["emailSent"] = False
        response["emailError"] = email_err
        response["message"] = (
            "Payment approved, but the registration form email could not be sent. "
            "You may retry approval or use Resend Registration Form."
        )

    json_response(handler, 200, response)


def handle_health_check(handler):
    supabase_ready = supabase_configured()
    gmail_ready = gmail_configured()
    json_response(handler, 200, {
        "success": True,
        "portal": "admin",
        "supabaseConfigured": supabase_ready,
        "supabaseUrl": SUPABASE_URL or None,
        "hasSecretKey": bool(SUPABASE_SECRET_KEY),
        "hasPublishableKey": bool(SUPABASE_PUBLISHABLE_KEY),
        "gmailConfigured": gmail_ready,
        "gmailUser": mask_email(GMAIL_USER) if gmail_ready else None,
        "adminEmail": mask_email(ADMIN_EMAIL) if ADMIN_EMAIL else None,
        "message": (
            "Supabase is configured. Admissions save to Supabase only."
            if supabase_ready
            else "SUPABASE_URL is missing in .env — data saves to local file only (data/admissions.json)."
        ),
        "gmailMessage": (
            "Gmail is configured. Enrollment emails will be sent."
            if gmail_ready
            else "Gmail is not configured — add GMAIL_USER and GMAIL_APP_PASSWORD to .env, then restart server."
        ),
        "groqConfigured": bool(GROQ_API_KEY),
        "groqModel": GROQ_MODEL if GROQ_API_KEY else None,
        "geminiConfigured": bool(GEMINI_API_KEY),
        "openrouterConfigured": bool(effective_openrouter_api_key()),
        "aiProvider": (
            get_scheduler_service().cloud_ai.primary_provider.name
            if get_scheduler_service().cloud_ai.primary_provider
            else None
        ),
        "aiProviderLabel": (
            get_scheduler_service().cloud_ai.primary_provider.label
            if get_scheduler_service().cloud_ai.primary_provider
            else None
        ),
        "aiModel": (
            get_scheduler_service().cloud_ai.primary_provider.model
            if get_scheduler_service().cloud_ai.primary_provider
            else None
        ),
        "aiModelReady": bool(GROQ_API_KEY or effective_openrouter_api_key() or GEMINI_API_KEY),
        "smartAiReady": True,
        "requiresApiKey": not bool(GROQ_API_KEY or effective_openrouter_api_key() or GEMINI_API_KEY),
    })


def handle_scheduling_config(handler):
    service = get_scheduler_service()
    json_response(handler, 200, {"success": True, "data": service.get_default_config()})


def handle_scheduling_context(handler):
    query = handler.path.split("?", 1)[-1] if "?" in handler.path else ""
    params = {}
    for part in query.split("&"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[unquote(key)] = unquote(value)

    strands = [s.strip() for s in (params.get("strands") or "").split(",") if s.strip()]
    service = get_scheduler_service()
    context = service.get_scheduling_context(
        grade_level=params.get("gradeLevel") or "Grade 12",
        semester_code=params.get("semesterCode") or "1st",
        strands=strands or None,
        rooms=[r.strip() for r in (params.get("rooms") or "").split(",") if r.strip()] or None,
    )
    json_response(handler, 200, {"success": True, "data": context})


def handle_scheduling_publish(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    if not supabase_configured():
        json_response(handler, 503, {
            "success": False,
            "error": "Supabase required to publish schedules.",
            "hint": "Run supabase/publish-schedules.sql in Supabase SQL Editor.",
        })
        return

    result, error = supabase_rpc("publish_schedules", {
        "p_payload": {
            "gradeLevel": body.get("gradeLevel") or "Grade 12",
            "semesterCode": body.get("semesterCode") or "1st",
        },
    }, timeout=20)
    if error:
        json_response(handler, 500, {
            "success": False,
            "error": parse_supabase_error(error) or "Failed to publish schedules.",
            "hint": "Run supabase/publish-schedules.sql in Supabase SQL Editor.",
        })
        return
    json_response(handler, 200, {"success": True, **(result or {})})


def handle_scheduling_generate(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    service = get_scheduler_service()
    result = service.generate(
        grade_level=body.get("gradeLevel") or body.get("grade_level") or "Grade 12",
        semester_code=body.get("semesterCode") or body.get("semester_code") or "1st",
        strands=body.get("strands"),
        sections_per_strand=int(body.get("sectionsPerStrand") or body.get("sections_per_strand") or 2),
        rooms=body.get("rooms"),
        use_ai=body.get("useAi", True),
        use_cloud_ai=body.get("useCloudAi", True),
        allow_local_fallback=body.get("allowLocalFallback", True),
    )
    status = 200 if result.get("success") else 422
    json_response(handler, status, result)


def _stamp_schedule_grade_level(schedules: list, grade_level: str) -> list:
    stamped = []
    for item in schedules or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if not row.get("gradeLevel") and not row.get("grade_level"):
            row["gradeLevel"] = grade_level
        stamped.append(row)
    return stamped


def _prepare_schedules_for_save(
    schedules: list,
    *,
    reject_invalid: bool = False,
) -> tuple[list, dict, str | None]:
    from scheduling.schedule_dedupe import sanitize_schedules_for_save

    cleaned, meta = sanitize_schedules_for_save(schedules)
    if reject_invalid and meta.get("dropped_invalid"):
        return cleaned, meta, (
            f"Rejected {meta['dropped_invalid']} schedule row(s) with invalid section names. "
            "Each strand only has sections A and B — regenerate the schedule and save again."
        )
    return cleaned, meta, None


def _deactivate_invalid_section_schedules(
    grade_level: str,
    semester_code: str,
    strand_codes: set[str] | None = None,
) -> int:
    """Deactivate DB rows attached to misnamed sections (e.g. wrong virtue on a strand)."""
    from scheduling.schedule_dedupe import normalize_section_letter

    rows, error = supabase_rest_get(
        "class_schedules",
        "select=id,is_active,"
        "sections(name,grade_level,strands(code)),"
        "subjects(semester_code)",
        use_secret=True,
        timeout=25,
    )
    if error or not rows:
        return 0

    targets = {str(code or "").upper() for code in (strand_codes or []) if code}
    deactivated = 0
    for row in rows:
        if not row.get("is_active"):
            continue
        section = row.get("sections") or {}
        subject = row.get("subjects") or {}
        strand = (section.get("strands") or {}).get("code") or ""
        grade = section.get("grade_level") or ""
        if grade != grade_level:
            continue
        if (subject.get("semester_code") or "1st") != semester_code:
            continue
        if targets and str(strand).upper() not in targets:
            continue
        suffix = str(section.get("name") or "").split("-", 1)
        suffix = suffix[1].strip() if len(suffix) > 1 else ""
        item = {
            "gradeLevel": grade,
            "strand": strand,
            "section": suffix,
            "subject_code": subject.get("code") or "",
        }
        if normalize_section_letter(item) is not None:
            continue
        _, patch_err = supabase_rest_patch(
            "class_schedules",
            f"id=eq.{row['id']}",
            {"is_active": False},
        )
        if not patch_err:
            deactivated += 1
    return deactivated


def _load_draft_schedules_from_rest(
    semester_code: str,
    *,
    exclude_strand: str | None = None,
    exclude_grade_level: str | None = None,
) -> list:
    rows, error = supabase_rest_get(
        "class_schedules",
        "select=faculty_id,section_id,subject_id,is_active,schedule_label,sessions_json,"
        "day_of_week,start_time,end_time,"
        "faculty(faculty_id,first_name,last_name),"
        "subjects(code,name,semester_code),"
        "sections(name,grade_level,strands(code)),"
        "rooms(name)"
        "&is_active=eq.true",
        use_secret=True,
        timeout=25,
    )
    if error or not rows:
        return []

    schedules = []
    exclude = str(exclude_strand or "").upper() if exclude_strand else ""
    exclude_grade = str(exclude_grade_level or "") if exclude_grade_level else ""
    for row in rows:
        section = row.get("sections") or {}
        strand = section.get("strands") or {}
        subject = row.get("subjects") or {}
        faculty = row.get("faculty") or {}
        strand_code = str(strand.get("code") or "").upper()
        grade = section.get("grade_level") or ""
        sem = subject.get("semester_code") or "1st"
        if sem not in (None, semester_code):
            continue
        if exclude and strand_code == exclude and (not exclude_grade or grade == exclude_grade):
            continue
        sessions = row.get("sessions_json") or []
        if not sessions and row.get("day_of_week"):
            sessions = [{
                "day": str(row.get("day_of_week") or "").split(",")[0].strip(),
                "start": row.get("start_time") or "8:00am",
                "end": row.get("end_time") or "9:00am",
                "room": (row.get("rooms") or {}).get("name") or "",
            }]
        section_letter = _section_letter_from_name(section.get("name") or "", strand_code, grade)
        row_item = {
            "gradeLevel": grade,
            "strand": strand_code,
            "section": section_letter,
            "subject_code": subject.get("code"),
        }
        from scheduling.schedule_dedupe import normalize_section_letter
        if normalize_section_letter(row_item) is None:
            continue
        schedules.append({
            "gradeLevel": grade,
            "strand": strand_code,
            "section": normalize_section_letter(row_item),
            "subject_code": subject.get("code"),
            "subject_name": subject.get("name"),
            "faculty_id": faculty.get("faculty_id"),
            "faculty_name": f"{faculty.get('first_name', '')} {faculty.get('last_name', '')}".strip(),
            "schedule_label": row.get("schedule_label") or "",
            "sessions": sessions if isinstance(sessions, list) else [],
        })
    return dedupe_schedule_entries(schedules)


def _is_rpc_missing_error(error: str | None) -> bool:
    text = str(error or "").lower()
    return (
        "could not find the function" in text
        or "schema cache" in text
        or "42883" in text
    )


def _is_updated_at_schema_error(error: str | None) -> bool:
    text = str(error or "").lower()
    return "updated_at" in text and "class_schedules" in text


def _schedule_day_and_times(sessions: list) -> tuple[str, str | None, str | None]:
    if not sessions:
        return "MW", None, None
    days: list[str] = []
    for session in sessions:
        day = str(session.get("day") or "").strip()
        if day and day not in days:
            days.append(day)
    first = sessions[0] if isinstance(sessions[0], dict) else {}
    return ", ".join(days) if days else "MW", first.get("start"), first.get("end")


def _apply_schedules_via_rest(record: dict) -> tuple[dict | None, str | None]:
    """Persist schedules without apply_generated_schedules RPC (schema-safe fallback)."""
    from enrollment_curriculum import format_section_name
    from scheduling.schedule_dedupe import normalize_section_letter
    from urllib.parse import quote

    semester_rows, err = supabase_rest_get(
        "semesters",
        "select=id&is_current=eq.true&limit=1",
        use_secret=True,
        timeout=15,
    )
    if err:
        return None, err
    if not semester_rows:
        return None, "No active semester configured in Supabase."
    semester_id = semester_rows[0]["id"]
    default_grade = record.get("gradeLevel") or "Grade 12"
    applied = 0

    for item in record.get("schedules") or []:
        if not isinstance(item, dict):
            continue
        grade = item.get("gradeLevel") or default_grade
        strand_code = str(item.get("strand") or "").upper()
        section_key = normalize_section_letter(item)
        subject_code = str(item.get("subject_code") or "").strip()
        if not section_key or not strand_code or not subject_code:
            continue

        strand_rows, err = supabase_rest_get(
            "strands",
            f"select=id&code=eq.{quote(strand_code)}&limit=1",
            use_secret=True,
            timeout=15,
        )
        if err or not strand_rows:
            return None, err or f"Unknown strand: {strand_code}"
        strand_id = strand_rows[0]["id"]

        section_name = format_section_name(strand_code, grade, section_key)
        section_rows, err = supabase_rest_get(
            "sections",
            f"select=id&name=eq.{quote(section_name)}&grade_level=eq.{quote(grade)}&limit=1",
            use_secret=True,
            timeout=15,
        )
        if err:
            return None, err
        if section_rows:
            section_id = section_rows[0]["id"]
        else:
            created, err = supabase_rest_insert(
                "sections",
                {"name": section_name, "strand_id": strand_id, "grade_level": grade},
                return_representation=True,
            )
            if err:
                return None, err
            section_id = created.get("id") if isinstance(created, dict) else None
            if not section_id:
                return None, f"Could not create section {section_name}"

        subject_rows, err = supabase_rest_get(
            "subjects",
            f"select=id&code=eq.{quote(subject_code)}&limit=1",
            use_secret=True,
            timeout=15,
        )
        if err:
            return None, err
        if subject_rows:
            subject_id = subject_rows[0]["id"]
        else:
            created, err = supabase_rest_insert(
                "subjects",
                {
                    "code": subject_code,
                    "name": item.get("subject_name") or subject_code,
                    "strand_id": strand_id,
                    "grade_level": grade,
                    "semester_code": record.get("semesterCode") or "1st",
                    "lec_hours": 3,
                    "lab_hours": 0,
                    "units": 3,
                },
                return_representation=True,
            )
            if err:
                return None, err
            subject_id = created.get("id") if isinstance(created, dict) else None
            if not subject_id:
                return None, f"Could not create subject {subject_code}"

        sessions = item.get("sessions") if isinstance(item.get("sessions"), list) else []
        day_of_week, start_time, end_time = _schedule_day_and_times(sessions)
        schedule_label = item.get("schedule_label") or "TBA"
        room_id = None
        room_name = ""
        if sessions and isinstance(sessions[0], dict):
            room_name = str(sessions[0].get("room") or "").strip().upper()
        if room_name:
            room_rows, err = supabase_rest_get(
                "rooms",
                f"select=id&name=eq.{quote(room_name)}&limit=1",
                use_secret=True,
                timeout=15,
            )
            if err:
                return None, err
            if room_rows:
                room_id = room_rows[0]["id"]
            else:
                created, err = supabase_rest_insert(
                    "rooms",
                    {"name": room_name, "capacity": 40, "room_type": "classroom"},
                    return_representation=True,
                )
                if err:
                    return None, err
                room_id = created.get("id") if isinstance(created, dict) else None

        faculty_uuid = None
        faculty_code = str(item.get("faculty_id") or "").strip().upper()
        if faculty_code:
            faculty_rows, err = supabase_rest_get(
                "faculty",
                f"select=id&faculty_id=eq.{quote(faculty_code)}&limit=1",
                use_secret=True,
                timeout=15,
            )
            if err:
                return None, err
            if faculty_rows:
                faculty_uuid = faculty_rows[0]["id"]

        existing_rows, err = supabase_rest_get(
            "class_schedules",
            "select=id&"
            f"subject_id=eq.{quote(str(subject_id))}&"
            f"section_id=eq.{quote(str(section_id))}&"
            f"semester_id=eq.{quote(str(semester_id))}&"
            "order=is_active.desc&limit=1",
            use_secret=True,
            timeout=15,
        )
        if err:
            return None, err

        payload = {
            "faculty_id": faculty_uuid,
            "room_id": room_id,
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "schedule_label": schedule_label,
            "sessions_json": sessions,
            "max_slots": 40,
            "is_published": True,
            "is_active": True,
        }
        if existing_rows:
            schedule_id = existing_rows[0]["id"]
            _, err = supabase_rest_patch(
                "class_schedules",
                f"id=eq.{quote(str(schedule_id))}",
                payload,
            )
            if err:
                return None, err
        else:
            payload.update({
                "subject_id": subject_id,
                "section_id": section_id,
                "semester_id": semester_id,
            })
            _, err = supabase_rest_insert("class_schedules", payload)
            if err:
                return None, err
        applied += 1

    return {"success": True, "applied": applied, "count": applied}, None


def _delete_schedules_via_rest(
    grade_level: str,
    semester_code: str,
    strand_code: str,
) -> tuple[dict | None, str | None]:
    """Delete class_schedules when delete_scheduler_schedules RPC is not deployed."""
    rows, error = supabase_rest_get(
        "class_schedules",
        "select=id,"
        "subjects(semester_code),"
        "sections(grade_level,strands(code)),"
        "semesters(is_current)"
        "&is_active=eq.true",
        use_secret=True,
        timeout=25,
    )
    if error:
        return None, error

    strand_upper = str(strand_code or "").upper()
    target_ids: list[str] = []
    for row in rows or []:
        section = row.get("sections") or {}
        strand = (section.get("strands") or {}).get("code") or ""
        subject = row.get("subjects") or {}
        semester = row.get("semesters") or {}
        grade = section.get("grade_level") or ""
        sub_sem = subject.get("semester_code") or "1st"
        if grade != grade_level:
            continue
        if str(strand).upper() != strand_upper:
            continue
        if sub_sem != semester_code:
            continue
        if semester and semester.get("is_current") is False:
            continue
        schedule_id = row.get("id")
        if schedule_id:
            target_ids.append(str(schedule_id))

    if not target_ids:
        return {"success": True, "deleted": 0}, None

    ids_filter = ",".join(target_ids)
    enrolled, enroll_err = supabase_rest_get(
        "enrollment_subjects",
        f"select=id&class_schedule_id=in.({ids_filter})",
        use_secret=True,
        timeout=15,
    )
    if enroll_err:
        return None, enroll_err
    if enrolled:
        return {
            "success": False,
            "error": f"{len(enrolled)} enrollment link(s) exist — cannot delete.",
            "enrolled_links": len(enrolled),
        }, None

    deleted = 0
    for schedule_id in target_ids:
        _, del_err = supabase_rest_delete("class_schedules", f"id=eq.{schedule_id}")
        if del_err:
            return None, del_err
        deleted += 1

    return {"success": True, "deleted": deleted}, None


def _section_letter_from_name(section_name: str, strand: str, grade_level: str) -> str:
    parts = str(section_name or "").split("-", 1)
    slot = parts[1].strip() if len(parts) > 1 else "A"
    if slot in ("A", "B"):
        return slot
    try:
        from enrollment_curriculum import section_slot_name

        for letter in ("A", "B"):
            if section_slot_name(strand, grade_level, letter) == slot:
                return letter
    except Exception:
        pass
    return slot[:1].upper() if slot else "A"


def _load_local_draft_schedules(
    grade_level: str,
    semester_code: str,
    *,
    exclude_strand: str | None = None,
    exclude_grade_level: str | None = None,
) -> list:
    if not GENERATED_SCHEDULES_FILE.exists():
        return []
    try:
        payload = json.loads(GENERATED_SCHEDULES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    saved_semester = payload.get("semesterCode") or "1st"
    if saved_semester != semester_code:
        return []
    schedules = payload.get("schedules") or []
    if not isinstance(schedules, list):
        return []
    if exclude_strand:
        exclude = str(exclude_strand).upper()
        exclude_grade = str(exclude_grade_level or grade_level)
        schedules = [
            item for item in schedules
            if not (
                str(item.get("strand") or "").upper() == exclude
                and str(item.get("gradeLevel") or exclude_grade) == exclude_grade
            )
        ]
    return schedules


def _draft_schedules_result(schedules, source):
    from scheduling.schedule_dedupe import dedupe_schedule_entries
    return dedupe_schedule_entries(schedules or []), source


def load_draft_schedules(
    grade_level: str,
    semester_code: str,
    *,
    exclude_strand: str | None = None,
    exclude_grade_level: str | None = None,
) -> tuple[list, str]:
    """Load saved schedules for conflict checks.

    Returns (schedules, source) where source is ``database`` or ``local``.
    """
    exclude_grade = exclude_grade_level or (grade_level if exclude_strand else None)
    if supabase_configured():
        rpc_payload = {
            "p_grade_level": grade_level,
            "p_semester_code": semester_code,
        }
        if exclude_strand:
            rpc_payload["p_exclude_strand"] = str(exclude_strand).upper()
        if exclude_grade:
            rpc_payload["p_exclude_grade_level"] = str(exclude_grade)
        result, error = supabase_rpc(
            "get_scheduler_existing_schedules",
            rpc_payload,
            timeout=15,
        )
        if error and _is_rpc_missing_error(error) and exclude_strand and exclude_grade:
            # Live DB may still have the 3-parameter RPC (no grade-level exclude).
            rest_schedules = _load_draft_schedules_from_rest(
                semester_code,
                exclude_strand=exclude_strand,
                exclude_grade_level=exclude_grade,
            )
            if rest_schedules:
                return _draft_schedules_result(rest_schedules, "database")
        if not error:
            schedules = normalize_rpc_json_array(result)
            if schedules:
                return _draft_schedules_result(schedules, "database")
            local = _load_local_draft_schedules(
                grade_level,
                semester_code,
                exclude_strand=exclude_strand,
                exclude_grade_level=exclude_grade,
            )
            if local:
                return _draft_schedules_result(local, "local")
            _clear_local_schedule_cache(semester_code)
            return _draft_schedules_result([], "database")
        rest_schedules = _load_draft_schedules_from_rest(
            semester_code,
            exclude_strand=exclude_strand,
            exclude_grade_level=exclude_grade,
        )
        if rest_schedules:
            return _draft_schedules_result(rest_schedules, "database")
        local = _load_local_draft_schedules(
            grade_level,
            semester_code,
            exclude_strand=exclude_strand,
            exclude_grade_level=exclude_grade,
        )
        return _draft_schedules_result(local, "local" if local else "database")

    local = _load_local_draft_schedules(
        grade_level,
        semester_code,
        exclude_strand=exclude_strand,
        exclude_grade_level=exclude_grade_level or (grade_level if exclude_strand else None),
    )
    return _draft_schedules_result(local, "local" if local else "database")


def _clear_local_schedule_cache(semester_code: str) -> None:
    """Drop stale local draft file when Supabase has no schedules for this term."""
    if not GENERATED_SCHEDULES_FILE.exists():
        return
    try:
        payload = json.loads(GENERATED_SCHEDULES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if payload.get("semesterCode") != semester_code:
        return
    GENERATED_SCHEDULES_FILE.write_text(
        json.dumps(
            {
                "gradeLevel": payload.get("gradeLevel") or "Grade 12",
                "semesterCode": semester_code,
                "schedules": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _remove_from_local_schedule_cache(
    grade_level: str,
    semester_code: str,
    strand_code: str,
) -> None:
    if not GENERATED_SCHEDULES_FILE.exists():
        return
    try:
        payload = json.loads(GENERATED_SCHEDULES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if payload.get("semesterCode") != semester_code:
        return
    strand = str(strand_code or "").upper()
    grade = str(grade_level)
    kept = [
        item for item in (payload.get("schedules") or [])
        if not (
            str(item.get("strand") or "").upper() == strand
            and str(item.get("gradeLevel") or grade) == grade
        )
    ]
    payload["schedules"] = kept
    GENERATED_SCHEDULES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def handle_scheduling_draft(handler):
    params = parse_qs(urlparse(handler.path).query)
    grade_level = (params.get("gradeLevel") or params.get("grade_level") or ["Grade 12"])[0]
    semester_code = (params.get("semesterCode") or params.get("semester_code") or ["1st"])[0]
    schedules, source = load_draft_schedules(grade_level, semester_code)
    json_response(handler, 200, {
        "success": True,
        "gradeLevel": grade_level,
        "semesterCode": semester_code,
        "count": len(schedules),
        "schedules": schedules,
        "source": source,
    })


from scheduling.schedule_dedupe import (
    dedupe_schedule_entries,
    exclude_regenerating_strand_schedules,
    merge_existing_schedules,
    merge_schedules_replacing_grade_strand,
)


def handle_scheduling_generate_strand(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    strand = body.get("strand") or body.get("strandCode")
    if not strand:
        json_response(handler, 400, {"success": False, "error": "strand is required"})
        return

    grade_level = body.get("gradeLevel") or body.get("grade_level") or "Grade 12"
    semester_code = body.get("semesterCode") or body.get("semester_code") or "1st"
    strand_upper = str(strand).upper()
    saved_schedules, _ = load_draft_schedules(
        grade_level,
        semester_code,
        exclude_strand=strand_upper,
        exclude_grade_level=grade_level,
    )
    body_existing = body.get("existingSchedules") or body.get("existing_schedules") or []
    existing_schedules = merge_existing_schedules(
        saved_schedules,
        body_existing,
        exclude_strand=strand_upper,
        exclude_grade_level=grade_level,
    )
    existing_schedules, _ = exclude_regenerating_strand_schedules(
        existing_schedules,
        strand=strand_upper,
        grade_level=grade_level,
    )

    service = get_scheduler_service()
    try:
        result = service.generate_strand(
            strand=strand,
            grade_level=grade_level,
            semester_code=semester_code,
            sections_per_strand=int(body.get("sectionsPerStrand") or body.get("sections_per_strand") or 2),
            rooms=body.get("rooms"),
            existing_schedules=existing_schedules,
            use_ai=body.get("useAi", True),
            use_cloud_ai=body.get("useCloudAi", True),
            allow_local_fallback=body.get("allowLocalFallback", True),
        )
    except Exception as err:
        json_response(handler, 500, {
            "success": False,
            "error": f"Schedule generation crashed: {err}",
            "hint": "Restart the admin server (python server.py) and try again.",
        })
        return
    status = 200 if result.get("success") else 422
    json_response(handler, status, result)


def handle_scheduling_validate(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    schedules = _stamp_schedule_grade_level(
        body.get("schedules") or [],
        body.get("gradeLevel") or body.get("grade_level") or "Grade 12",
    )
    if not isinstance(schedules, list):
        json_response(handler, 400, {"success": False, "error": "schedules must be an array"})
        return

    grade_level = body.get("gradeLevel") or body.get("grade_level") or "Grade 12"
    semester_code = body.get("semesterCode") or body.get("semester_code") or "1st"
    merge_with_saved = body.get("mergeWithSaved", True)

    if merge_with_saved:
        saved, _ = load_draft_schedules(grade_level, semester_code)
        incoming_strands = {
            str(item.get("strand") or "").upper()
            for item in schedules
            if item.get("strand")
        }
        schedules = merge_schedules_replacing_grade_strand(
            saved,
            schedules,
            grade_level=grade_level,
            replace_strands=incoming_strands,
        )

    schedules, _, sanitize_error = _prepare_schedules_for_save(schedules)
    if sanitize_error:
        json_response(handler, 422, {
            "success": False,
            "error": sanitize_error,
        })
        return

    service = get_scheduler_service()
    ctx = service.get_scheduling_context(
        grade_level=grade_level,
        semester_code=semester_code,
    )
    result = service.validate_payload(schedules, scheduling_context=ctx)
    status = 200 if result.get("success") else 422
    json_response(handler, status, result)


def handle_scheduling_apply(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    schedules = _stamp_schedule_grade_level(
        body.get("schedules") or [],
        body.get("gradeLevel") or body.get("grade_level") or "Grade 12",
    )
    schedules, sanitize_meta, sanitize_error = _prepare_schedules_for_save(
        schedules,
        reject_invalid=True,
    )
    if sanitize_error:
        json_response(handler, 422, {
            "success": False,
            "error": sanitize_error,
            "sanitize": sanitize_meta,
        })
        return
    if not schedules:
        json_response(handler, 400, {"success": False, "error": "schedules array is required"})
        return

    grade_level = body.get("gradeLevel") or body.get("grade_level") or "Grade 12"
    semester_code = body.get("semesterCode") or body.get("semester_code") or "1st"

    service = get_scheduler_service()
    ctx = service.get_scheduling_context(
        grade_level=grade_level,
        semester_code=semester_code,
    )

    saved, _ = load_draft_schedules(grade_level, semester_code)
    incoming_strands = {
        str(item.get("strand") or "").upper()
        for item in schedules
        if item.get("strand")
    }

    if supabase_configured() and incoming_strands:
        removed = _deactivate_invalid_section_schedules(
            grade_level,
            semester_code,
            incoming_strands,
        )
        if removed:
            sanitize_meta["deactivated_invalid"] = removed

    merged_schedules, merge_meta, merge_error = _prepare_schedules_for_save(
        merge_schedules_replacing_grade_strand(
            saved,
            schedules,
            grade_level=grade_level,
            replace_strands=incoming_strands,
        ),
    )
    if merge_error:
        json_response(handler, 422, {
            "success": False,
            "error": merge_error,
            "sanitize": merge_meta,
        })
        return

    validation = service.validate_payload(merged_schedules, scheduling_context=ctx)
    if not validation.get("success"):
        json_response(handler, 422, {
            "success": False,
            "error": "Cannot apply schedule with conflicts.",
            "validation": validation.get("validation"),
            "hint": "Each professor may teach at most 3 subjects per semester (G11+G12 combined).",
        })
        return

    record = {
        "appliedAt": datetime.now().isoformat(),
        "gradeLevel": grade_level,
        "semesterCode": semester_code,
        "schedules": validation.get("schedules") or merged_schedules,
        "source": body.get("source") or "manual",
    }

    if supabase_configured():
        result, error = supabase_rpc("apply_generated_schedules", {
            "p_payload": record,
        }, timeout=20)
        if error and _is_updated_at_schema_error(error):
            result, error = _apply_schedules_via_rest(record)
            if not error:
                result = {**(result or {}), "source": "rest_fallback"}
        if error:
            hint = "Run supabase/schedule-sync.sql in Supabase SQL Editor first."
            if _is_updated_at_schema_error(error):
                hint = (
                    "Run supabase/fix-class-schedules-save.sql in Supabase SQL Editor, "
                    "then retry. (Admin server can also auto-fallback — restart server.py if needed.)"
                )
            json_response(handler, 500, {
                "success": False,
                "error": parse_supabase_error(error) or "Failed to save schedules to Supabase.",
                "hint": hint,
            })
            return
        GENERATED_SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_SCHEDULES_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
        json_response(handler, 200, {
            "success": True,
            "source": "supabase",
            "count": len(record["schedules"]),
            "message": "Schedule saved. Students in this strand can now view it.",
            **(result or {}),
        })
        return

    GENERATED_SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_SCHEDULES_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    json_response(handler, 200, {
        "success": True,
        "source": "local_file",
        "path": str(GENERATED_SCHEDULES_FILE.relative_to(ROOT)),
        "count": len(record["schedules"]),
    })


def handle_scheduling_delete(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    grade_level = body.get("gradeLevel") or body.get("grade_level")
    semester_code = body.get("semesterCode") or body.get("semester_code") or "1st"
    strand_code = body.get("strandCode") or body.get("strand") or body.get("strand_code")

    if not grade_level:
        json_response(handler, 400, {"success": False, "error": "gradeLevel is required"})
        return
    if not strand_code:
        json_response(handler, 400, {"success": False, "error": "strandCode is required"})
        return

    if not supabase_configured():
        _remove_from_local_schedule_cache(grade_level, semester_code, str(strand_code))
        json_response(handler, 200, {
            "success": True,
            "deleted": 0,
            "source": "local",
            "message": "Removed from local cache. Connect Supabase to delete database rows.",
        })
        return

    rpc_args = {
        "p_grade_level": grade_level,
        "p_semester_code": semester_code,
        "p_strand_code": str(strand_code).upper(),
    }
    result, error = _delete_schedules_via_rest(
        grade_level,
        semester_code,
        str(strand_code),
    )
    delete_source = "rest"
    if error:
        rpc_result, rpc_error = supabase_rpc("delete_scheduler_schedules", rpc_args, timeout=20)
        if not rpc_error:
            result, error = rpc_result, None
            delete_source = "rpc"
        elif _is_rpc_missing_error(rpc_error):
            pass  # keep REST error
        else:
            result, error = rpc_result, rpc_error
            delete_source = "rpc"
    if error:
        json_response(handler, 500, {
            "success": False,
            "error": parse_supabase_error(error) or "Failed to delete schedules.",
            "hint": "Run supabase/schedule-sync.sql in Supabase SQL Editor first.",
        })
        return

    if isinstance(result, dict) and not result.get("success", True):
        json_response(handler, 422, result)
        return

    _remove_from_local_schedule_cache(grade_level, semester_code, str(strand_code))
    deleted = 0
    if isinstance(result, dict):
        deleted = int(result.get("deleted") or 0)
    json_response(handler, 200, {
        "success": True,
        "deleted": deleted,
        "source": delete_source,
        "gradeLevel": grade_level,
        "semesterCode": semester_code,
        "strandCode": str(strand_code).upper(),
        "message": f"Deleted {deleted} schedule row(s) for {strand_code} · {grade_level} · {semester_code} sem.",
    })


def handle_email_test(handler):
    if handler.command == "POST":
        body = read_json_body(handler)
        test_to = (body.get("to") or "").strip().lower()
    else:
        test_to = ""
    test_to = test_to or ADMIN_EMAIL or GMAIL_USER
    if not test_to:
        json_response(handler, 400, {
            "success": False,
            "error": "No recipient. Set ADMIN_EMAIL in .env or pass {\"to\": \"email@example.com\"}.",
        })
        return

    ok, err = send_email(
        test_to,
        f"Test Email — {SCHOOL_NAME}",
        f"""
        <div style="font-family:Arial,sans-serif;max-width:640px;">
          <h2 style="color:#1a3a6b;">Gmail Test Successful</h2>
          <p>This is a test email from the {SCHOOL_NAME} enrollment system.</p>
          <p>If you received this, Gmail SMTP is working correctly.</p>
        </div>
        """,
    )
    if ok:
        json_response(handler, 200, {"success": True, "sentTo": test_to})
    else:
        json_response(handler, 500, {"success": False, "error": err, "sentTo": test_to})


from enrollment_curriculum import (
    ENROLLMENT_SUBJECTS_DEMO,
    REQUIRED_SUBJECTS_PER_TERM,
    filter_demo_subjects_by_strand,
)


def handle_enrollment_offerings(handler):
    query = handler.path.split("?", 1)[1] if "?" in handler.path else ""
    student_id = ""
    strand_code = DEFAULT_STRAND_CODE
    grade_level = "Grade 12"
    semester_code = "1st"
    for part in query.split("&"):
        if part.startswith("studentId="):
            student_id = unquote(part.split("=", 1)[1])
        elif part.startswith("strandCode="):
            strand_code = unquote(part.split("=", 1)[1])
        elif part.startswith("gradeLevel="):
            grade_level = unquote(part.split("=", 1)[1])
        elif part.startswith("semesterCode="):
            semester_code = unquote(part.split("=", 1)[1])

    if not student_id:
        json_response(handler, 400, {"success": False, "error": "studentId is required"})
        return

    if supabase_configured():
        result, error = supabase_rpc("get_enrollment_offerings", {
            "p_student_id": student_id.strip().upper(),
        }, timeout=10)
        if error:
            json_response(handler, 500, {
                "success": False,
                "error": "Failed to load subject offerings.",
                "details": parse_supabase_error(error),
            })
            return
        offerings = result if isinstance(result, list) else []
        json_response(handler, 200, {
            "success": True,
            "data": offerings,
            "source": "supabase",
        })
        return

    json_response(handler, 200, {
        "success": True,
        "data": filter_demo_subjects_by_strand(strand_code, grade_level, semester_code),
        "source": "demo",
    })


def handle_enrollment_submit(handler):
    try:
        body = read_json_body(handler)
    except json.JSONDecodeError:
        json_response(handler, 400, {"success": False, "error": "Invalid request body"})
        return

    student_id = (body.get("studentId") or "").strip().upper()
    subjects = body.get("subjects") or []

    if not student_id:
        json_response(handler, 400, {"success": False, "error": "studentId is required"})
        return
    if not isinstance(subjects, list) or not subjects:
        json_response(handler, 400, {"success": False, "error": "Select at least one subject"})
        return

    if supabase_configured():
        result, error = supabase_rpc("submit_student_enrollment", {
            "p_student_id": student_id,
            "p_subjects": subjects,
        }, timeout=15)
        if error:
            err_text = parse_supabase_error(error) or "Enrollment validation failed."
            hint = None
            if any(token in err_text.lower() for token in ("strand", "subject", "schedule", "enrollment is")):
                hint = "You can only enroll in core subjects and subjects for your assigned strand."
            elif "does not exist" in err_text.lower() or "column" in err_text.lower():
                hint = "Run supabase/enrollment-workflow.sql in Supabase SQL Editor, then try again."
            payload = {"success": False, "error": err_text}
            if hint:
                payload["hint"] = hint
            json_response(handler, 400, payload)
            return
        json_response(handler, 200, {"success": True, **(result or {})})
        return

    json_response(handler, 503, {
        "success": False,
        "error": "Supabase is not configured. Subject enrollment requires database connection.",
    })


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])

        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/login.html")
            self.end_headers()
            return

        if path.startswith("/student/") or path in ("/enroll.html", "/payment-success.html"):
            self.send_error(404, "Student portal is on ENROLLSYSTEM (port 8000)")
            return

        if path == "/js/config.js" or path.endswith("/js/config.js"):
            content = build_config_js().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/admission/file":
            handle_admission_file(self)
            return

        if path == "/api/admission/pending":
            handle_get_pending_admissions(self)
            return

        if path == "/api/admission/history":
            handle_get_admission_history(self)
            return

        if path == "/api/admission/detail" or path.startswith("/api/admission/detail/"):
            handle_get_admission_detail(self)
            return

        if path == "/api/admission/cor-preview":
            handle_preview_registration_certificate(self)
            return

        if (
            path.startswith("/uploads/registration-forms/")
            and path.endswith("_Registration_Certificate.pdf")
        ):
            filename = path.rsplit("/", 1)[-1]
            student_id = filename.replace("_Registration_Certificate.pdf", "")
            if handle_serve_registration_certificate(self, student_id):
                return

        if path == "/api/student/registration-certificate":
            query = parse_qs(urlparse(self.path).query)
            student_id = (query.get("id") or [""])[0].strip()
            if student_id and handle_serve_registration_certificate(self, student_id):
                return
            json_response(self, 404, {"success": False, "error": "Registration certificate not found"})
            return

        if path == "/api/subject-enrollment/pending":
            handle_get_pending_subject_enrollments(self)
            return

        if path == "/api/subject-enrollment/history":
            handle_get_subject_enrollment_history(self)
            return

        if path == "/api/subject-enrollment/detail" or path.startswith("/api/subject-enrollment/detail/"):
            handle_get_subject_enrollment_detail(self)
            return

        if path == "/api/term/enrollment-period":
            handle_get_enrollment_period(self)
            return

        if path == "/api/grades/students":
            handle_get_students_for_grading(self)
            return

        if path == "/api/grades/sheet":
            handle_get_grades_sheet(self)
            return

        if path == "/api/payments/enrollment":
            handle_list_enrollment_payments(self)
            return

        if path == "/api/faculty/dashboard":
            handle_faculty_dashboard(self)
            return

        if path == "/api/strands":
            handle_list_strands(self)
            return

        if path == "/api/teachers/detail":
            handle_get_teacher_detail(self)
            return

        if path == "/api/teachers":
            handle_list_teachers(self)
            return

        if path == "/api/rooms":
            handle_list_rooms(self)
            return

        if path == "/api/section-quotas":
            handle_list_section_quotas(self)
            return

        if path == "/api/students":
            handle_list_students_api(self)
            return

        if path == "/api/subjects":
            handle_list_subjects(self)
            return

        if path == "/api/health":
            handle_health_check(self)
            return

        if path == "/api/setup/seed-faculty":
            handle_seed_faculty(self)
            return

        if path == "/api/email/test":
            handle_email_test(self)
            return

        if path == "/api/scheduling/config":
            handle_scheduling_config(self)
            return

        if path.startswith("/api/scheduling/context"):
            handle_scheduling_context(self)
            return

        if path == "/api/scheduling/draft":
            handle_scheduling_draft(self)
            return

        super().do_GET()

    def do_POST(self):
        path = unquote(self.path.split("?", 1)[0])

        if path.startswith("/api/admission/submit") or path.startswith("/api/auth/student"):
            self.send_error(404, "Student portal is on ENROLLSYSTEM (port 8000)")
            return

        if path == "/api/admission/review":
            handle_admission_review(self)
            return

        if path == "/api/admission/resend-credentials":
            handle_resend_admission_credentials(self)
            return
        if path == "/api/admission/resend-cor":
            handle_resend_registration_certificate(self)
            return

        if path == "/api/subject-enrollment/review":
            handle_subject_enrollment_review(self)
            return

        if path == "/api/term/enrollment-period":
            handle_set_enrollment_period(self)
            return

        if path == "/api/term/switch-semester":
            handle_switch_enrollment_semester(self)
            return

        if path == "/api/grades/save":
            handle_save_grades(self)
            return

        if path == "/api/payments/approve":
            handle_approve_enrollment_payment(self)
            return

        if path == "/api/auth/faculty":
            handle_faculty_login(self)
            return

        if path == "/api/teachers":
            handle_save_teacher(self)
            return

        if path == "/api/rooms":
            handle_save_room(self)
            return

        if path == "/api/section-quotas":
            handle_update_section_quota(self)
            return

        if path == "/api/students":
            handle_save_student_api(self)
            return

        if path == "/api/subjects":
            handle_save_subject(self)
            return

        if path == "/api/scheduling/generate":
            handle_scheduling_generate(self)
            return

        if path == "/api/scheduling/generate-strand":
            handle_scheduling_generate_strand(self)
            return

        if path == "/api/scheduling/validate":
            handle_scheduling_validate(self)
            return

        if path == "/api/scheduling/apply":
            handle_scheduling_apply(self)
            return

        if path == "/api/scheduling/publish":
            handle_scheduling_publish(self)
            return

        if path == "/api/scheduling/delete":
            handle_scheduling_delete(self)
            return

        self.send_error(404, "Not Found")


def open_admin_portal(url, open_path="/login.html"):
    if os.environ.get("EMS_NO_BROWSER", "").strip().lower() in ("1", "true", "yes"):
        return
    if not open_path.startswith("/"):
        open_path = "/" + open_path
    try:
        webbrowser.open(f"{url}{open_path}")
    except Exception:
        pass


def admin_server_responding(port):
    """True only when the admin API health endpoint responds (not just any HTTP server)."""
    try:
        req = Request(f"http://127.0.0.1:{port}/api/health")
        with urlopen(req, timeout=3) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("success") is True and data.get("portal") == "admin"
    except Exception:
        return False


def find_port_owner_pid(port):
    import subprocess

    try:
        output = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return None

    suffix = f":{port}"
    for line in output.splitlines():
        if "LISTENING" not in line or suffix not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        if not local_addr.endswith(suffix):
            continue
        try:
            return int(parts[-1])
        except ValueError:
            continue
    return None


def port_in_use_error(exc):
    if getattr(exc, "winerror", None) == 10048:
        return True
    if getattr(exc, "errno", None) in (98, 48, 10048):
        return True
    return "already in use" in str(exc).lower() or "10048" in str(exc)


def print_admin_banner(url, *, already_running=False, port_note=None):
    print("=" * 50)
    print("  Geranova EMS — ADMIN PORTAL ONLY")
    print("=" * 50)
    if port_note:
        print(f"\n  {port_note}")
    if already_running:
        print(f"\n  Admin server is already running at: {url}")
        print("\n  That terminal is serving the site — this window can close.")
        print("  To RESTART fresh, stop the other terminal (Ctrl+C), then run:")
        print("    python server.py")
    else:
        supabase_status = "Connected" if SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY else "Not configured (.env missing URL or key)"
        gmail_status = "Configured" if gmail_configured() else "Not configured (add GMAIL_USER + GMAIL_APP_PASSWORD to .env)"
        if gmail_configured():
            print(f"  Gmail sender:      {mask_email(GMAIL_USER)}")
            print(f"  Admin inbox:       {mask_email(ADMIN_EMAIL)}")
        print(f"\n  Server running at: {url}")
        print(f"\n  Supabase:          {supabase_status}")
        print(f"  Gmail:             {gmail_status}")
        if not already_running:
            print(f"  Applicant email:   {APPLICANT_EMAIL_VERSION} (full enrollment summary)")
            from shared.services.registration_form import COR_PDF_LAYOUT_VERSION
            print(f"  Registration cert: PDF attachment only (Registration_Certificate_*.pdf)")
            print(f"  COR PDF layout:    {COR_PDF_LAYOUT_VERSION} (open header, PUP-style)")
            print(f"  Scheduler:         Google OR-Tools (CP-SAT)")
    print(f"  Admin login:       {url}/login.html")
    print(f"  Dashboard:         {url}/admin/dashboard.html")
    print(f"  Auto-Schedule:     {url}/admin/auto-schedule.html")
    print(f"  Review Apps:       {url}/admin/enrollment-request.html")
    if not already_running:
        if SUPABASE_URL and SUPABASE_SECRET_KEY:
            seeded, seed_msg = seed_default_faculty()
            if seeded:
                print(f"  Faculty seed:        {DEFAULT_FACULTY['faculty_id']} saved to Supabase")
            else:
                print(f"  Faculty seed:        Failed ({seed_msg})")
        elif SUPABASE_URL:
            print("\n  Add SUPABASE_SECRET_KEY to .env to auto-save faculty account on startup.")
        if not SUPABASE_URL:
            print("\n  Add SUPABASE_URL to .env to enable Supabase.")
        if not GMAIL_USER:
            print("  Add GMAIL_USER and GMAIL_APP_PASSWORD to .env for email notifications.")
        print("\n  --- ADMIN ACCOUNT ---")
        print("  Admin ID:    FAC-2026-0001")
        print("  Password:    faculty123")
        print("\n  Press Ctrl+C to stop the server.")
    print("\n" + "=" * 50)


def admin_port_candidates(preferred_port, count=10):
    """Return ports to try; skip 8003 (faculty portal)."""
    reserved = {8003}
    ports = []
    port = preferred_port
    while len(ports) < count:
        if port not in reserved:
            ports.append(port)
        port += 1
    return ports


def main():
    os.chdir(ROOT)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    preferred_port = PORT
    httpd = None
    port_note = None
    chosen_port = None

    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        daemon_threads = True
        allow_reuse_address = False

    for port in admin_port_candidates(preferred_port):
        try:
            httpd = ThreadingHTTPServer(("", port), Handler)
            chosen_port = port
            break
        except OSError as exc:
            if not port_in_use_error(exc):
                raise
            if admin_server_responding(port):
                url = f"http://localhost:{port}"
                print_admin_banner(url, already_running=True)
                open_path = os.environ.get("EMS_OPEN_URL", "/login.html")
                open_admin_portal(url, open_path)
                return
            owner = find_port_owner_pid(port)
            if port == preferred_port:
                owner = find_port_owner_pid(port)
                owner_text = f" (PID {owner})" if owner else ""
                port_note = (
                    f"Port {preferred_port} was blocked{owner_text}. "
                    f"Close the other terminal (Ctrl+C) and try again."
                )
            continue

    if httpd is None or chosen_port is None:
        raise RuntimeError(
            f"Could not start admin server near port {preferred_port}.\n"
            f"  Close other terminals using that port, then run: python server.py"
        )

    if chosen_port != preferred_port and port_note:
        port_note = port_note.replace(
            "Trying the next available port.",
            f"Started on port {chosen_port} instead.",
        )

    url = f"http://localhost:{chosen_port}"
    print_admin_banner(url, port_note=port_note)
    open_path = os.environ.get("EMS_OPEN_URL", "/login.html")
    open_admin_portal(url, open_path)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
