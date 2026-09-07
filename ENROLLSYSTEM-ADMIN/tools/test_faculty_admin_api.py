"""Smoke-test admin Faculty page API endpoints."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8001"


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw or str(exc)}
        return exc.code, payload


def main() -> int:
    results: list[tuple[str, str, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, "OK" if ok else "FAIL", detail))

    code, health = call("GET", "/api/health")
    record("Health", code == 200 and health.get("success"), health.get("portal", ""))

    code, strands = call("GET", "/api/strands")
    strand_list = strands.get("data") or []
    record("List strands", code == 200 and len(strand_list) > 0, f"{len(strand_list)} strands")

    code, teachers = call("GET", "/api/teachers")
    teacher_list = teachers.get("data") or []
    record("List teachers", code == 200 and len(teacher_list) > 0, f"{len(teacher_list)} teachers")

    teacher = teacher_list[0] if teacher_list else None
    if teacher:
        tid = teacher.get("id")
        code, detail = call("GET", f"/api/teachers/detail?id={tid}")
        record(
            "Teacher detail",
            code == 200 and detail.get("data", {}).get("faculty_id") == teacher.get("faculty_id"),
            teacher.get("faculty_id") or "",
        )

        update_body = {
            "id": tid,
            "firstName": teacher.get("first_name") or "TEST",
            "lastName": teacher.get("last_name") or "TEACHER",
            "middleName": teacher.get("middle_name") or "",
            "email": teacher.get("email") or "",
            "department": teacher.get("department") or "ICT DEPARTMENT",
            "maxLoadUnits": teacher.get("max_load_units") or 3,
            "strands": teacher.get("strands") or ["ICT"],
        }
        code, updated = call("POST", "/api/teachers", update_body)
        record("Update teacher (save)", code == 200 and updated.get("success"), updated.get("message", ""))

    create_body = {
        "firstName": "SMOKE",
        "lastName": "TESTFACULTY",
        "email": "smoke.test.faculty@example.com",
        "department": "QA DEPARTMENT",
        "maxLoadUnits": 3,
        "strands": ["ICT"],
        "password": "teacher123",
    }
    code, created = call("POST", "/api/teachers", create_body)
    created_id = created.get("id")
    record(
        "Create teacher (save)",
        code == 200 and created.get("success") and bool(created_id),
        created.get("facultyId") or created.get("message") or str(created.get("error", "")),
    )

    if created_id:
        code, deactivate = call(
            "POST",
            "/api/teachers",
            {
                "id": created_id,
                "firstName": "SMOKE",
                "lastName": "TESTFACULTY",
                "department": "QA DEPARTMENT",
                "maxLoadUnits": 3,
                "strands": ["ICT"],
                "isActive": False,
            },
        )
        record("Deactivate test teacher", code == 200 and deactivate.get("success"), "")

    print("\n=== Faculty Admin API Smoke Test ===")
    for name, status, detail in results:
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    failed = sum(1 for _, status, _ in results if status != "OK")
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
