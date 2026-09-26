#!/usr/bin/env python3
"""Drive the ticket-resolver agent from the terminal.

    python run_ticket.py list            # what tickets can it see?
    python run_ticket.py ENG-1           # work a ticket, stop at approval
    python run_ticket.py ENG-1 --approve # ...and approve the reply

Stopping at the approval gate is the default on purpose: posting a comment to
a real Linear issue is not something a test script should do silently.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790").rstrip("/")
AGENT = "ticket-resolver"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw, status = r.read().decode(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode(), e.code
    except urllib.error.URLError as e:
        sys.exit(f"Cannot reach TrueForge at {BASE} ({e.reason}). Is it running?")
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def ok(s):
    return 200 <= s < 300


def inner(e):
    return e.get("event") or {}


def wait_for_turn(sid, tid, budget=300):
    """Poll the session event stream until the turn ends or halts for approval.

    Two gotchas this handles: the API returns events newest-first, and
    'turn.done' shows up on /sessions/{id}/events but not on the turn-scoped
    endpoint.
    """
    printed, t0 = 0, time.time()
    while time.time() - t0 < budget:
        status, ev = call("GET", f"/api/v1/sessions/{sid}/events")
        if ok(status):
            events = list(reversed(ev.get("data") or []))  # -> chronological
            for e in events[printed:]:
                describe(e)
            printed = len(events)

            pending = [e for e in events
                       if inner(e).get("type") == "tool.approval_required"]
            if pending:
                return events, pending[-1]
            if any(inner(e).get("type") == "turn.done" for e in events):
                return events, None
        time.sleep(3)
    print(f"  (timed out after {budget}s)")
    return [], None


def describe(e):
    """Print one line per meaningful event."""
    i = inner(e)
    t = i.get("type")
    if t == "sandbox.created":
        print(f"  [sandbox]  {i.get('sandbox_id')}")
    elif t == "tool.response":
        body = str(i.get("content", ""))[:160].replace("\n", " ")
        print(f"  [result]   {body}")
    elif t == "tool.approval_required":
        for tc in i.get("tool_calls", []):
            print(f"  [APPROVAL] {tc.get('name') or tc.get('id')}  <-- halted")
    elif i.get("tool_calls"):
        for tc in i["tool_calls"]:
            fn = (tc.get("function") or {})
            args = str(fn.get("arguments", ""))[:120].replace("\n", " ")
            print(f"  [tool]     {fn.get('name')}({args})")
    elif t == "model.message" and i.get("content"):
        text = i["content"] if isinstance(i["content"], str) else json.dumps(i["content"])
        print(f"\n  [agent]    {text[:1500]}\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    approve = "--approve" in sys.argv
    if not args:
        sys.exit(__doc__)
    target = args[0]

    if target == "list":
        prompt = ("List the open issues you can see in Linear. Just the "
                  "identifier and title for each. Do not run any code.")
    else:
        prompt = (f"Work Linear ticket {target} end to end. The repository to "
                  f"test is 'sample-repo' - recreate its files in the sandbox "
                  f"from the ticket's description if you cannot fetch it, then "
                  f"run the test suite. Follow your instructions exactly.")

    status, sess = call("POST", "/api/v1/sessions", {"agent": {"name": AGENT}})
    if not ok(status):
        sys.exit(f"session create failed ({status}): {sess}\n"
                 f"Has setup.py been run?")
    sid = sess["data"]["id"]
    print(f"session: {sid}\n")

    status, turn = call("POST", f"/api/v1/sessions/{sid}/turns", {
        "input": [{"type": "user.message", "content": prompt}],
        "stream": False,
    })
    if not ok(status):
        sys.exit(f"turn failed ({status}): {turn}")
    tid = turn["data"]["id"]

    events, pending = wait_for_turn(sid, tid)

    if not pending:
        print(f"\nno approval gate reached. session: {BASE}/sessions/{sid}")
        return

    tool_call = pending["event"]["tool_calls"][-1]
    print("\n" + "=" * 62)
    print("  APPROVAL REQUIRED - the agent is halted server-side.")
    print(f"  tool: {tool_call.get('name') or tool_call.get('id')}")
    print("=" * 62)

    if not approve:
        print(f"\nNot approving (pass --approve to allow). Session: {sid}")
        return

    print("\napproving...")
    status, turn2 = call("POST", f"/api/v1/sessions/{sid}/turns", {
        "input": [{
            "type": "user.tool_approval",
            "thread_id": pending["event"].get("thread_id"),
            "tool_call_id": tool_call.get("id"),
            "approval": {"status": "allow"},
        }],
        "stream": False,
    })
    if not ok(status):
        sys.exit(f"approval failed ({status}): {turn2}")
    wait_for_turn(sid, turn2["data"]["id"])
    print(f"\ndone. session: {BASE}/sessions/{sid}")


if __name__ == "__main__":
    main()
