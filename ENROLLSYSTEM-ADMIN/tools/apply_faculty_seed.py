"""Upsert full faculty roster into Supabase via REST API."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gen_faculty_seed import DEPT, FACULTY, split_name  # noqa: E402
from server import (  # noqa: E402
    get_supabase_strand_id,
    supabase_configured,
    supabase_rest_get,
    supabase_rest_insert,
    supabase_rest_upsert,
)


def main() -> None:
    if not supabase_configured():
        print("Supabase not configured — run seed-all-strand-faculty.sql in SQL Editor instead.")
        sys.exit(1)

    rows = []
    strand_links: list[tuple[str, str]] = []
    for strand, names in FACULTY.items():
        for index, name in enumerate(names, 1):
            first, last = split_name(name)
            faculty_id = f"FAC-{strand}-{index:02d}"
            rows.append({
                "faculty_id": faculty_id,
                "last_name": last,
                "first_name": first,
                "role": "Teacher",
                "department": DEPT[strand],
                "password": "teacher123",
                "max_load_units": 3,
                "is_active": True,
            })
            strand_links.append((faculty_id, strand))

    _, err = supabase_rest_upsert("faculty", rows, "faculty_id")
    if err:
        print("Faculty upsert failed:", err[:500])
        sys.exit(1)
    print(f"Upserted {len(rows)} faculty rows")

    linked = 0
    for faculty_id, strand_code in strand_links:
        faculty_rows, _ = supabase_rest_get(
            "faculty",
            f"faculty_id=eq.{faculty_id}&select=id",
            use_secret=True,
            timeout=15,
        )
        strand_id = get_supabase_strand_id(strand_code)
        if not faculty_rows or not strand_id:
            continue
        uuid = faculty_rows[0]["id"]
        _, link_err = supabase_rest_insert(
            "faculty_strands",
            {"faculty_id": uuid, "strand_id": strand_id},
        )
        if not link_err:
            linked += 1

    print(f"Linked {linked} faculty_strands rows")

    teachers, _ = supabase_rest_get(
        "faculty",
        "role=eq.Teacher&is_active=eq.true&select=faculty_id",
        use_secret=True,
        timeout=20,
    )
    print(f"Active teachers in database: {len(teachers or [])}")


if __name__ == "__main__":
    main()
