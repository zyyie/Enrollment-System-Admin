"""Room type classification and subject → room-type requirements."""

from __future__ import annotations

from typing import Any

ROOM_CLASSROOM = "classroom"
ROOM_COMPUTER_LAB = "computer_lab"
ROOM_SCIENCE_LAB = "science_lab"
ROOM_COOKERY_LAB = "cookery_lab"
ROOM_EIM_LAB = "eim_lab"

# Legacy DB values mapped to canonical types.
ROOM_TYPE_ALIASES = {
    "classroom": ROOM_CLASSROOM,
    "regular": ROOM_CLASSROOM,
    "regular_classroom": ROOM_CLASSROOM,
    "laboratory": ROOM_SCIENCE_LAB,
    "lab": ROOM_SCIENCE_LAB,
    "science_lab": ROOM_SCIENCE_LAB,
    "computer_lab": ROOM_COMPUTER_LAB,
    "cookery_lab": ROOM_COOKERY_LAB,
    "eim_lab": ROOM_EIM_LAB,
    "workshop": ROOM_EIM_LAB,
}


def normalize_room_type(raw: str | None) -> str:
    text = (raw or ROOM_CLASSROOM).strip().lower().replace(" ", "_")
    if text in ROOM_TYPE_ALIASES:
        return ROOM_TYPE_ALIASES[text]
    if text.startswith("lab") and "cook" in text:
        return ROOM_COOKERY_LAB
    if text.startswith("lab") and "eim" in text:
        return ROOM_EIM_LAB
    if text.startswith("lab") and "comp" in text:
        return ROOM_COMPUTER_LAB
    if text.startswith("lab"):
        return ROOM_SCIENCE_LAB
    return ROOM_CLASSROOM


def required_room_type(subject: dict[str, Any], strand: str | None = None) -> str:
    """Infer required room type from subject metadata."""
    explicit = subject.get("required_room_type") or subject.get("room_type")
    if explicit:
        return normalize_room_type(str(explicit))

    code = str(subject.get("code") or subject.get("subject_code") or "").upper()
    strand_code = str(subject.get("strand") or strand or "").upper()
    lab_hours = int(subject.get("lab") or subject.get("lab_hours") or 0)
    name = f"{subject.get('description') or ''} {subject.get('name') or ''}".lower()

    if code.startswith("G11-ICT-") or code.startswith("G12-ICT-") or strand_code == "ICT":
        if lab_hours > 0 or "computer" in name or "network" in name or "configure" in name:
            return ROOM_COMPUTER_LAB

    if code.startswith("G11-CK-") or code.startswith("G12-CK-") or strand_code == "COOKERY":
        if (
            lab_hours > 0
            or code.startswith("G11-CK-0")
            or code.startswith("G12-CK-0")
            or "prepare" in name
            or "housekeeping" in name
            or "front office" in name
        ):
            return ROOM_COOKERY_LAB

    if code.startswith("G11-EIM-") or code.startswith("G12-EIM-") or strand_code == "EIM":
        if lab_hours > 0 or "install" in name or "electrical" in name or "wiring" in name:
            return ROOM_EIM_LAB

    if lab_hours > 0 or "biology" in name or "chemistry" in name or "physics" in name:
        return ROOM_SCIENCE_LAB

    return ROOM_CLASSROOM


def rooms_for_subject(
    subject: dict[str, Any],
    *,
    strand: str | None = None,
    rooms_by_type: dict[str, list[str]] | None = None,
    fallback_classrooms: list[str] | None = None,
) -> list[str]:
    """Return ordered room pool for a subject (specialized first, then regular)."""
    needed = required_room_type(subject, strand)
    by_type = rooms_by_type or {}
    specialized = list(by_type.get(needed) or [])
    regular = list(by_type.get(ROOM_CLASSROOM) or [])
    fallback = list(fallback_classrooms or [])

    if needed == ROOM_CLASSROOM:
        pool = regular or fallback
        return list(dict.fromkeys(pool))

    pool = specialized + regular + fallback
    return list(dict.fromkeys(item for item in pool if item))


