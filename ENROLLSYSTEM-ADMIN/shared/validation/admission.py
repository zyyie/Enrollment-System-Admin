"""Admission enrollment field and file validation."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

MIN_SHS_AGE = 14
MAX_SHS_AGE = 25

MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_PAYMENT_PROOF_BYTES = 10 * 1024 * 1024

PROFILE_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
PAYMENT_PROOF_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONTACT_RE = re.compile(r"^09\d{9}$")
VALID_GENDERS = {"male", "female"}


def normalize_contact_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("639") and len(digits) == 12:
        return "0" + digits[2:]
    if digits.startswith("63") and len(digits) == 12:
        return "0" + digits[2:]
    return digits


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def is_valid_contact_number(value: str) -> bool:
    return bool(CONTACT_RE.match(normalize_contact_number(value)))


def is_valid_gender(value: str) -> bool:
    return (value or "").strip().lower() in VALID_GENDERS


def validate_birthdate_age(value: str, *, min_age: int = MIN_SHS_AGE, max_age: int = MAX_SHS_AGE) -> str | None:
    text = (value or "").strip()
    if not text:
        return "Birthdate is required."

    try:
        parts = text.split("-")
        if len(parts) != 3:
            raise ValueError("invalid format")
        year, month, day = (int(part) for part in parts)
        born = date(year, month, day)
    except (TypeError, ValueError):
        return "Please enter a valid birthdate."

    today = date.today()
    if born > today:
        return "Birthdate cannot be in the future."

    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < min_age:
        return f"You must be at least {min_age} years old to enroll in Enrollment Management System."
    if age > max_age:
        return (
            f"Birthdate indicates age over {max_age}. "
            "Please contact the registrar if this is incorrect."
        )
    return None


def _file_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _validate_uploaded_file(
    info: dict,
    *,
    label: str,
    allowed_extensions: set[str],
    max_bytes: int,
) -> str | None:
    if not info or not info.get("content"):
        return f"{label} is required."

    content = info["content"]
    if len(content) > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        return f"{label} must be {max_mb} MB or smaller."

    ext = _file_extension(info.get("filename") or "")
    if ext not in allowed_extensions:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in allowed_extensions))
        return f"{label} must be one of: {allowed.upper()}."

    return None


def validate_admission_fields(fields: dict) -> str | None:
    email = (fields.get("email") or "").strip()
    if not is_valid_email(email):
        return "Please enter a valid email address."

    contact = fields.get("contactNumber") or ""
    if not is_valid_contact_number(contact):
        return "Contact number must be 11 digits starting with 09 (example: 09171234567)."

    gender = fields.get("gender") or ""
    if not is_valid_gender(gender):
        return "Please select your gender."

    birthdate_error = validate_birthdate_age(fields.get("birthdate") or "")
    if birthdate_error:
        return birthdate_error

    return None


def validate_admission_files(files: dict, *, payment_mode: str = "") -> str | None:
    profile_keys = ("profile_upload", "profile_camera", "profile_photo")
    profile_info = next((files.get(key) for key in profile_keys if files.get(key)), None)
    profile_error = _validate_uploaded_file(
        profile_info,
        label="Profile photo",
        allowed_extensions=PROFILE_PHOTO_EXTENSIONS,
        max_bytes=MAX_PROFILE_PHOTO_BYTES,
    )
    if profile_error:
        return profile_error

    for key in ("form_138", "form_137", "good_moral", "birth_certificate", "high_school_diploma"):
        doc_error = _validate_uploaded_file(
            files.get(key),
            label="Document upload",
            allowed_extensions=DOCUMENT_EXTENSIONS,
            max_bytes=MAX_DOCUMENT_BYTES,
        )
        if doc_error:
            return doc_error

    mode = (payment_mode or "").strip().lower()
    if mode == "gcash":
        proof_error = _validate_uploaded_file(
            files.get("gcash_proof"),
            label="GCash payment receipt",
            allowed_extensions=PAYMENT_PROOF_EXTENSIONS,
            max_bytes=MAX_PAYMENT_PROOF_BYTES,
        )
        if proof_error:
            return proof_error

    if mode == "bank":
        proof_error = _validate_uploaded_file(
            files.get("bank_proof"),
            label="Bank payment receipt",
            allowed_extensions=PAYMENT_PROOF_EXTENSIONS,
            max_bytes=MAX_PAYMENT_PROOF_BYTES,
        )
        if proof_error:
            return proof_error

    return None
