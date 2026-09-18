"""Strict conflict validation — guarantees zero room/time/faculty overlaps."""

from __future__ import annotations

from .constants import DEFAULT_CLASS_MAX_SLOTS, MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER
from .models import ConflictError, ScheduleAssignment, ScheduleSession, ValidationResult
from .time_utils import DAY_NAME_TO_INDEX, parse_clock, sessions_overlap


def _section_key(strand: str, section: str, grade_level: str = "") -> str:
    grade = str(grade_level or "").strip()
    strand_key = strand.upper()
    section_key = section.upper()
    return f"{grade}|{strand_key}|{section_key}" if grade else f"{strand_key}|{section_key}"


def validate_schedule(
    assignments: list[ScheduleAssignment],
    *,
    strict_cross_strand_room: bool = True,
    teachers: list[dict] | None = None,
    room_capacities: dict[str, int] | None = None,
    class_max_slots: int = DEFAULT_CLASS_MAX_SLOTS,
    require_faculty: bool = True,
) -> ValidationResult:
    conflicts: list[ConflictError] = []

    room_bookings: list[tuple[str, str, int, int, str, str]] = []
    section_bookings: list[tuple[str, str, str, int, int, str, str]] = []
    faculty_bookings: list[tuple[str, str, str, str, int, int, str, str]] = []
    capacities = {k.upper(): v for k, v in (room_capacities or {}).items()}
    teacher_strands = {
        str(t.get("faculty_id", "")).upper(): [
            s.upper() for s in (t.get("strands") or [])
        ]
        for t in (teachers or [])
        if t.get("faculty_id")
    }

    for assignment in assignments:
        strand = (assignment.strand or "").upper()
        section = (assignment.section or "").upper()
        grade = str(assignment.grade_level or "").strip()
        subject = assignment.subject_code or assignment.subject_name or "UNKNOWN"

        if not assignment.sessions:
            conflicts.append(
                ConflictError(
                    "MISSING_SESSIONS",
                    f"{strand} {section} / {subject} has no sessions.",
                    {"strand": strand, "section": section, "subject_code": subject},
                )
            )
            continue

        for session in assignment.sessions:
            day_index = DAY_NAME_TO_INDEX.get(session.day.strip().lower())
            if day_index is None:
                conflicts.append(
                    ConflictError(
                        "INVALID_DAY",
                        f"Invalid day '{session.day}' for {subject}.",
                        {"subject_code": subject, "day": session.day},
                    )
                )
                continue

            try:
                start_minutes = parse_clock(session.start)
                end_minutes = parse_clock(session.end)
            except ValueError as err:
                conflicts.append(
                    ConflictError(
                        "INVALID_TIME",
                        f"Invalid time for {subject}: {err}",
                        {"subject_code": subject, "start": session.start, "end": session.end},
                    )
                )
                continue

            if end_minutes <= start_minutes:
                conflicts.append(
                    ConflictError(
                        "INVALID_RANGE",
                        f"End time must be after start time for {subject}.",
                        {"subject_code": subject, "start": session.start, "end": session.end},
                    )
                )
                continue

            room = (session.room or "").strip().upper()
            if not room:
                conflicts.append(
                    ConflictError(
                        "MISSING_ROOM",
                        f"Room is required for {subject}.",
                        {"subject_code": subject},
                    )
                )
                continue

            room_cap = capacities.get(room, DEFAULT_CLASS_MAX_SLOTS)
            if room_cap < class_max_slots:
                conflicts.append(
                    ConflictError(
                        "ROOM_CAPACITY",
                        f"Room {room} capacity ({room_cap}) is less than class size ({class_max_slots}) for {subject}.",
                        {"room": room, "capacity": room_cap, "subject_code": subject},
                    )
                )

            if assignment.faculty_id:
                faculty_key = assignment.faculty_id.strip().upper()
                allowed_strands = teacher_strands.get(faculty_key, [])
                if allowed_strands and strand not in allowed_strands:
                    conflicts.append(
                        ConflictError(
                            "FACULTY_STRAND_MISMATCH",
                            f"Faculty {faculty_key} cannot teach {strand} subject {subject}.",
                            {"faculty_id": faculty_key, "strand": strand, "subject_code": subject},
                        )
                    )

            room_bookings.append((room, session.day, day_index, start_minutes, end_minutes, subject))
            section_bookings.append(
                (grade, strand, section, session.day, day_index, start_minutes, end_minutes, subject)
            )
            if assignment.faculty_id:
                faculty_bookings.append(
                    (
                        assignment.faculty_id.strip().upper(),
                        grade,
                        strand,
                        section,
                        session.day,
                        day_index,
                        start_minutes,
                        end_minutes,
                        subject,
                    )
                )

    # Global room rule: one occupant per room/day/time (all strands)
    # Teacher semester load (unique subject-section assignments, max 3)
    faculty_assignment_counts = _assignment_loads(assignments)
    for assignment in assignments:
        if not assignment.faculty_id and require_faculty:
            conflicts.append(
                ConflictError(
                    "MISSING_FACULTY",
                    f"Unable to assign faculty for {assignment.subject_code} "
                    f"({assignment.strand} Section {assignment.section}).",
                    {
                        "strand": assignment.strand,
                        "section": assignment.section,
                        "subject_code": assignment.subject_code,
                    },
                )
            )

    for faculty_key, count in faculty_assignment_counts.items():
        if count > MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER:
            conflicts.append(
                ConflictError(
                    "TEACHER_OVERLOAD",
                    f"Faculty {faculty_key} has {count} assignments (maximum {MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER} per semester).",
                    {"faculty_id": faculty_key, "load": count, "max_load": MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER},
                )
            )

    for i, booking_a in enumerate(room_bookings):
        room_a, day_a, day_idx_a, start_a, end_a, subject_a = booking_a
        for booking_b in room_bookings[i + 1 :]:
            room_b, day_b, day_idx_b, start_b, end_b, subject_b = booking_b
            if room_a != room_b or day_idx_a != day_idx_b:
                continue
            if not sessions_overlap(start_a, end_a, start_b, end_b):
                continue
            conflicts.append(
                ConflictError(
                    "ROOM_CONFLICT",
                    f"Room {room_a} double-booked on {day_a} "
                    f"({subject_a} overlaps {subject_b}).",
                    {
                        "room": room_a,
                        "day": day_a,
                        "subjects": [subject_a, subject_b],
                        "strict_cross_strand_room": strict_cross_strand_room,
                    },
                )
            )

    # Same section cannot have overlapping subjects (within the same grade).
    for i, booking_a in enumerate(section_bookings):
        grade_a, strand_a, section_a, day_a, day_idx_a, start_a, end_a, subject_a = booking_a
        for booking_b in section_bookings[i + 1 :]:
            grade_b, strand_b, section_b, day_b, day_idx_b, start_b, end_b, subject_b = booking_b
            if _section_key(strand_a, section_a, grade_a) != _section_key(strand_b, section_b, grade_b):
                continue
            if day_idx_a != day_idx_b:
                continue
            if not sessions_overlap(start_a, end_a, start_b, end_b):
                continue
            conflicts.append(
                ConflictError(
                    "SECTION_CONFLICT",
                    f"{strand_a} Section {section_a} has overlapping classes on {day_a} "
                    f"({subject_a} vs {subject_b}).",
                    {
                        "strand": strand_a,
                        "section": section_a,
                        "day": day_a,
                        "subjects": [subject_a, subject_b],
                    },
                )
            )

    for i, booking_a in enumerate(faculty_bookings):
        faculty_a, grade_a, strand_a, section_a, day_a, day_idx_a, start_a, end_a, subject_a = booking_a
        for booking_b in faculty_bookings[i + 1 :]:
            faculty_b, grade_b, strand_b, section_b, day_b, day_idx_b, start_b, end_b, subject_b = booking_b
            if faculty_a != faculty_b or day_idx_a != day_idx_b:
                continue
            if _section_key(strand_a, section_a, grade_a) == _section_key(strand_b, section_b, grade_b):
                continue
            if not sessions_overlap(start_a, end_a, start_b, end_b):
                continue
            conflicts.append(
                ConflictError(
                    "FACULTY_CONFLICT",
                    f"Faculty {faculty_a} assigned to overlapping sections on {day_a} "
                    f"({subject_a} vs {subject_b}).",
                    {
                        "faculty_id": faculty_a,
                        "day": day_a,
                        "sections": [
                            f"{strand_a}-{section_a}",
                            f"{strand_b}-{section_b}",
                        ],
                        "subjects": [subject_a, subject_b],
                    },
                )
            )

    # Each grade's sections should share the same subject set (G11 vs G12 checked separately).
    subjects_by_section: dict[str, set[str]] = {}
    for assignment in assignments:
        key = _section_key(assignment.strand, assignment.section, assignment.grade_level)
        subjects_by_section.setdefault(key, set()).add(assignment.subject_code)

    by_grade_strand: dict[str, dict[str, set[str]]] = {}
    for section_key, subject_codes in subjects_by_section.items():
        parts = section_key.split("|")
        if len(parts) >= 3:
            group_key = f"{parts[0]}|{parts[1]}"
        else:
            group_key = parts[0]
        by_grade_strand.setdefault(group_key, {})[section_key] = subject_codes

    for group_key, sections in by_grade_strand.items():
        if len(sections) < 2:
            continue
        reference = next(iter(sections.values()))
        for section_key, subject_codes in sections.items():
            if subject_codes != reference:
                strand_label = group_key.split("|", 1)[-1]
                conflicts.append(
                    ConflictError(
                        "UNIFORM_SECTION_MISMATCH",
                        f"Strand {strand_label}: section {section_key} subject list differs from sibling section.",
                        {
                            "strand": strand_label,
                            "section": section_key,
                            "subjects": sorted(subject_codes),
                            "expected_subjects": sorted(reference),
                        },
                    )
                )

    return ValidationResult(valid=not conflicts, conflicts=conflicts)


