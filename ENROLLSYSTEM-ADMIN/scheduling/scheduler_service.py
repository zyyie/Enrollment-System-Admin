"""Orchestrates OR-Tools schedule generation, validation, and persistence."""

from __future__ import annotations

from typing import Any

from enrollment_curriculum import (
    ENROLLMENT_CURRICULUM,
    ENROLLMENT_SECTION_NAMES_BY_GRADE,
    ENROLLMENT_STRANDS,
    ENROLLMENT_TRACKS,
    STRAND_TRACK,
)

from .cloud_ai_client import CloudAIClient
from .schedule_dedupe import dedupe_schedule_entries, exclude_regenerating_strand_schedules
from .schedule_coverage import count_by_strand, is_complete
from .conflict_validator import (
    assignments_from_payload,
    blocking_saved_conflicts,
    blocking_saved_conflicts_for_strand,
    validate_for_new_strand,
    validate_schedule,
)
from .constants import CONGESTED_EXISTING_THRESHOLD, MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER
from .faculty_assigner import assign_faculty_to_assignments
from .models import ScheduleAssignment, SchedulerInput
from .ortools_scheduler import _faculty_load_counts
from .scheduling_context import build_scheduling_context
from .smart_scheduler import SmartScheduler
from .time_slots import DAY_NAMES, default_time_slot_labels
from .time_slots import is_applied_subject


from .constants import DEFAULT_SCHEDULER_ROOMS

DEFAULT_ROOMS = DEFAULT_SCHEDULER_ROOMS


def compute_ai_cooldown_sec(progress_log: list[dict[str, str]], source: str) -> int:
    """OR-Tools runs locally — no rate-limit cooldown between strands."""
    del progress_log
    if source in ("ortools", "smart_ai_fallback"):
        return 0
    return 0


def _strand_success_payload(
    *,
    strand_code: str,
    source: str,
    assignments: list[ScheduleAssignment],
    existing_assignments: list[ScheduleAssignment],
    progress_log: list[dict[str, str]],
    teachers: list[dict] | None = None,
    scheduling_context: dict[str, Any] | None = None,
    ai_error: str | None = None,
    grade_level: str = "Grade 12",
) -> dict[str, Any]:
    assign_faculty_to_assignments(assignments, teachers or [], existing_assignments=existing_assignments)
    combined = list(existing_assignments)
    combined.extend(assignments)
    validation = validate_schedule(
        combined,
        teachers=teachers,
        room_capacities=(scheduling_context or {}).get("room_capacities"),
        class_max_slots=int((scheduling_context or {}).get("class_max_slots") or 40),
    )
    cooldown_sec = compute_ai_cooldown_sec(progress_log, source)
    teacher_loads = _build_teacher_load_summary(combined, teachers or [])
    schedule_rows = []
    for item in assignments:
        row = item.to_dict()
        row["gradeLevel"] = grade_level
        schedule_rows.append(row)
    schedule_rows = dedupe_schedule_entries(schedule_rows)
    return {
        "success": validation.valid,
        "strand": strand_code,
        "source": source,
        "ai_error": ai_error,
        "progress": progress_log,
        "validation": validation.to_dict(),
        "count": len(schedule_rows),
        "strand_count": len(schedule_rows),
        "schedules": schedule_rows,
        "gradeLevel": grade_level,
        "teacher_loads": teacher_loads,
        "combined_valid": validation.valid,
        "cooldown_sec": cooldown_sec,
        "error": None if validation.valid else (
            f"Schedule has {len(validation.conflicts)} conflict(s). "
            "Check room, faculty load (max 3/semester), or strand assignment."
        ),
    }


def _build_teacher_load_summary(
    assignments: list[ScheduleAssignment],
    teachers: list[dict],
) -> list[dict[str, Any]]:
    counts = _faculty_load_counts(assignments)
    names = {
        str(teacher.get("faculty_id", "")).upper(): teacher.get("name") or ""
        for teacher in teachers
        if teacher.get("faculty_id")
    }
    summary = []
    for faculty_id, load in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        summary.append({
            "faculty_id": faculty_id,
            "faculty_name": names.get(faculty_id, faculty_id),
            "load": load,
            "max_load": MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER,
            "label": f"{names.get(faculty_id, faculty_id)} — {load}/{MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER} loads",
        })
    return summary


