# Integration status

Status: CONCURRENT_BATCH_ACTIVE

The manager integration branch is the canonical trace. Worker worktrees remain
isolated while a task is in progress; before every subsequent task handoff, the
manager merges the completed dependency, gives the worker the resulting commit,
and requires a rebase plus a full gate rerun before review. No push or
publication is authorized.

## Integrated and validated

- MC-001: readable My Cards list — `efebf51de139c94704555d8929578e13bc73c937`
- MC-003: production catalog cleanup — `1c65944e5fa50230c17db4214e3b5b278e6a4d68`
- MC-002: card record detail view — `59bbebb`, integrated at `d337811`
- MC-005: neutral MyCard wording — `f7bb1bd`, integrated at `532318f`
- MC-006: unmatched variant state — `a0236b0`, integrated at `4eeb303`
- MC-008 and MC-009: demo boundary and vault diagnostics — `d5405ff`
  and `8fc9e2c`, integrated through `7344b29` with manager correction
  `ad141cd`
- MC-021, MC-070, and MC-093: reviewed relationship graph, temporal benefit
  versions, and provenance assertions — worker sequence ending at `61e68d7`,
  integrated and manager-validated at `7a939a2`

## Awaiting integration

- Claude Sonnet: MC-024 and MC-177 on `agent/mc024-177-claude`.
- OpenCode DeepSeek V4 Flash Free: MC-098 on `agent/mc098-opencode`.
- Antigravity Gemini 3.6 Flash High: MC-085 on `agent/mc085-antigravity`.
- Manager: MC-206 encrypted local source consolidation and safe last-four
  projection. Private source data is not delegated.

This file is manager-owned. Workers must use their explicitly assigned task
record and may not edit another worktree or private data directory.