_BLOCKING_SAVED_CONFLICT_TYPES = frozenset({
    "ROOM_CONFLICT",
    "SECTION_CONFLICT",
    "FACULTY_CONFLICT",
    "MISSING_SESSIONS",
    "INVALID_DAY",
    "INVALID_TIME",
    "INVALID_RANGE",
    "MISSING_ROOM",
})


def blocking_saved_conflicts(validation: ValidationResult) -> list[ConflictError]:
    """Conflicts in saved schedules that block room/time sharing with a new strand."""
    return [
        conflict
        for conflict in validation.conflicts
        if conflict.code in _BLOCKING_SAVED_CONFLICT_TYPES
    ]


def blocking_saved_conflicts_for_strand(
    validation: ValidationResult,
    *,
    strand_code: str,
) -> list[ConflictError]:
    """Block generation only when the same strand's saved rows are invalid.

    Other strands (e.g. ICT) may have overlaps — warn and still allow COOKERY/STEM runs.
    """
    target = str(strand_code or "").upper()
    return [
        conflict
        for conflict in blocking_saved_conflicts(validation)
        if str((conflict.details or {}).get("strand") or "").upper() == target
    ]


def _assignment_loads(assignments: list[ScheduleAssignment]) -> dict[str, int]:
    counts: dict[str, int] = {}
    seen: set[tuple[str, str, str, str, str]] = set()
    for assignment in assignments:
        faculty_key = str(assignment.faculty_id or "").upper()
        if not faculty_key:
            continue
        slot_key = (
            str(assignment.grade_level or "").upper(),
            (assignment.strand or "").upper(),
            (assignment.section or "").upper(),
            (assignment.subject_code or assignment.subject_name or "").upper(),
            faculty_key,
        )
        if slot_key in seen:
            continue
        seen.add(slot_key)
        counts[faculty_key] = counts.get(faculty_key, 0) + 1
    return counts


