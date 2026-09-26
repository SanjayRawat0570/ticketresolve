# Demo runbook

**Hard cap: 3:00.** Over by a second and it may not be judged — cut to 2:45 to
leave margin.

Required by the spec:

- [ ] MP4, **1080p**
- [ ] Audio narration **or** captions
- [ ] **At least 30 continuous seconds showing TrueForge itself** — the chat
      UI, the SDK, or the API. This is a scored requirement, not a formality.
- [ ] Uploaded to Google Drive, **shared publicly**, link tested in incognito

The TrueForge-30s requirement is why you demo from the chat UI rather than the
terminal: the session view showing agent steps, tool calls and the
Approve/Reject control is unambiguously "TrueForge in use". The Agent Config
panel (model, instructions, MCP servers, sandbox toggle) is a good second or
two of B-roll if you need to pad it.

Two tickets, two outcomes, one approval click.

## Before you hit record

- [ ] `npx @truefoundry/trueforge` running.
- [ ] `python verify.py` — all 12 checks PASS.
- [ ] **`python cleanup_sandboxes.py --all`** — free the Daytona disk quota.
      Every run leaves a sandbox; at ~10 of them new runs fail with
      "Total disk limit exceeded" and the demo dies mid-take.
- [ ] `python smoke_test.py` — sandbox proven.
- [ ] **Delete any existing comments on SAN-5 / SAN-6** so the demo posts fresh
      ones. Test runs leave real comments behind.
- [ ] Browser zoomed to ~125% so text is legible in the recording.
- [ ] Close Slack/Discord/email. No notification popups.
- [ ] **Check your screen for keys** — no `.env` open in an editor, no terminal
      scrollback showing `export OPENAI_API_KEY=...`. Clear it: `clear`.

## The two Linear issues

Already seeded by `python seed_linear.py` (idempotent — re-run to restore the
wording):

- **SAN-5** `add() returns wrong sum` — a real, reproducible defect.
- **SAN-6** `App crashes on empty input` — vague, and no such bug exists.

Both carry the same `sample-repo` description, so the only difference is
whether the reported defect is actually there.

Run them from the terminal (`python run_ticket.py SAN-5`) or from the chat UI
by starting a session with `ticket-resolver` and typing the ticket ID. The UI
is better on camera — the approval prompt renders as a real Approve/Reject
control.

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

**2:40–2:50 — Close.**
"Real ticket in, real sandbox execution, a verified patch or an honest no — and
a human in the loop on anything the customer sees."

Leave 10 seconds of margin against the 3:00 cap.

## Submission checklist

- [ ] Video ≤ 3:00, 1080p MP4, ≥30s of TrueForge on screen
- [ ] Drive link tested in an incognito window
- [ ] `WRITEUP.md` in the repo root (covers problem, reach, stop point,
      architecture, TrueForge usage, real vs mocked, known limits)
- [ ] Repo public, MIT licensed, `.env.example` present, `.env` NOT committed
- [ ] **Do not squash the commits** — the spec requires visible history
- [ ] Both links pasted into the submission form

## If something breaks mid-demo

- **Linear OAuth dies on venue wifi** → fall back to `tickets.json`: paste the
  ticket JSON straight into the chat. Say you're doing it. Sandbox execution and
  the approval gate — the graded parts — are unaffected.
- **Sandbox is slow to cold-start** → keep talking through what it's doing;
  don't stop and stare at the spinner.
- **"Total disk limit exceeded"** → `python cleanup_sandboxes.py --all`, then
  re-run. This is the most likely failure if you've been testing all day.
- **Agent goes down a rabbit hole** → cut, re-run. Don't debug on camera.

Record ticket 1 and ticket 2 as **separate takes** and stitch them. A clean
two-minute cut beats one shaky three-minute run.
