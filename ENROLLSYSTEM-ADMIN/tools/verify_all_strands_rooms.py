"""Generate all G11 1st-sem strands sequentially and report room peak usage."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from scheduling.constants import DEFAULT_SCHEDULER_ROOMS  # noqa: E402
from scheduling.room_types import (  # noqa: E402
    ROOM_CLASSROOM,
    ROOM_COMPUTER_LAB,
    ROOM_COOKERY_LAB,
    ROOM_EIM_LAB,
    ROOM_SCIENCE_LAB,
    resolve_scheduler_rooms,
)
from scheduling.smart_scheduler import SmartScheduler  # noqa: E402
from scheduling.time_utils import DAY_NAME_TO_INDEX, parse_clock  # noqa: E402

STRANDS = ["STEM", "ABM", "HUMSS", "ICT", "COOKERY", "EIM"]


def room_type_for(name: str) -> str:
    upper = name.upper()
    if upper.startswith("COOKERY"):
        return ROOM_COOKERY_LAB
    if upper.startswith("EIM"):
        return ROOM_EIM_LAB
    if upper in ("LAB3", "LAB4"):
        return ROOM_SCIENCE_LAB
    if upper.startswith("LAB"):
        return ROOM_COMPUTER_LAB
    return ROOM_CLASSROOM


def available_by_type() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for room in DEFAULT_SCHEDULER_ROOMS:
        counts[room_type_for(room)] += 1
    return dict(counts)


def main() -> int:
    svc = server.get_scheduler_service()
    scheduler = SmartScheduler()
    grade = "Grade 11"
    sem = "1st"
    ctx = svc.get_scheduling_context(grade_level=grade, semester_code=sem, strands=STRANDS)
    accumulated = []
    failures: list[str] = []

    for strand in STRANDS:
        scheduler_input = svc.build_input(
            grade_level=grade,
            semester_code=sem,
            strands=[strand],
            sections_per_strand=2,
        )
        try:
            assignments = scheduler.generate(
                scheduler_input,
                teachers=ctx.get("teacher_availability"),
                scheduling_context=ctx,
                existing_assignments=list(accumulated),
            )
            accumulated.extend(assignments)
            print(f"{strand}: OK ({len(assignments)} slots)")
        except RuntimeError as err:
            failures.append(f"{strand}: {err}")
            print(f"{strand}: FAIL — {err}")

    by_type: dict[str, dict[tuple[int, int], set[str]]] = defaultdict(lambda: defaultdict(set))
    for assignment in accumulated:
        for session in assignment.sessions or []:
            day = DAY_NAME_TO_INDEX.get((session.day or "").strip().lower())
            if day is None:
                continue
            start = parse_clock(session.start)
            end = parse_clock(session.end)
            room = (session.room or "").strip().upper()
            if not room:
                continue
            room_type = room_type_for(room)
            cursor = start
            while cursor < end:
                by_type[room_type][(day, cursor)].add(room)
                cursor += 60

    avail = available_by_type()
    print(f"\nTotal assignments: {len(accumulated)}")
    print("Room capacity check (peak concurrent vs available):")
    all_ok = not failures
    for room_type in (
        ROOM_CLASSROOM,
        ROOM_COMPUTER_LAB,
        ROOM_SCIENCE_LAB,
        ROOM_COOKERY_LAB,
        ROOM_EIM_LAB,
    ):
        peak = max((len(rooms) for rooms in by_type[room_type].values()), default=0)
        have = avail.get(room_type, 0)
        status = "OK" if peak <= have else "NEED MORE"
        if status != "OK":
            all_ok = False
        print(f"  {room_type}: peak {peak} / available {have} — {status}")

    inp = svc.build_input(grade_level=grade, semester_code=sem, strands=["ICT"])
    rooms_by_type, _, fallback = resolve_scheduler_rooms(inp, ctx)
    print("\nMerged room pool:", {key: len(val) for key, val in rooms_by_type.items()})
    print("Fallback rooms:", len(fallback))

    return 1 if failures or not all_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
