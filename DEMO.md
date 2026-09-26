# Demo runbook

Target: **3 minutes**. Two tickets, two outcomes, one approval click.

## Before you hit record

- [ ] Run on the **macOS/Linux** machine (Windows has no local sandbox).
- [ ] `npx @truefoundry/trueforge` running, `python setup.py` green.
- [ ] Linear OAuth complete; `setup.py` re-run so the gate names the real tool.
- [ ] Two Linear issues open (see below).
- [ ] Browser zoomed to ~125% so text is legible in the recording.
- [ ] Close Slack/Discord/email. No notification popups.
- [ ] **Check your screen for keys** — no `.env` open in an editor, no terminal
      scrollback showing `export OPENAI_API_KEY=...`. Clear it: `clear`.

## The two Linear issues

**Issue 1 — reproducible**
> Title: `add() returns wrong sum`
> add(-2, 3) returns -5 but we expect 1. Positive inputs are wrong too:
> add(2, 3) gives -1 instead of 5. Repo: sample-repo, tests: python -m pytest -q

**Issue 2 — not reproducible**
> Title: `App crashes on empty input`
> Sometimes the app crashes when a field is submitted empty. We cannot give
> exact steps and it does not happen every time. Repo: sample-repo

## Script

**0:00–0:20 — Frame the problem.**
"Support engineers spend their day on tickets where the first real question is
just: is this actually broken? We built an agent that answers that by running
the code, not by guessing."

**0:20–1:20 — Ticket 1, the real bug.**
Start a session with `ticket-resolver`, give it the first Linear issue ID.

Narrate what's on screen as it happens:
- it pulls the issue from Linear over MCP — *real ticket, not a fixture*
- it runs `python -m pytest -q` **in the sandbox** — pause here, this is the
  graded bit. Let the failing output sit on screen for a beat.
- `2 failed` — it found the root cause: `calculator.py` subtracts
- it patches, **re-runs the tests**, and shows them passing

Say out loud: *"It didn't just propose a fix, it proved the fix."*

**1:20–1:50 — The approval gate.**
The agent tries to post the reply. It stops.

"This is a server-side hold, not a prompt instruction. TrueForge emits
`tool.approval_required` and halts the turn. No wording in the system prompt can
talk its way past this."

Show the pending call. **Click approve.** Cut to the comment live on the Linear
issue.

**1:50–2:40 — Ticket 2, the honest failure.**
Second issue. The suite runs and passes. Nothing matches the report.

"This is the case we care most about. There's no bug here, and the agent says
so — it reports what it ran, and asks for the version and a stack trace. It does
not invent a plausible fix."

Show the draft. Note it **still** goes through approval.

**2:40–3:00 — Close.**
"Real ticket in, real sandbox execution, a verified patch or an honest no — and
a human in the loop on anything the customer sees."

## If something breaks mid-demo

- **Linear OAuth dies on venue wifi** → fall back to `tickets.json`: paste the
  ticket JSON straight into the chat. Say you're doing it. Sandbox execution and
  the approval gate — the graded parts — are unaffected.
- **Sandbox is slow to cold-start** → keep talking through what it's doing;
  don't stop and stare at the spinner.
- **Agent goes down a rabbit hole** → cut, re-run. Don't debug on camera.

Record ticket 1 and ticket 2 as **separate takes** and stitch them. A clean
two-minute cut beats one shaky three-minute run.
