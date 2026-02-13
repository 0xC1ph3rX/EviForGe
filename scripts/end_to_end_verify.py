from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests


BASE_URL = os.getenv("EVIFORGE_BASE_URL", "http://127.0.0.1:8000/api")
USERNAME = os.getenv("EVIFORGE_ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("EVIFORGE_ADMIN_PASSWORD", "change-me")
ACK_TEXT = "I confirm I have legal authorization to process this evidence."


def log(msg: str) -> None:
    print(f"[E2E] {msg}")


def auth() -> dict[str, str]:
    r = requests.post(
        f"{BASE_URL}/auth/ack",
        json={"text": ACK_TEXT, "actor": "e2e-script"},
        timeout=5,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ack failed: {r.status_code} {r.text}")

    r = requests.post(
        f"{BASE_URL}/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login failed: {r.status_code} {r.text}")
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def run() -> int:
    headers = auth()
    log("authenticated")

    r = requests.post(
        f"{BASE_URL}/cases",
        json={"name": f"E2E-{int(time.time())}"},
        headers=headers,
        timeout=5,
    )
    if r.status_code != 200:
        log(f"create case failed: {r.status_code} {r.text}")
        return 1
    case_id = r.json()["id"]
    log(f"case={case_id}")

    sample = Path("import") / "e2e_sample.txt"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("forensic sample\nIOC: evil.test\n", encoding="utf-8")

    r = requests.post(
        f"{BASE_URL}/cases/{case_id}/evidence",
        json={"filename": sample.name},
        headers=headers,
        timeout=15,
    )
    if r.status_code != 200:
        log(f"ingest failed: {r.status_code} {r.text}")
        return 1
    evidence_id = r.json()["id"]
    log(f"evidence={evidence_id}")

    r = requests.post(
        f"{BASE_URL}/cases/{case_id}/jobs",
        json={"module": "verify", "evidence_id": evidence_id},
        headers=headers,
        timeout=10,
    )
    if r.status_code != 200:
        log(f"job submit failed: {r.status_code} {r.text}")
        return 1
    job_id = r.json()["id"]
    log(f"job={job_id}")

    final = None
    for _ in range(40):
        time.sleep(0.5)
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=headers, timeout=5)
        if r.status_code != 200:
            continue
        final = r.json()
        status = final.get("status")
        log(f"job status={status}")
        if status in {"COMPLETED", "FAILED"}:
            break

    if not final or final.get("status") != "COMPLETED":
        log("job did not complete successfully")
        return 1

    log("success")
    return 0


if __name__ == "__main__":
    sys.exit(run())
