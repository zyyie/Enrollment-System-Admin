"""FastAPI service for OR-Tools schedule generation."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .conflict_validator import assignments_from_payload, validate_schedule
from .db_bridge import save_generated_schedules, supabase_rest_get
from .faculty_assigner import assign_faculty_to_assignments
from .ortools_scheduler import OrtoolsScheduler
from .schedule_coverage import is_complete
from .scheduling_context import build_scheduling_context
from .scheduler_service import SchedulerService


app = FastAPI(
    title="EMS Scheduler",
    description="Conflict-free class scheduling powered by Google OR-Tools",
    version="1.0.0",
)


class GenerateScheduleRequest(BaseModel):
    grade_level: str = Field(default="Grade 12", alias="gradeLevel")
    semester_code: str = Field(default="1st", alias="semesterCode")
    strands: list[str] | None = None
    sections_per_strand: int = Field(default=2, alias="sectionsPerStrand")
    rooms: list[str] | None = None
    existing_schedules: list[dict[str, Any]] = Field(default_factory=list, alias="existingSchedules")
    save_to_db: bool = Field(default=True, alias="saveToDb")

    model_config = {"populate_by_name": True}


def _build_service() -> SchedulerService:
    def rest_get(table: str, query_string: str):
        return supabase_rest_get(table, query_string)

    return SchedulerService(rest_get=rest_get)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "ortools"}


@app.post("/generate-schedule")
def generate_schedule(body: GenerateScheduleRequest) -> dict[str, Any]:
    """Generate a conflict-free schedule and optionally persist it to Supabase."""
    service = _build_service()
    scheduler_input = service.build_input(
        grade_level=body.grade_level,
        semester_code=body.semester_code,
        strands=body.strands,
        sections_per_strand=body.sections_per_strand,
        rooms=body.rooms,
    )

    scheduling_ctx = build_scheduling_context(
        grade_level=body.grade_level,
        semester_code=body.semester_code,
        strands=scheduler_input.strands,
        rooms=body.rooms,
        rest_get=supabase_rest_get,
    )
    teachers = scheduling_ctx.get("teacher_availability") or []

    existing_assignments = assignments_from_payload(body.existing_schedules)
    engine = OrtoolsScheduler()

    try:
        assignments = engine.generate(
            scheduler_input,
            existing_assignments=existing_assignments,
            teachers=teachers,
            scheduling_context=scheduling_ctx,
        )
    except RuntimeError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    service._attach_schedule_labels(assignments)
    assign_faculty_to_assignments(assignments, teachers)

    combined = list(existing_assignments)
    combined.extend(assignments)
    validation = validate_schedule(combined)
    complete = is_complete(scheduler_input, assignments)
    schedules = [item.to_dict() for item in assignments]

    response: dict[str, Any] = {
        "success": validation.valid and complete,
        "source": "ortools",
        "engine": "google-or-tools",
        "count": len(assignments),
        "schedules": schedules,
        "validation": validation.to_dict(),
        "scheduling_context": {
            "teachers_loaded": len(teachers),
            "classrooms": scheduling_ctx.get("classroom_availability") or [],
            "laboratories": scheduling_ctx.get("laboratory_availability") or [],
            "errors": scheduling_ctx.get("errors") or [],
        },
    }

    if not complete:
        raise HTTPException(status_code=422, detail="Could not schedule all required subjects.")

    if not validation.valid:
        raise HTTPException(
            status_code=422,
            detail=f"Schedule has {len(validation.conflicts)} conflict(s).",
        )

    if body.save_to_db:
        merge_strands = {str(item.get("strand") or "").upper() for item in schedules if item.get("strand")}
        save_result = save_generated_schedules(
            schedules=schedules,
            grade_level=body.grade_level,
            semester_code=body.semester_code,
            source="ortools",
            merge_strands=merge_strands,
        )
        response["saved"] = save_result
        if not save_result.get("success"):
            raise HTTPException(status_code=500, detail=save_result)

    return response
