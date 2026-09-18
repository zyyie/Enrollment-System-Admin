"""One-off scan: saved schedules visible vs hidden in DB. Run from ENROLLSYSTEM-ADMIN root."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def rest_get(url: str, key: str, qs: str):
    req = Request(
        f"{url}/rest/v1/{qs}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def rpc(url: str, key: str, name: str, body: dict):
    req = Request(
        f"{url}/rest/v1/rpc/{name}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from enrollment_curriculum import section_slot_name

    env = load_env()
    base = env.get("SUPABASE_URL", "").rstrip("/")
    key = env.get("SUPABASE_SECRET_KEY") or env.get("SUPABASE_PUBLISHABLE_KEY", "")
    if not base or not key:
        print("Missing SUPABASE_URL or key in .env")
        return 1

    semester = "2nd"
    try:
        rpc_rows = rpc(
            base,
            key,
            "get_scheduler_existing_schedules",
            {"p_grade_level": "Grade 11", "p_semester_code": semester},
        )
        if isinstance(rpc_rows, str):
            rpc_rows = json.loads(rpc_rows)
    except Exception as exc:
        print("RPC get_scheduler_existing_schedules failed:", exc)
        rpc_rows = []

    print(f"=== RPC conflict load ({semester} sem, G11+G12) ===")
    print("count:", len(rpc_rows or []))
    by_strand: dict[str, int] = defaultdict(int)
    for row in rpc_rows or []:
        by_strand[f"{row.get('strand')} · {row.get('gradeLevel')}"] += 1
    for label in sorted(by_strand):
        print(f"  {label}: {by_strand[label]} rows")

    raw = rest_get(
        base,
        key,
        "class_schedules?select=id,is_active,subjects(code,semester_code),"
        "sections(name,grade_level,strands(code)),semesters(is_current)"
        "&is_active=eq.true",
    )
    print("\n=== Active class_schedules (all semesters) ===")
    print("total:", len(raw))

    def norm_section(strand: str, grade: str, name: str) -> str | None:
        suffix = str(name or "").split("-", 1)
        suffix = suffix[1].strip() if len(suffix) > 1 else ""
        for letter in ("A", "B"):
            if section_slot_name(strand, grade, letter).upper() == suffix.upper():
                return letter
        return None

    hidden: list[dict] = []
    current_2nd: list[dict] = []
    for row in raw:
        sem = row.get("semesters") or {}
        if not sem.get("is_current"):
            continue
        sub = row.get("subjects") or {}
        sc = sub.get("semester_code")
        if sc not in (None, "", semester):
            continue
        sec = row.get("sections") or {}
        strand = (sec.get("strands") or {}).get("code") or ""
        grade = sec.get("grade_level") or ""
        if norm_section(strand, grade, sec.get("name") or "") is None:
            hidden.append(row)
        else:
            current_2nd.append(row)

    print(f"current school year + {semester} sem (canonical sections):", len(current_2nd))
    print("current school year + wrong section name (HIDDEN from RPC):", len(hidden))
    for row in hidden[:20]:
        sec = row.get("sections") or {}
        sub = row.get("subjects") or {}
        print(
            f"  id={row['id']} {(sec.get('strands') or {}).get('code')} "
            f"{sec.get('grade_level')} section={sec.get('name')} sub={sub.get('code')}"
        )
    if len(hidden) > 20:
        print(f"  ... +{len(hidden) - 20} more")

    inactive = rest_get(base, key, "class_schedules?select=id&is_active=eq.false")
    print("\nInactive class_schedules (is_active=false):", len(inactive))

    cache = ROOT / "data" / "generated_schedules.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        print("\nLocal data/generated_schedules.json:")
        print("  semester:", payload.get("semesterCode"))
        print("  rows:", len(payload.get("schedules") or []))
    else:
        print("\nNo local generated_schedules.json cache.")

    # Simulate greedy seed: count room blocks per day from ICT G11
    ict_g11 = [
        r
        for r in rpc_rows or []
        if r.get("strand") == "ICT" and r.get("gradeLevel") == "Grade 11"
    ]
    print(f"\nICT Grade 11 rows in conflict load: {len(ict_g11)}")
    room_blocks = defaultdict(int)
    for row in ict_g11:
        for sess in row.get("sessions") or []:
            room_blocks[(sess.get("day"), sess.get("room"))] += 1
    print("Unique day+room pairs used by ICT G11:", len(room_blocks))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
