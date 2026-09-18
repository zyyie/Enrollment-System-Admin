"""Conflict-free class scheduling using Google OR-Tools CP-SAT.

Each (strand, section, subject) is a task. Feasible placements combine a meeting
pattern, room, and qualified teacher. CP-SAT picks one placement per task while
respecting room, teacher, section, and cross-strand constraints.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from .constants import (
    CONGESTED_OCCUPIED_KEYS_THRESHOLD,
    DEFAULT_CLASS_MAX_SLOTS,
    MAX_CANDIDATES_COLLECT,
    MAX_CANDIDATES_PER_TASK,
    MAX_PATTERNS_PER_TASK,
    MAX_ROOMS_PER_PATTERN,
    MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER,
    MAX_TEACHERS_PER_PATTERN,
    ORTOOLS_FAST_TIME_LIMIT_SEC,
    ORTOOLS_RETRY_ATTEMPTS,
)
from .models import ScheduleAssignment, ScheduleSession, SchedulerInput, TimeSlot
from .room_types import rooms_for_subject
from .time_slots import (
    DAY_NAMES,
    build_flexible_meeting_patterns,
    build_schedule_label,
    meetings_per_week,
    pattern_meeting_signature,
    pattern_preference_penalty,
    session_duration_minutes,
)
from .time_utils import DAY_NAME_TO_INDEX, parse_clock


# ---------------------------------------------------------------------------
# Teacher availability
# ---------------------------------------------------------------------------

def _default_availability_window() -> tuple[set[int], int, int]:
    """Weekdays Mon–Fri, 8:00 AM – 5:00 PM."""
    return set(range(5)), 8 * 60, 17 * 60


def parse_teacher_availability(availability: str | None) -> tuple[set[int], int, int]:
    """Parse simple availability strings like 'Mon–Fri 8am–5pm'."""
    days, start, end = _default_availability_window()
    text = (availability or "").strip().lower()
    if not text:
        return days, start, end

    if "sat" in text:
        days.add(5)
    if "mon" in text and "fri" in text:
        days = set(range(5))

    import re

    times = re.findall(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text)
    if len(times) >= 2:
        start = _clock_parts_to_minutes(times[0])
        end = _clock_parts_to_minutes(times[1])
    return days, start, end


def _clock_parts_to_minutes(parts: tuple) -> int:
    hour = int(parts[0])
    minute = int(parts[1] or 0)
    suffix = parts[2]
    if suffix == "am" and hour == 12:
        hour = 0
    elif suffix == "pm" and hour != 12:
        hour += 12
    return hour * 60 + minute


def teacher_available_for_pattern(
    teacher: dict[str, Any],
    pattern: list[TimeSlot],
) -> bool:
    """Return True when every session in the pattern fits the teacher's availability."""
    days, avail_start, avail_end = parse_teacher_availability(teacher.get("availability"))
    for slot in pattern:
        if slot.day not in days:
            return False
        if slot.start_minutes < avail_start or slot.end_minutes > avail_end:
            return False
    return True


def teacher_qualifies_for_strand(teacher: dict[str, Any], strand: str) -> bool:
    """Teachers must belong to the target strand (one strand per teacher)."""
    strand = strand.upper()
    teacher_strands = [item.upper() for item in (teacher.get("strands") or [])]
    return bool(teacher_strands) and strand in teacher_strands


# ---------------------------------------------------------------------------
# Constraint keys (shared with conflict_validator rules)
# ---------------------------------------------------------------------------

def _format_minutes(minutes: int) -> str:
    hour = minutes // 60
    minute = minutes % 60
    suffix = "am" if hour < 12 else "pm"
    display = hour % 12 or 12
    if minute:
        return f"{display}:{minute:02d}{suffix}"
    return f"{display}:00{suffix}"


def _subject_needs_lab(subject: dict[str, Any]) -> bool:
    lab_units = subject.get("lab") or subject.get("lab_hours") or 0
    if lab_units:
        return True
    name = f"{subject.get('description') or ''} {subject.get('name') or ''}".lower()
    return "laboratory" in name or " lab" in name


