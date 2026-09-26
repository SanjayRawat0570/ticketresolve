#!/usr/bin/env python3
"""Drive the ticket-resolver agent from the terminal.

    python run_ticket.py list             # what tickets can it see?
    python run_ticket.py SAN-5            # work a ticket, stop at approval
    python run_ticket.py SAN-5 --approve  # ...and approve the reply

Stopping at the approval gate is the default on purpose: posting a comment to
a real Linear issue is not something a test run should do silently.
"""

import json
import sys
import time

from tfclient import BASE, call, ok, inner, events_of, run_turn

AGENT = "ticket-resolver"

WORK_PROMPT = (
    "Work Linear ticket {t} end to end.\n\n"
    "The code under test is the `sample-repo` project described in the "
    "ticket. Recreate its files in the sandbox from the ticket description, "
    "then run the test suite there. Follow your instructions exactly: "
    "reproduce first, and only claim a fix you have re-run the tests against."
)


def describe(event):
    """Print one line per meaningful event."""
    i = inner(event)
    kind = i.get("type")

    if kind == "sandbox.created":
        print(f"  [sandbox]  {i.get('sandbox_id')}")
    elif kind == "tool.approval_required":
        for tc in i.get("tool_calls", []):
            print(f"  [APPROVAL] {tc.get('name') or tc.get('id')}  <-- halted")
    elif kind == "tool.response":
        body = str(i.get("content", ""))[:160].replace("\n", " ")
        print(f"  [result]   {body}")
    elif i.get("tool_calls"):
        for tc in i["tool_calls"]:
            fn = tc.get("function") or {}
            args = str(fn.get("arguments", ""))[:120].replace("\n", " ")
            print(f"  [tool]     {fn.get('name')}({args})")
    elif kind == "model.message" and i.get("content"):
        text = i["content"]
        if not isinstance(text, str):
            text = json.dumps(text)
        print(f"\n  [agent]    {text[:2000]}\n")


def approve(session_id, pending):
    """Resume a turn halted by tool.approval_required."""
    event = pending["event"]
    tool_call = event["tool_calls"][-1]
    status, turn = call("POST", f"/api/v1/sessions/{session_id}/turns", {
        "input": [{
            "type": "user.tool_approval",
            "thread_id": event.get("thread_id"),
            "tool_call_id": tool_call.get("id"),
            "approval": {"status": "allow"},
        }],
        "stream": False,
    })
    if not ok(status):
        sys.exit(f"approval failed ({status}): {turn}")


def wait_until_done(session_id, since=0, budget=180):
    """Stream events from `since` onward until the turn reports done."""
    t0, printed = time.time(), since
    while time.time() - t0 < budget:
        events = events_of(session_id)
        for e in events[printed:]:
            describe(e)
        if len(events) > printed and any(
                inner(e).get("type") == "turn.done" for e in events[printed:]):
            return
        printed = len(events)
        time.sleep(3)
    print(f"  (timed out after {budget}s)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    auto_approve = "--approve" in sys.argv
    if not args:
        sys.exit(__doc__)
    target = args[0]

    prompt = ("List the open issues you can see in Linear - identifier and "
              "title only. Do not run any code."
              if target == "list" else WORK_PROMPT.format(t=target))

    status, sess = call("POST", "/api/v1/sessions", {"agent": {"name": AGENT}})
    if not ok(status):
        sys.exit(f"session create failed ({status}): {sess}\nRun setup.py first.")
    sid = sess["data"]["id"]
    print(f"session: {sid}\n")

    pending_events, pending = run_turn(sid, prompt, on_event=describe)

    if not pending:
        print(f"\nFinished with no approval gate. {BASE}/sessions/{sid}")
        return

    tool_call = pending["event"]["tool_calls"][-1]
    print("\n" + "=" * 64)
    print("  APPROVAL REQUIRED - the agent is halted server-side.")
    print(f"  tool: {tool_call.get('name') or tool_call.get('id')}")
    print("=" * 64)

    if not auto_approve:
        print(f"\nNot approving (pass --approve to allow). Session: {sid}")
        return

    print("\napproving...\n")
    printed = len(pending_events)
    approve(sid, pending)
    wait_until_done(sid, since=printed)
    print(f"\ndone. {BASE}/sessions/{sid}")


if __name__ == "__main__":
    main()
