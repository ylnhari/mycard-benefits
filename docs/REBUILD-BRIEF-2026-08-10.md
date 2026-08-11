# Rebuild brief — MyCard Benefits

Author: Claude (independent product review + owner interview)
Date: 2026-08-10
Owner decision: **keep the data, delete the machinery, rewrite the app.**

Related review document: `docs/CLAUDE-FINAL-PRODUCT-REVIEW-2026-08-10.md` — read its
Section 0 (ADDENDUM) for the owner's decisions and its P0/P1 list for verified
defects with exact `file:line` citations. This brief supersedes it wherever they
differ, because this brief assumes a rewrite rather than a repair.

---

## Why we are doing this

The app is not badly built. It is **mis-scoped**. Measured:

| Area | Lines | Fate |
| --- | --- | --- |
| UI — `static/app.js`, `app.css`, `templates/index.html` | 3,709 | **Rewrite** |
| `research`, `candidates`, `agents`, `sources`, `qa`, `optimizer`, `lifecycle` | 14,377 | **Delete** |
| `vault` | 6,797 | **Keep**, simplify auth |
| top-level (`app.py`, `config.py`, `portlib.py`, …) | 8,416 | Keep the thin parts, drop the rest |
| `tests/` | 21,455 | Delete what tests deleted code |

Roughly 14,000 lines of public-catalog governance — review gates, candidate
stores, source-admission tiers, research schedulers, agent runtimes — were built
around what is, for now, one person's personal card wallet. Every UI change had to
satisfy an approval apparatus the owner does not need. That is why two days of
work produced no visible progress.

The research, by contrast, is genuinely valuable and slow to recreate:
**72 curated card offerings** and **61 source references represented by 60
deduplicated benefit records drawn from 30 distinct official source URLs** (HDFC
×25, Visa ×11, DBS ×9, BookMyShow ×9, plus RuPay, Tata Neu, Swiggy) with 32
recorded content hashes.

So: keep the data, delete the apparatus, rewrite the app.

---

## Branch

Work on a clean branch off the current tip:

```
git switch -c rebuild/consumer-app agent/luna-final-integration
```

**Assumption stated for the owner to override:** staying in this repository rather
than creating a new one, because `catalog/offerings/*.json` is already here and
re-homing it into a fresh repo is pure risk for no gain. Say so if you want a new
repository instead.

Do not create worktrees. Local commits only — **no push, no publication**.

---

## STAGE 1 — Rescue the research. Nothing is deleted until this passes.

**This is the highest-risk step in the whole plan.** The 61 researched source
references do not live in `catalog/`. They live as Python seed data inside the package being
deleted:

```
src/mycard_benefits/candidates/consumer_benefit_candidates.py   561
src/mycard_benefits/candidates/regalia_gold_research.py         380
src/mycard_benefits/candidates/visa_infinite_proposals.py       313
src/mycard_benefits/candidates/tata_neu_infinity_2026.py        251
src/mycard_benefits/candidates/pilot_proposals.py               212
```

Delete `candidates/` before extracting and the research is gone.

**Do this:** with the current app still running, export every benefit to plain
JSON files under `catalog/benefits/`, one per deduplicated benefit record. Preserve, per benefit:

`id`, `offering_id`, `title`, `benefit_type` / `category`, `allowance` (full
object), `eligibility`, `conditions`, `exclusions`, `redemption_steps`,
`provider`, `effective_from`, `effective_to`, `end_date_known`, `source_url`,
`source_policy_class`, `content_sha256`, and — critically — **`not_claimed`**,
which records what a source explicitly does *not* promise. That field is the
reason this catalog is trustworthy; do not drop it.

Add one new field, `state`, with exactly three values after deduplicating the
conflicting RuPay record: `verified` (1 item), `check_before_use` (53),
`sources_differ` (6).

**Acceptance — all four must pass before Stage 2 begins:**
- `ls catalog/benefits/*.json | wc -l` → **60**
- Distinct `source_url` values across those files → **30**
- Distinct `content_sha256` values across those files → **32**
- The Tata lounge benefit retains its `not_claimed` array
- A checked-in script re-reads all 60 deduplicated files and validates them against a schema; all 61 source references remain represented by provenance

### Stage 1 correction notes — 2026-08-10

The rescue retains six `sources_differ` records. Five cannot be structurally
reconciled from the retained evidence and remain an explicit owner decision
before any state is published:

