"""Time grid: Mon–Fri 8:00 AM–5:00 PM, Sat 8:00 AM–12:00 PM."""

from __future__ import annotations

import random
from itertools import combinations

from .models import TimeSlot
from .time_utils import DAY_CODES, format_clock

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

SCHOOL_OPEN = 8 * 60
SCHOOL_CLOSE_WEEKDAY = 17 * 60
SCHOOL_CLOSE_SATURDAY = 12 * 60
SLOT_MINUTES = 60
WEEKDAY_COUNT = 5


def weekday_slots(include_saturday: bool = False) -> list[TimeSlot]:
    slots: list[TimeSlot] = []
    for day in range(5 if not include_saturday else 6):
        close = SCHOOL_CLOSE_SATURDAY if day == 5 else SCHOOL_CLOSE_WEEKDAY
        start = SCHOOL_OPEN
        while start + SLOT_MINUTES <= close:
            slots.append(TimeSlot(day=day, start_minutes=start, end_minutes=start + SLOT_MINUTES))
            start += SLOT_MINUTES
    return slots


def is_pe_subject(subject: dict | None) -> bool:
    code = str((subject or {}).get("code") or (subject or {}).get("subject_code") or "").upper()
    return "-PE" in code or code.startswith("PE-")


def is_applied_subject(subject: dict | None) -> bool:
    if not subject:
        return False
    if str(subject.get("type") or "").lower() == "applied":
        return True
    code = str(subject.get("code") or subject.get("subject_code") or "").upper()
    return "-A0" in code or "-A1" in code or "-A2" in code or "-A3" in code


def is_main_subject(subject: dict | None) -> bool:
    """Core (non-PE) and specialized subjects → MAIN (2 meeting days)."""
    if not subject:
        return False
    if is_pe_subject(subject) or is_applied_subject(subject):
        return False
    subject_type = str(subject.get("type") or "").lower()
    if subject_type in ("core", "specialized"):
        return True
    code = str(subject.get("code") or subject.get("subject_code") or "").upper()
    if code.startswith("G11-C") or code.startswith("G12-C"):
        return True
    if subject.get("strand"):
        return True
    for marker in ("-STEM-", "-ABM-", "-HUM-", "-ICT-", "-CK-", "-EIM-"):
        if marker in code:
            return True
    return False


def meetings_per_week(units: int, subject: dict | None = None) -> int:
    """MAIN (core + specialized) → 2 days; MINOR (applied + PE) → 1 day."""
    if subject:
        explicit = subject.get("meetings_per_week")
        if explicit is not None:
            return max(1, int(explicit))
        if is_main_subject(subject):
            return 2
        return 1

    unit_count = max(1, int(units or 1))
    return 2 if unit_count >= 3 else 1


