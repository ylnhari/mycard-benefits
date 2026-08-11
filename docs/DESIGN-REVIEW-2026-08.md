# Design & product review — MyCard Benefits

Reviewed: full repo. `PRODUCT_REQUIREMENTS.md`, `docs/QUESTIONNAIRE-DECISIONS.md`
(all 120 accepted decisions), `PROJECT_STATUS.md`, `src/mycard_benefits/templates/index.html`,
`src/mycard_benefits/static/app.css`, all 11 dashboard views.
Date: 2026-08-10.

> Historical snapshot: this dated review records the reviewed repository and
> decisions as of 2026-08-10. References below to Family Finance or integration
> are review-era findings, not current product capabilities or roadmap items.

---

## Part 0 — The two findings that matter most

Everything else in this document is secondary to these.

### 0.1 The product loop has never run once, end to end

From `PROJECT_STATUS.md`:

- 68 real public card-variant identities in the catalog.
- **Zero verified benefit claims.** The four Tata Neu / Regalia Gold pilot proposals are
  `needs_review`. Official source admissions remain `candidate`, so "no real source
  transport is authorized". The Planner's own UI copy admits "the reviewed catalog has no
  verified benefits for these cards yet".

So the app can currently answer *"does this card product exist?"* and cannot answer
*"what does my card do for me?"* — which is the entire product outcome in
`PRODUCT_REQUIREMENTS.md`.

Meanwhile the repo contains: Argon2id key wrapping, AES-GCM envelope authentication,
one-use reveal authorization, TOCTOU corrections, raw-ASGI header duplicate/case-variant
CSRF rejection, cross-process claim locks, Windows reparse-point handle guards,
DAG-enforced relationship graphs, source-tier derivation with tier-6 prohibition,
per-admission 24-hour transport floors surviving process restart, and a candidate-store
schema migration boundary.

That is genuinely impressive engineering. It is also **infrastructure for a product that
has not yet demonstrated it works**. The risk is not that the security is wrong — it's
that you can harden a pipeline indefinitely without ever finding out whether the benefit
data model survives contact with one real card's real terms.

**Recommendation — do this before anything else in this document.** Take one card, Tata
Neu HDFC Infinity, and one benefit, the lounge allowance. Drive it all the way through:
admitted source → evidence → candidate → human approval → active rule → visible on
Today with a provenance chip → counted in "2 lounge visits left" → surfaced by "which
card for this ₹8,000 purchase". One card, one benefit, no exceptions, all the way to
pixels.

You will learn more from that single thread than from the next twenty governance
corrections. It will also tell you whether the allowance/counter model, the valuation
range model, and the condition-predicate model are right — while changing them is still
cheap.

### 0.2 Accepting all 120 recommended defaults produced a scope with no shape

`QUESTIONNAIRE-DECISIONS.md` opens: *"The owner accepted every recommended default in
the initial 120-item product questionnaire."*

Each decision is individually sensible. Collectively they are not a product — they're a
category survey. Consider what item 39 alone commits you to:

> rewards, conversions, movies, hotels, dining, cashback, vouchers, meet-and-greet,
> lounges, Priority Pass, fee waivers, milestones, forex, fuel, insurance, golf,
> concierge, subscriptions, transfers, and railway lounges

Twenty benefit families. Plus 13 lifecycle states (item 18), 5 rule owners (49), 12
condition dimensions (50), 8 review states (52), 6 reminder types (56), 4 export formats
(100), 6 source tiers (59).

A questionnaire where every answer is "yes, the recommended default" is a questionnaire
that never forced a *choice*. The consequence is visible in the UI: 11 nav items, six
stacked sections on the home screen, a 5-column planner form. **The interface is
sprawling because the scope is.** No amount of visual design fixes that.

**Recommendation.** Re-read the 120 with one question per item: *does a user notice
this in the first week?* My cut, applied below in Part 3: roughly 30 items are the
product; roughly 50 are correct-but-later; roughly 40 are governance that should be
invisible. Nothing needs deleting from the docs — but the build order should stop
treating them as peers.

