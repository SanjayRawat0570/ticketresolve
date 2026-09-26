#!/usr/bin/env python3
"""Delete leftover Daytona sandboxes.

Every agent run that executes code provisions a sandbox. They are not cleaned
up immediately, and a free Daytona account has a 30 GiB total disk cap - once
you hit it, new runs fail with:

    Sandbox initialization failed: Total disk limit exceeded

Run this before a demo, or any time runs start failing to start.

    python cleanup_sandboxes.py          # list what's there
    python cleanup_sandboxes.py --all    # delete all of them
"""

import json
import os
import sys
import urllib.error
import urllib.request

from tfclient import load_dotenv

load_dotenv()

API = os.environ.get("DAYTONA_API_URL", "https://app.daytona.io/api").rstrip("/")
KEY = os.environ.get("DAYTONA_API_KEY")


def daytona(method, path):
    if not KEY:
        sys.exit("DAYTONA_API_KEY is not set (put it in .env).")
    req = urllib.request.Request(API + path, method=method,
                                 headers={"Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def main():
    status, data = daytona("GET", "/sandbox")
    if status != 200:
        sys.exit(f"Could not list sandboxes ({status}): {data}")

    boxes = data if isinstance(data, list) else data.get("items", [])
    if not boxes:
        print("No sandboxes. Nothing to clean up.")
        return

    print(f"{len(boxes)} sandbox(es):\n")
    for b in boxes:
        print(f"  {b.get('id')}  state={b.get('state')}")

    if "--all" not in sys.argv:
        print("\nPass --all to delete them.")
        return

    print("\ndeleting...")
    failed = 0
    for b in boxes:
        sid = b.get("id")
        status, resp = daytona("DELETE", f"/sandbox/{sid}?force=true")
        if 200 <= status < 300:
            print(f"  deleted {sid}")
        else:
            failed += 1
            print(f"  FAILED  {sid}  ({status}) {resp}")

    print(f"\n{len(boxes) - failed} deleted, {failed} failed.")


if __name__ == "__main__":
    main()