- `indusind-legend-visa-bookmyshow-bogo.json` — one provenance URL, with no alternative claim value preserved.
- `indusind-legend-visa-signature-bookmyshow-bogo.json` — one provenance URL, with no alternative claim value preserved.
- `rbl-play-monthly-bookmyshow-movie-and-food-offer.json` — one provenance URL, with no alternative claim value preserved.
- `regalia-gold-accelerated-reward-points-at-designated-merchants.json` — two provenance URLs, with no alternative claim value preserved.
- `regalia-gold-reward-point-travel-and-cashback-redemption-limits.json` — two provenance URLs, with no alternative claim value preserved.

No state was relabelled. The owner must decide whether each record is a real
source conflict, a mislabel, or a lost divergence before any state is
published. The checked-in validator keeps this dated exception set explicit
and fails closed if the failing set changes.

The rescue also exposes the old pre-Stage-2 loader shape. The exact known red
suite is five failures in `tests/test_ui.py` (Stage 2 owner: the catalog loader
and kept UI transition), one failure in `tests/test_user_onboarding.py`
(Stage 2 owner: the catalog loader and kept onboarding transition), and nine
errors in `tests/test_candidate_router.py` (Stage 2 owner: delete this
candidate package and its tests). These are not fixed in Stage 1. The two
repository-wide Ruff findings — `I001` in
`tests/test_conditional_benefit_ux.py` and `F841` in `tests/test_ui.py` — are
pre-existing and out of scope.

### Candidate review-metadata handoff — 2026-08-10

Before any Stage 2 deletion, `catalog/benefit-review-metadata.json` preserves
the candidate review metadata in a reader-findable public archive. It has
61 entries keyed by the original proposal benefit ID and tied to 60 rescued
records through `rescued_benefit_id`; the merged RuPay proposal
`b1000001-0000-4000-8000-000000000004` maps to rescued record
`b3000001-0000-4000-8000-000000000007`. Each entry retains its title,
offering, `review_tier`, `review_note`, `official_reference`, and per-source
`confidence` values.

The archive contains all 61 review tiers, 54 non-empty review notes, 12
official references, and 71 confidence observations (35 high, 36 low).
Confidence was already preserved in normalized provenance for all 60 rescued
records, so that portion is an explicit archive projection rather than a
genuine catalog loss. The review tiers, notes, and official references had no
general home in `catalog/benefits` and are now reversible rather than lost.

The archive intentionally omits the redundant candidate envelope fields
`record_kind`, `target_record_id`, and `base_record`, the empty
`conflicts_with` payload field, and the uniform `status: needs_review` value;
the rescued `state` is the catalog's canonical state. No state was relabelled,
and no Stage 2 deletion has occurred.

Commit this on its own. It is the safety net for everything after.

### Catalog loader transition — 2026-08-10

The kept catalog loader now accepts the source-native rescued benefit shape in
`catalog/benefits` without reading candidate metadata or rewriting the public
records. It preserves the exact rescued `state` internally, keeps
`check_before_use` and `sources_differ` non-publishable, and retains the one
legacy-shaped `verified` record behind the existing human-evidence gate.
Missing rescue review metadata is not invented, and the structured RuPay
`source_divergence` claims remain validated and attached to the loaded rule. A
separate `consumer_visible_benefits` accessor now lets the kept catalog display
routes show all three rescued states without changing the active-only
governance, eligibility, ranking, QA, or purchase paths. The benefit list,
offering detail, and discovery responses expose only the safe `state`, dates,
provenance pointers, `not_claimed`, and divergence fields; internal status and
review vocabulary are not serialized. The optimizer component boundary also
rejects any explicit non-`verified` benefit state before route ranking.

Validation evidence: `load_catalog(catalog)` loads 72 offerings and 60
benefits with states `verified: 1`, `check_before_use: 53`, and
`sources_differ: 6`; `tests/test_ui.py` and `tests/test_user_onboarding.py`
pass; the consumer visibility and state-only response regressions cover all 60
API records; the active-only optimizer boundary regression passes; changed
catalog/optimizer modules pass Ruff; and
`scripts/validate_rescued_benefits.py` passes its 60/30/32 and five-exception
gates. The legacy Draft 2020-12 schema test is scoped to release, offerings,
and committed legacy-shaped synthetic fixtures; rescued production files are
validated by their dedicated rescued-benefit schema. No candidate/vault
deletion was performed.

### Consumer contract migration — 2026-08-10

The benefit list, offering-detail benefit, and discovery consumer payloads now
use the safe state vocabulary `verified`, `check_before_use`, and
`sources_differ`. The migration removes internal `status`, `review_tier`,
evidence `review_state`, and discovery `evidence_status`; it also prevents the
scalar governance values `needs_review`, `superseded`, `historical`, `approved`,
and `stale` from crossing these consumer boundaries. The replacement fields are
the consumer `state`, evidence state, conflict state, `not_claimed`, and
`source_divergence`, with dates and provenance pointers retained. This keeps a
reader from learning a false governance judgment about their own card from
`needs_review` vocabulary.

