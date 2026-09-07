"""Deactivate schedules saved under wrong section names (e.g. Cookery virtues on ICT)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scheduling.schedule_dedupe import normalize_section_letter  # noqa: E402
from server import supabase_rest_get, supabase_rest_patch  # noqa: E402


def _suffix(name: str) -> str:
    parts = str(name or "").split("-", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def main() -> int:
    rows, err = supabase_rest_get(
        "class_schedules",
        "select=id,is_active,"
        "sections(name,grade_level,strands(code)),"
        "subjects(code,semester_code)",
        use_secret=True,
    )
    if err:
        print("Load error:", err)
        return 1

    deactivated = 0
    for row in rows or []:
        if not row.get("is_active"):
            continue
        section = row.get("sections") or {}
        strand = (section.get("strands") or {}).get("code") or ""
        grade = section.get("grade_level") or ""
        suffix = _suffix(section.get("name") or "")
        item = {
            "gradeLevel": grade,
            "strand": strand,
            "section": suffix,
            "subject_code": (row.get("subjects") or {}).get("code") or "",
        }
        if normalize_section_letter(item) is not None:
            continue
        _, patch_err = supabase_rest_patch(
            "class_schedules",
            f"id=eq.{row['id']}",
            {"is_active": False},
        )
        if patch_err:
            print(f"FAIL {row['id']} ({section.get('name')}): {patch_err}")
            continue
        deactivated += 1
        print(f"Deactivated: {section.get('name')} / {(row.get('subjects') or {}).get('code')}")

    print(f"\nDone. Deactivated {deactivated} invalid schedule row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
