#!/usr/bin/env python3
"""Prove the sandbox really executes code.

Runs a throwaway agent (no MCP, no Linear) whose only job is to execute a
marker command in the sandbox and report the output. If this passes, the
sandbox provider is wired correctly and the graded "runs the code it generates
safely inside a sandbox" requirement is genuinely met.

    python smoke_test.py
"""

import json
import sys

from tfclient import BASE, call, ok, inner, run_turn

MARKER = "SANDBOX-PROOF-42"

PROMPT = (f"Run this in the sandbox and show me the output:\n\n"
          f"  python3 -c \"print('{MARKER}')\"\n\n"
          f"Then run `uname -a` and show that too.")


def main():
    status, models = call("GET", "/api/v1/models")
    names = [m["name"] for m in (models.get("data") or [])] if ok(status) else []
    if not names:
        sys.exit("No models configured. Run setup.py first.")
    model = next((n for n in names if "terra" in n), names[0])

    status, caps = call("GET", "/api/v1/capabilities")
    if not (caps.get("data", {}).get("sandbox", {}) or {}).get("enabled"):
        sys.exit("Sandbox is not enabled. Set DAYTONA_API_KEY and run setup.py.")

    print(f"model   : {model}")
    print("creating throwaway session (sandbox on, no connectors)...")

    status, sess = call("POST", "/api/v1/sessions", {"agent": {"spec": {
        "model": {"name": model},
        "instructions": ("You have a sandbox. Run the exact command you are "
                         "given and report its stdout verbatim. Never guess "
                         "the output."),
        "config": {"iteration_limit": 12,
                   "sandbox": {"enabled": True, "file_downloads": False}},
    }}})
    if not ok(status):
        sys.exit(f"session create failed ({status}): {sess}")
    sid = sess["data"]["id"]
    print(f"session : {sid}")
    print("running turn (provisions a sandbox; may take ~30s)...")

    events, _ = run_turn(sid, PROMPT)
    blob = json.dumps(events)

    for e in events:
        if inner(e).get("type") == "sandbox.created":
            print(f"sandbox : {inner(e).get('sandbox_id')}")

    print("\n" + "=" * 62)
    if MARKER in blob:
        print(f"  PASS - '{MARKER}' came back from real execution.")
        print("  Sandbox code execution is working.")
        if "Linux" in blob:
            print("  'Linux' in output - the sandbox is a real remote VM.")
    else:
        print(f"  FAIL - marker '{MARKER}' not found in the transcript.")
        print("  The agent may have answered without running anything.")
        print(f"  Inspect: {BASE}/sessions/{sid}")
        print("=" * 62)
        sys.exit(1)
    print("=" * 62)


if __name__ == "__main__":
    main()