---

## Part 1 — What the decisions promise vs what the UI delivers

The decision matrix is emphatic about user-facing priority. Item 89:

> Prioritize urgent expiries/actions, available benefits, resets, uncertain card
> matches, and recent verified changes.

That is an excellent home screen spec. **You wrote it and then didn't build it.** The
Overview instead shows catalog inventory counts and three paragraphs of verification
philosophy. Item 89 alone, implemented literally, would fix most of Part 2.

Other decisions the UI contradicts or hasn't reached:

| # | Decision | UI reality |
| --- | --- | --- |
| 89 | Prioritize expiries, actions, resets, uncertain matches, recent changes | Overview shows catalog counts + disclaimers |
| 92 | Benefit-first browsing shows **eligible owned cards first**, alternatives separately | Benefits view is catalog-first; owned cards are a filter |
| 93 | Every benefit provides How to use / Where to use / What to verify / official links | Not present as a consistent four-part structure |
| 82 | First-class questions: usable now, which card, how to claim, what expires, uses remaining, what changed, why eligibility fails | Ask is a free-text box; none of the seven are offered as affordances |
| 90 | Add a card: select offering → confirm variant → create instance → optional encrypted fields | "Add or edit — next protected milestone" (permanently disabled) |
| 25 | 10-minute idle lock, immediate lock on browser close | No visible lock state or countdown in the UI |
| 26 | Fresh one-use confirmation for every PAN/CVV/PIN reveal | No reveal flow in the dashboard at all |
| 15 | `unverified_match` shows candidate variants, withholds entitlements | Present in data model; surfaced only as `.unmatched-note` red text |
| 54 | Rank cards only with assumptions, uncertainty, caps, exclusions visible | Planner does this well — best-implemented decision in the app |
| 3 | Responsive desktop **and mobile** browser UI | Mobile is column-collapse; nav becomes an 11-item scroll strip |

Item 82 deserves emphasis. You identified the seven questions your users actually ask.
Those seven questions are your information architecture — literally. Each should be a
tappable affordance on Today, not something a user must phrase correctly into a search
box. "Which card works?" "What expires?" "Uses remaining?" "What changed?" — those are
buttons.

---

## Part 2 — UI findings

### Scorecard

| Area | Verdict |
| --- | --- |
| Information architecture | Needs work |
| Copy & tone | Needs work |
| Visual hierarchy | Mixed |
| Data display | Mixed |
| Mobile | Needs work |
| Accessibility basics | Strong |
| Trust & provenance *model* | Strong |
| Trust *expression* | Needs work |
| Security engineering | Strong (and ahead of need) |

### 01 — CRITICAL · The app apologises for itself, over and over

On the Overview alone: "it is not proof that a benefit applies", "read its conditions and
current official terms before relying on it", "candidate proposals remain unverified",
"general education, not advice", "This is general education, not a recommendation".
Planner adds five more. Settings repeats them in a `<details>`. "Verified" or
"unverified" appears in nearly every heading.

**Fix.** Move rigor from prose to primitives. Build one provenance chip — status dot,
as-of date, source link — and attach it to every claim. Then delete the paragraphs. A
user who sees `● Verified · 12 Jul · HDFC` on every row learns your epistemology in
three seconds and never needs the essay. Keep exactly one standing disclaimer, in the
footer. Ship the EMI/utilization education as a contextual note on a Planner result that
actually involves EMI.

Note this is *not* a request to weaken item 52 (eight review states) or item 68
(preserve conflicts, reduce confidence). Those stay. It's a request to express them as
data, not as warnings.

### 02 — CRITICAL · Operator tooling sits at the same level as user tasks

Eleven flat nav items; four are pipeline internals. "Candidate Review & Research Queue"
exposes `needs_review` states, field-level diffs, evidence hashes, and an "MC-214 refresh
ledger" to a consumer.

