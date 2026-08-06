# Public Q&A review evidence

Review date: 2026-08-07

Scope: deterministic, ephemeral questions over the approved synthetic public
catalog plus the human-facing Ask panel. No LLM, private card value, persistence,
network source retrieval, or real claim was used.

The engine supports offering benefits, offerings by benefit type, one benefit
type for an offering, and two-offering comparison. It uses exact normalized
tokens and aliases, returns ambiguity/unknown guidance rather than guessing,
and emits only active in-date high/medium-evidence rules with exact citations.

The final DeepSeek V4 Flash read-only audit reported no High or Medium findings.
Twenty-four focused UI, Q&A, and application tests passed after the keyboard
fix. Rendered checks covered Enter submit, Escape clear, loading/focus behavior,
safe citation links, unsupported questions, disabled private controls,
desktop/mobile layouts, both themes, and an empty browser error console.
