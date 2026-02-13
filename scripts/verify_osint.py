from __future__ import annotations

import os
import sys
import requests


BASE_URL = os.getenv("EVIFORGE_BASE_URL", "http://127.0.0.1:8000/api")
USERNAME = os.getenv("EVIFORGE_ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("EVIFORGE_ADMIN_PASSWORD", "change-me")
ACK_TEXT = "I confirm I have legal authorization to process this evidence."


def _auth_headers() -> dict[str, str]:
    r = requests.post(
        f"{BASE_URL}/auth/ack",
        json={"text": ACK_TEXT, "actor": "verify_osint"},
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


def main() -> int:
    headers = _auth_headers()
    print("[+] auth ok")

    r = requests.post(
        f"{BASE_URL}/cases",
        json={"name": "OSINT Verify Case"},
        headers=headers,
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] create case failed: {r.status_code} {r.text}")
        return 1
    case_id = r.json()["id"]
    print(f"[+] case: {case_id}")

    r = requests.post(
        f"{BASE_URL}/cases/{case_id}/osint/actions",
        json={
            "provider": "facecheck",
            "action_type": "remove_my_photos",
            "target_label": "test-target",
            "notes": "initial draft",
        },
        headers=headers,
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] create action failed: {r.status_code} {r.text}")
        return 1
    action = r.json()
    action_id = action["id"]
    print(f"[+] action: {action_id}")

    r = requests.patch(
        f"{BASE_URL}/cases/{case_id}/osint/actions/{action_id}",
        json={
            "status": "in_review",
            "tracking_url": "https://example.test/ticket/123",
            "notes": "updated",
        },
        headers=headers,
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] update action failed: {r.status_code} {r.text}")
        return 1
    print(f"[+] action updated: {r.json()['status']}")

    r = requests.get(
        f"{BASE_URL}/cases/{case_id}/osint/actions",
        headers=headers,
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] list actions failed: {r.status_code} {r.text}")
        return 1
    print(f"[+] actions in case: {len(r.json())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
