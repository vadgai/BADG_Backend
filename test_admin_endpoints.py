#!/usr/bin/env python3
"""Quick smoke test for all admin panel API endpoints."""
import requests

BASE = "http://127.0.0.1:8000"

def main():
    r = requests.post(
        f"{BASE}/api/admin/login",
        json={"email": "m87.krishna@gmail.com", "password": "Vadg@44"},
        timeout=10,
    )
    print("LOGIN:", r.status_code)
    r.raise_for_status()
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    endpoints = [
        ("GET", "/api/admin/summary"),
        ("GET", "/api/dashboard"),
        ("GET", "/api/reports?page=1&limit=5"),
        ("GET", "/api/visit?page=1&limit=5"),
        ("GET", "/api/admin/visitors"),
        ("GET", "/api/admin/funnel"),
        ("GET", "/api/admin/diseases"),
        ("GET", "/api/admin/languages"),
        ("GET", "/api/admin/contacts?skip=0&limit=5"),
        ("GET", "/api/admin/report-analyzer-submissions?skip=0&limit=5"),
        ("GET", "/admin/insights/funnel"),
        ("GET", "/admin/insights/diseases?limit=5"),
        ("GET", "/admin/insights/locations"),
        ("GET", "/admin/insights/devices"),
        ("GET", "/admin/sessions/active"),
        ("GET", "/admin/model-logs?limit=10"),
        ("GET", "/admin/api-failures?limit=10"),
        ("GET", "/admin/errors?limit=10"),
        ("GET", "/admin/pdf-logs?limit=10"),
        ("DELETE", "/api/admin/reports/nonexistent-id"),
    ]

    failed = []
    for method, path in endpoints:
        resp = requests.request(method, f"{BASE}{path}", headers=headers, timeout=15)
        ok = resp.status_code == 200 or (method == "DELETE" and resp.status_code == 404)
        label = "OK" if ok else "FAIL"
        print(f"{label} {resp.status_code} {method} {path}")
        if not ok:
            print("   ", resp.text[:150])
            failed.append(path)

    print("---")
    print(f"Passed: {len(endpoints) - len(failed)}/{len(endpoints)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