def build_rooms_by_type(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group active rooms by canonical type, including capacity metadata on side channel."""
    grouped: dict[str, list[str]] = {
        ROOM_CLASSROOM: [],
        ROOM_COMPUTER_LAB: [],
        ROOM_SCIENCE_LAB: [],
        ROOM_COOKERY_LAB: [],
        ROOM_EIM_LAB: [],
    }
    for row in rows or []:
        name = (row.get("name") or "").strip().upper()
        if not name:
            continue
        room_type = normalize_room_type(row.get("room_type"))
        # Name-based fallback when room_type is generic laboratory/classroom.
        upper = name.upper()
        if room_type in (ROOM_CLASSROOM, ROOM_SCIENCE_LAB):
            if upper.startswith("COOKERY"):
                room_type = ROOM_COOKERY_LAB
            elif upper.startswith("EIM"):
                room_type = ROOM_EIM_LAB
            elif upper in ("LAB3", "LAB4"):
                room_type = ROOM_SCIENCE_LAB
            elif upper.startswith("LAB") and room_type == ROOM_CLASSROOM:
                room_type = ROOM_COMPUTER_LAB
        grouped.setdefault(room_type, []).append(name)
    return grouped


def _lab_room_type(room_name: str) -> str:
    upper = room_name.upper()
    if upper in ("LAB3", "LAB4"):
        return ROOM_SCIENCE_LAB
    if upper.startswith("LAB"):
        return ROOM_COMPUTER_LAB
    if upper.startswith("COOKERY"):
        return ROOM_COOKERY_LAB
    if upper.startswith("EIM"):
        return ROOM_EIM_LAB
    return ROOM_CLASSROOM


def _default_room_rows() -> list[dict[str, Any]]:
    from .constants import DEFAULT_CLASS_MAX_SLOTS, DEFAULT_SCHEDULER_ROOMS

    rows = [
        {"name": room, "room_type": ROOM_CLASSROOM, "capacity": DEFAULT_CLASS_MAX_SLOTS}
        for room in DEFAULT_SCHEDULER_ROOMS
    ]
    for room in DEFAULT_SCHEDULER_ROOMS:
        lab_type = _lab_room_type(room)
        if lab_type != ROOM_CLASSROOM:
            rows.append(
                {"name": room, "room_type": lab_type, "capacity": DEFAULT_CLASS_MAX_SLOTS}
            )
    return rows


def _merge_rooms_by_type(
    base: dict[str, list[str]] | None,
    extra: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {
        ROOM_CLASSROOM: [],
        ROOM_COMPUTER_LAB: [],
        ROOM_SCIENCE_LAB: [],
        ROOM_COOKERY_LAB: [],
        ROOM_EIM_LAB: [],
    }
    for room_type in merged:
        combined = list((base or {}).get(room_type) or []) + list(extra.get(room_type) or [])
        merged[room_type] = list(dict.fromkeys(name for name in combined if name))
    return merged


def resolve_scheduler_rooms(
    scheduler_input,
    scheduling_context: dict[str, Any] | None,
) -> tuple[dict[str, list[str]], dict[str, int], list[str]]:
    """Return (rooms_by_type, room_capacities, fallback_classrooms) for solvers."""
    from .constants import DEFAULT_CLASS_MAX_SLOTS, DEFAULT_SCHEDULER_ROOMS

    input_rooms = [
        room.strip().upper()
        for room in (getattr(scheduler_input, "rooms", None) or [])
        if str(room).strip()
    ]
    if not input_rooms:
        input_rooms = list(DEFAULT_SCHEDULER_ROOMS)

    if scheduling_context:
        rooms_by_type = dict(scheduling_context.get("rooms_by_type") or {})
        capacities = {
            str(key).upper(): int(value)
            for key, value in (scheduling_context.get("room_capacities") or {}).items()
        }
        classrooms = [
            room.strip().upper()
            for room in (scheduling_context.get("classroom_availability") or [])
            if str(room).strip()
        ]
        all_typed_rooms: list[str] = []
        for pool in rooms_by_type.values():
            for room in pool or []:
                name = str(room).strip().upper()
                if name:
                    all_typed_rooms.append(name)
        db_rooms = list(dict.fromkeys(classrooms or all_typed_rooms))
        fallback = list(dict.fromkeys(db_rooms + list(DEFAULT_SCHEDULER_ROOMS)))
        default_by_type = build_rooms_by_type(_default_room_rows())
        rooms_by_type = _merge_rooms_by_type(rooms_by_type, default_by_type)
        if fallback:
            for room in fallback:
                capacities.setdefault(room, DEFAULT_CLASS_MAX_SLOTS)
            return rooms_by_type, capacities, fallback

    rows = [
        {"name": room, "room_type": ROOM_CLASSROOM, "capacity": DEFAULT_CLASS_MAX_SLOTS}
        for room in input_rooms
    ]
    for room in input_rooms:
        lab_type = _lab_room_type(room)
        if lab_type != ROOM_CLASSROOM:
            rows.append(
                {"name": room, "room_type": lab_type, "capacity": DEFAULT_CLASS_MAX_SLOTS}
            )
    return build_rooms_by_type(rows), {room: DEFAULT_CLASS_MAX_SLOTS for room in input_rooms}, input_rooms


def room_capacities(rows: list[dict[str, Any]]) -> dict[str, int]:
    caps: dict[str, int] = {}
    for row in rows or []:
        name = (row.get("name") or "").strip().upper()
        if not name:
            continue
        caps[name] = int(row.get("capacity") or 40)
    return caps
