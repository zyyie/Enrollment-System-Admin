"""Display names for EMS — strip legacy Geranova / SHS branding."""

import re

DEFAULT_SCHOOL_NAME = "Enrollment Management System"

_LEGACY_MARKERS = re.compile(r"(?i)geranova|senior\s+high\s+school|\bshs\b")


def display_school_name(text: str | None) -> str:
    if text is None or not str(text).strip():
        return DEFAULT_SCHOOL_NAME
    cleaned = str(text).strip()
    cleaned = re.sub(r"(?i)\bgeranova\b\s*", "", cleaned)
    cleaned = re.sub(r"(?i)\bsenior\s+high\s+school\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,-–—")
    if not cleaned or _LEGACY_MARKERS.search(str(text)):
        return DEFAULT_SCHOOL_NAME
    return cleaned


def email_brand_name(text: str | None = None) -> str:
    _ = text
    return DEFAULT_SCHOOL_NAME


def scrub_legacy_brand_text(text: str) -> str:
    if not text:
        return text
    out = str(text)
    out = re.sub(r"(?i)\bgeranova\b\s*", "", out)
    out = re.sub(r"(?i)\bsenior\s+high\s+school\b", DEFAULT_SCHOOL_NAME, out)
    out = re.sub(r"(?i)geranova\s+enrollment\s+management\s+system", DEFAULT_SCHOOL_NAME, out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    dup = re.escape(DEFAULT_SCHOOL_NAME)
    out = re.sub(rf"({dup}\s*){{2,}}", DEFAULT_SCHOOL_NAME, out, flags=re.I)
    return out


strip_geranova_brand = display_school_name
