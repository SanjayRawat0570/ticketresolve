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
  "require_approval_for_tools": ["create_comment"]
}]
```

When the agent tries to comment, the server emits `tool.approval_required` and
halts the turn. It resumes only on a `user.tool_approval` event carrying an
`allow` decision. This is enforced server-side — prompt wording cannot bypass it.

## Layout

```
tickets.json              mocked ticket queue (2 tickets, 2 outcomes)
sample-repo/              the "customer" codebase with a real bug
  calculator.py           add() subtracts instead of adds
  test_calculator.py      2 tests that genuinely fail
agent/system_prompt.md    the agent's instructions
```

## The two demo paths

- **TICK-001** — real bug. Sandbox runs the suite → 2 tests fail → agent finds
  the root cause in `calculator.py`, patches it, re-runs to prove the fix, drafts
  a reply → **stops for approval**.
- **TICK-002** — vague, non-reproducible report. Sandbox runs the suite → nothing
  matches the report → agent drafts an honest "could not reproduce, here's what
  I ran, here's what I need from you" → **still stops for approval**.

## Setup

```bash
node -v                          # must be >= 22.14
npx @truefoundry/trueforge       # starts local server + chat UI on :8790

export OPENAI_API_KEY=sk-...     # never commit this
python setup.py                  # provisions everything via the HTTP API
```

`setup.py` is idempotent. It configures the model provider, registers the Linear
MCP server, prints the OAuth link if Linear isn't authorized yet, discovers the
real comment-tool name, and creates the agent with the sandbox enabled and the
approval gate attached. Re-run it after completing OAuth so it can gate the
exact tool by name instead of falling back to `@write`.

### Sandbox note — run the demo on macOS or Linux

TrueForge's local sandbox provider is **macOS/Linux only**. On Windows it logs:

```
Local sandbox fallback is unavailable
{"reason":"LocalSandboxProvider supports macOS and Linux only (got win32)"}
```

On Windows the only sandbox provider is Daytona, so a `DAYTONA_API_KEY` is
mandatory there. On macOS/Linux the local provider works with no key.

## Verifying the bug is real

```bash
cd sample-repo && python -m pytest -q
# 2 failed, 2 passed
```
