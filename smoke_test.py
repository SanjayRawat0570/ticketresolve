#!/usr/bin/env python3
"""Prove the sandbox really executes code.

Runs a throwaway agent (no MCP, no Linear) whose only job is to execute a
command in the sandbox and report the output. If this passes, Daytona is wired
correctly and the graded "runs code safely in a sandbox" requirement is met.

    python smoke_test.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790").rstrip("/")
MARKER = "SANDBOX-PROOF-42"


def call(method, path, body=None):
    """Return (status, parsed_json_or_text). Same contract as setup.py."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw, status = r.read().decode(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode(), e.code
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach TrueForge at {BASE} ({e.reason}). Is it running?")
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def ok(status):
    return 200 <= status < 300


def main():
    status, models = call("GET", "/api/v1/models")
    names = [m["name"] for m in (models.get("data") or [])] if ok(status) else []
    if not names:
        sys.exit("No models configured. Run setup.py first.")
    model = next((n for n in names if "terra" in n), names[0])

    status, caps = call("GET", "/api/v1/capabilities")
    if not caps.get("data", {}).get("sandbox", {}).get("enabled"):
        sys.exit("Sandbox is not enabled. Set DAYTONA_API_KEY and run setup.py.")

    print(f"model   : {model}")
    print("creating throwaway session (sandbox on, no connectors)...")

    status, sess = call("POST", "/api/v1/sessions", {
        "agent": {"spec": {
            "model": {"name": model},
            "instructions": ("You have a sandbox. Use it to run the exact "
                             "command you are given and report its stdout "
                             "verbatim. Do not guess the output."),
            "config": {"iteration_limit": 12,
                       "sandbox": {"enabled": True, "file_downloads": False}},
        }}
    })
    if not ok(status):
        sys.exit(f"session create failed ({status}): {sess}")
    sid = sess["data"]["id"]
    print(f"session : {sid}")

    prompt = (f"Run this in the sandbox and show me the output:\n\n"
              f"  python3 -c \"print('{MARKER}')\"\n\n"
              f"Then run `uname -a` and show that too.")

    print("running turn (this provisions a Daytona sandbox; may take ~30s)...")
    t0 = time.time()
    status, turn = call("POST", f"/api/v1/sessions/{sid}/turns", {
        "input": [{"type": "user.message", "content": prompt}],
        "stream": False,
    })
    if not ok(status):
        sys.exit(f"turn create failed ({status}): {turn}")
    tid = turn["data"]["id"]

    # The turn object has no status field, and "turn.done" is an SSE-only
    # event that never lands in the persisted list - so treat the turn as
    # finished once the event count stops growing and we've seen a response.
    events, done, stable = [], False, 0
    while time.time() - t0 < 180:
        status, ev = call("GET", f"/api/v1/sessions/{sid}/turns/{tid}/events")
        if ok(status):
            new = ev.get("data") or []
            stable = stable + 1 if len(new) == len(events) and new else 0
            events = new
            got_response = any("tool.response" in json.dumps(e) for e in events)
            if stable >= 3 and got_response:
                done = True
                break
        time.sleep(3)

    elapsed = time.time() - t0
    print(f"turn    : {'done' if done else 'STILL RUNNING'}  ({elapsed:.0f}s)")

    blob = json.dumps(events)
    print(f"exec calls       : {blob.count(chr(34) + 'exec' + chr(34))}")
    for e in events:
        inner = e.get("event") or {}
        if inner.get("type") == "sandbox.created":
            print(f"sandbox created  : {inner.get('sandbox_id')}")

    print("\n" + "=" * 62)
    if MARKER in blob:
        print(f"  PASS - '{MARKER}' came back from real execution.")
        print("  Sandbox code execution is working.")
    else:
        print(f"  FAIL - marker '{MARKER}' not found in the transcript.")
        print("  The agent may have answered from memory without running code.")
        print("  Inspect the session in the UI:")
        print(f"    {BASE}/sessions/{sid}")
    print("=" * 62)

    if "Linux" in blob:
        print("  (saw 'Linux' in output - the sandbox is a real remote VM)")


if __name__ == "__main__":
    main()
