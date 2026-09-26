# Ticket Resolver

An agent that takes a customer bug ticket, **actually runs the code in a
sandbox** to try to reproduce it, and then either returns a verified patch and a
draft reply — or an honest "could not reproduce".

Replying to the customer is gated behind a **human approval step**. The agent
never sends anything on its own.

## What's real

| Piece | Status |
| --- | --- |
| Ticket source — Linear via MCP (OAuth) | **Real** |
| Sandbox code execution | **Real** |
| Bug reproduction — tests genuinely run and fail | **Real** |
| Patch generation + post-patch re-verification | **Real** |
| Human approval before the customer reply is posted | **Real** |
| Offline fallback queue (`tickets.json`) | Mocked — demo-day backup only |

The reply to the customer is a real comment posted back to the Linear issue, and
it is gated by TrueForge's `require_approval_for_tools`. The agent cannot post
it without a human clicking approve.

`tickets.json` exists only as a contingency if venue wifi breaks the Linear
OAuth flow during the demo.

## How the approval gate works

TrueForge attaches approval to MCP tools, not to the model. The agent config
sets:

```json
"mcp_servers": [{
  "name": "linear",
  "enable_tools": ["get_issue", "list_issues", "list_comments", "save_comment"],
  "require_approval_for_tools": ["save_comment"]
}]
```

Linear exposes 68 tools; the agent gets four. `save_comment` — the one that
posts the customer reply — is the only gated one.

When the agent tries to comment, the server emits `tool.approval_required` and
halts the turn. It resumes only on a `user.tool_approval` event carrying an
`allow` decision. This is enforced server-side — prompt wording cannot bypass it.

The agent config also sets `ask_user_questions.enabled: false`. Without it the
model asks *"may I send this reply?"* through `ask_user_question` instead of
calling `save_comment` — which looks like an approval step but isn't one, and
leaves the reply unsent. The gate has to be the platform's, not the model's
good manners.

## Layout

```
setup.py                  provisions everything (idempotent)
verify.py                 one-command health check of every phase
seed_linear.py            upserts the two demo tickets into Linear
run_ticket.py             drive a ticket from the terminal
smoke_test.py             proves the sandbox really executes code
tfclient.py               shared TrueForge HTTP client

agent/system_prompt.md    the agent's instructions
sample-repo/              the "customer" codebase with a real bug
  calculator.py           add() subtracts instead of adds
  test_calculator.py      4 tests; 2 genuinely fail
tickets.json              offline fallback queue
```

## Verifying everything works

```bash
python verify.py                # all phases configured?
python smoke_test.py            # sandbox really runs code
python run_ticket.py SAN-5      # reproduce -> patch -> approval gate
python run_ticket.py SAN-6      # honest "could not reproduce"
```

`verify.py` makes no model calls and costs nothing. Expected output:

```
PASS  TrueForge reachable
PASS  Model provider configured  -  5 model(s)
PASS  Sandbox provider configured  -  Daytona
PASS  Sandbox capability enabled
PASS  Linear MCP authenticated
PASS  Linear reply tool available  -  68 tools exposed
PASS  Agent 'ticket-resolver' exists
PASS  Agent has sandbox enabled
PASS  ask_user_questions disabled
PASS  Approval gate on the reply tool  -  gates: save_comment
PASS  System prompt loaded
PASS  Sample bug genuinely fails  -  2 failed, 2 passed
```

## The two demo paths

- **TICK-001** — real bug. Sandbox runs the suite → 2 tests fail → agent finds
  the root cause in `calculator.py`, patches it, re-runs to prove the fix, drafts
  a reply → **stops for approval**.
- **TICK-002** — vague, non-reproducible report. Sandbox runs the suite → nothing
  matches the report → agent drafts an honest "could not reproduce, here's what
  I ran, here's what I need from you" → **still stops for approval**.

## Start it

```powershell
.\start.ps1
```

That's the whole thing. It checks the Node version, starts TrueForge if it
isn't already up, provisions the agent, and runs the health check. Safe to
re-run.

Then open <http://localhost:8790> and start a session with `ticket-resolver`,
or drive it from the terminal:

```powershell
python run_ticket.py SAN-5     # reproduce -> patch -> approval gate
python run_ticket.py SAN-6     # honest "could not reproduce"
```

### First run only

Put your keys in `.env` (gitignored — never commit it):

```
OPENAI_API_KEY=sk-...
DAYTONA_API_KEY=dtn_...
```

Then `.\start.ps1` will print a Linear OAuth link. Approve it, re-run
`.\start.ps1`, and run `python seed_linear.py` once to create the two demo
tickets.

### Manual equivalent

```bash
node -v                          # must be >= 22.14
npx @truefoundry/trueforge       # local server + chat UI on :8790
python setup.py                  # provision via the HTTP API
python verify.py                 # health check
```

`setup.py` is idempotent. It configures the model provider, registers the Linear
MCP server, prints the OAuth link if Linear isn't authorized yet, discovers the
real comment-tool name, and creates the agent with the sandbox enabled and the
approval gate attached. Re-run it after completing OAuth so it can gate the
exact tool by name instead of falling back to `@write`.

### Sandbox note — Windows requires Daytona

TrueForge's local sandbox provider is **macOS/Linux only**. On Windows it logs:

```
Local sandbox fallback is unavailable
{"reason":"LocalSandboxProvider supports macOS and Linux only (got win32)"}
```

This project is built and demoed on Windows, so `DAYTONA_API_KEY` is **required**
— there is no keyless fallback. Without it, agent creation fails outright:

```
sandbox is enabled but no sandbox provider is configured
```

Get a free key at [daytona.io](https://daytona.io), put it in `.env`, and re-run
`setup.py`.

## Verifying the sandbox really executes code

```bash
python smoke_test.py
```

Runs a throwaway agent with no connectors whose only job is to execute a marker
command in the sandbox. Passing output looks like:

```
turn    : done  (24s)
exec calls       : 4
PASS - 'SANDBOX-PROOF-42' came back from real execution.
(saw 'Linux' in output - the sandbox is a real remote VM)
```

## Verifying the bug is real

```bash
cd sample-repo && python -m pytest -q
# 2 failed, 2 passed
```
