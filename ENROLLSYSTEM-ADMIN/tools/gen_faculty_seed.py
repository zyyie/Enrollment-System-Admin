"""Generate supabase/seed-all-strand-faculty.sql from the full roster."""
from pathlib import Path

FACULTY = {
    "STEM": [
        "Maria Santos", "Joshua Reyes", "Angela Cruz", "Daniel Aquino", "Patricia Garcia",
        "Kevin Bautista", "Sofia Lim", "Mark Villanueva", "Rachel Navarro", "Victor Ramos",
        "Laura Mendoza", "Henry Flores", "Nina Castillo", "Owen Reyes", "Clara Reyes",
        "Paula Mendoza", "Eric Villanueva", "Grace Ramos", "Adrian Flores", "Lara Bautista",
        "Noah Santos", "Mia Reyes",
    ],
    "ABM": [
        "Andrea Villanueva", "Miguel Sy", "Carla Ong", "Ramon Flores", "Grace Tan",
        "Paolo Mercado", "Liza Chua", "Monica Reyes", "Jerome Santos", "Bea Navarro",
        "Carlos Lim", "Diana Cruz", "Felix Garcia", "Nora Ramos", "Ivan Bautista",
        "Chloe Sy", "Marco Ong", "Leah Flores", "Ryan Mercado", "Ella Chua",
    ],
    "HUMSS": [
        "Jessa Fernandez", "Luis Dela Cruz", "Karen Bautista", "Ethan Villanueva", "Nicole Ramos",
        "Eric Santos", "Laura Reyes", "Miguel Flores", "Anna Cruz", "Gabriel Tan",
        "Sofia Mercado", "Rina Garcia", "Paolo Sy", "Clara Dizon", "Mara Fernandez",
        "Jonas Cruz", "Leah Santos", "Nico Bautista",
    ],
    "COOKERY": [
        "Ana Reyes", "Ben Cruz", "Clara Santos", "Diego Ramos", "Ella Garcia",
        "Felix Navarro", "Grace Dela Cruz", "Hannah Lim", "Irene Santos", "Marco Reyes",
        "Nina Cruz", "Oscar Tan", "Paula Garcia", "Rico Flores", "Mia Ramos", "Leo Santos",
    ],
    "EIM": [
        "Ramon Garcia", "Leo Santos", "May Reyes", "Carlo Torres", "Nina Bautista",
        "Omar Flores", "Paolo Cruz", "Rhea Santos", "Victor Lim", "Daisy Reyes",
        "Marco Dizon", "Lara Garcia", "Noel Ramos", "Aiden Santos", "Mika Cruz",
    ],
    "ICT": [
        "Adrian Lopez", "Brian Dizon", "Vince Tan", "Ella Cruz", "Paolo Reyes",
        "Grace Lim", "Carlo Santos", "Mia Navarro", "Jason Garcia", "Nina Flores",
        "Ryan Cruz", "Trisha Santos", "Kevin Dela Cruz", "Ava Ramos", "Leo Dizon", "Mara Lopez",
    ],
}

DEPT = {
    "STEM": "STEM Department",
    "ABM": "ABM Department",
    "HUMSS": "HUMSS Department",
    "COOKERY": "Cookery Department",
    "EIM": "EIM Department",
    "ICT": "ICT Department",
}

MULTI_LAST = {"DELA CRUZ", "DE LA CRUZ"}


def split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split()
    up = [p.upper() for p in parts]
    if len(up) >= 3 and f"{up[-2]} {up[-1]}" in MULTI_LAST:
        return " ".join(up[:-2]), f"{up[-2]} {up[-1]}"
    if len(up) >= 2:
        return up[0], up[-1]
    return up[0], up[0]


def sql_str(value: str) -> str:
    return value.replace("'", "''")


def main() -> None:
    rows: list[tuple[str, str, str, str, str]] = []
    for strand, names in FACULTY.items():
        for index, name in enumerate(names, 1):
            first, last = split_name(name)
            rows.append((
                f"FAC-{strand}-{index:02d}",
                sql_str(last),
                sql_str(first),
                DEPT[strand],
                strand,
            ))

    lines = [
        "-- Full SHS faculty roster (107 teachers) — max 3 subjects per semester each",
        "-- Run in Supabase SQL Editor AFTER faculty-strands-rooms.sql",
        "-- Safe to re-run (ON CONFLICT updates).",
        "",
        "INSERT INTO faculty (faculty_id, last_name, first_name, role, department, password, max_load_units, is_active) VALUES",
    ]
    value_lines = [
        f"  ('{fid}', '{last}', '{first}', 'Teacher', '{dept}', 'teacher123', 3, TRUE)"
        for fid, last, first, dept, _ in rows
    ]
    lines.append(",\n".join(value_lines))
    lines.extend([
        "ON CONFLICT (faculty_id) DO UPDATE SET",
        "  last_name = EXCLUDED.last_name,",
        "  first_name = EXCLUDED.first_name,",
        "  department = EXCLUDED.department,",
        "  max_load_units = 3,",
        "  is_active = TRUE;",
        "",
    ])

    for strand in FACULTY:
        lines.extend([
            f"-- Link {strand} teachers",
            "INSERT INTO faculty_strands (faculty_id, strand_id)",
            "SELECT f.id, s.id",
            "FROM faculty f",
            f"JOIN strands s ON s.code = '{strand}'",
            f"WHERE f.faculty_id LIKE 'FAC-{strand}-%'",
            "ON CONFLICT (faculty_id, strand_id) DO NOTHING;",
            "",
        ])

    lines.append("-- Summary counts per strand")
    for strand in FACULTY:
        lines.extend([
            f"SELECT '{strand}' AS strand, COUNT(*) AS teachers",
            "FROM faculty f",
            "JOIN faculty_strands fs ON fs.faculty_id = f.id",
            "JOIN strands s ON s.id = fs.strand_id",
            f"WHERE s.code = '{strand}' AND f.faculty_id LIKE 'FAC-{strand}-%' AND f.is_active = TRUE;",
            "",
        ])

    lines.extend([
        "-- Optional: deactivate old sample teachers replaced by this roster",
        "UPDATE faculty SET is_active = FALSE",
        "WHERE faculty_id IN (",
        "  'FAC-CK-01', 'FAC-CSS-01', 'FAC-GAS-01', 'FAC-HE-01', 'FAC-HUM-01', 'FAC-IA-01'",
        ");",
    ])

    out = Path(__file__).resolve().parents[1] / "supabase" / "seed-all-strand-faculty.sql"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} teachers)")


if __name__ == "__main__":
    main()