def session_duration_minutes(units: int, meeting_count: int) -> int:
    """Weekly contact minutes split across meetings (60–180 min each)."""
    weekly_minutes = max(1, int(units or 1)) * 60
    meetings = max(1, meeting_count)
    per_meeting = weekly_minutes // meetings
    if meetings == 1:
        per_meeting = max(SLOT_MINUTES, min(weekly_minutes, 180))
    else:
        per_meeting = max(SLOT_MINUTES, min(SLOT_MINUTES * 2, per_meeting))
    if per_meeting % 30:
        per_meeting = max(SLOT_MINUTES, (per_meeting // 30) * 30)
    return per_meeting


def _valid_start_minutes(session_duration_minutes: int) -> list[int]:
    step = 30 if session_duration_minutes % 60 else SLOT_MINUTES
    return [
        start
        for start in range(SCHOOL_OPEN, SCHOOL_CLOSE_WEEKDAY, step)
        if start + session_duration_minutes <= SCHOOL_CLOSE_WEEKDAY
    ]


def build_flexible_meeting_patterns(
    meeting_count: int,
    duration_minutes: int,
    *,
    rng: random.Random | None = None,
    max_patterns: int = 72,
) -> list[list[TimeSlot]]:
    """Build patterns where each meeting may use a different day and time."""
    starts = _valid_start_minutes(duration_minutes)
    patterns: list[list[TimeSlot]] = []

    if meeting_count <= 0:
        return patterns

    if meeting_count == 1:
        for day in range(WEEKDAY_COUNT):
            for start in starts:
                patterns.append([
                    TimeSlot(
                        day=day,
                        start_minutes=start,
                        end_minutes=start + duration_minutes,
                    )
                ])
    elif meeting_count == 2:
        for day_a, day_b in combinations(range(WEEKDAY_COUNT), 2):
            for start_a in starts:
                for start_b in starts:
                    patterns.append([
                        TimeSlot(
                            day=day_a,
                            start_minutes=start_a,
                            end_minutes=start_a + duration_minutes,
                        ),
                        TimeSlot(
                            day=day_b,
                            start_minutes=start_b,
                            end_minutes=start_b + duration_minutes,
                        ),
                    ])
    else:
        raise ValueError(f"Unsupported meeting count: {meeting_count}")

    if rng is not None:
        rng.shuffle(patterns)
    if len(patterns) > max_patterns:
        step = len(patterns) / max_patterns
        patterns = [patterns[int(index * step)] for index in range(max_patterns)]
    return patterns


def build_meeting_patterns(max_hours: int = 2) -> list[list[TimeSlot]]:
    """Legacy recurring patterns — kept for compatibility; prefer build_flexible_meeting_patterns."""
    del max_hours
    patterns: list[list[TimeSlot]] = []
    for duration in (60, 90, 120):
        patterns.extend(build_flexible_meeting_patterns(1, duration, max_patterns=50))
        patterns.extend(build_flexible_meeting_patterns(2, duration, max_patterns=120))
    return patterns


def pattern_day_set(pattern: list[TimeSlot]) -> frozenset[int]:
    return frozenset(slot.day for slot in pattern)


def pattern_meeting_signature(pattern: list[TimeSlot]) -> tuple[tuple[int, int, int], ...]:
    """Unique signature using each session's actual day/start/end."""
    return tuple(sorted(
        (slot.day, slot.start_minutes, slot.end_minutes)
        for slot in pattern
    ))


def pattern_preference_penalty(
    pattern: list[TimeSlot],
    *,
    task_id: int = 0,
    section_index: int = 0,
    section_day_counts: dict[int, int] | None = None,
) -> int:
    """Lower is better. Spread days/times and vary solutions between runs."""
    if not pattern:
        return 0

    penalty = 0
    days = sorted(slot.day for slot in pattern)

    if len(pattern) == 2 and pattern[0].start_minutes == pattern[1].start_minutes:
        penalty += 40

    if len(set(days)) != len(days):
        penalty += 100

    if section_day_counts:
        for slot in pattern:
            load = section_day_counts.get(slot.day, 0)
            penalty += load * 35
            duration = slot.end_minutes - slot.start_minutes
            if duration >= 180 and load > 0:
                penalty += 80

    penalty += (sum(days) + task_id + section_index * 3) % 7
    return penalty


def section_day_counts(
    section_usage: list[tuple[str, int, int, int, str]],
    section_key: str,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for used_key, used_day, _start, _end, _subject in section_usage:
        if used_key != section_key:
            continue
        counts[used_day] = counts.get(used_day, 0) + 1
    return counts


def build_schedule_label(sessions: list[TimeSlot]) -> str:
    if not sessions:
        return "TBA"

    ordered = sorted(sessions, key=lambda slot: (slot.day, slot.start_minutes))
    if len(ordered) == 1:
        slot = ordered[0]
        day_part = DAY_CODES[slot.day]
        return f"{day_part} {format_clock(slot.start_minutes)}-{format_clock(slot.end_minutes)}"

    same_duration = len({slot.end_minutes - slot.start_minutes for slot in ordered}) == 1
    same_time = len({slot.start_minutes for slot in ordered}) == 1

    if same_duration and same_time:
        day_part = "".join(DAY_CODES[slot.day] for slot in ordered)
        slot = ordered[0]
        return (
            f"{day_part} {format_clock(slot.start_minutes)}-"
            f"{format_clock(slot.end_minutes)}"
        )

    parts = [
        f"{DAY_CODES[slot.day]} {format_clock(slot.start_minutes)}-"
        f"{format_clock(slot.end_minutes)}"
        for slot in ordered
    ]
    return ", ".join(parts)


def _placement_tier(subject: dict) -> int:
    """Higher tier = schedule earlier.

    Specialized/lab first (limited rooms), then applied/PE (need long single blocks),
    then core (most flexible).
    """
    if str(subject.get("type") or "").lower() == "specialized":
        return 3
    if int(subject.get("lab") or subject.get("lab_hours") or 0) > 0:
        return 3
    if is_applied_subject(subject) or is_pe_subject(subject):
        return 2
    return 1


def order_subjects_for_placement(
    subjects: list[dict],
    *,
    reverse: bool = False,
    shuffle: bool = False,
    seed: int = 0,
) -> list[dict]:
    """Specialized/lab first, applied/PE next, core last."""
    ordered = sorted(
        subjects,
        key=lambda subject: (
            -_placement_tier(subject),
            -meetings_per_week(max(1, int(subject.get("units") or 1)), subject),
            str(subject.get("code") or subject.get("subject_code") or ""),
        ),
    )
    if reverse:
        ordered = list(reversed(ordered))
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(ordered)
    return ordered


def default_time_slot_labels(include_saturday: bool = False) -> list[str]:
    labels: list[str] = []
    for slot in weekday_slots(include_saturday=include_saturday):
        labels.append(f"{format_clock(slot.start_minutes)}-{format_clock(slot.end_minutes)}")
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            unique.append(label)
    return unique
