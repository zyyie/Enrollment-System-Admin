"""Deterministic conflict-free fallback scheduler (no AI)."""

from __future__ import annotations

import random
import time

from .constants import MAX_PATTERNS_PER_TASK, MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER
from .models import ScheduleAssignment, ScheduleSession, SchedulerInput, TimeSlot
from .room_types import resolve_scheduler_rooms, rooms_for_subject
from .time_slots import (
    DAY_NAMES,
    build_flexible_meeting_patterns,
    build_schedule_label,
    meetings_per_week,
    order_subjects_for_placement,
    pattern_meeting_signature,
    pattern_preference_penalty,
    section_day_counts,
    session_duration_minutes,
)
from .time_utils import DAY_NAME_TO_INDEX, parse_clock, sessions_overlap


def _section_usage_key(grade_level: str, strand: str, section: str) -> str:
    grade = str(grade_level or "").strip().upper()
    strand_key = strand.upper()
    section_key = section.upper()
    if grade:
        return f"{grade}|{strand_key}|{section_key}"
    return f"{strand_key}|{section_key}"


class GreedyScheduler:
    def generate(
        self,
        scheduler_input: SchedulerInput,
        *,
        existing_assignments: list[ScheduleAssignment] | None = None,
        teachers: list[dict] | None = None,
        scheduling_context: dict | None = None,
        reverse_rooms: bool = False,
        reverse_patterns: bool = False,
        shuffle_rooms: bool = False,
        shuffle_patterns: bool = False,
        reverse_subjects: bool = False,
        shuffle_subjects: bool = False,
    ) -> list[ScheduleAssignment]:
        ctx = scheduling_context or {}
        rooms_by_type, room_capacities, fallback_classrooms = resolve_scheduler_rooms(
            scheduler_input, ctx if ctx else None
        )
        rooms = list(fallback_classrooms)
        if not rooms:
            rooms = [room.strip().upper() for room in scheduler_input.rooms if room.strip()] or ["NB101"]
        if reverse_rooms:
            rooms = list(reversed(rooms))
        if shuffle_rooms:
            rng = random.Random(int(time.time() * 1000) % 1_000_000)
            rooms = list(rooms)
            rng.shuffle(rooms)

        grade_level = scheduler_input.grade_level or ""
        section_labels = ["A", "B"][: scheduler_input.sections_per_strand]
        teacher_pool = list(teachers or [])
        pattern_shuffle_seed = int(time.time() * 1000) % 1_000_000 + 17
        subject_seed = 42

        room_usage: list[tuple[int, int, int, str, str, str, str]] = []
        section_usage: list[tuple[str, int, int, int, str]] = []
        faculty_usage: list[tuple[str, str, str, int, int, int, str]] = []

        _seed_usage_from_assignments(existing_assignments or [], room_usage, section_usage, faculty_usage)

        assignments: list[ScheduleAssignment] = []
        parallel_a_signatures: dict[tuple[str, str], set[tuple]] = {}

        for strand in scheduler_input.strands:
            strand_code = strand.upper()
            filtered = [
                subject
                for subject in scheduler_input.subjects
                if subject.get("strand") is None
                or str(subject.get("strand")).upper() == strand_code
            ]
            strand_subjects = order_subjects_for_placement(
                filtered,
                reverse=reverse_subjects,
                shuffle=shuffle_subjects,
                seed=subject_seed,
            )

            for subject_index, subject in enumerate(strand_subjects):
                for section_idx, section in enumerate(section_labels):
                    subject_code = subject.get("code") or subject.get("subject_code") or ""
                    parallel_key = (strand_code, subject_code.upper())
                    units = max(1, int(subject.get("units") or 1))
                    meeting_count = meetings_per_week(units, subject)
                    duration_minutes = session_duration_minutes(units, meeting_count)
                    subject_patterns = build_flexible_meeting_patterns(
                        meeting_count,
                        duration_minutes,
                        rng=None,
                        max_patterns=9999,
                    )
                    if reverse_patterns:
                        subject_patterns = list(reversed(subject_patterns))
                    if shuffle_patterns:
                        pattern_rng = random.Random(pattern_shuffle_seed + subject_index)
                        pattern_rng.shuffle(subject_patterns)

                    placement_index = section_idx * 97 + subject_index * 13
                    section_key = _section_usage_key(grade_level, strand_code, section)
                    day_counts = section_day_counts(section_usage, section_key)
                    ranked_patterns = sorted(
                        subject_patterns,
                        key=lambda pattern: pattern_preference_penalty(
                            pattern,
                            task_id=placement_index,
                            section_index=section_idx,
                            section_day_counts=day_counts,
                        ),
                    )
                    pattern_batches = [
                        ranked_patterns[:MAX_PATTERNS_PER_TASK],
                        ranked_patterns,
                    ]

                    subject_rooms = rooms_for_subject(
                        subject,
                        strand=strand_code,
                        rooms_by_type=rooms_by_type,
                        fallback_classrooms=rooms,
                    ) or rooms
                    rotated_rooms = (
                        subject_rooms[(placement_index + section_idx * 3) % len(subject_rooms) :]
                        + subject_rooms[: (placement_index + section_idx * 3) % len(subject_rooms)]
                    )

                    placed = False
                    for batch_index, rotated_patterns in enumerate(pattern_batches):
                        if placed:
                            break
                        offset = placement_index % max(1, len(rotated_patterns))
                        rotated_patterns = (
                            rotated_patterns[offset:] + rotated_patterns[:offset]
                        )
                        for pattern in rotated_patterns:
                            meeting_sig = pattern_meeting_signature(pattern)
                            if section_idx == 1 and meeting_sig in parallel_a_signatures.get(parallel_key, set()):
                                continue
                            for room in rotated_rooms:
                                faculty_id, faculty_name = _pick_faculty(
                                    teacher_pool,
                                    strand_code,
                                    pattern,
                                    faculty_usage,
                                    preferred_id=subject.get("faculty_id"),
                                )
                                if (
                                    faculty_id
                                    and _faculty_assignment_count(faculty_id, faculty_usage)
                                    >= MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER
                                ):
                                    faculty_id, faculty_name = None, ""
                                elif not faculty_id:
                                    faculty_id, faculty_name = None, ""

                                if _pattern_conflicts(
                                    pattern,
                                    room,
                                    strand_code,
                                    section,
                                    subject_code,
                                    room_usage,
                                    section_usage,
                                    faculty_usage,
                                    faculty_id,
                                    grade_level=grade_level,
                                ):
                                    continue

                                sessions = [
                                    ScheduleSession(
                                        day=DAY_NAMES[slot.day],
                                        start=_format_minutes(slot.start_minutes),
                                        end=_format_minutes(slot.end_minutes),
                                        room=room,
                                    )
                                    for slot in pattern
                                ]
                                assignment = ScheduleAssignment(
                                    strand=strand_code,
                                    section=section,
                                    subject_code=subject_code,
                                    subject_name=subject.get("description")
                                    or subject.get("name")
                                    or subject.get("subject_name")
                                    or "",
                                    sessions=sessions,
                                    faculty_id=faculty_id,
                                    faculty_name=faculty_name or "",
                                    grade_level=grade_level,
                                )
                                assignment.schedule_label = build_schedule_label(pattern)
                                assignments.append(assignment)
                                _mark_usage(
                                    pattern,
                                    room,
                                    strand_code,
                                    section,
                                    subject_code,
                                    room_usage,
                                    section_usage,
                                    faculty_usage,
                                    faculty_id,
                                    grade_level=grade_level,
                                )
                                if section_idx == 0:
                                    parallel_a_signatures.setdefault(parallel_key, set()).add(meeting_sig)
                                placed = True
                                break
                            if placed:
                                break
                    if not placed:
                        from enrollment_curriculum import format_section_name

                        section_label = format_section_name(strand_code, grade_level, section)
                        raise RuntimeError(
                            f"Could not place {subject.get('code')} for {strand_code} "
                            f"({section_label}) — try deleting old saved schedules first."
                        )

        return assignments


