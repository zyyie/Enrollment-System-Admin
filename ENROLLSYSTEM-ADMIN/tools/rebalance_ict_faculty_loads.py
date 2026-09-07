"""Rebalance ICT faculty loads: max 3/subject slots, spread fairly (priority FAC-ICT-07+)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import supabase_rest_get, supabase_rest_patch  # noqa: E402

MAX_LOAD = 3
ICT_FACULTY_ORDER = [f"FAC-ICT-{i:02d}" for i in range(1, 17)]


def _parse_time(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    m = re.match(r"(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _day_indices(day_of_week: str) -> set[int]:
    mapping = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
    }
    out: set[int] = set()
    for part in re.split(r"[,/]+", str(day_of_week or "")):
        key = part.strip().lower()
        if key in mapping:
            out.add(mapping[key])
    return out


def _conflicts(a: dict, b: dict) -> bool:
    days_a = _day_indices(a.get("day_of_week") or "")
    days_b = _day_indices(b.get("day_of_week") or "")
    if not days_a.intersection(days_b):
        return False
    start_a = _parse_time(a.get("start_time"))
    end_a = _parse_time(a.get("end_time"))
    start_b = _parse_time(b.get("start_time"))
    end_b = _parse_time(b.get("end_time"))
    if None in (start_a, end_a, start_b, end_b):
        return False
    return start_a < end_b and start_b < end_a


def _teacher_can_take(faculty_id: str, schedule: dict, by_teacher: dict[str, list[dict]]) -> bool:
    if len(by_teacher.get(faculty_id, [])) >= MAX_LOAD:
        return False
    for existing in by_teacher.get(faculty_id, []):
        if _conflicts(existing, schedule):
            return False
    return True


def main() -> int:
    rows, err = supabase_rest_get(
        "class_schedules",
        "select=id,day_of_week,start_time,end_time,schedule_label,"
        "subjects(code,name),sections(name,grade_level,strands(code)),"
        "faculty(faculty_id,first_name,last_name)&is_active=eq.true",
        use_secret=True,
    )
    if err:
        print("Load error:", err)
        return 1

    ict_rows = [
        r
        for r in rows or []
        if ((r.get("sections") or {}).get("strands") or {}).get("code") == "ICT"
    ]
    if not ict_rows:
        print("No ICT schedules found.")
        return 1

    faculty_ids = {((r.get("faculty") or {}).get("faculty_id") or "").upper() for r in ict_rows}
    teachers = [fid for fid in ICT_FACULTY_ORDER if fid in faculty_ids]
    teachers.extend(sorted(fid for fid in faculty_ids if fid not in teachers and fid.startswith("FAC-ICT")))

    # Priority: teachers 07–16 get first pick for 3 loads, then 01–06.
    priority = [fid for fid in teachers if fid >= "FAC-ICT-07"] + [
        fid for fid in teachers if fid < "FAC-ICT-07"
    ]

    by_teacher: dict[str, list[dict]] = {fid: [] for fid in teachers}
    unassigned: list[dict] = []

    # Sort schedules: harder slots first (more days / longer blocks)
    def sort_key(row: dict) -> tuple:
        days = len(_day_indices(row.get("day_of_week") or ""))
        start = _parse_time(row.get("start_time")) or 0
        end = _parse_time(row.get("end_time")) or 0
        return (-days, -(end - start), row.get("id") or "")

    ordered = sorted(ict_rows, key=sort_key)

    for row in ordered:
        placed = False
        # Prefer teachers under max load, sorted by current load then priority index
        candidates = sorted(
            priority,
            key=lambda fid: (len(by_teacher.get(fid, [])), priority.index(fid)),
        )
        for fid in candidates:
            if _teacher_can_take(fid, row, by_teacher):
                by_teacher[fid].append(row)
                placed = True
                break
        if not placed:
            unassigned.append(row)

    if unassigned:
        print(f"WARNING: {len(unassigned)} schedule(s) could not be placed without conflict.")

    changes = 0
    for fid, assigned in by_teacher.items():
        for row in assigned:
            current = ((row.get("faculty") or {}).get("faculty_id") or "").upper()
            if current == fid:
                continue
            faculty_uuid_rows, _ = supabase_rest_get(
                "faculty",
                f"select=id&faculty_id=eq.{fid}",
                use_secret=True,
            )
            if not faculty_uuid_rows:
                print(f"Missing faculty row for {fid}")
                continue
            faculty_uuid = faculty_uuid_rows[0]["id"]
            _, patch_err = supabase_rest_patch(
                "class_schedules",
                f"id=eq.{row['id']}",
                {"faculty_id": faculty_uuid},
            )
            if patch_err:
                print(f"Patch failed {row['id']} -> {fid}: {patch_err}")
            else:
                sub = (row.get("subjects") or {}).get("code")
                sec = (row.get("sections") or {}).get("name")
                print(f"Assigned {fid}: {sub} · {sec}")
                changes += 1

    print("\nFinal loads:")
    for fid in ICT_FACULTY_ORDER:
        if fid not in by_teacher:
            continue
        count = len(by_teacher[fid])
        mark = "OK" if count == MAX_LOAD else f"{count}/{MAX_LOAD}"
        print(f"  {fid}: {count} [{mark}]")

    slots = sum(len(v) for v in by_teacher.values())
    max_at_3 = slots // MAX_LOAD
    print(f"\nTotal ICT slots: {slots}. At most {max_at_3} teachers can have {MAX_LOAD} loads.")
    print(f"Applied {changes} reassignment(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
