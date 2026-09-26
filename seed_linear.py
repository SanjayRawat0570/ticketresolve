#!/usr/bin/env python3
"""Create the two demo tickets in Linear, if they aren't there already.

Run once. Idempotent - it matches on title and skips anything that exists.
Delete the issues from Linear if you want to start over.

    python seed_linear.py
"""

import sys

from tfclient import call, ok, inner, run_turn

# Both tickets carry the same repo description so the agent can rebuild it in
# the sandbox. Only the first one describes a defect that actually exists -
# the second must come back "could not reproduce".
REPO = """
Repo: sample-repo   Tests: python -m pytest -q

calculator.py:
    def add(a, b):
        return a - b

    def divide(a, b):
        if b == 0:
            raise ValueError("division by zero")
        return a / b

test_calculator.py covers add() for positive and negative inputs, divide(),
and that divide by zero raises ValueError.
"""

TICKETS = [
    ("add() returns wrong sum",
     "add(-2, 3) returns -5 but we expect 1. Positive inputs are wrong too: "
     "add(2, 3) gives -1 instead of 5.\n" + REPO),
    ("App crashes on empty input",
     "Sometimes the app crashes when a field is submitted empty. We cannot "
     "give exact steps and it does not happen every time. No stack trace.\n"
     + REPO),
]


def main():
    status, info = call("GET", "/api/v1/mcp-servers/linear")
    state = (info.get("data", {}).get("auth_status", {}).get("status")
             if ok(status) else "unreachable")
    if state != "authenticated":
        sys.exit(f"Linear is '{state}'. Authorize it first:\n"
                 f"  python setup.py   (prints the OAuth link)")

    status, models = call("GET", "/api/v1/models")
    names = [m["name"] for m in (models.get("data") or [])] if ok(status) else []
    if not names:
        sys.exit("No models configured. Run setup.py first.")
    model = next((n for n in names if "terra" in n), names[0])

    # A throwaway agent with issue-writing rights. The real ticket-resolver
    # agent deliberately cannot create or edit issues - it only comments.
    status, sess = call("POST", "/api/v1/sessions", {"agent": {"spec": {
        "model": {"name": model},
        "instructions": ("You manage a Linear workspace. Create exactly the "
                         "issues you are asked for, in the first team you "
                         "find. Do not create duplicates."),
        "mcp_servers": [{
            "name": "linear",
            "enable_tools": ["list_teams", "list_issues", "save_issue"],
            "preload": True,
            "require_approval_for_tools": [],
        }],
        "config": {"iteration_limit": 30, "sandbox": {"enabled": False}},
    }}})
    if not ok(status):
        sys.exit(f"session create failed ({status}): {sess}")
    sid = sess["data"]["id"]

    body = "\n\n====\n".join(f"Title: {t}\nDescription:\n{d}"
                             for t, d in TICKETS)
    prompt = (f"Upsert these two issues in Linear. If an issue with the exact "
              f"title already exists, update its description to match "
              f"verbatim; otherwise create it. Never create duplicates. Then "
              f"list every issue with its identifier and title.\n\n{body}")

    print(f"session: {sid}\nseeding...\n")

    def show(e):
        i = inner(e)
        if i.get("type") == "model.message" and i.get("content"):
            print(i["content"][:800])
        elif i.get("tool_calls"):
            for tc in i["tool_calls"]:
                print(f"  [tool] {(tc.get('function') or {}).get('name')}")

    run_turn(sid, prompt, on_event=show)


if __name__ == "__main__":
    main()