Item 88 listed those views — but listing them isn't the same as making them peers of
"My Cards".

**Fix.** Two audiences, two surfaces. Five-item consumer nav. Everything pipeline-shaped
moves behind a **Contributor mode** toggle in Settings, off by default — and genuinely
valuable to the open-source contributors item 70 invites. Internal IDs like "MC-214"
must never appear in user copy.

### 03 — CRITICAL · The metrics measure your database, not the user's life

Card variants · Active benefits · My cards. Two are catalog inventory; the third the user
already knows. All three render as `—` at 2rem until an API resolves, so the app's first
impression is three large em-dashes.

**Fix.** Item 89's list, as three numbers: **expiring in 30 days**, **unused
allowances**, **changed since you last looked**. Each links to a filtered list. Your
allowance/reset model (items 46, 41) already supports the middle one — and *no competitor
has it*. It is the most valuable number in this product.

### 04 — HIGH · Two titles fight on every screen

The persistent `.topline` carries an eyebrow, an H1 up to `4.5rem`, and a lede — a
marketing headline that never changes as you navigate. Overview's hero then adds a second
eyebrow, H2, and paragraph. On My Cards the largest text on screen is "Know what a card
offers—before you rely on it".

**Fix.** Delete the persistent topline; it belongs on a first-run screen. One H1 per
view at ~28–32px. Retire the eyebrow pattern (20+ instances, always accent green).

### 05 — CRITICAL · The vault reads as a status message, and the docs contradict the UI

"Checking private card access…" in a dashed box with a `⌾` at 3rem. Locked vs unlocked —
the most consequential state in the app — is a sentence.

**Settings says** *"There is no browser unlock or lock button"*. **My Cards renders**
`#vaultUnlockForm` with a passphrase field and an "Unlock My Cards" button. One of these
is wrong and a user will find it.

Items 25–28 specify idle lock, one-use reveal confirmation, 30-second clipboard clearing,
last-4 masking. **None of it is visible in the UI.** The most sophisticated part of your
codebase is invisible to the person it protects.

**Fix.** Resolve the contradiction. Promote lock state to a persistent sidebar control:
lock icon, state as a word, click target, idle countdown. Then *show* items 26–28 when
they fire — the one-use reveal confirmation and the clipboard-clear timer are trust-building
moments, not chores. "Your card numbers never leave this computer" is your positioning
against every app-store competitor; it is currently a caveat in a `<details>`.

### 06 — HIGH · Cards are rendered as text blocks, not as cards

Every entity — private card, benefit, source, candidate, research job — uses the same
`.panel` / `.card-grid` treatment. Nothing looks like a payment card.

This matters more here than in most apps because of items 16, 17 and 22: one user can
hold multiple instances of the same offering, plus add-on/supplementary/virtual/tokenized
siblings, plus Priority Pass and voucher child records. That is a genuinely hard
recognition problem and identical text panels make it unsolvable by eye.

**Fix.** A real card object: 1.586 aspect ratio, issuer wordmark, network mark, last-4
when the vault is open, lifecycle pip, neutral generated colourway per issuer. Costs
nothing in privacy. Show child records (item 22) as physically attached to their parent —
nested, indented, or clipped to the card — not as sibling panels. Show lineage (item 19)
as a visible chain: *"replaces the card ending 4412, closed Mar 2025"*.

### 07 — HIGH · The Planner asks for a form before it earns the right to

A 5-column grid (merchant, category, amount, date, currency) — five stacked full-width
fields on mobile — plus a channels fieldset, plus a per-card routing fieldset the user
fills by hand, plus three explanatory paragraphs, before any result exists.

Asking the user to type routing assumptions is the deepest problem: the vault already
knows their cards. That's your data, not theirs.

**Fix.** One input: `₹8,000 at Amazon`, parsed. Rank immediately from the vault's cards.
Reveal category / date / currency / channel as refinements *after* a first result. Keep
item 54's visible assumptions and uncertainty — that part is the best-implemented
decision in the app, and the `.planner-badge-user` amber treatment for user-entered
assumptions is exactly right. Don't lose it in the simplification.