def _session_bookings(assignments: list[ScheduleAssignment]) -> list[tuple]:
    bookings: list[tuple] = []
    for assignment in assignments:
        strand = (assignment.strand or "").upper()
        section = (assignment.section or "").upper()
        grade = str(assignment.grade_level or "").strip()
        subject = assignment.subject_code or assignment.subject_name or "UNKNOWN"
        faculty_key = str(assignment.faculty_id or "").upper()
        for session in assignment.sessions or []:
            day_index = DAY_NAME_TO_INDEX.get((session.day or "").strip().lower())
            if day_index is None:
                continue
            try:
                start_minutes = parse_clock(session.start)
                end_minutes = parse_clock(session.end)
            except ValueError:
                continue
            room = (session.room or "").strip().upper()
            if not room:
                continue
            bookings.append(
                (
                    room,
                    session.day,
                    day_index,
                    start_minutes,
                    end_minutes,
                    subject,
                    grade,
                    strand,
                    section,
                    faculty_key,
                    _section_key(strand, section, grade),
                )
            )
    return bookings


def validate_for_new_strand(
    existing: list[ScheduleAssignment],
    incoming: list[ScheduleAssignment],
    *,
    teachers: list[dict] | None = None,
    room_capacities: dict[str, int] | None = None,
    class_max_slots: int = DEFAULT_CLASS_MAX_SLOTS,
    require_faculty: bool = True,
) -> ValidationResult:
    """Validate a newly generated strand without failing on other strands' internal issues."""
    conflicts: list[ConflictError] = []

    incoming_result = validate_schedule(
        incoming,
        teachers=teachers,
        room_capacities=room_capacities,
        class_max_slots=class_max_slots,
        require_faculty=require_faculty,
    )
    conflicts.extend(incoming_result.conflicts)

    existing_bookings = _session_bookings(existing)
    incoming_bookings = _session_bookings(incoming)

    for booking_a in existing_bookings:
        (
            room_a,
            day_a,
            day_idx_a,
            start_a,
            end_a,
            subject_a,
            grade_a,
            strand_a,
            section_a,
            faculty_a,
            section_key_a,
        ) = booking_a
        for booking_b in incoming_bookings:
            (
                room_b,
                day_b,
                day_idx_b,
                start_b,
                end_b,
                subject_b,
                grade_b,
                strand_b,
                section_b,
                faculty_b,
                section_key_b,
            ) = booking_b
            if day_idx_a != day_idx_b:
                continue
            if not sessions_overlap(start_a, end_a, start_b, end_b):
                continue
            if room_a == room_b:
                conflicts.append(
                    ConflictError(
                        "ROOM_CONFLICT",
                        f"Room {room_a} double-booked on {day_a} "
                        f"({subject_a} [{strand_a}] overlaps new {subject_b} [{strand_b}]).",
                        {
                            "room": room_a,
                            "day": day_a,
                            "subjects": [subject_a, subject_b],
                            "strands": [strand_a, strand_b],
                        },
                    )
                )
            if faculty_a and faculty_a == faculty_b and section_key_a != section_key_b:
                conflicts.append(
                    ConflictError(
                        "FACULTY_CONFLICT",
                        f"Faculty {faculty_a} assigned to overlapping sections on {day_a} "
                        f"({subject_a} vs new {subject_b}).",
                        {
                            "faculty_id": faculty_a,
                            "day": day_a,
                            "subjects": [subject_a, subject_b],
                        },
                    )
                )

    existing_loads = _assignment_loads(existing)
    incoming_loads = _assignment_loads(incoming)
    for faculty_key, incoming_count in incoming_loads.items():
        total = existing_loads.get(faculty_key, 0) + incoming_count
        if total > MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER:
            conflicts.append(
                ConflictError(
                    "TEACHER_OVERLOAD",
                    f"Faculty {faculty_key} would have {total} assignments "
                    f"(maximum {MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER} per semester).",
                    {
                        "faculty_id": faculty_key,
                        "load": total,
                        "max_load": MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER,
                    },
                )
            )

    return ValidationResult(valid=not conflicts, conflicts=conflicts)


