"""Check whether generated schedules cover all strands and sections."""

from __future__ import annotations

from .models import ScheduleAssignment, SchedulerInput


def subjects_for_strand(scheduler_input: SchedulerInput, strand: str) -> list[dict]:
    strand_code = strand.upper()
    filtered: list[dict] = []
    for subject in scheduler_input.subjects:
        sub_strand = subject.get("strand")
        if sub_strand is None or str(sub_strand).upper() == strand_code:
            filtered.append(subject)
    return filtered


def expected_keys(scheduler_input: SchedulerInput) -> set[tuple[str, str, str]]:
    sections = ["A", "B"][: scheduler_input.sections_per_strand]
    keys: set[tuple[str, str, str]] = set()
    for strand in scheduler_input.strands:
        strand_code = strand.upper()
        for section in sections:
            for subject in subjects_for_strand(scheduler_input, strand_code):
                code = subject.get("code") or subject.get("subject_code") or ""
                if code:
                    keys.add((strand_code, section.upper(), code.upper()))
    return keys


def actual_keys(assignments: list[ScheduleAssignment]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for item in assignments:
        code = item.subject_code or ""
        if code:
            keys.add(
                (
                    (item.strand or "").upper(),
                    (item.section or "").upper(),
                    code.upper(),
                )
            )
    return keys


def missing_keys(
    scheduler_input: SchedulerInput,
    assignments: list[ScheduleAssignment],
) -> set[tuple[str, str, str]]:
    return expected_keys(scheduler_input) - actual_keys(assignments)


def strands_with_gaps(
    scheduler_input: SchedulerInput,
    assignments: list[ScheduleAssignment],
) -> list[str]:
    missing = missing_keys(scheduler_input, assignments)
    if not missing:
        return []
    return sorted({strand for strand, _, _ in missing})


def count_by_strand(assignments: list[ScheduleAssignment]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in assignments:
        strand = (item.strand or "UNKNOWN").upper()
        counts[strand] = counts.get(strand, 0) + 1
    return counts


def is_complete(
    scheduler_input: SchedulerInput,
    assignments: list[ScheduleAssignment],
) -> bool:
    return not missing_keys(scheduler_input, assignments)
