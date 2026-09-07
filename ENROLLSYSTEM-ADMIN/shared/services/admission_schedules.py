"""Resolve preferred subject schedules for admission review."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

RestGetFn = Callable[[str, str, bool, int], tuple]


def _count_meeting_days(day_code: str) -> int:
    text = str(day_code or "")
    count = 0
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair == "Th":
            count += 1
            i += 2
        elif pair == "Sa":
            count += 1
            i += 2
        elif text[i] in "MTWFS":
            count += 1
            i += 1
        else:
            i += 1
    return max(count, 1)


def _parse_time_minutes(value: str) -> int | None:
    match = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", str(value or "").strip(), re.I)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    meridiem = (match.group(3) or "").lower()
    if meridiem == "pm" and hours < 12:
        hours += 12
    if meridiem == "am" and hours == 12:
        hours = 0
    return hours * 60 + minutes


def _contact_units_from_schedule_label(label: str) -> float | int | None:
    text = str(label or "").strip()
    match = re.match(r"^(\S+)\s+(.+)$", text)
    if not match:
        return None
    time_range = match.group(2)
    if "-" not in time_range:
        return None
    start_text, end_text = time_range.split("-", 1)
    start_min = _parse_time_minutes(start_text)
    end_min = _parse_time_minutes(end_text)
    if start_min is None or end_min is None or end_min <= start_min:
        return None
    hours_per_session = (end_min - start_min) / 60
    weekly_hours = hours_per_session * _count_meeting_days(match.group(1))
    rounded = round(weekly_hours, 1)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _normalize_schedule_row(item: dict) -> dict:
    row = dict(item)
    day_time = row.get("dayTime") or row.get("schedule_label") or ""
    contact_units = _contact_units_from_schedule_label(day_time)
    if contact_units is not None:
        row["units"] = contact_units
    return row


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def _coerce_schedule_list(value: Any) -> List[dict]:
    parsed = _parse_json(value)
    if isinstance(parsed, list) and parsed:
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _coerce_preferred_map(record: dict) -> dict:
    preferred = (
        record.get("preferredSubjectSchedules")
        or record.get("preferred_subject_schedules")
        or record.get("subjectSchedules")
        or {}
    )
    parsed = _parse_json(preferred)
    if isinstance(parsed, dict) and parsed:
        return parsed
    return {}


def schedule_rows_have_times(rows: List[dict]) -> bool:
    return any(
        str(item.get("dayTime") or item.get("schedule_label") or "").strip()
        or str(item.get("section") or "").strip()
        for item in rows
        if isinstance(item, dict)
    )


_schedule_rows_have_times = schedule_rows_have_times


def _in_filter(values: List[str]) -> str:
    cleaned = [str(value).strip() for value in values if str(value or "").strip()]
    if not cleaned:
        return ""
    return ",".join(f'"{value}"' for value in cleaned)


def _hydrate_from_preferred_map(
    preferred: dict,
    rest_get_fn: Optional[RestGetFn],
) -> List[dict]:
    if not preferred:
        return []

    schedule_ids = [str(value).strip() for value in preferred.values() if value]
    lookup: Dict[str, dict] = {}

    if schedule_ids and rest_get_fn:
        id_list = _in_filter(schedule_ids)
        if not id_list:
            return []
        rows, err = rest_get_fn(
            "class_schedules",
            (
                f"id=in.({id_list})"
                "&select=id,schedule_label,max_slots,enrolled_count,subject_id,section_id"
            ),
            True,
            12,
        )
        if not err and rows:
            subject_ids = {row["subject_id"] for row in rows if row.get("subject_id")}
            section_ids = {row["section_id"] for row in rows if row.get("section_id")}
            subjects: Dict[Any, dict] = {}
            sections: Dict[Any, dict] = {}

            if subject_ids:
                subject_filter = _in_filter([str(subject_id) for subject_id in subject_ids])
                subject_rows, _ = rest_get_fn(
                    "subjects",
                    f"id=in.({subject_filter})&select=id,code,name,units",
                    True,
                    12,
                )
                subjects = {row["id"]: row for row in (subject_rows or [])}

            if section_ids:
                section_filter = _in_filter([str(section_id) for section_id in section_ids])
                section_rows, _ = rest_get_fn(
                    "sections",
                    f"id=in.({section_filter})&select=id,name",
                    True,
                    12,
                )
                sections = {row["id"]: row for row in (section_rows or [])}

            for row in rows:
                schedule_id = str(row.get("id"))
                subject = subjects.get(row.get("subject_id")) or {}
                section = sections.get(row.get("section_id")) or {}
                max_slots = int(row.get("max_slots") or 40)
                enrolled = int(row.get("enrolled_count") or 0)
                lookup[schedule_id] = {
                    "description": subject.get("name") or "",
                    "section": section.get("name") or "",
                    "dayTime": row.get("schedule_label") or "",
                    "units": _contact_units_from_schedule_label(row.get("schedule_label") or "")
                    or subject.get("units"),
                    "slots": max(max_slots - enrolled, 0),
                }

    result = []
    for code, schedule_id in preferred.items():
        info = lookup.get(str(schedule_id), {})
        result.append({
            "code": code,
            "description": info.get("description") or code,
            "scheduleId": str(schedule_id),
            "section": info.get("section") or "",
            "dayTime": info.get("dayTime") or "",
            "units": info.get("units"),
            "slots": info.get("slots"),
        })
    return result


def load_admission_schedule_record(
    application_id: str | None = None,
    application_number: str | None = None,
    rest_get_fn: Optional[RestGetFn] = None,
) -> dict:
    """Fetch raw schedule fields from admission_applications when RPC/detail omits them."""
    if not rest_get_fn:
        return {}

    app_id = str(application_id or "").strip()
    app_number = str(application_number or "").strip()
    if not app_id and not app_number:
        return {}

    if app_id:
        query = f"id=eq.{app_id}&select=id,application_number,preferred_subject_schedules,documents"
    else:
        query = (
            f"application_number=eq.{app_number}"
            "&select=id,application_number,preferred_subject_schedules,documents"
        )

    rows, err = rest_get_fn("admission_applications", query, True, 12)
    if err or not rows:
        return {}

    row = rows[0]
    documents = row.get("documents") or {}
    preferred = row.get("preferred_subject_schedules") or {}
    return {
        "id": row.get("id"),
        "applicationNumber": row.get("application_number"),
        "preferredSubjectSchedules": preferred,
        "preferred_subject_schedules": preferred,
        "documents": documents,
        "subjectScheduleDetails": (
            documents.get("subject_schedule_details")
            if isinstance(documents, dict)
            else None
        ),
    }


def load_enrollment_schedule_details(
    student_id: str | None = None,
    rest_get_fn: Optional[RestGetFn] = None,
) -> List[dict]:
    """Load enrolled subject rows for COR when admission snapshots are missing."""
    sid = str(student_id or "").strip().upper()
    if not sid or not rest_get_fn:
        return []

    students, err = rest_get_fn(
        "students",
        f"student_id=eq.{sid}&select=id",
        True,
        12,
    )
    if err or not students:
        return []

    enrollments, err = rest_get_fn(
        "enrollments",
        (
            f"student_id=eq.{students[0]['id']}"
            "&select=id&order=created_at.desc&limit=1"
        ),
        True,
        12,
    )
    if err or not enrollments:
        return []

    enrollment_id = enrollments[0]["id"]
    rows, err = rest_get_fn(
        "enrollment_subjects",
        (
            f"enrollment_id=eq.{enrollment_id}"
            "&select=units,schedule_label,subject_id,class_schedule_id"
        ),
        True,
        12,
    )
    if err or not rows:
        return []

    subject_ids = {row["subject_id"] for row in rows if row.get("subject_id")}
    schedule_ids = {
        row["class_schedule_id"] for row in rows if row.get("class_schedule_id")
    }
    subjects: Dict[Any, dict] = {}
    schedules: Dict[Any, dict] = {}
    sections: Dict[Any, dict] = {}

    if subject_ids:
        subject_filter = _in_filter([str(subject_id) for subject_id in subject_ids])
        subject_rows, _ = rest_get_fn(
            "subjects",
            f"id=in.({subject_filter})&select=id,code,name,units",
            True,
            12,
        )
        subjects = {row["id"]: row for row in (subject_rows or [])}

    if schedule_ids:
        schedule_filter = _in_filter([str(schedule_id) for schedule_id in schedule_ids])
        schedule_rows, _ = rest_get_fn(
            "class_schedules",
            (
                f"id=in.({schedule_filter})"
                "&select=id,schedule_label,section_id"
            ),
            True,
            12,
        )
        schedules = {row["id"]: row for row in (schedule_rows or [])}
        section_ids = {row["section_id"] for row in schedule_rows or [] if row.get("section_id")}
        if section_ids:
            section_filter = _in_filter([str(section_id) for section_id in section_ids])
            section_rows, _ = rest_get_fn(
                "sections",
                f"id=in.({section_filter})&select=id,name",
                True,
                12,
            )
            sections = {row["id"]: row for row in (section_rows or [])}

    result = []
    for row in rows:
        subject = subjects.get(row.get("subject_id")) or {}
        schedule = schedules.get(row.get("class_schedule_id")) or {}
        section = sections.get(schedule.get("section_id")) or {}
        day_time = row.get("schedule_label") or schedule.get("schedule_label") or ""
        result.append(_normalize_schedule_row({
            "code": subject.get("code") or "",
            "description": subject.get("name") or subject.get("code") or "",
            "section": section.get("name") or "",
            "dayTime": day_time,
            "units": row.get("units") or subject.get("units"),
        }))

    return [item for item in result if item.get("code") or item.get("description")]


def resolve_subject_schedule_details(
    record: dict,
    rest_get_fn: Optional[RestGetFn] = None,
) -> List[dict]:
    """Return subject schedule rows for review/COR from stored admission data."""
    if not isinstance(record, dict):
        return []

    details = _coerce_schedule_list(
        record.get("subjectScheduleDetails") or record.get("subject_schedule_details")
    )
    if details:
        normalized = [_normalize_schedule_row(item) for item in details]
        if _schedule_rows_have_times(normalized):
            return normalized

    documents = record.get("documents") or {}
    if isinstance(documents, dict):
        nested = _coerce_schedule_list(documents.get("subject_schedule_details"))
        if nested:
            normalized = [_normalize_schedule_row(item) for item in nested]
            if _schedule_rows_have_times(normalized):
                return normalized

    preferred = _coerce_preferred_map(record)
    if preferred:
        hydrated = _hydrate_from_preferred_map(preferred, rest_get_fn)
        if hydrated and _schedule_rows_have_times(hydrated):
            return hydrated

    student_id = (
        record.get("studentId")
        or record.get("student_id_generated")
        or record.get("student_id")
    )
    if student_id:
        enrolled = load_enrollment_schedule_details(student_id, rest_get_fn)
        if enrolled:
            return enrolled

    return []
