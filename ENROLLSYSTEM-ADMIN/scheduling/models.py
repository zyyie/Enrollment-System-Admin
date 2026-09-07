"""Data models for the auto-scheduling module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TimeSlot:
    day: int  # 0=Monday .. 5=Saturday
    start_minutes: int
    end_minutes: int

    @property
    def duration_minutes(self) -> int:
        return self.end_minutes - self.start_minutes


@dataclass
class ScheduleSession:
    day: str
    start: str
    end: str
    room: str

    def to_dict(self) -> dict[str, str]:
        return {
            "day": self.day,
            "start": self.start,
            "end": self.end,
            "room": self.room,
        }


@dataclass
class ScheduleAssignment:
    strand: str
    section: str
    subject_code: str
    subject_name: str
    sessions: list[ScheduleSession] = field(default_factory=list)
    faculty_id: str | None = None
    faculty_name: str = ""
    schedule_label: str = ""
    grade_level: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "strand": self.strand,
            "section": self.section,
            "subject_code": self.subject_code,
            "subject_name": self.subject_name,
            "sessions": [session.to_dict() for session in self.sessions],
            "faculty_id": self.faculty_id,
            "faculty_name": self.faculty_name,
            "schedule_label": self.schedule_label,
        }
        if self.grade_level:
            payload["gradeLevel"] = self.grade_level
        return payload


@dataclass
class ConflictError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class ValidationResult:
    valid: bool
    conflicts: list[ConflictError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


@dataclass
class SchedulerInput:
    grade_level: str
    semester_code: str
    strands: list[str]
    sections_per_strand: int
    rooms: list[str]
    days: list[str]
    time_slots: list[str]
    subjects: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "grade_level": self.grade_level,
            "semester_code": self.semester_code,
            "strands": self.strands,
            "sections_per_strand": self.sections_per_strand,
            "rooms": self.rooms,
            "days": self.days,
            "time_slots": self.time_slots,
            "subjects": self.subjects,
        }