### 08 — HIGH · Everything is 1rem apart, so nothing groups

Nearly every gap in `app.css` is `1rem`: `.metrics`, `.card-grid`, `.stack`,
`.updates-grid`, `.overview-readiness`. Six unrelated Overview sections are the same
distance apart as two related items inside one of them.

**Fix.** Three steps, strictly: **8px** within a component, **16px** between siblings,
**48px** between sections. Proximity is free hierarchy and you aren't spending it.

### 09 — MEDIUM · Mobile is a desktop layout with the columns removed

At ≤850px the sidebar becomes a horizontally-scrolling strip of 11 links (items 7–11
invisible, no scroll affordance) and every grid becomes `1fr`. The H1 still renders at
`5vw` / `-.06em`.

A benefits app is used **at the payment counter**, phone in hand. That's the primary
context, not desktop. Item 3 chose responsive-browser-first and item 4 deferred PWA —
worth revisiting: loopback-only bind (item 106) makes the counter scenario awkward, and
item 3's "remote phone use goes through an authenticated gateway" is a lot of friction
for the app's most important moment. Decide this before investing further in desktop
layout.

### 10 — MEDIUM · Dead ends where momentum should be

A permanently `disabled` button labelled "Add or edit — next protected milestone". "No
local reminder signals are loaded yet." "Open this view to load local reminders."

Item 99 explicitly asks for *"useful empty/demo states"*. These aren't that. Never ship a
disabled control naming an internal milestone. Every empty state: what this will show,
why it's empty, one button. Load reminders on view entry.

### 11 — MEDIUM · One accent colour doing five jobs

Mint `#84e7b5` is primary button fill, every eyebrow, every link, the "verified" state,
disclosure triggers, the vault dashed border, the hero gradient, and `.planner-value`.

**Fix.** Assign mint one meaning: **verified & trustworthy**. Links become plain
underlined text; eyebrows go grey; the primary button takes a non-mint fill. You then
have a legible provenance scale for item 52's eight states: mint = verified active,
amber = needs review / upcoming / personalized / user assumption, red = withdrawn /
conflicting / expired, grey = unverified. Eight states will not survive as eight colours —
three plus a label is the readable ceiling.

The dark palette itself is good; `#0c1016` / `#151b24` is a well-judged cool near-black.
Keep it.

### 12 — KEEP · Credit where it's due

- **Accessibility is above average and matches item 6.** Skip link, `aria-live` on every
  async region, 44px targets throughout, 3px `:focus-visible`, `prefers-reduced-motion`,
  real `aria-labelledby`. Most teams ship none of it.
- **The light theme is properly re-derived,** not auto-inverted — `#176b4a` shows someone
  thought about contrast.
- **Temporal honesty** (item 53, and `end_date_known: False`) is the rigor that will make
  this trustworthy in a category full of stale scraped tables. Surface it; don't explain it.
- **Refusing a collapsed single value score** (items 42, 54) is right and rare. Make it a
  visible strength in Compare, not a missing feature.
- **The Planner's user-assumption badge** is the single best design decision in the app.
  Generalise that pattern — it *is* the provenance chip from finding 01.

---

## Part 3 — How to build this: what's product, what's later, what's plumbing

The 120 decisions, re-sorted by when a user notices them.

### Tier A — the product (build and surface these first, ~30 items)

Card identity & wallet: 11, 12, 13, 16, 17, 18 *(reduce to 5 visible states, see below)*,
19, 22, 90, 91.
Benefit intelligence: 39 *(narrow to 4 families, see below)*, 41, 42, 43, 46, 51, 52
*(3 visible tiers)*, 54, 92, 93.
Answers: 80, 82.
Vault, made visible: 25, 26, 28, 32.
Home screen: 89.
Reminders: 56, 57.

These are the app. If a user can't feel it in week one, it isn't Tier A.

