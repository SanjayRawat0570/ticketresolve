#!/usr/bin/env python3
"""One-command health check for every phase of Ticket Resolver.

    python verify.py

Checks configuration only - it makes no model calls and costs nothing. For
proof that the sandbox actually executes code, run smoke_test.py; for proof
that the approval gate fires, run run_ticket.py against a ticket.
"""

import os
import subprocess
import sys

from tfclient import HERE, call, ok

AGENT_NAME = "ticket-resolver"
REQUIRED_TOOLS = {"get_issue", "save_comment"}

results = []


def check(label, passed, detail=""):
    results.append((label, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {label}"
          + (f"  -  {detail}" if detail else ""))
    return passed


print("\nTicket Resolver - phase check\n" + "-" * 58)

# 1. Server -----------------------------------------------------------------
status, caps = call("GET", "/api/v1/capabilities")
server_up = check("TrueForge reachable", ok(status))
if not server_up:
    sys.exit("\nStart it first:  npx @truefoundry/trueforge")

sandbox_on = (caps.get("data", {}).get("sandbox", {}) or {}).get("enabled")

# 2. Model ------------------------------------------------------------------
status, models = call("GET", "/api/v1/models")
names = [m["name"] for m in (models.get("data") or [])] if ok(status) else []
check("Model provider configured", bool(names),
      f"{len(names)} model(s), e.g. {names[0]}" if names else "none")

# 3. Sandbox ----------------------------------------------------------------
status, _ = call("GET", "/api/v1/settings/sandbox-providers")
check("Sandbox provider configured", ok(status),
      "Daytona" if ok(status) else "no provider - agent cannot run code")
check("Sandbox capability enabled", bool(sandbox_on),
      "" if sandbox_on else "graded requirement is NOT met")

if sys.platform == "win32" and not ok(status):
    print("        note: Windows has no local sandbox fallback; "
          "DAYTONA_API_KEY is required here.")

# 4. Linear -----------------------------------------------------------------
status, info = call("GET", "/api/v1/mcp-servers/linear")
state = (info.get("data", {}).get("auth_status", {}).get("status")
         if ok(status) else "not registered")
linear_ok = check("Linear MCP authenticated", state == "authenticated", state)

tools = []
if linear_ok:
    status, t = call("GET", "/api/v1/mcp-servers/linear/tools")
    tools = [x.get("name") for x in (t.get("data") or [])] if ok(status) else []
    check("Linear reply tool available", REQUIRED_TOOLS <= set(tools),
          f"{len(tools)} tools exposed")

# 5. Agent ------------------------------------------------------------------
status, agents = call("GET", "/api/v1/agents")
agent = next((a for a in (agents.get("data") or [])
              if a.get("name") == AGENT_NAME), None) if ok(status) else None
check(f"Agent '{AGENT_NAME}' exists", agent is not None)

if agent:
    m = agent["manifest"]
    cfg = m.get("config") or {}
    check("Agent has sandbox enabled",
          bool((cfg.get("sandbox") or {}).get("enabled")))
    check("ask_user_questions disabled",
          (cfg.get("ask_user_questions") or {}).get("enabled") is False,
          "otherwise the agent asks instead of triggering the real gate")

    servers = m.get("mcp_servers") or []
    linear = next((s for s in servers if s.get("name") == "linear"), None)
    gated = (linear or {}).get("require_approval_for_tools") or []
    check("Approval gate on the reply tool",
          "save_comment" in gated or "@write" in gated,
          f"gates: {', '.join(gated) or 'NONE'}")
    check("System prompt loaded", len(m.get("instructions") or "") > 500,
          f"{len(m.get('instructions') or '')} chars")

# 6. Sample repo really fails ----------------------------------------------
repo = os.path.join(HERE, "sample-repo")
try:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo,
                          capture_output=True, text=True, timeout=120)
    check("Sample bug genuinely fails", proc.returncode != 0,
          proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "")
except Exception as e:  # pytest missing, repo moved, etc.
    check("Sample bug genuinely fails", False, str(e)[:60])

# Summary -------------------------------------------------------------------
failed = [label for label, passed, _ in results if not passed]
print("-" * 58)
if failed:
    print(f"\n{len(failed)} check(s) failed:")
    for label in failed:
        print(f"  - {label}")
    print("\nMost failures are fixed by:  python setup.py")
    sys.exit(1)

print("\nAll phases configured. Deeper proofs:")
print("  python smoke_test.py          sandbox really executes code")
print("  python run_ticket.py SAN-5    reproduce -> patch -> approval gate")
print("  python run_ticket.py SAN-6    honest 'could not reproduce'\n")