def _pick_faculty(
    teachers: list[dict],
    strand: str,
    pattern: list[TimeSlot],
    faculty_usage: list,
    *,
    preferred_id: str | None = None,
) -> tuple[str | None, str | None]:
    if not teachers:
        return None, None

    strand = strand.upper()
    candidates: list[tuple[int, dict]] = []
    for teacher in teachers:
        teacher_strands = [item.upper() for item in (teacher.get("strands") or [])]
        if not teacher_strands or strand not in teacher_strands:
            continue
        faculty_id = teacher.get("faculty_id")
        if not faculty_id:
            continue
        if _faculty_assignment_count(faculty_id, faculty_usage) >= MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER:
            continue
        load = _faculty_assignment_count(faculty_id, faculty_usage)
        if preferred_id and str(faculty_id).upper() == str(preferred_id).upper():
            load -= 100
        candidates.append((load, teacher))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: item[0])
    for _, teacher in candidates:
        faculty_id = teacher.get("faculty_id")
        faculty_name = teacher.get("name") or ""
        if _faculty_available(faculty_id, pattern, faculty_usage):
            return faculty_id, faculty_name

    fallback = candidates[0][1]
    faculty_id = fallback.get("faculty_id")
    if _faculty_available(faculty_id, pattern, faculty_usage):
        return faculty_id, fallback.get("name") or ""
    return None, None