**Two aggressive cuts inside Tier A:**

*Item 18's 13 lifecycle states.* Applied, pending, active, frozen, lost, stolen, expired,
renewed, replaced, upgraded, downgraded, closed, archived. Keep all 13 in the data model —
they're cheap and history matters (item 19). But show the user **five**: Active, Not
active, Replaced, Archived, and "Needs attention" (lost/stolen/frozen). Thirteen states
cannot be made legible as thirteen visual treatments, and the distinction between
"upgraded" and "replaced" is your model's concern, not the user's glanceable one.

*Item 39's 20 benefit families.* Pick **four** for v1 and go deep: **lounge access,
movie/BookMyShow, dining, and reward-points earn**. Reasons: they're the four an Indian
cardholder actually uses monthly; lounge and movie both have hard allowances and resets,
which exercises your counter model (item 46); reward earn exercises the valuation-range
model (item 42); and dining exercises MCC/merchant conditions (item 50). Four families
covering four different model shapes is a far better test of the architecture than twenty
shallow ones. The remaining sixteen stay documented, unbuilt.

### Tier B — correct, but later (~50 items)

Recovery and portability: 29, 30, 31, 100. Audit: 33, 34. Attachments: 35, 58. Multi-owner
households: 2. Localization: 5. PWA: 4. Compare depth. Manual counters: 44, 47, 55.
Personalized offers: 48. Historical as-of queries: 53. Optimizer route stacking: the full
7-layer model in `docs/PURCHASE-OPTIMIZER.md`. Family Finance import: 37, 38, 95–98.
Agents and LLM adapters: 74–79, 83–85. Contribution workflow: 70, 71.

None of these is wrong. All of them can wait until the Tier A loop demonstrably works.

Two specific warnings here. **Item 44's "one optional manually entered aggregate toward a
spend threshold"** looks small and is a UX trap: a number the user must maintain by hand,
that silently goes stale, that then drives a fee-waiver claim. Either design the staleness
handling properly (last updated, confidence decay, prompt to re-check) or don't ship the
number. **Item 55's realized-value totals**, disabled by default, are the thin end of
becoming the spending ledger the PRD explicitly refuses to be. Guard that boundary in
design reviews, not just in code.

### Tier C — plumbing that should be invisible (~40 items)

59–69, 72, 73, 86, 87, 101–116. Source tiers, cadence, admission, review gates, migration
boundaries, port registries, CI gating, catalog signing, release audit.

This work is excellent and most of it should never appear on a consumer screen. Its
*outputs* appear — as one chip per claim. The tier number, the content hash, the adapter
identity, the reservation ledger: Contributor mode only.

Item 87 ("route bounded public work to the lowest-cost capable worker") produced dozens of
temporary coordination reports. They were useful during integration but were later removed
from the working tree because Git history already preserves them. Keep future coordination
lighter than the user-visible product work it supports.

### The build order I'd actually follow

1. **The single thread** (Part 0.1). One card, one benefit, source to pixel. Nothing else
   until this works.
2. **Delete, don't add.** CSS + copy only, no API change: cut the persistent topline and
   second hero, remove the Overview education block, collapse the eyebrows, strip internal
   IDs, hide the disabled milestone button, adopt 8/16/48 spacing. A day or two; it changes
   the app's whole character.
3. **The provenance chip.** One component, three visual tiers, a label for precision, used
   everywhere a claim appears. This is the design system's keystone — it's how items 52,
   59, 66 and 68 become legible instead of verbose.
4. **Nav split.** Five consumer items; pipeline behind Contributor mode. Vault lock as a
   persistent sidebar control. Resolve the unlock contradiction.
5. **Today.** Item 89, literally. Needs endpoints for expiring / unused / changed — build
   *unused allowances* first; it's your differentiator.
6. **Add a card.** Item 90. Right now the wallet is read-only, which means the app cannot
   be adopted by anyone who hasn't run the one-time JSON import. This is the biggest
   functional gap after the empty catalog.
