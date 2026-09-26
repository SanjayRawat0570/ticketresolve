# Ticket Resolver

## The problem

The slowest part of a support queue isn't fixing bugs — it's working out which
reports are real. An engineer reads a ticket, guesses, and either burns an hour
on something that was never broken or sends a confident reply about a fix
nobody verified.

## What the agent reaches

- **Linear**, over the hosted Linear MCP server (OAuth via dynamic client
  registration). It reads the issue and posts the reply as a comment.
- **A Daytona sandbox**, provisioned on demand, where it recreates the project
  and runs the test suite.

It is given four Linear tools out of the 68 available: `get_issue`,
`list_issues`, `list_comments`, `save_comment`. It cannot create or edit
issues.

## Where it stops

`save_comment` — the customer reply — is gated by
`require_approval_for_tools`. The server emits `tool.approval_required`, halts
the turn, and resumes only on an explicit `allow`. This is enforced outside the
model, so prompt wording cannot route around it. Every ticket ends at this
gate, including "could not reproduce".

## Architecture

Ticket → sandbox reproduction → verdict → patch → reply → human gate. The agent
must re-run the suite after patching and report both the before and after
output. Three verdicts: `REPRODUCED`, `NOT_REPRODUCED`, and `BLOCKED` — the
last one exists because an infrastructure failure must never be dressed up as a
finding about the customer's code.

## How TrueForge was used

TrueForge is the harness: agent loop, MCP routing, sandbox-as-tool, and the
approval checkpoint. Everything is provisioned through its HTTP API by
`setup.py` — model provider, sandbox provider, MCP server, and the agent
manifest — so the whole build is reproducible from a clean machine with one
command.

## Real vs. mocked

Nothing is mocked. The Linear integration, the sandbox execution, the
reproduction, the patch verification and the approval gate all genuinely run.
`tickets.json` ships as an offline fallback if OAuth fails on venue wifi; it is
unused when Linear is connected.

## Known limits

- The agent rebuilds the project in the sandbox from the ticket description
  rather than cloning a repository — fine for the demo, not for real codebases.
- A free Daytona account caps total disk at 30 GiB; leftover sandboxes must be
  cleared (`cleanup_sandboxes.py`) or runs begin to fail.
- Sandboxes cold-start without pytest, costing a few turns per run.
- Only Linear is wired; Jira and Zendesk are not.
- Patch quality is untested beyond single-function bugs.

**Built with:** TrueForge, Linear MCP, Daytona, OpenAI.
