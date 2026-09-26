#!/usr/bin/env python3
"""Provision the Ticket Resolver agent on a running TrueForge instance.

Idempotent - safe to re-run. Reads secrets from the environment only; nothing
is written to disk.

    export OPENAI_API_KEY=sk-...
    export DAYTONA_API_KEY=dtn-...      # optional on macOS/Linux
    python setup.py

Run it after `npx @truefoundry/trueforge` is already up.
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790").rstrip("/")
MODEL = os.environ.get("TICKET_RESOLVER_MODEL", "openai/gpt-5.6-terra")
AGENT_NAME = "ticket-resolver"
PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "agent", "system_prompt.md")

# Linear tool names vary by MCP server version, so we match on substrings
# instead of hardcoding. Anything that posts a comment is the customer reply.
REPLY_TOOL_HINTS = ("create_comment", "createcomment", "add_comment", "comment")


def call(method, path, body=None):
    """Return (status, parsed_json_or_text)."""
    url = path if path.startswith("http") else BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode(), e.code
    except urllib.error.URLError as e:
        die(f"Cannot reach TrueForge at {BASE} ({e.reason}).\n"
            f"       Start it first:  npx @truefoundry/trueforge")
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def ok(status):
    return 200 <= status < 300


def say(sym, msg):
    print(f"  {sym} {msg}")


def die(msg):
    print(f"\nFAILED: {msg}")
    sys.exit(1)


def step(n, title):
    print(f"\n[{n}] {title}")


# --------------------------------------------------------------------------
step(1, "TrueForge reachable?")

status, caps = call("GET", "/api/v1/capabilities")
if not ok(status):
    die(f"/capabilities returned {status}: {caps}")
say("OK", f"connected to {BASE}")

# --------------------------------------------------------------------------
step(2, "Model provider (OpenAI)")

status, existing = call("GET", "/api/v1/settings/model-providers")
configured = {p.get("name") for p in (existing.get("data") or [])} if ok(status) else set()

if "openai" in configured:
    say("OK", "openai provider already configured (leaving key untouched)")
else:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        say("!!", "OPENAI_API_KEY not set - skipping.")
        say("  ", "Set it and re-run, or add the key in Settings -> Models.")
    else:
        model_id = MODEL.split("/", 1)[1]
        status, resp = call("POST", "/api/v1/settings/model-providers", {
            "manifest": {
                "type": "openai",
                "auth": {"api_key": key},
                "models": [{"model_id": model_id, "name": model_id.replace(".", "-")}],
            }
        })
        if ok(status):
            say("OK", f"configured openai with {model_id}")
        else:
            say("!!", f"could not configure openai ({status}): {resp}")
            say("  ", "Add it via Settings -> Models in the UI instead.")

# --------------------------------------------------------------------------
step(3, "Sandbox provider")

status, sb = call("GET", "/api/v1/settings/sandbox-providers")
if ok(status):
    say("OK", "sandbox provider already configured")
else:
    dkey = os.environ.get("DAYTONA_API_KEY")
    if not dkey:
        if sys.platform == "win32":
            say("!!", "No Daytona key AND this is Windows - there is no local")
            say("  ", "sandbox fallback on win32. Sandbox execution WILL NOT WORK.")
            say("  ", "Use the macOS/Linux machine, or set DAYTONA_API_KEY.")
        else:
            say("--", f"No Daytona key; falling back to the local sandbox "
                      f"provider ({sys.platform} supports it).")
    else:
        status, resp = call("PUT", "/api/v1/settings/sandbox-providers", {
            "manifest": {
                "type": "daytona",
                "auth": {"api_key": dkey},
                "exec_timeout_ms": 60000,
                "auto_stop_interval_in_minutes": 5,
                "auto_archive_interval_in_minutes": 60,
                "auto_delete_interval_in_minutes": 7200,
            }
        })
        say("OK" if ok(status) else "!!",
            "configured daytona" if ok(status) else f"daytona failed ({status}): {resp}")

# --------------------------------------------------------------------------
step(4, "Linear MCP server")

status, resp = call("POST", "/api/v1/settings/mcp-servers", {
    "manifest": {
        "type": "remote",
        "name": "linear",
        "url": "https://mcp.linear.app/mcp",
        "description": "Search, read, and comment on Linear issues.",
        "auth": {"type": "dcr"},
    }
})
say("OK", "linear registered" if ok(status) else "linear already registered")

status, info = call("GET", "/api/v1/mcp-servers/linear")
auth_state = (info.get("data", {}).get("auth_status", {}).get("status")
              if ok(status) else "unknown")

linear_tools = []
if auth_state == "auth_required":
    status, auth = call("GET", "/api/v1/mcp-servers/linear/authorize")
    url = auth.get("authorization_url") if isinstance(auth, dict) else None
    say("!!", "Linear needs OAuth. Open this in a browser and approve:")
    print(f"\n      {url or BASE + '/api/v1/mcp-servers/linear/authorize'}\n")
    say("  ", "Then re-run this script to gate the reply tool automatically.")
else:
    say("OK", "linear authenticated")
    status, tools = call("GET", "/api/v1/mcp-servers/linear/tools")
    if ok(status):
        linear_tools = [t.get("name") for t in (tools.get("data") or []) if t.get("name")]
        say("OK", f"{len(linear_tools)} tools discovered")

# Which Linear tools must pause for a human? Anything that posts a comment.
reply_tools = [t for t in linear_tools
               if any(h in t.lower() for h in REPLY_TOOL_HINTS)]
if reply_tools:
    say("OK", f"approval will gate: {', '.join(reply_tools)}")
    approval = reply_tools
else:
    # Safe default: gate every write. Never leave the reply ungated.
    approval = ["@write", "@destructive"]
    say("--", "reply tool not identified yet - gating @write + @destructive "
              "(safe default)")

# --------------------------------------------------------------------------
step(5, f"Agent '{AGENT_NAME}'")

try:
    with open(PROMPT_FILE, encoding="utf-8") as f:
        instructions = f.read()
except OSError as e:
    die(f"cannot read {PROMPT_FILE}: {e}")

manifest = {
    "model": {"name": MODEL},
    "instructions": instructions,
    "mcp_servers": [{
        "name": "linear",
        "enable_tools": ["@all"],
        "require_approval_for_tools": approval,
    }],
    "config": {
        "iteration_limit": 60,
        "sandbox": {"enabled": True, "file_downloads": True},
    },
}
payload = {
    "name": AGENT_NAME,
    "description": "Reproduces customer bug tickets in a sandbox and drafts a reply.",
    "manifest": manifest,
}

status, agents = call("GET", "/api/v1/agents")
existing_id = None
for a in (agents.get("data") or []) if ok(status) else []:
    if a.get("name") == AGENT_NAME:
        existing_id = a.get("id")

if existing_id:
    status, resp = call("PUT", f"/api/v1/agents/{existing_id}", payload)
    verb = "updated"
else:
    status, resp = call("POST", "/api/v1/agents", payload)
    verb = "created"

if not ok(status):
    die(f"agent {verb} failed ({status}): {json.dumps(resp, indent=2)[:900]}")

agent_id = (resp.get("data") or {}).get("id", existing_id)
say("OK", f"agent {verb}  (id: {agent_id})")

# --------------------------------------------------------------------------
status, caps = call("GET", "/api/v1/capabilities")
sandbox_on = (caps.get("data", {}).get("sandbox", {}).get("enabled")
              if ok(status) else False)

print(f"""
{'=' * 70}
  Agent ready:  {BASE}

  sandbox execution : {'ENABLED' if sandbox_on else 'NOT ENABLED  <-- graded requirement, fix this'}
  linear auth       : {auth_state}
  approval gate     : {', '.join(approval)}

  Next: open the UI, start a session with '{AGENT_NAME}', and paste a
  Linear issue ID (or a ticket from tickets.json for the offline fallback).
{'=' * 70}""")
