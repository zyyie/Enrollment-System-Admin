"""Deduplicate schedule rows when merging DB drafts with client state."""

from __future__ import annotations


def normalize_section_letter(item: dict) -> str | None:
    """Map virtue names to slot A/B for the row's strand. Returns None if invalid."""
    section = str(item.get("section") or "").strip().upper()
    grade = str(item.get("gradeLevel") or item.get("grade_level") or "").strip()
    strand = str(item.get("strand") or "").strip().upper()
    if not strand or not grade:
        return None
    if section in ("A", "B"):
        return section
    try:
        from enrollment_curriculum import section_slot_name

        for letter in ("A", "B"):
            if section_slot_name(strand, grade, letter).upper() == section:
                return letter
    except Exception:
        pass
    return None


def normalize_schedule_entry(item: dict) -> dict:
    """Return a copy with normalized grade/strand/section/subject fields."""
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    normalized["gradeLevel"] = str(
        item.get("gradeLevel") or item.get("grade_level") or ""
    ).strip()
    normalized["strand"] = str(item.get("strand") or "").upper()
    normalized["section"] = normalize_section_letter(item)
    subject = str(item.get("subject_code") or item.get("subject_name") or "").upper()
    if subject:
        normalized["subject_code"] = subject
    return normalized


def schedule_entry_key(item: dict) -> tuple[str, str, str, str] | None:
    grade = str(item.get("gradeLevel") or item.get("grade_level") or "").upper()
    strand = str(item.get("strand") or "").upper()
    section = normalize_section_letter(item)
    subject = str(item.get("subject_code") or item.get("subject_name") or "").upper()
    if not strand or not subject or not section:
        return None
    return grade, strand, section, subject


def filter_canonical_schedule_entries(schedules: list) -> tuple[list, int]:
    """Keep only rows whose section belongs to the strand's A/B virtue names."""
    kept: list = []
    dropped = 0
    for item in schedules or []:
        if not isinstance(item, dict):
            continue
        if normalize_section_letter(item) is None:
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped


def sanitize_schedules_for_save(schedules: list) -> tuple[list, dict[str, int]]:
    """Normalize, drop invalid sections, and dedupe before save/load."""
    raw_count = len(schedules or [])
    canonical, dropped_invalid = filter_canonical_schedule_entries(schedules)
    seen: set[tuple[str, str, str, str]] = set()
    cleaned: list = []
    dropped_duplicates = 0
    for item in canonical:
        key = schedule_entry_key(item)
        if key is None:
            continue
        if key in seen:
            dropped_duplicates += 1
            continue
        seen.add(key)
        cleaned.append(normalize_schedule_entry(item))
    return cleaned, {
        "input_count": raw_count,
        "output_count": len(cleaned),
        "dropped_invalid": dropped_invalid,
        "dropped_duplicates": dropped_duplicates,
    }


def dedupe_schedule_entries(schedules: list) -> list:
    """Drop invalid sections and duplicate subject rows."""
    cleaned, _ = sanitize_schedules_for_save(schedules)
    return cleaned


def merge_schedules_replacing_grade_strand(
    saved_schedules: list,
    incoming_schedules: list,
    *,
    grade_level: str,
    replace_strands: set[str],
) -> list:
    """Keep all grades/strands except the same grade+strand being replaced."""
    incoming_grade = str(grade_level)
    replace = {str(code or "").upper() for code in replace_strands if code}
    merged = [
        item for item in (saved_schedules or [])
        if not (
            str(item.get("strand") or "").upper() in replace
            and str(item.get("gradeLevel") or item.get("grade_level") or incoming_grade) == incoming_grade
        )
    ]
    merged.extend(incoming_schedules or [])
    return dedupe_schedule_entries(merged)


def exclude_regenerating_strand_schedules(
    schedules: list,
    *,
    strand: str,
    grade_level: str,
) -> tuple[list, int]:
    """Drop saved rows for the strand+grade being regenerated.

    Those rows must not participate in conflict checks — they are being replaced.
    """
    target_strand = str(strand or "").upper()
    target_grade = str(grade_level or "").strip()
    if not target_strand or not target_grade:
        return dedupe_schedule_entries(schedules), 0

    kept: list = []
    removed = 0
    for item in schedules or []:
        if not isinstance(item, dict):
            continue
        item_strand = str(item.get("strand") or "").upper()
        item_grade = str(
            item.get("gradeLevel") or item.get("grade_level") or ""
        ).strip()
        if item_strand == target_strand and item_grade == target_grade:
            removed += 1
            continue
        kept.append(item)
    return dedupe_schedule_entries(kept), removed


def merge_existing_schedules(
    saved_schedules: list,
    incoming_schedules: list,
    *,
    exclude_strand: str,
    exclude_grade_level: str | None = None,
) -> list:
    """Combine DB drafts with client state without duplicating strands already saved."""
    exclude = str(exclude_strand or "").upper()
    exclude_grade = str(exclude_grade_level or "") if exclude_grade_level else None
    saved_strands = {
        str(item.get("strand") or "").upper()
        for item in saved_schedules
        if isinstance(item, dict) and item.get("strand")
    }
    merged = list(saved_schedules)
    for item in incoming_schedules or []:
        if not isinstance(item, dict):
            continue
        strand_key = str(item.get("strand") or "").upper()
        if not strand_key or strand_key == exclude:
            continue
        if exclude_grade:
            item_grade = str(item.get("gradeLevel") or item.get("grade_level") or exclude_grade)
            if strand_key == exclude and item_grade == exclude_grade:
                continue
        if strand_key in saved_strands:
            continue
        merged.append(item)
    return dedupe_schedule_entries(merged)