7. **Merge Ask + Planner + Compare into "Which card?"** One screen, one input, progressive
   refinement, Compare as a result mode. Item 82's seven questions become the affordances.
8. **Decide the real client** (finding 09) before further desktop investment.

---

## Part 4 — Target navigation

Now — 11 flat items:
`Overview · My Cards · Benefits · Ask · Compare · Planner · Expiring Soon · Updates ·
Sources · Research Queue · Settings`

Proposed — 5:

| Item | Contains |
| --- | --- |
| **Today** | item 89: expiring, unused, resets, uncertain matches, changed |
| **My Cards** | the wallet; vault state and lineage on it; add a card (item 90) |
| **Benefits** | owned-first (item 92); catalog as a filter; each with item 93's four parts |
| **Which card?** | Ask + Planner + Compare merged; item 82's seven questions as affordances |
| **Settings** | incl. Contributor mode |

**"Which card?" is the merge that matters.** Ask, Compare and Planner are three
interfaces to one intent. Compare becomes a result *mode*, not a destination.

**Contributor mode** reveals Updates, Sources, Research Queue, diffs, tiers, hashes and
the refresh ledger — unchanged, just not in a consumer's way. This also gives item 70's
pull-request contributors a real home.

## Part 5 — What "Today" should be

Replacing Overview. Same palette, same components, same privacy posture.

1. **Three action metrics** — Expiring in 30 days · Unused this quarter · Changed since
   last visit. Each a link to a filtered list, not a dead stat. Skeleton-shim the load;
   never a bare `—` where a number will be.
2. **"Act before these lapse"** — concrete money-shaped rows, each with its own provenance
   chip:
   - `2 complimentary lounge visits left` — Tata Neu HDFC Infinity · quarter ends 30 Sep ·
     ● Verified 12 Jul
   - `Annual fee waiver needs ₹42,000 more spend` — HDFC Regalia Gold · anniversary 14 Nov
     · ● Needs review
   - `1 BookMyShow voucher unclaimed` — Tata Neu HDFC Infinity · expires 31 Aug ·
     ● Verified 2 Aug
3. **One entry point** — "Buying something?" → single field (`₹8,000 at Amazon`) → Best
   card. Two lines beneath: nothing typed is saved; rankings ignore affiliate links
   (item 8).
4. **Vault state as a persistent sidebar control**, with idle-lock countdown (item 25).
5. **Uncertain matches surfaced** (item 15) — "we're not sure which variant your HDFC card
   is" is a *task*, with a resolve button, not red helper text.

Why it works: rigor is inline (every row carries state and date; "Needs review" beside
"Verified" teaches the distinction better than a paragraph); money is the unit, not
records (each line is actionable today, which is what brings the user back tomorrow);
privacy stays visible (lock promoted to a control, remaining legal copy sits where the
risk is — relocated, not hidden).

## Part 6 — Contributor / Admin mode

You want a mode where the owner sees the machinery, corrects information for their own
needs, pushes a correction toward getting a benefit live, watches agents research in the
background, and hands the result to the repo as a pull request. Right instinct — it also
resolves finding 02. But it only works if one distinction is designed first.

### 6.1 The distinction everything hangs on

*"I need this fixed for me, now"* and *"the catalog should say this for everyone"* are two
different actions. Today the architecture only has the second — which is why every
correction waits for human review, and why the UI is full of apologies about things not
being verified yet.

Three layers, not two:

| Layer | What it is | Changes how |
| --- | --- | --- |
| **1 · Verified catalog** | Reviewed, evidence-backed, shared across installations. Immutable, versioned. | Review gate only |
| **2 · Community candidate** | Proposed by an agent or contributor. Visible, labelled, never counted as fact. | Your existing `needs_review` store |
| **3 · My override** | Private, local, instant, never published. **Missing today — and the one users need most.** | In the vault, beside the card |

