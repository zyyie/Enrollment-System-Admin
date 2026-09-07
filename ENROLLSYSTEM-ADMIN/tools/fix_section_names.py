"""Rename mislabeled sections and deactivate legacy single-letter schedules."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from enrollment_curriculum import ENROLLMENT_SECTION_NAMES_BY_GRADE, format_section_name, section_slot_name
from server import supabase_rest_get, supabase_rest_patch  # noqa: E402


def _suffix(name: str) -> str:
    parts = str(name or "").split("-", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _resolve_slot(strand: str, grade: str, suffix: str) -> str | None:
    text = (suffix or "").strip()
    if text in ("A", "B"):
        return text
    for letter in ("A", "B"):
        if section_slot_name(strand, grade, letter) == text:
            return letter
    return None


def main() -> int:
    rows, err = supabase_rest_get(
        "sections",
        "select=id,name,grade_level,strands(code)&order=grade_level.asc,name.asc",
        use_secret=True,
    )
    if err:
        print("Failed to load sections:", err)
        return 1

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows or []:
        strand = ((row.get("strands") or {}).get("code") or "").upper()
        grade = row.get("grade_level") or ""
        if not strand or not grade or strand == "GAS":
            continue
        groups[(grade, strand)].append(row)

    renamed = 0
    deactivated = 0

    for (grade, strand), items in sorted(groups.items()):
        canonical: list[tuple[dict, str]] = []
        legacy: list[dict] = []

        for item in items:
            suffix = _suffix(item.get("name") or "")
            slot = _resolve_slot(strand, grade, suffix)
            if slot:
                canonical.append((item, slot))
            else:
                legacy.append(item)

        assigned = {slot for _, slot in canonical}
        orphans = [item for item, slot in canonical if list(assigned).count(slot) > 1]
        if orphans:
            canonical = [(item, slot) for item, slot in canonical if item not in orphans]
            legacy.extend(orphans)

        for item, slot in canonical:
            expected = format_section_name(strand, grade, slot)
            current = item.get("name") or ""
            if current != expected:
                _, patch_err = supabase_rest_patch(
                    "sections",
                    f"id=eq.{item['id']}",
                    {"name": expected},
                )
                if patch_err:
                    print(f"FAIL rename {current} -> {expected}: {patch_err}")
                else:
                    print(f"Renamed: {current} -> {expected}")
                    renamed += 1

        for leg in legacy:
            sched_rows, _ = supabase_rest_get(
                "class_schedules",
                f"select=id,is_active&section_id=eq.{leg['id']}",
                use_secret=True,
            )
            for sched in sched_rows or []:
                if sched.get("is_active"):
                    _, patch_err = supabase_rest_patch(
                        "class_schedules",
                        f"id=eq.{sched['id']}",
                        {"is_active": False},
                    )
                    if patch_err:
                        print(f"FAIL deactivate {sched['id']}: {patch_err}")
                    else:
                        print(f"Deactivated legacy schedule on {leg.get('name')}")
                        deactivated += 1

    print(f"\nDone. Renamed {renamed} section(s), deactivated {deactivated} schedule(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
