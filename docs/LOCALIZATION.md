# Localization path

MyCard Benefits ships English-only today. This documents what is already
locale-ready, what is intentionally not float-localized, and the concrete
path to add a second language without touching the money-exactness contract
in `docs/PURCHASE-OPTIMIZER.md`.

## Already locale-ready

- **Dates.** Every rendered date goes through `fmtDate()` in
  `static/app.js`, which calls `Intl.DateTimeFormat(undefined, { dateStyle:
  "medium" })`. Passing `undefined` as the locale means the browser's own
  locale is used automatically; no code change is needed to render a date in
  a different locale's convention.

## Intentionally not float-localized: money

Every monetary value shown in the dashboard (optimizer totals, component
values, caps, allowances) is rendered as `${currency} ${value}`, where
`value` is the exact decimal string the API returned — never a JavaScript
number. This is deliberate, not an oversight: the optimizer's contract
(`docs/PURCHASE-OPTIMIZER.md` "Loopback API") requires money to survive the
browser round trip as an exact decimal string precisely so a locale-aware
*formatter* (which operates on floating-point `Number`s) cannot introduce
rounding drift into a guaranteed/conditional/estimated total.

A future locale-aware money layer must preserve exactness — for example, by
formatting only the currency symbol/grouping around the untouched decimal
string, never by parsing the string into a `Number`. That work is a separate,
explicitly reviewed gate; it is not attempted here to avoid touching a
reviewed, heavily tested core contract as a side effect of a general
localization pass.

## Extracting user-facing strings

`templates/index.html` and `static/app.js` currently hold inline English
string literals rather than message keys. The documented path to a second
language is additive and incremental, not a single rewrite:

1. Add a `static/strings.<locale>.json` message catalog (starting with
   `strings.en.json` capturing today's literals verbatim, so the first
   change is a no-op refactor with no copy change).
2. Add a small `t(key)` lookup helper to `static/app.js` that falls back to
   the English string if a key is missing in the active locale, so a partial
   translation never renders blank text.
3. Migrate one view at a time, highest-traffic first (Overview, Benefits,
   Planner), replacing inline literals with `t("view.benefits.title")`-style
   keys as each view is otherwise touched — not as one large mechanical
   sweep, so each migration stays reviewable and testable.
4. Add a deterministic test per migrated view asserting every key referenced
   by that view exists in `strings.en.json`, mirroring the contract-test
   style already used in `tests/test_ui.py`.

This batch does not perform step 3 for any view: a full-codebase string
extraction touches nearly every rendering function and was judged too broad
a change to make safely alongside 29 other bounded tasks in one sitting. What
is delivered here is the plan itself, plus the two already-safe pieces above
(locale-aware dates, and the documented reason money stays a raw decimal
string).
