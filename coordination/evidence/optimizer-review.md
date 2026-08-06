# Optimizer review evidence

Review date: 2026-08-06 to 2026-08-07

Scope: the pure, synthetic-only purchase-route optimizer. No network request,
private card value, or real offer was used.

## Claude review

Claude Code reviewed the first implementation read-only and identified missing
aggregate value budgets, stricter freshness for time-limited offers,
affiliate-neutral tie handling, official-only filtering, anonymous HTTPS URL
validation, named estimated-value assumptions, and explicit evidence tiers.
Those findings were implemented and covered by focused tests.

## Independent worker review

A different worker then found four remaining issues:

- the same public benefit could be double counted under different component IDs;
- an `official` caller label was not bound to an approved host;
- non-finite or unbounded Decimal values had no calculation boundary; and
- malformed HTTPS ports were not rejected.

The implementation worker added canonical benefit-rule IDs, an explicit
official-host allow-list, finite magnitude/scale validation with deterministic
currency quantization, and strict port parsing. It also separates budgets by
value class, rejects unsupported currencies and duplicate fee labels, and does
not rank conditional or estimated value as guaranteed value.

The final DeepSeek V4 Flash read-only audit reported no High or Medium findings;
24 focused optimizer tests passed. Accepted low risks are that shared caps rely
on correct catalog `cap_group` identity and an empty official-origin allow-list
intentionally yields no verified route. The engine remains unexposed until a
separate UI/API contract is reviewed.
