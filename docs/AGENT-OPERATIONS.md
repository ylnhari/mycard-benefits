# Agent Operations

What any background agent or delegated LLM runner — source agent, catalog
assistant, or coding assistant — may and may not do in this repository. Read
`AGENTS.md` first; this document elaborates it for day-to-day agent work and
does not relax anything in it.

## Hard boundaries (from `AGENTS.md`, restated for agents specifically)

- Never handle, store, log, or place in a prompt any real PAN, CVV, PIN,
  owner identity, boarding pass, credential, or private card record. Use
  conspicuously fake, non-personal data in every test and demo.
- Never receive or output decrypted vault values. An agent may request that
  the human-facing UI perform a protected action after reauthentication; the
  agent itself never sees or handles the plaintext.
- Never bypass authentication, CAPTCHA, robots restrictions, access
  controls, rate limits, or a source's terms — for any reason, including
  "just to check" or "just this once." Block and report instead. See
  `SOURCE-POLICY.md` for the full detail of this line as it applies to
  source work.
- Never purchase, apply for a card, book, redeem, upload, make a paid model
  call, touch a public remote, push, or publish without that action's
  explicit gate having already been granted by a human for that specific
  action.
- Source and catalog agents create candidates only (see
  `CATALOG-GOVERNANCE.md`). Publishing requires approval by a human reviewer;
  an agent may assist but may not hold a reviewer or second-reviewer role.
  No assertion reaches `active` without human-approved evidence.

## Unattended work: what is fine vs. what is not

This project deliberately allows unattended/scheduled source work. That
permission has a hard edge, and agents must not treat proximity to the edge
as license to lean on it:

**Fine to run unattended:**
- Fetching and parsing publicly reachable pages within an admitted source's
  scope and cadence (`SOURCE-POLICY.md`, `SOURCE-ADAPTER-RUNBOOK.md`).
- Generating candidate catalog assertions and evidence records for review.
- Running deterministic catalog evaluation, tests, and lint.
- Appending honest state to `coordination/jobs.jsonl` and
  `coordination/events.jsonl`.

**Never fine, unattended or not:**
- Anything on the hard-boundaries list above.
- Treating a CAPTCHA, login wall, blocked request, or rate-limit response as
  an obstacle to engineer around rather than a stop condition.
- Widening the application's network bind, or routing around the
  authenticated remote-access gateway, to make an agent's job easier.

## Delegated runners

Claude and other delegated runners operate on public code and public catalog
data only — never on private vault data, runtime databases, or evidence
capture contents. If a delegated runner hits a quota or capability limit
mid-task, it records `deferred_quota` in the task's on-disk state and stops;
the next runner resumes from that on-disk task file, not from chat memory or
an assumption about what was already done.

## Coordination substrate

Before starting assigned work, an agent reads, in order: `AGENTS.md`,
`PROJECT_STATUS.md`, `DECISIONS.md`, and its assigned file under
`coordination/tasks/`. While working, it:

- Works only in the files and scope its task assigns. Touching anything
  outside that scope is a separate, explicitly authorized task.
- Stops and reports after 2–3 repeated failures on the same problem rather
  than escalating tactics.
- Appends honest job/event state to the coordination logs rather than
  leaving resumable context only in a chat transcript.
- Hands off with tests/evidence for whatever it changed — a handoff without
  evidence is not a complete handoff.

## Related documents

- `SOURCE-POLICY.md` — the source-side detail of the bypass boundary.
- `SOURCE-ADAPTER-RUNBOOK.md` — how an adapter enforces these boundaries in
  code.
- `CATALOG-GOVERNANCE.md` — the review workflow an agent's candidates enter.
- `../CONTRIBUTING.md` — the same boundaries as they apply to human
  contributors.
