# Ticket Resolver — submission write-up

*~300 words. Trim the last paragraph first if you need to fit a shorter limit.*

---

**The problem.** The slowest part of a support queue isn't fixing bugs — it's
finding out which reports are real. An engineer reads a ticket, guesses, and
either burns an hour on something that was never broken or writes a confident
reply about a fix nobody verified.

**What we built.** Ticket Resolver takes a Linear issue, reproduces it by
actually running the code in a sandbox, and comes back with one of two things: a
patch it has proven works, or an honest "could not reproduce."

The agent pulls the ticket from Linear over MCP, checks out the referenced repo
into a sandbox, and runs the test suite. If tests fail in a way that matches the
report, it finds the root cause, writes a minimal patch, applies it, and
**re-runs the suite to prove the fix holds** — the before and after output are
both in its report. If the suite passes, it says so and asks for the specific
information it would need. It is instructed never to fabricate a fix, and every
claim it makes about the code must trace to sandbox output from that run.

**The human checkpoint.** Replying to the customer requires approval. This is
enforced by TrueForge's `require_approval_for_tools`, which halts the turn with
a `tool.approval_required` event and resumes only on an explicit allow. It is a
server-side gate, not a line in the system prompt — no amount of clever model
reasoning can route around it.

**What's real.** The Linear integration, the sandboxed execution, the
reproduction, the patch verification, and the approval gate all genuinely run.
The bug in our sample repo is a real one and the tests genuinely fail. We ship a
local `tickets.json` queue purely as an offline fallback in case OAuth breaks on
venue wifi; it is not used when Linear is connected.

**Built with:** TrueForge, Linear MCP, OpenAI.
