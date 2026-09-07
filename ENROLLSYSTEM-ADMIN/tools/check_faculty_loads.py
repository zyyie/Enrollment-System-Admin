"""Check ICT faculty loads across G11+G12 for 1st sem."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import load_draft_schedules, supabase_rest_get  # noqa: E402

MAX_LOAD = 3


def analyze(schedules: list, label: str) -> None:
    ict = [s for s in schedules if str(s.get("strand", "")).upper() == "ICT"]
    loads = Counter()
    details: dict[str, list[str]] = defaultdict(list)
    for item in ict:
        fid = (item.get("faculty_id") or "UNASSIGNED").upper()
        loads[fid] += 1
        grade = item.get("gradeLevel") or "?"
        details[fid].append(
            f"{grade} Sec {item.get('section')} · {item.get('subject_code')}"
        )

    print(f"\n=== {label} ({len(ict)} ICT assignments) ===")
    over = 0
    for fid in sorted(loads, key=lambda k: (-loads[k], k)):
        name = next(
            (s.get("faculty_name") for s in ict if (s.get("faculty_id") or "").upper() == fid),
            "",
        )
        count = loads[fid]
        status = "OK" if count <= MAX_LOAD else "OVER LIMIT"
        if count > MAX_LOAD:
            over += 1
        print(f"  {fid} ({name}): {count} subjects [{status}]")
        for line in details[fid]:
            print(f"      · {line}")
    print(f"  Max load: {max(loads.values()) if loads else 0} | Over {MAX_LOAD}: {over}")


def main() -> None:
    local_path = ROOT / "data" / "generated_schedules.json"
    if local_path.exists():
        payload = json.loads(local_path.read_text(encoding="utf-8"))
        analyze(
            payload.get("schedules") or [],
            f"Local file ({payload.get('gradeLevel')} {payload.get('semesterCode')})",
        )

    for grade in ("Grade 11", "Grade 12"):
        schedules, source = load_draft_schedules(grade, "1st")
        ict_count = sum(1 for s in schedules if str(s.get("strand", "")).upper() == "ICT")
        print(f"\nload_draft_schedules({grade}, 1st) -> source={source}, total={len(schedules)}, ICT={ict_count}")

    combined, source = load_draft_schedules("Grade 11", "1st")
    analyze(combined, f"Combined G11+G12 conflict pool (source={source})")

    rows, err = supabase_rest_get(
        "class_schedules",
        "select=faculty_id,section_id,subject_id,is_active,"
        "faculty(faculty_id,first_name,last_name),"
        "subjects(code,name,semester_code),"
        "sections(name,grade_level,strands(code))"
        "&is_active=eq.true",
        use_secret=True,
        timeout=30,
    )
    if err:
        print(f"\nDB class_schedules query error: {str(err)[:200]}")
        return

    db_items = []
    for row in rows or []:
        section = row.get("sections") or {}
        strand = section.get("strands") or {}
        subject = row.get("subjects") or {}
        if str(strand.get("code", "")).upper() != "ICT":
            continue
        if subject.get("semester_code") not in (None, "1st"):
            continue
        faculty = row.get("faculty") or {}
        db_items.append({
            "gradeLevel": section.get("grade_level"),
            "section": section.get("name"),
            "subject_code": subject.get("code"),
            "faculty_id": faculty.get("faculty_id"),
            "faculty_name": f"{faculty.get('first_name', '')} {faculty.get('last_name', '')}".strip(),
            "strand": "ICT",
        })
    analyze(db_items, "Live database (class_schedules ICT 1st sem)")


if __name__ == "__main__":
    main()