class SchedulerService:
    def __init__(
        self,
        *,
        groq_api_key: str = "",
        groq_model: str = "llama-3.1-8b-instant",
        openrouter_api_key: str = "",
        openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free",
        gemini_api_key: str = "",
        gemini_model: str = "gemini-2.0-flash",
        rest_get=None,
    ):
        self._rest_get = rest_get
        self.cloud_ai = CloudAIClient(
            groq_api_key=groq_api_key,
            groq_model=groq_model,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
        )
        self.smart = SmartScheduler()

    def get_default_config(self) -> dict[str, Any]:
        return {
            "strands": ENROLLMENT_STRANDS,
            "tracks": ENROLLMENT_TRACKS,
            "strand_tracks": STRAND_TRACK,
            "sections_per_strand": 2,
            "rooms": DEFAULT_ROOMS,
            "days": DAY_NAMES[:5],
            "time_slots": default_time_slot_labels(include_saturday=False),
            "grade_levels": ["Grade 11", "Grade 12"],
            "semester_codes": ["1st", "2nd"],
            "sectionNamesByGrade": ENROLLMENT_SECTION_NAMES_BY_GRADE,
            "scheduler_mode": "ortools",
            "requires_api_key": False,
            "ai_model_ready": True,
            "ai_provider": "ortools",
            "ai_provider_label": "Google OR-Tools",
            "ai_model": "cp-sat",
            "ai_providers": [{"name": "ortools", "label": "Google OR-Tools", "model": "cp-sat"}],
            "setup_hint": None,
            "rate_limit": {
                "section_delay_sec": 0,
                "strand_delay_sec": 0,
                "subject_chunk_size": 0,
                "max_retries": 0,
                "backoff_base_sec": 0,
                "mode": "ortools",
                "build": "ortools-v1",
            },
            "fallback_providers": ["greedy"],
            "cloud_ai_available": False,
            "cloud_ai_model": None,
            "smart_ai_ready": True,
        }

    def build_input(
        self,
        *,
        grade_level: str = "Grade 12",
        semester_code: str = "1st",
        strands: list[str] | None = None,
        sections_per_strand: int = 2,
        rooms: list[str] | None = None,
    ) -> SchedulerInput:
        selected_strands = [strand.upper() for strand in (strands or ENROLLMENT_STRANDS)]
        subjects = self._subjects_for_term(grade_level, semester_code)
        if strands:
            strand_set = set(selected_strands)
            subjects = [
                subject
                for subject in subjects
                if subject.get("strand") is None
                or str(subject.get("strand")).upper() in strand_set
            ]

        return SchedulerInput(
            grade_level=grade_level,
            semester_code=semester_code,
            strands=selected_strands,
            sections_per_strand=max(1, min(sections_per_strand, 2)),
            rooms=rooms or DEFAULT_ROOMS,
            days=DAY_NAMES[:5],
            time_slots=default_time_slot_labels(include_saturday=False),
            subjects=subjects,
        )

    def get_scheduling_context(
        self,
        *,
        grade_level: str = "Grade 12",
        semester_code: str = "1st",
        strands: list[str] | None = None,
        rooms: list[str] | None = None,
    ) -> dict[str, Any]:
        return build_scheduling_context(
            grade_level=grade_level,
            semester_code=semester_code,
            strands=strands,
            rooms=rooms,
            rest_get=self._rest_get,
        )

    def generate(
        self,
        *,
        grade_level: str = "Grade 12",
        semester_code: str = "1st",
        strands: list[str] | None = None,
        sections_per_strand: int = 2,
        rooms: list[str] | None = None,
        use_ai: bool = True,
        use_cloud_ai: bool = True,
        allow_local_fallback: bool = True,
    ) -> dict[str, Any]:
        del use_cloud_ai, allow_local_fallback  # kept for API compatibility

        scheduler_input = self.build_input(
            grade_level=grade_level,
            semester_code=semester_code,
            strands=strands,
            sections_per_strand=sections_per_strand,
            rooms=rooms,
        )
        payload = scheduler_input.to_dict()

        if not use_ai:
            return {
                "success": False,
                "error": "Scheduling is disabled.",
                "source": "failed",
                "input": payload,
            }

        scheduling_ctx = self.get_scheduling_context(
            grade_level=grade_level,
            semester_code=semester_code,
            strands=scheduler_input.strands,
            rooms=rooms,
        )
        teachers = scheduling_ctx.get("teacher_availability") or []

        try:
            assignments = self._generate_local(
                scheduler_input,
                teachers=teachers,
                scheduling_context=scheduling_ctx,
            )
            self._attach_schedule_labels(assignments)
        except RuntimeError as err:
            return {
                "success": False,
                "error": str(err),
                "source": "failed",
                "input": payload,
            }

        validation = validate_schedule(
            assignments,
            teachers=teachers,
            room_capacities=scheduling_ctx.get("room_capacities"),
            class_max_slots=int(scheduling_ctx.get("class_max_slots") or 40),
        )
        if not validation.valid or not is_complete(scheduler_input, assignments):
            return {
                "success": False,
                "error": "OR-Tools scheduler could not produce a complete conflict-free schedule.",
                "source": "failed",
                "validation": validation.to_dict(),
                "input": payload,
            }

        return self._success_response(
            assignments,
            source="ortools",
            validation=validation,
            input_payload=payload,
            ai_error=None,
            strand_counts=count_by_strand(assignments),
        )

    def generate_strand(
        self,
        *,
        strand: str,
        grade_level: str = "Grade 12",
        semester_code: str = "1st",
        sections_per_strand: int = 2,
        rooms: list[str] | None = None,
        existing_schedules: list[dict] | None = None,
        use_ai: bool = True,
        use_cloud_ai: bool = True,
        allow_local_fallback: bool = True,
    ) -> dict[str, Any]:
        del use_cloud_ai, allow_local_fallback  # kept for API compatibility

        strand_code = (strand or "").upper()
        if not strand_code:
            return {"success": False, "error": "Strand is required.", "source": "failed"}

        if not use_ai:
            return {
                "success": False,
                "error": "Scheduling is disabled.",
                "source": "failed",
                "strand": strand_code,
            }

        scheduler_input = self.build_input(
            grade_level=grade_level,
            semester_code=semester_code,
            strands=[strand_code],
            sections_per_strand=sections_per_strand,
            rooms=rooms,
        )

        subject_count = len(scheduler_input.subjects)
        expected_assignments = subject_count * scheduler_input.sections_per_strand
        if subject_count == 0:
            return {
                "success": False,
                "error": (
                    f"No subjects found for {grade_level} {semester_code} semester. "
                    "Run seed-shs-curriculum-2026.sql in Supabase, then refresh."
                ),
                "source": "failed",
                "strand": strand_code,
                "progress": [],
            }

        progress_log: list[dict[str, str]] = []

        def on_progress(level: str, message: str) -> None:
            progress_log.append({"level": level, "message": message})

        existing_payload = dedupe_schedule_entries(existing_schedules or [])
        if len(existing_schedules or []) > len(existing_payload):
            dropped = len(existing_schedules or []) - len(existing_payload)
            on_progress(
                "warn",
                f"Removed {dropped} duplicate saved entr{'y' if dropped == 1 else 'ies'} from database.",
            )
        existing_payload, stripped_self = exclude_regenerating_strand_schedules(
            existing_payload,
            strand=strand_code,
            grade_level=grade_level,
        )
        if stripped_self:
            on_progress(
                "warn",
                f"Excluded {stripped_self} saved {strand_code} · {grade_level} row(s) "
                "from conflict check (replacing this schedule).",
            )
        existing_assignments = assignments_from_payload(existing_payload)
        self._attach_schedule_labels(existing_assignments)

        scheduling_ctx = self.get_scheduling_context(
            grade_level=grade_level,
            semester_code=semester_code,
            strands=[strand_code],
            rooms=rooms,
        )
        teachers = scheduling_ctx.get("teacher_availability") or []

        if existing_assignments:
            saved_validation = validate_schedule(
                existing_assignments,
                teachers=teachers,
                room_capacities=scheduling_ctx.get("room_capacities"),
                class_max_slots=int(scheduling_ctx.get("class_max_slots") or 40),
                require_faculty=False,
            )
            all_blocking = blocking_saved_conflicts(saved_validation)
            blocking = blocking_saved_conflicts_for_strand(
                saved_validation,
                strand_code=strand_code,
            )
            if blocking:
                on_progress(
                    "error",
                    f"Saved {strand_code} schedules have {len(blocking)} conflict(s) — delete that strand first.",
                )
                return {
                    "success": False,
                    "error": (
                        f"Saved {strand_code} schedules have {len(blocking)} conflict(s). "
                        f"Delete {strand_code} in the sidebar, then generate again."
                    ),
                    "hint": "Use Delete & Generate or the sidebar Delete button for this strand only.",
                    "source": "failed",
                    "strand": strand_code,
                    "validation": saved_validation.to_dict(),
                    "progress": progress_log,
                }
            if all_blocking:
                on_progress(
                    "warn",
                    f"Other saved strands have {len(all_blocking)} room/time overlap(s) "
                    f"(e.g. ICT) — {strand_code} will still generate; fix other strands when you can.",
                )
            internal_issues = len(saved_validation.conflicts) - len(all_blocking)
            if internal_issues > 0:
                on_progress(
                    "warn",
                    f"Saved schedules have {internal_issues} other issue(s) "
                    f"(e.g. faculty load). {strand_code} generation will still proceed.",
                )

        room_pool_size = len(scheduling_ctx.get("classroom_availability") or [])
        typed_rooms = scheduling_ctx.get("rooms_by_type") or {}
        total_rooms = sum(len(pool or []) for pool in typed_rooms.values()) or room_pool_size
        if total_rooms < 8:
            on_progress(
                "warn",
                f"Only {total_rooms} room(s) loaded from database — run seed-scheduler-rooms.sql "
                "in Supabase for reliable scheduling.",
            )
        on_progress("info", "Loaded teachers, rooms, labs, and student load from database.")

        other_grade = "Grade 12" if "11" in grade_level else "Grade 11"
        sem_label = "1st" if semester_code == "1st" else "2nd"
        on_progress(
            "info",
            f"Conflict check includes {grade_level} and {other_grade} "
            f"({sem_label} semester only — not compared with the other semester).",
        )

        saved_same = sum(
            1
            for a in existing_assignments
            if (a.strand or "").upper() == strand_code
            and (a.grade_level or "") == grade_level
        )
        saved_other_grade = sum(
            1
            for a in existing_assignments
            if (a.strand or "").upper() == strand_code
            and (a.grade_level or "") == other_grade
        )
        if saved_other_grade and not saved_same:
            on_progress(
                "warn",
                f"May naka-save na {strand_code} · {other_grade} ({saved_other_grade} slots) pero wala pang "
                f"{grade_level}. Mas madali kung {grade_level} muna bago {other_grade} — i-delete ang "
                f"{strand_code} · {other_grade} sa sidebar kung paulit-ulit ang error.",
            )

        on_progress(
            "info",
            f"Scheduling {subject_count} subjects × {scheduler_input.sections_per_strand} sections "
            f"({expected_assignments} slots) for {strand_code}.",
        )

        assignments = None
        last_gen_error = ""
        max_attempts = 3
        if len(existing_payload) >= CONGESTED_EXISTING_THRESHOLD:
            max_attempts = 5
        elif len(existing_payload) >= 15:
            max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                assignments = self._generate_local(
                    scheduler_input,
                    existing_payload,
                    teachers=teachers,
                    scheduling_context=scheduling_ctx,
                    prefer_fast=True,
                )
                for assignment in assignments:
                    if not assignment.grade_level:
                        assignment.grade_level = grade_level
                self._attach_schedule_labels(assignments)

                local_complete = is_complete(scheduler_input, assignments)
                preview_validation = validate_for_new_strand(
                    existing_assignments,
                    assignments,
                    teachers=teachers,
                    room_capacities=scheduling_ctx.get("room_capacities"),
                    class_max_slots=int(scheduling_ctx.get("class_max_slots") or 40),
                    require_faculty=False,
                )
                if local_complete and preview_validation.valid:
                    break

                issue_bits = []
                if not local_complete:
                    issue_bits.append("incomplete subjects")
                if not preview_validation.valid:
                    issue_bits.append(f"{len(preview_validation.conflicts)} conflict(s)")
                last_gen_error = " and ".join(issue_bits) or "validation failed"
                if attempt < max_attempts:
                    on_progress(
                        "warn",
                        f"Attempt {attempt} failed — retrying with alternate placement "
                        f"({last_gen_error}).",
                    )
                    assignments = None
                    continue

                on_progress("error", f"OR-Tools result had {last_gen_error}.")
                return {
                    "success": False,
                    "error": f"Could not build a valid schedule for {strand_code}: {last_gen_error}.",
                    "source": "failed",
                    "strand": strand_code,
                    "schedules": [item.to_dict() for item in assignments],
                    "count": len(assignments),
                    "validation": preview_validation.to_dict(),
                    "progress": progress_log,
                }
            except RuntimeError as err:
                last_gen_error = str(err)
                if attempt < max_attempts:
                    on_progress(
                        "warn",
                        f"Attempt {attempt} failed — retrying with alternate placement ({last_gen_error}).",
                    )
                    continue
                on_progress("error", last_gen_error)
                hint = (
                    f"May naka-save na {strand_code} · {grade_level} schedule na nakakasagabal. "
                    "I-delete muna sa sidebar o pindutin ang Delete & Generate. "
                    "Kung paulit-ulit: (1) run schedule-sync.sql sa Supabase, "
                    "(2) restart admin server (python server.py)."
                )
                if existing_assignments and "Could not place" in last_gen_error:
                    others = {
                        (a.strand or "").upper()
                        for a in existing_assignments
                        if (a.strand or "").upper() != strand_code
                    }
                    if others:
                        hint = (
                            f"May {len(existing_assignments)} naka-save na schedule mula sa ibang strand "
                            f"({', '.join(sorted(others))}) para sa {sem_label} sem — puno na ang maraming room/time "
                            f"slot kaya hindi mailagay ang {last_gen_error.split('Could not place ', 1)[-1].split(' for ', 1)[0] if 'Could not place' in last_gen_error else 'subject'}. "
                            "I-delete muna ang ibang strand sa sidebar (hal. ICT G11 + G12), i-generate at i-save ang "
                            f"{strand_code}, saka ibalik ang ibang strand. O i-generate lahat nang walang naka-save."
                        )
                if stripped_self:
                    hint = (
                        f"Naka-detect ang {stripped_self} lumang {strand_code} row(s) sa database. "
                        "I-delete muna ang schedule sa sidebar bago mag-generate ulit. "
                        "Restart admin server pagkatapos mag-delete."
                    )
                return {
                    "success": False,
                    "error": last_gen_error,
                    "hint": hint,
                    "source": "failed",
                    "strand": strand_code,
                    "progress": progress_log,
                }

        if not assignments:
            return {
                "success": False,
                "error": last_gen_error or "Could not build schedule.",
                "source": "failed",
                "strand": strand_code,
                "progress": progress_log,
            }

        on_progress("success", f"{strand_code} schedule built successfully.")
        return _strand_success_payload(
            strand_code=strand_code,
            source="smart_scheduler",
            assignments=assignments,
            existing_assignments=existing_assignments,
            progress_log=progress_log,
            teachers=teachers,
            scheduling_context=scheduling_ctx,
            grade_level=grade_level,
        )

    def _generate_local(
        self,
        scheduler_input: SchedulerInput,
        existing_schedules: list[dict] | None = None,
        teachers: list[dict] | None = None,
        scheduling_context: dict[str, Any] | None = None,
        prefer_fast: bool = False,
    ) -> list[ScheduleAssignment]:
        ctx = scheduling_context
        if teachers is None or ctx is None:
            ctx = self.get_scheduling_context(
                grade_level=scheduler_input.grade_level,
                semester_code=scheduler_input.semester_code,
                strands=scheduler_input.strands,
                rooms=scheduler_input.rooms,
            )
            if teachers is None:
                teachers = ctx.get("teacher_availability") or []
        existing = assignments_from_payload(existing_schedules or [])
        self._attach_schedule_labels(existing)
        if ctx is not None and len(existing) >= CONGESTED_EXISTING_THRESHOLD:
            ctx = dict(ctx)
            ctx["scheduling_congested"] = True
        return self.smart.generate(
            scheduler_input,
            existing_assignments=existing,
            teachers=teachers,
            scheduling_context=ctx,
            prefer_fast=prefer_fast,
        )

    def _fill_gaps(
        self,
        scheduler_input: SchedulerInput,
        assignments: list[ScheduleAssignment],
        gap_strands: list[str],
    ) -> list[ScheduleAssignment]:
        if not gap_strands:
            return assignments

        gap_set = {strand.upper() for strand in gap_strands}
        merged = [item for item in assignments if (item.strand or "").upper() not in gap_set]

        for strand in gap_strands:
            strand_input = SchedulerInput(
                grade_level=scheduler_input.grade_level,
                semester_code=scheduler_input.semester_code,
                strands=[strand.upper()],
                sections_per_strand=scheduler_input.sections_per_strand,
                rooms=scheduler_input.rooms,
                days=scheduler_input.days,
                time_slots=scheduler_input.time_slots,
                subjects=scheduler_input.subjects,
            )
            merged.extend(
                self.smart.generate(
                    strand_input,
                    existing_assignments=list(merged),
                    teachers=self.get_scheduling_context(
                        grade_level=scheduler_input.grade_level,
                        semester_code=scheduler_input.semester_code,
                        strands=[strand.upper()],
                        rooms=scheduler_input.rooms,
                    ).get("teacher_availability")
                    or [],
                )
            )
        return merged

    def validate_payload(
        self,
        schedules: list[dict],
        *,
        scheduling_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assignments = assignments_from_payload(schedules)
        self._attach_schedule_labels(assignments)
        ctx = scheduling_context or {}
        if not ctx and self._rest_get:
            ctx = self.get_scheduling_context()
        validation = validate_schedule(
            assignments,
            teachers=ctx.get("teacher_availability"),
            room_capacities=ctx.get("room_capacities"),
            class_max_slots=int(ctx.get("class_max_slots") or 40),
        )
        return {
            "success": validation.valid,
            "validation": validation.to_dict(),
            "schedules": [item.to_dict() for item in assignments],
            "count": len(assignments),
            "teacher_loads": _build_teacher_load_summary(
                assignments,
                ctx.get("teacher_availability") or [],
            ),
        }

    def _subjects_for_term(self, grade_level: str, semester_code: str) -> list[dict[str, Any]]:
        if self._rest_get:
            encoded_grade = grade_level.replace(" ", "%20")
            rows, err = self._rest_get(
                "subjects",
                "select=code,name,description,strand_id,grade_level,semester_code,"
                "lec_hours,lab_hours,units,is_active,strands(code)"
                f"&is_active=eq.true&grade_level=eq.{encoded_grade}",
            )
            if not err and rows:
                subjects: list[dict[str, Any]] = []
                for row in rows:
                    sem = row.get("semester_code")
                    if sem and str(sem) != semester_code:
                        continue
                    strand_info = row.get("strands")
                    strand_code = None
                    if isinstance(strand_info, dict):
                        strand_code = strand_info.get("code")
                    code = row.get("code") or ""
                    if strand_code:
                        subject_type = "specialized"
                    elif is_applied_subject({"code": code}):
                        subject_type = "applied"
                    else:
                        subject_type = "core"
                    subjects.append({
                        "code": code,
                        "description": row.get("name") or row.get("description") or code,
                        "name": row.get("name") or row.get("description") or code,
                        "units": row.get("units") or 3,
                        "lab": row.get("lab_hours") or 0,
                        "lab_hours": row.get("lab_hours") or 0,
                        "strand": strand_code.upper() if strand_code else None,
                        "semester_code": row.get("semester_code") or semester_code,
                        "type": subject_type,
                    })
                if subjects:
                    return subjects

        term = ENROLLMENT_CURRICULUM.get(grade_level, {}).get(semester_code)
        if not term:
            return []

        subjects: list[dict[str, Any]] = []
        for core in term.get("core", []):
            subjects.append(
                {
                    "code": core["code"],
                    "description": core["description"],
                    "units": core.get("units", 3),
                    "lab": core.get("lab", 0),
                    "strand": None,
                    "type": "core",
                }
            )
        for applied in term.get("applied", []):
            subjects.append(
                {
                    "code": applied["code"],
                    "description": applied["description"],
                    "units": applied.get("units", 3),
                    "lab": applied.get("lab", 0),
                    "strand": None,
                    "type": "applied",
                }
            )
        for strand, specs in term.get("specialized", {}).items():
            for spec in specs:
                subjects.append(
                    {
                        "code": spec["code"],
                        "description": spec["description"],
                        "units": spec.get("units", 3),
                        "lab": spec.get("lab", 0),
                        "strand": strand,
                        "type": "specialized",
                    }
                )
        return subjects

    @staticmethod
    def _attach_schedule_labels(assignments: list[ScheduleAssignment]) -> None:
        for assignment in assignments:
            if assignment.schedule_label:
                continue
            assignment.schedule_label = build_schedule_label(
                [session.to_dict() for session in assignment.sessions]
            )

    @staticmethod
    def _success_response(
        assignments: list[ScheduleAssignment],
        *,
        source: str,
        validation,
        input_payload: dict,
        ai_error: str | None,
        strand_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "source": source,
            "ai_error": ai_error,
            "validation": validation.to_dict(),
            "input": input_payload,
            "count": len(assignments),
            "strand_counts": strand_counts or count_by_strand(assignments),
            "schedules": [assignment.to_dict() for assignment in assignments],
        }
