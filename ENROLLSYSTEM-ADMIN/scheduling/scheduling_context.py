"""Collect scheduling inputs: teachers, rooms, labs, student load, time constraints."""

from __future__ import annotations

from typing import Any, Callable

from enrollment_curriculum import ENROLLMENT_TRACKS

from .room_types import ROOM_CLASSROOM, build_rooms_by_type, normalize_room_type, room_capacities

DEFAULT_TIME = {
    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "hours": "8:00am – 5:00pm",
    "slot_minutes": 60,
}


def build_scheduling_context(
    *,
    grade_level: str = "Grade 12",
    semester_code: str = "1st",
    strands: list[str] | None = None,
    rooms: list[str] | None = None,
    rest_get: Callable[[str, str], tuple[list | None, str | None]] | None = None,
) -> dict[str, Any]:
    selected = [s.upper() for s in (strands or [])]
    room_rows, classrooms, laboratories, room_errors = _load_rooms(rest_get, rooms)
    rooms_by_type = build_rooms_by_type(room_rows) if room_rows else {}
    capacities = room_capacities(room_rows) if room_rows else {}
    teachers, teacher_errors = _load_teachers(rest_get)
    student_load, student_errors = _load_student_load(grade_level, selected, rest_get)
    errors = room_errors + teacher_errors + student_errors

    return {
        "grade_level": grade_level,
        "semester_code": semester_code,
        "tracks": ENROLLMENT_TRACKS,
        "selected_strands": selected,
        "teacher_availability": teachers,
        "classroom_availability": classrooms,
        "laboratory_availability": laboratories,
        "rooms_by_type": rooms_by_type,
        "room_capacities": capacities,
        "student_load": student_load,
        "time_constraints": DEFAULT_TIME,
        "section_capacity_default": 40,
        "class_max_slots": 40,
        "data_source": "supabase" if rest_get else "unconfigured",
        "errors": errors,
    }


def _load_teachers(rest_get) -> tuple[list[dict[str, Any]], list[str]]:
    if not rest_get:
        return [], ["Supabase not configured — add teachers in Faculty module after connecting .env"]

    rows, err = rest_get(
        "faculty",
        "select=faculty_id,first_name,last_name,department,max_load_units,is_active,"
        "faculty_strands(strands(code))&role=eq.Teacher&is_active=eq.true",
    )
    if err:
        return [], [f"Could not load teachers: {err}"]
    if not rows:
        return [], ["No teachers in database — add professors in Manage → Faculty"]

    teachers = []
    for row in rows:
        strand_links = row.get("faculty_strands") or []
        strand_codes = []
        for link in strand_links:
            strand = link.get("strands") if isinstance(link, dict) else None
            if isinstance(strand, dict) and strand.get("code"):
                strand_codes.append(strand["code"].upper())
        teachers.append({
            "faculty_id": row.get("faculty_id"),
            "name": f"{row.get('first_name', '')} {row.get('last_name', '')}".strip(),
            "department": row.get("department"),
            "strands": sorted(set(strand_codes)),
            "max_load_units": row.get("max_load_units") or 3,
            "max_assignments": 3,
            "availability": "Mon–Fri 8am–5pm",
        })
    return teachers, []


def _load_rooms(
    rest_get,
    rooms_param: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """Return (room_rows, classrooms, laboratories, errors)."""
    errors: list[str] = []
    if rest_get:
        rows, err = rest_get(
            "rooms",
            "select=name,room_type,capacity,is_active&is_active=eq.true&order=name.asc",
        )
        if err:
            errors.append(f"Could not load rooms: {err}")
        elif rows:
            room_rows = []
            classrooms = []
            laboratories = []
            for row in rows:
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                room_rows.append({
                    "name": name.upper(),
                    "room_type": normalize_room_type(row.get("room_type")),
                    "capacity": int(row.get("capacity") or 40),
                    "is_active": row.get("is_active", True),
                })
                room_type = normalize_room_type(row.get("room_type"))
                if room_type == ROOM_CLASSROOM:
                    classrooms.append(name.upper())
                else:
                    laboratories.append(name.upper())
                    if room_type != ROOM_CLASSROOM:
                        classrooms.append(name.upper())
            if room_rows:
                return room_rows, classrooms, laboratories, errors
            errors.append("No active rooms in database — add rooms in Manage → Classrooms")
        else:
            errors.append("No rooms in database — add classrooms/labs in Manage → Classrooms")

    if rooms_param:
        all_rooms = [r.strip().upper() for r in rooms_param if r.strip()]
        room_rows = [
            {"name": name, "room_type": ROOM_CLASSROOM, "capacity": 40, "is_active": True}
            for name in all_rooms
        ]
        classrooms = [r for r in all_rooms if not r.startswith("LAB") and not r.startswith("COOKERY") and not r.startswith("EIM")]
        laboratories = [r for r in all_rooms if r not in classrooms]
        return room_rows, classrooms or all_rooms, laboratories, errors

    return [], [], [], errors


def _load_student_load(
    grade_level: str,
    strands: list[str],
    rest_get,
) -> tuple[dict[str, Any], list[str]]:
    load: dict[str, int] = {}
    errors: list[str] = []

    if not rest_get:
        return {
            "by_strand": {},
            "recommended_sections": {},
            "total_students": 0,
        }, ["Supabase not configured — student counts unavailable"]

    rows, err = rest_get(
        "students",
        "select=strand_id,is_active,grade_level,strands(code)&is_active=eq.true",
    )
    if err:
        return {
            "by_strand": {},
            "recommended_sections": {},
            "total_students": 0,
        }, [f"Could not load students: {err}"]

    for row in rows or []:
        if row.get("grade_level") != grade_level:
            continue
        strand_info = row.get("strands") or {}
        code = (strand_info.get("code") or "").upper()
        if code:
            load[code] = load.get(code, 0) + 1

    payload = {
        "by_strand": load,
        "recommended_sections": {
            strand: max(1, min(2, (count + 39) // 40)) for strand, count in load.items()
        },
        "total_students": sum(load.values()),
    }
    return payload, errors
