from __future__ import annotations

import os
import sys
import requests


BASE_URL = os.getenv("EVIFORGE_BASE_URL", "http://127.0.0.1:8000/api")
USERNAME = os.getenv("EVIFORGE_ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("EVIFORGE_ADMIN_PASSWORD", "change-me")
ACK_TEXT = "I confirm I have legal authorization to process this evidence."


def main() -> int:
    print(f"[*] Base URL: {BASE_URL}")

    r = requests.get(f"{BASE_URL}/auth/bootstrap/status", timeout=5)
    if r.status_code != 200:
        print(f"[-] bootstrap/status failed: {r.status_code} {r.text}")
        return 1
    print(f"[+] bootstrap/status: {r.json()}")

    r = requests.post(
        f"{BASE_URL}/auth/ack",
        json={"text": ACK_TEXT, "actor": "verify_auth"},
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] ack failed: {r.status_code} {r.text}")
        return 1
    print("[+] acknowledgement stored")

    r = requests.post(
        f"{BASE_URL}/auth/token",
        data={"username": USERNAME, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] login failed: {r.status_code} {r.text}")
        return 1
    token = r.json()["access_token"]
    print("[+] login ok")

    r = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )
    if r.status_code != 200:
        print(f"[-] /auth/me failed: {r.status_code} {r.text}")
        return 1
    print(f"[+] /auth/me: {r.json()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
