#!/usr/bin/env python3
"""Shared TrueForge HTTP client used by setup.py, smoke_test.py and friends.

Importing this module has no side effects beyond loading .env.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

__all__ = ["BASE", "call", "ok", "inner", "load_dotenv", "run_turn", "events_of"]

HERE = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(path=None):
    """Read .env into the environment. Already-exported values win.

    Values are never printed - secrets must not reach stdout or a transcript.
    """
    path = path or os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


load_dotenv()

BASE = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790").rstrip("/")


def call(method, path, body=None, timeout=180, retries=3):
    """Return (status, parsed_json_or_raw_text).

    Retries on dropped connections - proxied MCP calls (Linear tool listing in
    particular) occasionally reset mid-response, and a demo should not die on
    a transient socket error.
    """
    data = json.dumps(body).encode() if body is not None else None

    for attempt in range(retries):
        req = urllib.request.Request(BASE + path, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw, status = r.read().decode(), r.status
            break
        except urllib.error.HTTPError as e:
            raw, status = e.read().decode(), e.code
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit(f"Cannot reach TrueForge at {BASE} ({reason}).\n"
                     f"Start it with:  npx @truefoundry/trueforge")

    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def ok(status):
    return 200 <= status < 300


def inner(event):
    """Unwrap {"turn_id": ..., "event": {...}} -> the inner event dict."""
    return event.get("event") or {}


def events_of(session_id):
    """Session events in chronological order (the API returns newest first)."""
    status, ev = call("GET", f"/api/v1/sessions/{session_id}/events")
    return list(reversed(ev.get("data") or [])) if ok(status) else []


def run_turn(session_id, prompt, on_event=None, budget=300):
    """Send a message and poll until the turn ends or halts for approval.

    Returns (events, pending_approval_event_or_None).

    Note: 'turn.done' lands on /sessions/{id}/events but not on the
    turn-scoped endpoint, which is why we poll the session stream.
    """
    status, turn = call("POST", f"/api/v1/sessions/{session_id}/turns", {
        "input": [{"type": "user.message", "content": prompt}],
        "stream": False,
    })
    if not ok(status):
        sys.exit(f"turn failed ({status}): {turn}")

    printed, t0 = 0, time.time()
    while time.time() - t0 < budget:
        events = events_of(session_id)
        if on_event:
            for e in events[printed:]:
                on_event(e)
        printed = len(events)

        pending = [e for e in events
                   if inner(e).get("type") == "tool.approval_required"]
        if pending:
            return events, pending[-1]
        if any(inner(e).get("type") == "turn.done" for e in events):
            return events, None
        time.sleep(3)

    print(f"  (timed out after {budget}s)")
    return events_of(session_id), None