def assignments_from_payload(items: list[dict]) -> list[ScheduleAssignment]:
    assignments: list[ScheduleAssignment] = []
    for item in items or []:
        sessions = []
        for raw_session in item.get("sessions") or []:
            sessions.append(
                ScheduleSession(
                    day=raw_session.get("day") or raw_session.get("day_of_week") or "",
                    start=raw_session.get("start") or raw_session.get("start_time") or "",
                    end=raw_session.get("end") or raw_session.get("end_time") or "",
                    room=raw_session.get("room") or raw_session.get("room_name") or "",
                )
            )
        if not sessions and item.get("day") and item.get("time_slot"):
            start, end = _split_time_slot(item["time_slot"])
            sessions.append(
                ScheduleSession(
                    day=item["day"],
                    start=start,
                    end=end,
                    room=item.get("room") or item.get("room_name") or "",
                )
            )
        assignments.append(
            ScheduleAssignment(
                strand=item.get("strand") or "",
                section=item.get("section") or "",
                subject_code=item.get("subject_code") or item.get("subject") or "",
                subject_name=item.get("subject_name") or item.get("description") or "",
                sessions=sessions,
                faculty_id=item.get("faculty_id"),
                faculty_name=item.get("faculty_name") or "",
                schedule_label=item.get("schedule_label") or "",
                grade_level=str(item.get("gradeLevel") or item.get("grade_level") or "").strip(),
            )
        )
    return assignments


def _split_time_slot(value: str) -> tuple[str, str]:
    text = (value or "").replace(" ", "")
    if "-" not in text:
        raise ValueError(f"Invalid time_slot: {value}")
    start, end = text.split("-", 1)
    return start, end
