"""Shared time/day helpers for scheduling."""

from __future__ import annotations

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DAY_CODES = ["M", "T", "W", "Th", "F", "Sa"]

DAY_NAME_TO_INDEX = {
    "monday": 0,
    "mon": 0,
    "m": 0,
    "tuesday": 1,
    "tue": 1,
    "t": 1,
    "wednesday": 2,
    "wed": 2,
    "w": 2,
    "thursday": 3,
    "thu": 3,
    "th": 3,
    "friday": 4,
    "fri": 4,
    "f": 4,
    "saturday": 5,
    "sat": 5,
    "sa": 5,
}


def parse_clock(value: str) -> int:
    text = (value or "").strip().upper().replace(" ", "")
    if not text:
        raise ValueError("Empty time value")

    suffix = None
    if text.endswith("AM") or text.endswith("PM"):
        suffix = text[-2:]
        text = text[:-2]

    if ":" in text:
        hour_str, minute_str = text.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
    else:
        hour = int(text)
        minute = 0

    if suffix == "AM":
        if hour == 12:
            hour = 0
    elif suffix == "PM":
        if hour != 12:
            hour += 12

    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid clock value: {value}")
    return hour * 60 + minute


def format_clock(minutes: int) -> str:
    hour = minutes // 60
    minute = minutes % 60
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    if minute:
        return f"{display_hour}:{minute:02d}{suffix.lower()}"
    return f"{display_hour}:00{suffix.lower()}"


def sessions_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def build_schedule_label(sessions: list[dict]) -> str:
    if not sessions:
        return "TBA"

    parsed: list[tuple[int, int, int]] = []
    for session in sessions:
        day_index = DAY_NAME_TO_INDEX.get((session.get("day") or "").strip().lower(), 99)
        if day_index == 99:
            continue
        try:
            start = parse_clock(session["start"])
            end = parse_clock(session["end"])
        except (KeyError, ValueError):
            continue
        parsed.append((day_index, start, end))

    if not parsed:
        return "TBA"

    parsed.sort(key=lambda item: (item[0], item[1]))
    if len(parsed) == 1:
        day_index, start, end = parsed[0]
        return f"{DAY_CODES[day_index]} {format_clock(start)}-{format_clock(end)}"

    same_time = len({start for _, start, _ in parsed}) == 1
    same_duration = len({end - start for _, start, end in parsed}) == 1
    if same_time and same_duration:
        day_part = "".join(DAY_CODES[day_index] for day_index, _, _ in parsed)
        _, start, end = parsed[0]
        return f"{day_part} {format_clock(start)}-{format_clock(end)}"

    parts = [
        f"{DAY_CODES[day_index]} {format_clock(start)}-{format_clock(end)}"
        for day_index, start, end in parsed
    ]
    return ", ".join(parts)