The exact contract regression deliberately holds out pre-existing serialized
fields `category`, `owners`, `conditions`, `earn`, `conversion`, `valuations`,
`value_class`, and `inheritance`. They were already declared on
`BenefitSummary` and emitted by `_benefit_summary` before this migration, while
the earlier locked test omitted them. They are reported as pre-existing drift,
not silently blessed as part of this migration, and require separate approval
before entering the new locked set.

---

## STAGE 2 — Delete the machinery

Remove entirely:

- `src/mycard_benefits/research/`, `candidates/`, `agents/`, `sources/`, `qa/`,
  `optimizer/`, `lifecycle/`
- The routers they register in `app.py`, and their `tests/`
- Contributor mode: the nav block, `.contributor-only` regions, Updates, Sources,
  Research Queue, Local reminders, route diagnostics
- **The Today view**, entirely
- **All private card data.** Wipe the vault to a clean first-run state — all 80
  encrypted records, **no backup**. The owner confirmed this after being told it
  is irreversible. The public catalog is **not** wiped.

Leave no dead imports, dead routes, or stale documentation. `AGENTS.md`,
`PROJECT_STATUS.md`, `TASKS.md`, `DECISIONS.md` and `CONTINUE-HERE.md` all
describe the deleted apparatus and must be rewritten to describe the app that
now exists.

---

## STAGE 3 — Keep and simplify: vault + auth

Keep the cryptography (`Argon2id`, AES-GCM envelopes, CSRF, `no-store`, loopback
bind, rate limiting). Replace the access model:

- **No credential on first run.** A fresh clone opens straight into the app.
  Cards are **not locked by default**. Browsing, sorting, filtering and search all
  work with no credential at all.
- A credential gates **exactly one thing**: revealing full card details — PAN,
  CVV, PIN, exact expiry. Nothing else.
- The **first time** the user reveals full details, prompt them to set a
  credential then and there. **No default credential ships in the repository.**
  The owner initially proposed a hardcoded `123456`; that was rejected because an
  open-source clone would carry a publicly-known secret and a vault key derived
  from it makes encryption-at-rest worthless. Do not reintroduce a default.
- The user chooses **PIN or passphrase**. PIN minimum 6 digits. Argon2id at high
  cost, escalating delay and lockout on repeated failure.
- Changing the credential requires entering the current one.
- Reveal supports **copy to clipboard** with an auto-clear timer and a visible
  countdown.

Today `POST /cards/{card_id}/reveal-authorize` returns HTTP 410 "plaintext reveal
is disabled" (`vault/router.py:1474-1486`). Reveal now genuinely exists — this is
the one change that materially alters the security posture. **Write a short
design note covering the reauth model, clipboard auto-clear duration, and what is
and is not audited, before implementing it.** Plaintext must never reach a log, a
tracked file, an agent prompt, or a screenshot.

---

## STAGE 4 — The app, rewritten

The owner's words, verbatim:

> *"first have my cards properly stored, displayed, and I can sort, filter, look
> for cards by different aspects; and all the benefits of my cards are collected,
> sorted clearly, saved — not only my card, every credit card available, based on
> categories; and then I can search for any benefit, or any benefit on my card,
> look out for feature details."*

**Four screens. No more.**

**1 · My Cards**
Cards stored and displayed *recognisably*: card-shaped object, issuer colourway,
network mark, lifecycle pip, last-4 when present — and looking correct when
absent, because a fresh vault has none. Sort and filter by issuer, network, card
type (credit / debit / prepaid / membership), lifecycle, whether a given benefit
category is present, fee, and free text. Add a card by choosing its exact variant;
every sensitive field optional.

**2 · Benefits**
Grouped **by category** — lounge, movie, dining, rewards, cashback, fuel, forex,
insurance, meet-and-greet. Benefits on the owner's cards surface first, clearly
separated from the rest of the catalog. Never one flat alphabetical list; the
current build renders all 72 tiles flat and that is precisely what the owner is
rejecting.

**3 · Search**
One search spanning both axes, scopeable to "only my cards". Filter by category,
merchant, value or cap, condition, and claim route. Every result carries feature
detail: what it is, the condition, the cap, how to claim, the official link, and
its state chip.

**4 · Settings**
Credential management, theme, and nothing else.

**Every benefit, everywhere, shows one of three state chips** and an as-of date:

