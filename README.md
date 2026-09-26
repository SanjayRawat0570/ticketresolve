# Ticket Resolver

An agent that takes a customer bug ticket, **actually runs the code in a
sandbox** to try to reproduce it, and then either returns a verified patch and a
draft reply — or an honest "could not reproduce".

Replying to the customer is gated behind a **human approval step**. The agent
never sends anything on its own.

## What's real vs. mocked

| Piece | Status |
| --- | --- |
| Sandbox code execution (Daytona via TrueForge) | **Real** |
| Bug reproduction — tests genuinely run and fail | **Real** |
| Patch generation + post-patch re-verification | **Real** |
| Human approval before customer reply | **Real** |
| Ticket source (Zendesk/Linear/Jira) | **Mocked** — `tickets.json` |
| Outbound email to the customer | **Mocked** — logged, not sent |

Mocking the ticket source is disclosed deliberately: the graded requirements are
sandboxed execution and the approval gate, and both are real.

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
node -v                              # must be >= 22.14
cp .env.example .env                 # add your OpenAI + Daytona keys
npx @truefoundry/trueforge@latest    # starts local server + chat UI
```

Then in the TrueForge UI: connect the model provider, connect the Daytona
sandbox, create an agent using `agent/system_prompt.md`, and enable approval on
the customer-reply tool.

## Verifying the bug is real

```bash
cd sample-repo && python -m pytest -q
# 2 failed, 2 passed
```