def _required_hours(subject: dict[str, Any]) -> int:
    """Weekly contact hours (uses curriculum units, minimum 1 hour)."""
    return max(1, int(subject.get("units") or 1))


def _faculty_load_counts(assignments: list[ScheduleAssignment]) -> dict[str, int]:
    """Count subject-section assignments per faculty (not sessions)."""
    counts: dict[str, int] = {}
    for assignment in assignments:
        faculty_id = assignment.faculty_id
        if not faculty_id:
            continue
        key = str(faculty_id).upper()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _pattern_preference_penalty(
    faculty_id: str | None,
    existing_loads: dict[str, int],
) -> int:
    """Soft preference: assign teachers with lighter semester loads first."""
    if not faculty_id:
        return 100
    return existing_loads.get(str(faculty_id).upper(), 0) * 5


@dataclass
class ScheduleCandidate:
    """One feasible placement for a scheduling task."""

    task_id: int
    pattern: list[TimeSlot]
    room: str
    faculty_id: str | None
    faculty_name: str
    constraint_keys: list[str] = field(default_factory=list)
    preference_penalty: int = 0


@dataclass
class SchedulingTask:
    """One subject that must be scheduled for a strand section."""

    task_id: int
    strand: str
    section: str
    subject: dict[str, Any]
    grade_level: str = ""

    @property
    def subject_code(self) -> str:
        return (self.subject.get("code") or self.subject.get("subject_code") or "").upper()

    @property
    def required_hours(self) -> int:
        return _required_hours(self.subject)


def _hourly_slot_starts(start: int, end: int) -> list[int]:
    """Return each fixed 30-minute grid block that overlaps [start, end)."""
    from .time_slots import SCHOOL_CLOSE_WEEKDAY, SCHOOL_OPEN
    from .time_utils import sessions_overlap

    step = 30
    slots: list[int] = []
    cursor = SCHOOL_OPEN
    while cursor + step <= SCHOOL_CLOSE_WEEKDAY:
        if sessions_overlap(start, end, cursor, cursor + step):
            slots.append(cursor)
        cursor += step
    return slots


def _section_constraint_key(grade_level: str, strand: str, section: str) -> str:
    grade = str(grade_level or "").strip().upper()
    strand_key = strand.upper()
    section_key = section.upper()
    if grade:
        return f"{grade}|{strand_key}|{section_key}"
    return f"{strand_key}|{section_key}"


def _session_constraint_keys(
    *,
    grade_level: str,
    strand: str,
    section: str,
    subject_code: str,
    room: str,
    day: int,
    start: int,
    end: int,
    faculty_id: str | None,
) -> list[str]:
    """Build resource keys using hourly slots so overlaps always share a key."""
    keys: list[str] = []
    section_key = _section_constraint_key(grade_level, strand, section)
    for slot_start in _hourly_slot_starts(start, end):
        keys.append(f"room:{room}:{day}:{slot_start}")
        keys.append(f"section:{section_key}:{day}:{slot_start}")
        if faculty_id:
            keys.append(f"faculty:{str(faculty_id).upper()}:{day}:{slot_start}")
    return keys


def _occupied_keys_from_assignments(
    assignments: list[ScheduleAssignment],
) -> set[str]:
    """Extract constraint keys already taken by existing schedules."""
    occupied: set[str] = set()
    for assignment in assignments:
        strand = (assignment.strand or "").upper()
        section = (assignment.section or "").upper()
        subject_code = (assignment.subject_code or "").upper()
        for session in assignment.sessions or []:
            day_index = DAY_NAME_TO_INDEX.get((session.day or "").strip().lower())
            if day_index is None:
                continue
            try:
                start = parse_clock(session.start)
                end = parse_clock(session.end)
            except ValueError:
                continue
            room = (session.room or "").strip().upper()
            if not room:
                continue
            for key in _session_constraint_keys(
                grade_level=assignment.grade_level or "",
                strand=strand,
                section=section,
                subject_code=subject_code,
                room=room,
                day=day_index,
                start=start,
                end=end,
                faculty_id=assignment.faculty_id,
            ):
                occupied.add(key)
    return occupied