Layer 3 is what makes the app usable on day one with an empty catalog. A user whose
statement says they get 4 lounge visits should type 4, see their counters work
immediately, and carry on — with the value labelled *"you told us this"*. It costs nothing
in rigor because it never leaves their machine, and it converts the empty-catalog problem
(Part 0.1) from a blocker into a gentle prompt.

Design consequence: the provenance chip from finding 01 needs a fourth state — *your
value* — visually distinct from verified, needs-review, and withdrawn. Grey, not mint.

### 6.2 The override → contribute bridge

The flow worth designing most carefully: where a private correction becomes public
knowledge, and where governance either holds or leaks.

1. **Correct it for yourself.** Inline edit on the benefit row. Instant, private, no
   review. Row now reads `● Your value · edited 10 Aug`.
2. **Offer it upstream — optional, always.** A quiet "Help fix this for everyone?"
   affordance. Never a nag, never a precondition for the override working.
3. **Attach evidence, or it stays a lead.** Official URL required. Statement screenshots
   are private and never uploaded — they can justify an override but cannot back a public
   claim. This is item 60 and it must be enforced in the UI, not only the API.
4. **Redact, preview, confirm.** Show the exact structured diff that will leave the
   machine, field by field, before it leaves. No card instance, no lineage ID, no last-4.
   The user approves a payload they can read.
5. **Becomes a pull request.** Schema-validated YAML + sources + conflict-of-interest
   disclosure (items 70, 73). The app generates the branch and body; the human clicks
   Create. Then show PR state on the row that started it — *"you proposed this · open 3
   days"*. That round trip is what turns a user into a contributor.

### 6.3 The hazard: admin mode must not become self-approval

Item 67 requires an *independent* human to approve ordinary claims, and two for
high-impact ones. If admin mode lets the owner approve their own proposal into the active
catalog, the whole evidence discipline collapses into "the owner said so" — and the
provenance chip starts lying.

So: **Contributor mode can propose, override, research, and stage — never promote.**
Promotion to Layer 1 lives in PR review on the repo, where a second human is structurally
required. Make that visible: the Approve control simply isn't there, and a line says why.
That refusal is a feature to show off, not hide.

### 6.4 Naming and shape

Call it **Contributor mode**, not Admin. Local-first means the owner already has every
permission — there is nothing to administer, and "admin" implies power over other users,
a promise this architecture deliberately cannot make. "Contributor" also names the second
real audience: the people item 70 invites to send pull requests.

One toggle in Settings, off by default, remembered locally. Not a login, not a role — a
lens. When on, the consumer nav gains one sixth item, `Contributor`, with tabs:

- **Proposals** — the existing candidate queue, diffs, evidence provenance. Add: which of
  these affect *cards you actually hold* (sort by that; it's the only ordering that
  matters to an owner-contributor).
- **Evidence** — source registry, admission state, tiers, hashes, refresh ledger.
- **Agents** — item 84's scheduler view: last run, next run, failures, pause. Currently
  the research pipeline runs invisibly; an owner who can't see or pause background agents
  won't trust them. Show what each agent is doing, on which source, and what it produced.
- **Sources** — admission workflow (items 59–63), including the request-admission path.
- **My overrides** — every Layer 3 edit in one list, with "offer upstream" per row. This
  doubles as the honest answer to *"what in this app is just me?"*

Everything in `#research`, `#updates`, and `#sources` today moves here unchanged. No work
is lost; it stops being in a consumer's way.

## Closing

Two sentences of feedback, if you only keep two.

**Prove the loop before you harden it further.** One card, one benefit, source to pixel.
Everything in the repo is currently a well-built answer to a question the product hasn't
yet asked out loud.

**Stop warning and start being precise.** The thing that will make this app win is that
it tells the truth about uncertainty in a category built on stale scraped tables. But
telling the truth and warning constantly are different behaviours, and the app currently
does the second. `● Verified 12 Jul · HDFC` reads as far more trustworthy than a
paragraph explaining that you might be wrong.