def _faculty_assignment_count(faculty_id: str | None, faculty_usage: list) -> int:
    if not faculty_id:
        return 0
    faculty_key = str(faculty_id).upper()
    assignments = {
        (used[1], used[2], used[6])
        for used in faculty_usage
        if used[0] == faculty_key
    }
    return len(assignments)


def _faculty_available(
    faculty_id: str | None,
    pattern: list[TimeSlot],
    faculty_usage: list,
) -> bool:
    if not faculty_id:
        return True
    faculty_key = str(faculty_id).upper()
    for slot in pattern:
        start = slot.start_minutes
        end = slot.end_minutes
        for (
            used_faculty,
            _used_strand,
            _used_section,
            used_day,
            used_start,
            used_end,
            _subject,
        ) in faculty_usage:
            if used_faculty != faculty_key or used_day != slot.day:
                continue
            if sessions_overlap(start, end, used_start, used_end):
                return False
    return True


def _seed_usage_from_assignments(
    assignments: list[ScheduleAssignment],
    room_usage: list,
    section_usage: list,
    faculty_usage: list,
) -> None:
    for assignment in assignments:
        strand = (assignment.strand or "").upper()
        section = (assignment.section or "").upper()
        if not strand or not section:
            continue
        grade = str(assignment.grade_level or "").strip()
        section_key = _section_usage_key(grade, strand, section)
        subject_code = assignment.subject_code or assignment.subject_name or "UNKNOWN"
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
            room_usage.append(
                (day_index, start_minutes, end_minutes, room, strand, section, subject_code.upper())
            )
            section_usage.append((section_key, day_index, start_minutes, end_minutes, subject_code))
            if assignment.faculty_id:
                faculty_usage.append(
                    (
                        str(assignment.faculty_id).upper(),
                        strand,
                        section,
                        day_index,
                        start_minutes,
                        end_minutes,
                        subject_code,
                    )
                )


def _format_minutes(minutes: int) -> str:
    hour = minutes // 60
    minute = minutes % 60
    suffix = "am" if hour < 12 else "pm"
    display = hour % 12 or 12
    if minute:
        return f"{display}:{minute:02d}{suffix}"
    return f"{display}:00{suffix}"


def _pattern_conflicts(
    pattern: list[TimeSlot],
    room: str,
    strand: str,
    section: str,
    subject_code: str,
    room_usage,
    section_usage,
    faculty_usage,
    faculty_id,
    *,
    grade_level: str = "",
) -> bool:
    subject_code = (subject_code or "").upper()
    for slot in pattern:
        start = slot.start_minutes
        end = slot.end_minutes
        day = slot.day

        for (
            used_day,
            used_start,
            used_end,
            used_room,
            used_strand,
            used_section,
            _used_subject,
        ) in room_usage:
            if used_day != day or used_room != room:
                continue
            if sessions_overlap(start, end, used_start, used_end):
                return True

        section_key = _section_usage_key(grade_level, strand, section)
        for used_key, used_day, used_start, used_end, _subject in section_usage:
            if used_key != section_key or used_day != day:
                continue
            if sessions_overlap(start, end, used_start, used_end):
                return True

        if faculty_id:
            faculty_key = str(faculty_id).upper()
            for (
                used_faculty,
                used_strand,
                used_section,
                used_day,
                used_start,
                used_end,
                _subject,
            ) in faculty_usage:
                if used_faculty != faculty_key or used_day != day:
                    continue
                if used_strand == strand and used_section == section:
                    continue
                if sessions_overlap(start, end, used_start, used_end):
                    return True

        for (
            used_day,
            used_start,
            used_end,
            used_room,
            used_strand,
            used_section,
            _used_subject,
        ) in room_usage:
            if used_day != day or used_room != room or used_strand != strand:
                continue
            if used_section == section:
                continue
            if sessions_overlap(start, end, used_start, used_end):
                return True

    return False


def _mark_usage(
    pattern: list[TimeSlot],
    room: str,
    strand: str,
    section: str,
    subject_code: str,
    room_usage,
    section_usage,
    faculty_usage,
    faculty_id,
    *,
    grade_level: str = "",
):
    section_key = _section_usage_key(grade_level, strand, section)
    subject_code = (subject_code or "").upper()
    for slot in pattern:
        start = slot.start_minutes
        end = slot.end_minutes
        room_usage.append((slot.day, start, end, room, strand, section, subject_code))
        section_usage.append((section_key, slot.day, start, end, subject_code))
        if faculty_id:
            faculty_usage.append(
                (
                    str(faculty_id).upper(),
                    strand,
                    section,
                    slot.day,
                    start,
                    end,
                    subject_code,
                )
            )
