#!/usr/bin/env python3
"""Provision the Ticket Resolver agent on a running TrueForge instance.

Idempotent - safe to re-run. Reads secrets from the environment only; nothing
is written to disk.

Keys come from the shell environment or from a local .env (gitignored, never
printed). Supplying them through the TrueForge UI instead also works - this
script detects an already-configured provider and leaves it alone.

    export OPENAI_API_KEY=sk-...
    export DAYTONA_API_KEY=dtn-...      # optional on macOS/Linux
    python setup.py

Run it after `npx @truefoundry/trueforge` is already up.
"""

import json
import os
import sys

from tfclient import BASE, HERE, call, ok

# Empty means "auto-discover from whatever is configured". Note the model FQN
# uses the hyphenated `name` (openai/gpt-5-6-terra), not the dotted `model_id`.
MODEL = os.environ.get("TICKET_RESOLVER_MODEL", "")

# Preferred in order; first one actually configured wins.
MODEL_PREFERENCE = ("gpt-5-6-terra", "gpt-5-6-sol", "gpt-5-6-luna", "gpt-5-5")
AGENT_NAME = "ticket-resolver"
PROMPT_FILE = os.path.join(HERE, "agent", "system_prompt.md")

# Linear exposes 68 tools; handing the agent all of them wastes context and
# invites it to wander. It only needs to read a ticket and reply to it.
LINEAR_TOOLS = ["get_issue", "list_issues", "list_comments", "save_comment"]

# The customer reply. Linear calls it save_comment (not create_comment).
# Ordered by preference; the first one the server actually exposes wins.
REPLY_TOOL_CANDIDATES = ("save_comment", "create_comment", "add_comment")


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
        model_id = "gpt-5.6-terra"
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

# Resolve the model FQN against what is actually configured, so a model the
# provider doesn't expose can't blow up agent creation at step 5.
status, models = call("GET", "/api/v1/models")
available = [m.get("name") for m in (models.get("data") or [])] if ok(status) else []
if not available:
    die("no models configured. Add an OpenAI key in Settings -> Models, then re-run.")

if MODEL and MODEL in available:
    pass
elif MODEL:
    say("!!", f"{MODEL} is not configured; ignoring TICKET_RESOLVER_MODEL")
    MODEL = ""

if not MODEL:
    MODEL = next((f"openai/{p}" for p in MODEL_PREFERENCE
                  if f"openai/{p}" in available), available[0])
say("OK", f"using model {MODEL}")

# --------------------------------------------------------------------------
step(3, "Sandbox provider")

# Agent creation is rejected outright when sandbox.enabled is true and no
# provider exists, so this flag lets us validate the Linear wiring and the
# approval gate on a machine that cannot run a sandbox. Never demo with it.
NO_SANDBOX = "--no-sandbox" in sys.argv or os.environ.get("NO_SANDBOX") == "1"

status, sb = call("GET", "/api/v1/settings/sandbox-providers")
sandbox_provider_ok = ok(status)
dkey = os.environ.get("DAYTONA_API_KEY")

if sandbox_provider_ok and not dkey:
    say("OK", "sandbox provider already configured")
else:
    if not dkey:
        if sys.platform == "win32":
            say("!!", "No Daytona key AND this is Windows - there is no local")
            say("  ", "sandbox fallback on win32. Sandbox execution WILL NOT WORK.")
            say("  ", "Use a macOS/Linux machine, or set DAYTONA_API_KEY.")
        else:
            say("--", f"No Daytona key; falling back to the local sandbox "
                      f"provider ({sys.platform} supports it).")
    else:
        # Re-PUT even when already configured, so the retention intervals
        # below stay applied. A real key value rotates it; the stored key is
        # kept if the value is the redacted placeholder.
        status, resp = call("PUT", "/api/v1/settings/sandbox-providers", {
            "manifest": {
                "type": "daytona",
                "auth": {"api_key": dkey},
                "exec_timeout_ms": 60000,
                # Aggressive cleanup: a free Daytona account caps total disk
                # at 30 GiB, and every run that executes code leaves a
                # sandbox behind. The stock 7200-minute delete (5 days) fills
                # the quota after ~10 runs, after which new runs fail with
                # "Total disk limit exceeded". See cleanup_sandboxes.py.
                "auto_stop_interval_in_minutes": 5,
                "auto_archive_interval_in_minutes": 10,
                "auto_delete_interval_in_minutes": 30,
            }
        })
        say("OK" if ok(status) else "!!",
            "configured daytona" if ok(status) else f"daytona failed ({status}): {resp}")
        sandbox_provider_ok = ok(status)

sandbox_enabled = sandbox_provider_ok or not NO_SANDBOX
if NO_SANDBOX and not sandbox_provider_ok:
    sandbox_enabled = False
    say("!!", "--no-sandbox: creating the agent WITHOUT sandbox execution.")
    say("  ", "This validates Linear + the approval gate only. The agent")
    say("  ", "cannot reproduce bugs. DO NOT DEMO THIS BUILD.")

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

# Which Linear tool posts the customer reply? That one must pause for a human.
reply_tool = next((c for c in REPLY_TOOL_CANDIDATES if c in linear_tools), None)
if reply_tool:
    approval = [reply_tool]
    enabled = [t for t in LINEAR_TOOLS if t in linear_tools]
    say("OK", f"tools enabled: {', '.join(enabled)}")
    say("OK", f"approval gates: {reply_tool}")
else:
    # Never leave the reply ungated. If we cannot name the tool, gate all
    # writes and expose everything so the agent can still function.
    approval = ["@write", "@destructive"]
    enabled = ["@all"]
    say("--", "reply tool not identified (Linear may be unauthenticated) - "
              "gating @write + @destructive")

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
        "enable_tools": enabled,
        "preload": True,
        "require_approval_for_tools": approval,
    }],
    "config": {
        "iteration_limit": 60,
        "sandbox": {"enabled": sandbox_enabled, "file_downloads": True},
        # Without this the agent asks "may I send this?" via ask_user_question
        # instead of calling save_comment - which bypasses the real approval
        # gate and leaves the reply unsent. The gate must be the platform's.
        "ask_user_questions": {"enabled": False},
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
    # PUT rejects "name" - it takes description + manifest only.
    status, resp = call("PUT", f"/api/v1/agents/{existing_id}",
                        {k: v for k, v in payload.items() if k != "name"})
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