| Chip | Meaning | Count today |
| --- | --- | --- |
| **Verified** | Reviewed against the official source | 1 |
| **Check before use** | Source is linked; current terms unconfirmed | 55 |
| **Sources differ** | Recorded sources disagree | 5 |

All three are **live and usable** — the owner's explicit decision: *"I want them
to be live right away; if I see a mistake I will tell the agent to fix it."* Never
badge anything "Activated"; that reads as "switched on".

---

## Rules that carry over from the review

These are verified defects in the old UI. Do not reproduce them in the new one.

- **Never render a value the source explicitly does not claim.** The old build
  showed a bare "8 vouchers per year" while that rule's own `not_claimed` rejected
  "unconditional 8 visits per year".
- **Never mangle numbers.** The old `_consumer_label` did
  `value.replace(".", "_").split("_")`, so `"0.5"` rendered as `"0 5"` — readable
  as 5, a tenfold overstatement.
- **Never describe an archived card as active.** Ownership must carry lifecycle.
- **Never show machine field paths or operators.** No
  `calendar_quarter.eligible_net_posted_spend_inr gte 50000`, no `Cap: 2`, no
  `gte` / `equals`. If a field has no consumer label, it does not render.
- **Never pick a headline value alphabetically.** The old
  `_primary_allowance` returned `sorted(allowance)[0]`.
- **Never ship a control that cannot succeed.** The old purchase form always
  answered "not available yet"; seven "Common questions" buttons all returned "no
  match".
- **Never claim a remaining count** the app cannot prove. Show the allowance, the
  qualifying condition, and the official source.

## Quality bars that must not regress

The old build was genuinely strong here. Match it.

- **Accessibility:** zero WCAG AA contrast failures in light theme (the old build
  achieved this across 977 elements); focus moves to the view heading on
  navigation with a live announcement; no focusable elements inside hidden views;
  skip link, `:focus-visible`, `prefers-reduced-motion`.
- **Mobile:** no horizontal overflow at 320 / 375 / 414px. The old build was 406px
  wide in a 375px viewport. Minimum 44px touch targets — especially official-source
  links, which were 21–32px and are the app's primary trust action.
- **Privacy:** loopback bind only; no decrypted value in logs, tracked files,
  prompts or screenshots; synthetic fixtures stay `SYNTHETIC-ONLY-` and non-Luhn.
- **Gates:** `uv run ruff check .`, `uv run pytest`, `uv run mypy src`.

---

## Content reality — do not mistake this for a bug

72 offerings, but only **18** have any benefit reference at all; 54 have none.
Of the owner's 68 distinct card products, only **13** have any benefit data.
"Zero benefits on this card" is a **content-coverage gap**, not a rendering
failure. Report content gaps and code defects separately, always.

Three things the owner asked for have **no data model at all** and are content or
schema work, not UI work:

- **meet-and-greet** — exists only as a schema enum; zero seeded benefits.
- **guest / companion lounge coverage** — no such dimension exists anywhere. The
  allowance model has `unit` / `count` / `period` only. Schema change required.
- **"the maximum I will get"** — `valuations` is never populated in any seed. Caps
  exist (`cap_inr` ×12, `ticket_cap_inr` ×6) but are never surfaced comparably.

---

## Execution order and reporting

1. **Rescue the research** — reconcile 60 deduplicated benefit records from 61
   source references, verify the four
   acceptance checks, commit alone.
2. **Delete the machinery** — packages, contributor mode, Today view, and vault
   wipe.
3. **Vault and auth** — design note first, then implement.
4. **The four screens** — My Cards, Benefits by category, Search, Settings.
5. **Polish** — mobile, accessibility, empty and error states, docs rewrite.

**Stop and report after each stage.** Each report: what changed, diff summary, and
acceptance results measured against the served app at `127.0.0.1:8777`. Do not run
all five silently. Do not report anything complete because tests pass — exercise it
rendered, desktop and mobile, both themes, with the keyboard.

### Current staged implementation notes — 2026-08-10

- The consumer contract correction explicitly approves the six pre-existing
  consumer fields `category`, `conditions`, `value_class`, `earn`, `conversion`,
  and `valuations`; `owners` and `inheritance` are internal metadata and are
  removed. The remaining raw JSON/snake_case rendering of `earn`, `conversion`,
  and `value_class` is tracked as Stage 4 work.
- The approved design source is now clone-self-contained at
  `docs/design/mycard-design.html`, copied byte-for-byte from the reviewed local
  artifact and verified by SHA-256 before integration.
- Stage 2a remains separate from the owner-authorized Stage 2b wipe. The wipe
  has not been executed; private card records remain present until the deletion
  is reviewed and approved.