def _build_tasks(scheduler_input: SchedulerInput) -> list[SchedulingTask]:
    """Expand strand/section/subject combinations into atomic scheduling tasks."""
    section_labels = ["A", "B"][: scheduler_input.sections_per_strand]
    tasks: list[SchedulingTask] = []
    task_id = 0

    for strand in scheduler_input.strands:
        strand_code = strand.upper()
        strand_subjects = [
            subject
            for subject in scheduler_input.subjects
            if subject.get("strand") is None
            or str(subject.get("strand")).upper() == strand_code
        ]
        for subject in strand_subjects:
            for section in section_labels:
                tasks.append(
                    SchedulingTask(
                        task_id=task_id,
                        strand=strand_code,
                        section=section,
                        subject=subject,
                        grade_level=scheduler_input.grade_level,
                    )
                )
                task_id += 1
    return tasks


def _resolve_rooms(
    scheduler_input: SchedulerInput,
    scheduling_context: dict[str, Any] | None,
) -> tuple[dict[str, list[str]], dict[str, int], list[str]]:
    """Return (rooms_by_type, room_capacities, fallback_classrooms)."""
    from .room_types import resolve_scheduler_rooms

    return resolve_scheduler_rooms(scheduler_input, scheduling_context)


def build_candidates(
    tasks: list[SchedulingTask],
    *,
    scheduler_input: SchedulerInput,
    teachers: list[dict[str, Any]] | None,
    occupied_keys: set[str],
    scheduling_context: dict[str, Any] | None = None,
    existing_faculty_loads: dict[str, int] | None = None,
    random_seed: int | None = None,
) -> dict[int, list[ScheduleCandidate]]:
    """Enumerate feasible (pattern, room, teacher) options for every task."""
    rooms_by_type, room_capacities, fallback_classrooms = _resolve_rooms(
        scheduler_input, scheduling_context
    )
    teacher_pool = list(teachers or [])
    section_labels = ["A", "B"][: scheduler_input.sections_per_strand]
    class_max_slots = int(
        (scheduling_context or {}).get("class_max_slots")
        or DEFAULT_CLASS_MAX_SLOTS
    )
    faculty_loads = dict(existing_faculty_loads or {})
    congested = len(occupied_keys) >= CONGESTED_OCCUPIED_KEYS_THRESHOLD or bool(
        (scheduling_context or {}).get("scheduling_congested")
    )
    max_collect = 720 if congested else MAX_CANDIDATES_COLLECT
    max_per_task = 280 if congested else MAX_CANDIDATES_PER_TASK

    candidates_by_task: dict[int, list[ScheduleCandidate]] = {}

    for task in tasks:
        section_index = section_labels.index(task.section) if task.section in section_labels else 0
        room_pool = rooms_for_subject(
            task.subject,
            strand=task.strand,
            rooms_by_type=rooms_by_type,
            fallback_classrooms=fallback_classrooms,
        )
        room_pool = [
            room for room in room_pool
            if int(room_capacities.get(room, DEFAULT_CLASS_MAX_SLOTS)) >= class_max_slots
        ]
        if not room_pool:
            room_pool = [
                room for room in fallback_classrooms
                if int(room_capacities.get(room, DEFAULT_CLASS_MAX_SLOTS)) >= class_max_slots
            ] or fallback_classrooms

        meeting_count = meetings_per_week(task.required_hours, task.subject)
        duration_minutes = session_duration_minutes(task.required_hours, meeting_count)
        task_patterns = build_flexible_meeting_patterns(
            meeting_count,
            duration_minutes,
            rng=None,
            max_patterns=MAX_PATTERNS_PER_TASK,
        )
        offset = (
            task.task_id * 11
            + section_index * 5
            + int(random_seed or 0)
        ) % max(len(task_patterns), 1)
        task_patterns = task_patterns[offset:] + task_patterns[:offset]
        room_offset = task.task_id % max(len(room_pool), 1)
        rotated_rooms = room_pool[room_offset:] + room_pool[:room_offset]
        max_rooms = (
            min(len(rotated_rooms), 20) if congested else MAX_ROOMS_PER_PATTERN
        )
        rooms_to_try = rotated_rooms[:max_rooms]

        task_candidates: list[ScheduleCandidate] = []
        strand_teachers = [
            teacher for teacher in teacher_pool
            if teacher_qualifies_for_strand(teacher, task.strand)
        ]

        for pattern in task_patterns:
            if len(task_candidates) >= max_collect:
                break
            if len({slot.day for slot in pattern}) != len(pattern):
                continue

            for room in rooms_to_try:
                if len(task_candidates) >= max_collect:
                    break
                teacher_options: list[tuple[str | None, str | None, int]] = []
                for teacher in strand_teachers:
                    faculty_id = teacher.get("faculty_id")
                    if not faculty_id:
                        continue
                    faculty_key = str(faculty_id).upper()
                    load = faculty_loads.get(faculty_key, 0)
                    if load >= MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER:
                        continue
                    if not teacher_available_for_pattern(teacher, pattern):
                        continue
                    teacher_options.append((faculty_id, teacher.get("name") or "", load))

                teacher_options.sort(key=lambda item: item[2])
                teacher_options = [
                    (faculty_id, faculty_name)
                    for faculty_id, faculty_name, _load in teacher_options[:MAX_TEACHERS_PER_PATTERN]
                ]
                if (None, None) not in teacher_options:
                    teacher_options.append((None, None))

                for faculty_id, faculty_name in teacher_options:
                    if len(task_candidates) >= max_collect:
                        break
                    keys: list[str] = []
                    for slot in pattern:
                        keys.extend(
                            _session_constraint_keys(
                                grade_level=task.grade_level or scheduler_input.grade_level,
                                strand=task.strand,
                                section=task.section,
                                subject_code=task.subject_code,
                                room=room,
                                day=slot.day,
                                start=slot.start_minutes,
                                end=slot.end_minutes,
                                faculty_id=faculty_id,
                            )
                        )
                    if any(key in occupied_keys for key in keys):
                        continue

                    penalty = _pattern_preference_penalty(faculty_id, faculty_loads)
                    penalty += pattern_preference_penalty(
                        pattern,
                        task_id=task.task_id,
                        section_index=section_index,
                    )

                    task_candidates.append(
                        ScheduleCandidate(
                            task_id=task.task_id,
                            pattern=pattern,
                            room=room,
                            faculty_id=faculty_id,
                            faculty_name=faculty_name or "",
                            constraint_keys=keys,
                            preference_penalty=penalty,
                        )
                    )

        task_candidates.sort(
            key=lambda candidate: (
                candidate.preference_penalty,
                candidate.pattern[0].day,
                candidate.pattern[0].start_minutes,
                candidate.room,
            )
        )
        if len(task_candidates) > max_per_task:
            unassigned = [item for item in task_candidates if not item.faculty_id]
            assigned = [item for item in task_candidates if item.faculty_id]
            keep_unassigned = unassigned[: max(24, max_per_task // 4)]
            remaining = max_per_task - len(keep_unassigned)
            task_candidates = keep_unassigned + assigned[:remaining]

        candidates_by_task[task.task_id] = task_candidates

    return candidates_by_task


def solve_with_cp_sat(
    tasks: list[SchedulingTask],
    candidates_by_task: dict[int, list[ScheduleCandidate]],
    *,
    time_limit_sec: float = 30.0,
    existing_faculty_loads: dict[str, int] | None = None,
    random_seed: int | None = None,
) -> dict[int, ScheduleCandidate]:
    """Run CP-SAT: exactly one candidate per task, no shared constraint keys."""
    model = cp_model.CpModel()
    choice_vars: dict[int, list[cp_model.IntVar]] = {}
    candidate_lookup: dict[tuple[int, int], ScheduleCandidate] = {}
    base_loads = dict(existing_faculty_loads or {})

    for task in tasks:
        options = candidates_by_task.get(task.task_id) or []
        if not options:
            raise RuntimeError(
                f"No feasible slot for {task.subject_code} "
                f"({task.strand} Section {task.section}) — "
                "check room availability, faculty load (max 3/semester), or strand teachers."
            )

        vars_for_task: list[cp_model.IntVar] = []
        for index, candidate in enumerate(options):
            var = model.NewBoolVar(f"t{task.task_id}_c{index}")
            vars_for_task.append(var)
            candidate_lookup[(task.task_id, index)] = candidate
        model.Add(sum(vars_for_task) == 1)
        choice_vars[task.task_id] = vars_for_task

    constraint_groups: dict[str, list[cp_model.IntVar]] = {}
    for task in tasks:
        for index, var in enumerate(choice_vars[task.task_id]):
            candidate = candidate_lookup[(task.task_id, index)]
            for key in candidate.constraint_keys:
                constraint_groups.setdefault(key, []).append(var)

    for involved in constraint_groups.values():
        if len(involved) > 1:
            model.Add(sum(involved) <= 1)

    faculty_vars: dict[str, list[cp_model.IntVar]] = {}
    for task in tasks:
        for index, var in enumerate(choice_vars[task.task_id]):
            candidate = candidate_lookup[(task.task_id, index)]
            if candidate.faculty_id:
                faculty_key = str(candidate.faculty_id).upper()
                faculty_vars.setdefault(faculty_key, []).append(var)

    for faculty_key, involved in faculty_vars.items():
        max_allowed = MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER - base_loads.get(faculty_key, 0)
        if max_allowed < 0:
            max_allowed = 0
        if len(involved) > max_allowed:
            model.Add(sum(involved) <= max_allowed)

    tasks_by_parallel: dict[tuple[str, str, str], dict[str, SchedulingTask]] = {}
    for task in tasks:
        section_key = str(task.section or "").upper()
        if section_key not in ("A", "B"):
            continue
        parallel_key = (task.strand, task.subject_code, task.grade_level or "")
        tasks_by_parallel.setdefault(parallel_key, {})[section_key] = task

    for paired in tasks_by_parallel.values():
        task_a = paired.get("A")
        task_b = paired.get("B")
        if not task_a or not task_b:
            continue
        vars_a = choice_vars.get(task_a.task_id) or []
        vars_b = choice_vars.get(task_b.task_id) or []
        sig_vars_a: dict[tuple, list[cp_model.IntVar]] = defaultdict(list)
        sig_vars_b: dict[tuple, list[cp_model.IntVar]] = defaultdict(list)
        for index_a, var_a in enumerate(vars_a):
            candidate_a = candidate_lookup[(task_a.task_id, index_a)]
            sig_a = pattern_meeting_signature(candidate_a.pattern)
            sig_vars_a[sig_a].append(var_a)
        for index_b, var_b in enumerate(vars_b):
            candidate_b = candidate_lookup[(task_b.task_id, index_b)]
            sig_b = pattern_meeting_signature(candidate_b.pattern)
            sig_vars_b[sig_b].append(var_b)
        for sig in set(sig_vars_a).intersection(sig_vars_b):
            model.Add(sum(sig_vars_a[sig]) + sum(sig_vars_b[sig]) <= 1)

    objective_terms: list[cp_model.IntVar] = []
    for task in tasks:
        for index, var in enumerate(choice_vars[task.task_id]):
            penalty = candidate_lookup[(task.task_id, index)].preference_penalty
            if penalty:
                weighted = model.NewIntVar(0, penalty, f"penalty_t{task.task_id}_c{index}")
                model.Add(weighted == penalty).OnlyEnforceIf(var)
                model.Add(weighted == 0).OnlyEnforceIf(var.Not())
                objective_terms.append(weighted)
    if objective_terms:
        model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_sec
    if random_seed is not None:
        solver.parameters.random_seed = random_seed
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        missing = [
            task.subject_code
            for task in tasks
            if not candidates_by_task.get(task.task_id)
        ]
        detail = f" Missing options for: {', '.join(missing)}." if missing else ""
        if not missing:
            tight = sorted(
                (
                    (task, len(candidates_by_task.get(task.task_id) or []))
                    for task in tasks
                ),
                key=lambda item: item[1],
            )[:5]
            tight_parts = [
                f"{task.subject_code} ({count})"
                for task, count in tight
                if count <= 8
            ]
            if tight_parts:
                detail = f" Tightest subjects: {', '.join(tight_parts)}."
        raise RuntimeError(f"OR-Tools could not find a conflict-free schedule.{detail}")

    selected: dict[int, ScheduleCandidate] = {}
    for task in tasks:
        for index, var in enumerate(choice_vars[task.task_id]):
            if solver.Value(var) == 1:
                selected[task.task_id] = candidate_lookup[(task.task_id, index)]
                break
    return selected


def candidates_to_assignments(
    tasks: list[SchedulingTask],
    selected: dict[int, ScheduleCandidate],
) -> list[ScheduleAssignment]:
    """Convert solver output into ScheduleAssignment objects."""
    assignments: list[ScheduleAssignment] = []

    for task in tasks:
        candidate = selected[task.task_id]
        sessions = [
            ScheduleSession(
                day=DAY_NAMES[slot.day],
                start=_format_minutes(slot.start_minutes),
                end=_format_minutes(slot.end_minutes),
                room=candidate.room,
            )
            for slot in candidate.pattern
        ]
        assignment = ScheduleAssignment(
            strand=task.strand,
            section=task.section,
            subject_code=task.subject_code,
            subject_name=(
                task.subject.get("description")
                or task.subject.get("name")
                or task.subject.get("subject_name")
                or ""
            ),
            sessions=sessions,
            faculty_id=candidate.faculty_id,
            faculty_name=candidate.faculty_name,
            grade_level=task.grade_level,
        )
        assignment.schedule_label = build_schedule_label(candidate.pattern)
        assignments.append(assignment)

    return assignments


class OrtoolsScheduler:
    """Google OR-Tools scheduling engine."""

    def generate(
        self,
        scheduler_input: SchedulerInput,
        *,
        existing_assignments: list[ScheduleAssignment] | None = None,
        teachers: list[dict[str, Any]] | None = None,
        scheduling_context: dict[str, Any] | None = None,
        time_limit_sec: float = ORTOOLS_FAST_TIME_LIMIT_SEC,
        random_seed: int | None = None,
    ) -> list[ScheduleAssignment]:
        """Build a conflict-free schedule for all sections in one OR-Tools solve."""
        tasks = _build_tasks(scheduler_input)
        if not tasks:
            return []

        existing = list(existing_assignments or [])
        occupied = _occupied_keys_from_assignments(existing)
        faculty_loads = _faculty_load_counts(existing)
        seed = int(random_seed if random_seed is not None else time.time() * 1000) % 1_000_000

        candidates_by_task = build_candidates(
            tasks,
            scheduler_input=scheduler_input,
            teachers=teachers,
            occupied_keys=occupied,
            scheduling_context=scheduling_context,
            existing_faculty_loads=faculty_loads,
            random_seed=seed,
        )
        selected = solve_with_cp_sat(
            tasks,
            candidates_by_task,
            time_limit_sec=time_limit_sec,
            existing_faculty_loads=faculty_loads,
            random_seed=seed,
        )
        return candidates_to_assignments(tasks, selected)
