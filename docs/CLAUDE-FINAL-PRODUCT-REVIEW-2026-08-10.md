# Final product review — MyCard Benefits

Reviewer: Claude (independent final product review)
Date: 2026-08-10
Checkout: `<repo>`
Branch reviewed: **`agent/luna-final-integration`** at **`7787548`**
Served app: `http://127.0.0.1:8777/`

> Historical snapshot: this report records the state of the reviewed branch and
> owner decisions as of 2026-08-10. References below to Family Finance,
> imports, pairing, or companion integration are retained as review evidence;
> they are not current product capabilities or roadmap items.

> **Note on branch identification.** At session start `git branch --show-current`
> reported `main` @ `24f8122` with a clean tree, which I initially recorded as a
> discrepancy against the brief. That HEAD reading was stale. The decisive check:
> `static/app.js` was **3195 lines** in the working tree I read — `7787548`'s
> version. `main` @ `24f8122` has **547 lines** and contains none of
> `ownerReviewLibrary`, `familyFinanceImport`, `contributorModeToggle`, or
> `vaultUnlockPanel`, all of which I read and exercised. `main` is an ancestor of
> `7787548` (`git log HEAD..main` is empty); the feature branch is ahead by ~20
> commits.
>
> **Every file citation and line number in this report is against
> `agent/luna-final-integration` @ `7787548`**, which is the branch the brief
> named and `CONTINUE-HERE.md:9` records. There is no branch discrepancy to
> resolve. Work on `7787548`.

**Method.** Every claim below is either (a) exercised in the live browser against
`127.0.0.1:8777`, (b) read from a live API response, or (c) read from source and
marked **source-only**. Screenshots were unavailable in this session (the browser
pane does not composite frames headlessly), so visual verification was done via
the accessibility tree, computed styles, rendered `innerText`, and measured
geometry rather than by eye. No private card values were read, printed, or stored;
aggregate counts and lifecycle distributions only.

---

---

## 0. ADDENDUM — owner redirection, 2026-08-10 (supersedes parts of this report)

After reading the review, Hari changed direction. **These decisions override
anything below that conflicts with them.** Everything not listed here still stands.

**Cancelled / removed**

- **Family Finance integration is cancelled entirely.** Remove all of it from
  **both** repos: `mycard-benefits` and `<family-finance-repo>`
  (branch `main`; integration surface includes `mycard_export.py` and
  `docs/MYCARD-BENEFITS.md`). Product-intent item #10 no longer exists. §3's
  positive finding about the import boundary, and WP-9's dependency on it, are void.
- **The Today view is removed.** Nav loses it. P1-1's "fix Today" and §5 journey 1
  are replaced by the shape below.
- **All 80 private card records are wiped permanently, no backup** — Hari
  confirmed this after I flagged its irreversibility. Vault resets to a clean
  first-run state. The seeded public catalog (72 offerings, 61 benefit references)
  is **not** wiped.

**New authentication model** (replaces the 12-char-passphrase-at-unlock design)

- **No password on first run.** A fresh clone opens straight into the app. Cards
  are **not locked by default**. Browsing cards, benefits, search and filtering all
  work with no credential at all.
- A credential gates **one thing only: revealing full card details** (PAN, CVV,
  PIN, exact expiry). Nothing else.
- The first time the user reveals full details, the app asks them to set a
  credential right then. **No default credential ships in the repo** — Hari
  accepted this in place of his initial `123456` proposal, so there is no
  publicly-known secret in an open-source clone and the vault key is real from the
  moment it protects anything.
- The user chooses **PIN or passphrase**. PIN minimum 6 digits, Argon2id at high
  cost, escalating delay and lockout on repeated failure (the existing
  `rate_limited` path already supports this).
- Changing the credential requires entering the current one.

**The product shape Hari actually wants** — in his words: *"first have my cards
properly stored, displayed, and I can sort, filter, look for cards by different
aspects; and all the benefits of my cards are collected, sorted clearly, saved —
not only my card, every credit card available, based on categories; and then I can
search for any benefit, or any benefit on my card, look out for feature details."*

Two browse axes, one search:

1. **My Cards** — stored, displayed recognisably (last-4 + issuer colourway +
   network mark), and **sortable/filterable by many aspects**: issuer, network,
   card type (credit/debit/prepaid/membership), lifecycle, benefit category
   present, fee, and free text.
2. **Benefits** — every benefit on the user's cards, collected and grouped
   clearly; **and** the same for every card in the catalog, organised **by
   category** (lounge, movie, dining, rewards, cashback, fuel, forex, insurance,
   meet-and-greet…). Owned cards surface first; the full catalog is browsable by
   category rather than as one alphabetical dump.
3. **Search** — one search that spans both: any benefit anywhere, or scoped to
   "only my cards", filterable by category, merchant, value/cap, condition and
   claim route, with feature detail on every result.

**Still fully in force from this report:** P0-1 (fabricated "8 vouchers per year"),
P0-2 (archived card described as active), P0-3 (decimal corruption `0.5` → `0 5`),
P1-2 (machine field paths in consumer copy), P1-3/P1-4 (Which card? and the
hardcoded purchase stub), P1-5 (Compare), P1-6 (card recognition), P1-7 (unlock
panel shown while unlocked — note it must now follow the new auth model), P1-8
("Activated" badge), P1-9 (mobile overflow, 44px targets), P1-10 (dead shortcut
buttons), P1-11 (alphabetical headlines), P1-12 ("Add this card" when owned), and
the whole of §8's coverage analysis and §10's accessibility findings.

---

## 1. Executive verdict

# NOT RELEASE READY

Not because the architecture is wrong — it is sound, and I found no reason to
rebuild anything. Two specific reasons:

1. **The app currently tells the user things that are not true.** It renders an
   entitlement ("8 vouchers per year") that its own reviewed evidence explicitly
   records as *not claimed*; it describes an archived card as "an active local
   card"; and it corrupts decimal values so that `0.5` renders as `0 5`. In a
   product whose entire differentiator is *honesty about evidence*, these are
   disqualifying. They are also all small, local fixes.

2. **What is built is a public-catalog browser with a private card list attached.
   What Hari asked for is a search engine over the benefits of the cards he
   owns.** He said so directly in the interview: *"what I needed is a way to
   store, search, filter, and find the benefits of my card."* The current Today
   screen leads with 72 alphabetical public card tiles beginning with "AU Kosmos".
   The two decision surfaces he named — Which card? and Compare — are stubs.

Distance to release is short. The data, the security, the accessibility and the
evidence model are in good shape. The gap is a re-pointing of the information
architecture plus roughly a dozen concrete fixes. No rewrite.

---

## 2. What the product is, in plain consumer language

You keep your cards in one place on your own computer. Nothing leaves the
machine. Then you ask it questions about *your* cards:

- *Which of my cards gets me into an airport lounge, and what do I have to do
  first?*
- *I'm buying an IMAX ticket — which of my cards takes the most off, and how
  much?*
- *I'm travelling in March with my partner — which card covers a guest?*
- *What do I actually own, and which of them are worth carrying?*

And for every answer it tells you plainly whether it is **checked**, **worth
checking before you rely on it**, or **sources disagree** — with a link to the
bank's own page and the date it was last looked at. It never guesses, never
invents a number, and never pretends you qualify for something.

That is the product. The current build does the honesty part well and the
"my cards" part poorly.

---

## 3. What is genuinely working now (verified in the real app)

I want to be precise here, because a lot of the earlier design review's
recommendations *have* been implemented and should not be re-reported as pending.

| Working | Evidence |
| --- | --- |
| **Consumer/contributor split is real** | Nav is exactly `Today · My Cards · Benefits · Which card? · Settings`. Toggling `#contributorModeToggle` adds `Updates · Sources · Research Queue · Local reminders` and reveals 7 `.contributor-only` regions. Verified live. |
| **No pipeline internals leak to consumers** | Scanned rendered `innerText` for internal IDs, UUIDs, and content hashes with contributor mode off: **zero** of each. Only `needs_review` appears, and only with contributor mode on. |
| **Provenance chip exists and is used** | `.provenance-chip.provenance-verified` renders on benefit evidence with policy class, tier, and as-of date. Design review finding 01's keystone component was built. |
| **The one reviewed benefit is modelled honestly** | `/api/v1/catalog/benefits` returns the Tata rule with an explicit `not_claimed` list rejecting "unconditional 8 visits per year", "direct complimentary swipe access", and "voucher rollover". This is unusually good discipline. |
| **Tata consumer copy invents nothing** | Benefit detail reads *"Up to 2 lounge visits per qualifying calendar quarter"* + *"Requirement: INR 50,000 eligible net posted spend in one calendar quarter"* + a **"Check eligibility and terms"** action. No "visits left" anywhere. Verified live. |
| **Item 93's four parts are present** | The detail renders *How to use / Where to use / What to verify / Official terms*, plus effective-from, "No end date is recorded", and evidence. |
| **Accessibility is strong** | 977 rendered elements scanned for WCAG AA contrast: **0 failures in light theme, 1 marginal in dark** (the "Search benefits" button at 4.15:1 vs 4.5 required). Focus moves to the view `<h1>` on navigation with a live announcement; 0 focusable elements inside hidden views; skip link, `:focus-visible` rules, `prefers-reduced-motion`, 42 live regions. |
| **Family Finance import respects the privacy boundary** | The browser POSTs *bodyless* to `/api/v1/private/imports/family-finance/preview`; the **server** opens the native picker (`family_finance_picker()`, `vault/router.py:919`) and parses in-process. The browser receives only `preview_id`, `preview_digest`, and counts. Apply requires the passphrase. **Source-only** — I did not trigger the OS dialog. |
| **Local reviewability is honest in aggregate** | `/api/v1/candidates/owner-local-review` returns `{active_catalog_rule: 1, terms_to_check: 55, source_conflict: 5}` = 61, and the UI states exactly that. |
| **Lifecycle data is intact** | 80 records, all catalog-matched, `active: 20 / archived: 60`, filterable. |

---

## 4. User interview decisions and their implications

Four questions asked; the fourth answer changed the shape of this report.

**D1 — Locally-reviewed benefits go live immediately.**
> *"I want them to be live right away if I see a mistake I will tell the agent to fix it."*

**Implication.** The 61-item library stops being a separate read-only annex and
becomes the benefit index. All of Benefits, Which card?, and Compare read from it.
This is a deliberate, owner-authorised relaxation of the "reviewed-active only"
rule for *this local installation*. It does **not** change publication: nothing
gets promoted to the shared catalog without the `AGENTS.md` review gate. The
distinction to encode is **local-live** vs **publishable**, and Codex must not
collapse them.

**D2 — Inline, with a "Check before use" chip.**

**Implication.** One list, ordered verified-first, each row carrying its own
state chip. The current badge text **"Activated locally for your review"** must
go — "Activated" reads as *switched on*, which is the opposite of the intent.

**D3 — Last 4 + issuer colour + network mark.**

**Implication.** Cards become recognisable objects. Note the content precondition:
**all 80 records currently render "Last four unavailable"** — the digits are not
in the vault. Colour + network mark work immediately; last-4 needs Hari to fill
them in, so the card component must look right *without* digits too.

**D4 — All four journeys must be flawless, and the framing is wrong.**
> *"I am not even sure the current UI is what I intended… what I needed is a way
> to store, search, filter, and find the benefits of my card… Public Catalog is
> something different, right?… which particular card of mine will give me
> meet-and-greet… I need at least ₹800 off per ticket… I need to know the maximum
> amount I will get from a particular card… lounge access for me and my guests…
> Also copying my card number, CVV, expiry onto the clipboard whenever I want."*

**Implications, and this is the core of the handoff:**

- **Owned-first is not a filter, it is the default surface.** Public catalog
  becomes a distinct secondary mode ("look up any card"), not the home screen.
- **Three capabilities in that quote do not exist in any form today** — see §8.
  They are not bugs. They are unbuilt:
  - *meet-and-greet*: exists only as a schema enum. **Zero** seeded benefits.
  - *guest / companion coverage*: **no such dimension exists** in the allowance
    model anywhere in the codebase. (`companion.py` is Family Finance pairing,
    unrelated.)
  - *"maximum I will get"*: `valuations` is **never populated** in any seed. Caps
    exist (`cap_inr` ×12, `ticket_cap_inr` ×6) but are never surfaced as a
    comparable number.
- **Clipboard copy of PAN/CVV/expiry is currently disabled by design.**
  `POST /cards/{card_id}/reveal-authorize` returns **HTTP 410 "plaintext reveal is
  disabled"** (`vault/router.py:1474-1486`), and there is no reveal UI at all.
  `AGENTS.md` boundary 3 *permits* this ("only the human-facing UI may reveal or
  copy plaintext after reauthentication") — so it is allowed policy, simply
  unbuilt. This is the single largest new work item and the one that touches the
  security boundary hardest.

**Where I push back.** On D1, "live right away" is right for *your* installation,
but two of the 61 items would be actively harmful if shipped as-is (see P0-1 and
P0-3): they contain a fabricated entitlement and corrupted numbers. "Live" must
mean *live after the projection layer is fixed*, not *live as currently rendered*.
That is a two-file fix, not a delay of substance.

**Benchmark note (CRED / SaveSage).** Used only as usability reference; nothing
copied. The two patterns worth taking: (1) **the card is a recognisable object**,
not a text row — CRED's whole recognition model rests on this, and it is exactly
D3; (2) **one primary question per screen** — SaveSage leads with "which card
should I use", with coverage breadth (500+ cards) as the moat. MyCard cannot win
on breadth and should not try; its moat is *provenance you can check*. The
anti-pattern to avoid: both are spend-ledger-adjacent, which
`PRODUCT_REQUIREMENTS.md:10` explicitly refuses. Keep refusing it.

---

## 5. End-to-end journey scorecard

| # | Journey | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | First impression / Today | **FAIL** | Today renders **all 72** public offering tiles; its `innerText` is 8,722 chars and opens with "AU Kosmos RuPay Select". A user with 80 saved cards sees a public catalog, not their wallet. |
| 2 | Setup and unlock | **PARTIAL** | Sidebar correctly shows "Unlocked" + idle copy. But `#vaultUnlockPanel` is **visible with `hidden=false` while unlocked**, so My Cards renders a panel titled *"Unlock your cards"* plus a second "Lock My Cards" button. Verified live. |
| 3 | My Cards list / recognise cards | **FAIL** | All 80 records render identically as *"Last four unavailable"* + product name. Recognition by eye is impossible. |
| 4 | Add a card, optional details | **PASS** | `#cardAddForm`: 72-option variant select, optional last-4, `<details>` for PAN/expiry/CVV/PIN/nickname, passphrase required. Sensitive fields correctly optional. Not submitted (would mutate the vault). |
| 5 | Lifecycle / history | **PASS** | Filter shows `active (20) / archived (60)`; edit, lifecycle, replace, delete/purge forms all present with fresh-passphrase reauth. **Source-only** — not executed. |
| 6 | Benefits browsing and search | **PARTIAL** | Search works and is honest ("1 catalog match"). But the reviewed catalog and the 61-item library are two stacked, separately-searched lists; library search ignores issuer/card name and `allowance_details`. |
| 7 | Open a card / open a benefit | **PARTIAL** | Structure is good (four parts, evidence, dates). Copy leaks machine internals — see P1-2. |
| 8 | Tata conditional lounge detail | **PASS in catalog view / FAIL in library view** | Catalog detail is exemplary. The *same* benefit in the review library, badged "Active rule", lists **"8 vouchers per year"** — see P0-1. |
| 9 | Axis NEO / BookMyShow | **PARTIAL** | Renders with source link and "Use on the web or app". Badged "Activated locally for your review". Does not reach Which card? or Compare. |
| 10 | HDFC Millennia rewards | **PARTIAL** | 8 references present and source-linked. Headline values are alphabetically-chosen ("Calendar month cap: 1,000" on *both* base and accelerated earn — the differentiating rate is hidden). |
| 11 | Regalia Gold lounge | **PARTIAL** | Present ("Cap: 3" domestic, "Cap: 6" Priority Pass). "Cap: 3" is a machine label, not consumer copy. Best-covered card at 17 refs. |
| 12 | "Which card?" purchase question | **FAIL** | `INR 8,000 at Amazon` → *"No matching benefit found."* |
| 13 | "Which card?" category question | **PARTIAL/FAIL** | `airport lounge` → one result, correctly tied to an owned card — but asserts *"An active local card matches this product"* when that card is **archived** (P0-2). All seven "Common questions" buttons feed the same token matcher; *"How many uses remain?"* → "No matching benefit found." |
| 14 | Compare | **FAIL** | Regalia Gold vs Tata Neu — the two best-covered cards — returns *"Comparison data is not ready yet."* Compare reads only the 1-rule catalog, so **no pair can ever produce output** today. |
| 15 | Settings | **PASS** | Contributor toggle, theme, reminder education, pairing, remote-access explanation. Clean. |
| 16 | Contributor separation | **PASS** | See §3. |
| 17 | Family Finance import preview | **PASS (source-only)** | Native picker server-side; browser sees counts only. Not executed. |
| 18 | Mobile | **FAIL** | At 375px the document is **406px wide** — 31px horizontal overflow, caused by `article.benefit-card` (right edge 405px) on Benefits. 13 "Open official source" / "Official source" links are **21–32px tall**, below the 44px target — and these are the app's primary trust action. |
| 19 | Themes | **PASS** | 0 contrast failures light, 1 marginal dark. |
| 20 | Keyboard | **PASS** | See §3. |
| 21 | Locked / error states | **NOT EXERCISED** | I declined to lock the vault, which would force Hari to re-enter his password. Copy reviewed **source-only** (`VAULT_DIAGNOSTICS`, `app.js:1300-1400`) and reads well. |

---

## 6–7. Severity-ranked problems

Each entry: harm · screen · source · desired behaviour · acceptance test · class.

### P0 — release blockers

---

**P0-1 · The app publishes an entitlement its own evidence rejects**

- **Harm.** A user reads *"8 vouchers per year"* under a badge saying **"Active
  rule"** and **"This is a reviewed active catalog benefit."** They plan four
  lounge visits a year they have not earned. The reviewed rule *explicitly*
  records `not_claimed: ["unconditional 8 visits per year"]`. The app contradicts
  its own source of truth on the single benefit it has fully reviewed.
- **Screen.** Benefits → *Your local benefit library* → Tata Neu Infinity lounge →
  "How to use and what to check" → *Recorded limits*.
- **Source.** `candidates/router.py:596-610` (`_allowance_details`) flattens the
  whole `allowance` dict; `static/app.js:660-664` renders every entry as a bare
  bullet. Neither consults `not_claimed`.
- **Desired behaviour.** `_allowance_details` must exclude any derived aggregate
  the reviewed rule lists under `not_claimed`, and per-period figures must carry
  their qualifier. Render: **"2 vouchers per qualifying quarter"** and, if a yearly
  figure is shown at all, **"up to 8 a year — only if you qualify in all four
  quarters"**. Never a bare "8 vouchers per year".
- **Acceptance test.** Load `#benefits`, expand the Tata library card. Assert the
  rendered text contains no substring matching `/\b8 vouchers? per year\b/` unqualified,
  and that every `not_claimed` entry of the linked catalog rule is absent from
  `.evidence-list`.
- **Class.** Content/data + product.

---

**P0-2 · The app calls an archived card "active"**

- **Harm.** Which card? → `airport lounge` returns *"A matching benefit for one of
  your cards"* / *"An active local card matches this product."* The only owned
  card carrying that rule has `lifecycle: "archived"`. If that card is closed or
  reissued, the user is told to rely on a card they cannot use — at an airport.
  The benefit *detail* view gets this right ("Archived local record"), so the app
  contradicts itself between two screens.
- **Screen.** Which card? result card.
- **Source.** `static/app.js:138-145` — `isOwnedBenefit()` returns true via
  `discoveryMatch`, which tests `rule_ids` and **never checks lifecycle**;
  `app.js:290` then hardcodes the word "active". Verified: the sole card with
  `rule_ids` is `{lifecycle: "archived"}`.
- **Desired behaviour.** Separate *owned* from *usable*. Copy must derive from the
  matched record's lifecycle: active → *"Your <product> matches this."*;
  archived/closed/expired/lost/stolen → *"Only an archived card of yours matches
  this — check whether you still hold it."* Never the word "active" unless a
  matched record is `active`.
- **Acceptance test.** With only archived matches present, assert the Which card?
  result contains no occurrence of "active local card" and does contain the
  archived wording; flip one record to active in a fixture and assert the inverse.
- **Class.** Product correctness (safety-relevant).

---

**P0-3 · Decimal points are destroyed in money-shaped values**

- **Harm.** *"Maximum airmiles per reward point: 0 5"* — a user can read this as
  **5**, a 10× overstatement of transfer value. Also *"Merchant emi percent: 1 5"*
  (should be 1.5%), *"Validation fee usd: 3 25"* (should be $3.25), *"Any upi
  percent: 0 5"*. This is exactly the "developer console" feel Hari objected to,
  and it is numerically wrong, not just ugly.
- **Screen.** Benefits → review library → any Regalia Gold / Tata Neu earn or
  conversion row.
- **Source.** Pinned exactly. `candidates/router.py:512-513` — `_consumer_value`
  routes **string** values to `_consumer_label`. `_consumer_label`
  (`router.py:495-499`) does `value.replace(".", "_").split("_")` and joins with
  spaces. So `"1.5"` → `"1_5"` → `"1 5"`. Seeds store these as strings:
  `regalia_gold_research.py:239` (`"0.5"`), `tata_neu_infinity_2026.py:222`
  (`"1.5"`), `:228` (`"3.25"`).
- **Desired behaviour.** `_consumer_value` must attempt numeric coercion on strings
  *before* falling through to label humanisation, and `_consumer_label` must never
  be applied to a value that parses as a number. `"0.5"` with key
  `maximum_airmiles_per_reward_point` → **"0.5 airmiles per reward point"**.
- **Acceptance test.** Unit-test `_consumer_value("0.5")  == "0.5"`,
  `_consumer_value("3.25") == "3.25"`. Integration: assert no
  `allowance_details` string in `/api/v1/candidates/owner-local-review` matches
  `/\d+ \d+/`.
- **Class.** Technical defect with content-integrity consequences.

---

### P1 — must fix before a first useful release

---

**P1-1 · The product is pointed at the public catalog, not at the user's cards**

- **Harm.** Hari's stated need — *"store, search, filter, and find the benefits of
  my card"* — has no home. Today opens with 72 alphabetical public tiles. Benefits
  leads with the public catalog. Owned cards are a checkbox
  (`#benefitOwnedOnly`), and that checkbox lives inside the **contributor-only**
  filter block, so a normal user cannot even reach it.
- **Screen.** Today, Benefits.
- **Source.** `templates/index.html:58` (catalog preview embedded in `#today`),
  `index.html:197` (`.discovery-filters.contributor-only` contains
  `#benefitOwnedOnly`), `app.js` `renderOfferings()`.
- **Desired behaviour.** Benefits defaults to **"My benefits"** — the union of
  every benefit attached to a card the user holds, grouped by card, ordered
  active-lifecycle first. A visible second mode, **"Look up any card"**, is the
  public catalog. Today shows the user's own next useful thing, never the catalog
  list. Copy: *"Benefits on your cards"* / *"Look up any card"*.
- **Acceptance test.** Fresh load of `#benefits`: first rendered group is an owned
  card; `#offeringPreview` is absent from `#today`; the owned/all switch is
  reachable with contributor mode **off**.
- **Class.** Product / information architecture.

---

**P1-2 · Consumer copy leaks machine field paths and operators**

- **Harm.** Under *"What to verify"* the app prints
  `calendar_quarter.eligible_net_posted_spend_inr gte 50000`,
  `spend_definition equals posted purchases/debits after credits…`,
  `card_instance_scope equals for upgraded, replaced…`. Elsewhere: *"Cap: 2"*,
  *"Cap: 3"*, *"Incremental points cap per month: 5,000"*, *"Where to use:
  lounge"*, *"Telecom cable monthly cap neucoins"*. This is the Jupyter-notebook
  feel, verbatim.
- **Screen.** Benefit detail; every review-library row.
- **Source.** `candidates/router.py:487-593` (`_consumer_label` /
  `_consumer_allowance_line` fallback at `:592`), `app.js` benefit-detail
  "What to verify" renderer.
- **Desired behaviour.** A closed label map for every field that ships, and a
  hard rule: **if a field has no consumer label, it does not render on a consumer
  screen** — it renders only in contributor mode. `"Cap: 3"` → *"Up to 3 visits a
  quarter"*. `"Where to use: lounge"` → the actual lounge network or *"At
  participating airport lounges"*. Operators (`gte`, `equals`) never appear.
- **Acceptance test.** With contributor mode off, assert no rendered text matches
  `/\b(gte|lte|equals|not_in|exists)\b/` or `/[a-z]+_[a-z_]+/`, and that every
  `allowance` key present in seeded data has an entry in the label map (test over
  the map, so a new key fails CI).
- **Class.** Design / content.

---

**P1-3 · "Which card?" is a token matcher, not a recommender**

- **Harm.** The headline journey. `INR 8,000 at Amazon` returns nothing. Amount,
  merchant and category are never parsed. It returns **one** result
  (`ownedMatches[0] || matches[0]`), so it never actually compares cards — the
  question "which card?" is structurally unanswerable by the current code.
- **Screen.** Which card?.
- **Source.** `app.js:267-297`. Line 275 is a bare token-overlap filter over
  `state.benefits` (currently 1 item). Line 277 takes `[0]`. The real optimizer
  (`POST /api/v1/optimizer/routes`, called at `app.js:2545`) is reachable **only**
  from `#plannerAdvanced`, which is `.contributor-only`.
- **Desired behaviour.** Parse amount / merchant / category, then rank **every**
  owned card that has a candidate benefit, showing per card: what you'd get, the
  cap, the condition, and its evidence state. Return a list, not a single card.
  Say plainly when a card is excluded and why. Route the consumer path through the
  optimizer rather than keeping it behind contributor mode.
- **Acceptance test.** `INR 8,000 at Amazon` with the unified index returns ≥1
  ranked row per eligible owned card, each with a value or an explicit "no value
  recorded"; `airport lounge` returns all owned lounge-capable cards, not one.
- **Class.** Product.

---

**P1-4 · The consumer purchase form is a hardcoded dead end**

- **Harm.** The user fills merchant, category, amount, and selects cards, and
  **always** receives *"A verified ranking is not available for these cards yet."*
  — regardless of data. It cannot ever succeed.
- **Screen.** Which card? → Refine the result → "Choose a card for a purchase".
- **Source.** `app.js:2623-2633`. `renderPurchaseLimitation()` validates input then
  unconditionally sets the same string. There is no success branch.
- **Desired behaviour.** Delete this form and fold its inputs into P1-3's
  progressive refinement, or wire it to the optimizer. Do not ship a form whose
  only outcome is an apology.
- **Acceptance test.** No code path in the consumer bundle sets a
  "not available … yet" string unconditionally after successful validation.
- **Class.** Product / technical debt.

---

**P1-5 · Compare can never produce output**

- **Harm.** Regalia Gold vs Tata Neu — the two richest cards — returns
  *"Comparison data is not ready yet."* Since only one benefit is in the reviewed
  catalog, **every** pair returns this.
- **Screen.** Which card? → Refine → Compare choices.
- **Source.** `renderComparison()` reads `state.benefits` (reviewed catalog only).
- **Desired behaviour.** Compare over the unified index (D1). Align by category:
  Lounge, Movie, Dining, Rewards, Fees. Per cell show value/cap, condition, and
  state chip. Keep the refusal to collapse to one score — that is a strength;
  label it. Where a card genuinely has no data, say *"nothing recorded yet"*, not
  "not ready".
- **Acceptance test.** Regalia Gold vs Tata Neu renders ≥4 aligned category rows
  with per-cell state chips and no single composite score.
- **Class.** Product.

---

**P1-6 · Cards are unrecognisable**

- **Harm.** 80 identical text blocks reading *"Last four unavailable"*. With 60
  archived and multiple same-issuer products, the user cannot find a card.
  Directly blocks D3 and journey 1.
- **Screen.** My Cards.
- **Source.** `app.js` `renderPrivateCards()` / `.card-grid`.
- **Desired behaviour.** A real card object: ~1.586 aspect ratio, issuer wordmark,
  network mark, generated per-issuer colourway, lifecycle pip, last-4 when present
  and a neutral treatment when not. Group active above archived. Costs nothing in
  privacy.
- **Acceptance test.** Two cards from different issuers are distinguishable with
  card text removed; a record with no last-4 renders without a placeholder that
  looks like an error.
- **Class.** Design (with a content precondition — see H-1).

---

**P1-7 · "Unlock your cards" is displayed while unlocked**

- **Harm.** Sidebar says "Unlocked"; My Cards simultaneously shows a panel headed
  *"Unlock your cards"* with unlock help text and a **second** "Lock My Cards"
  button. Two lock controls, one contradictory heading.
- **Screen.** My Cards.
- **Source.** **`static/app.js:1355`** — `unlockPanel.hidden = unlocked ? false : !unlock;`
  explicitly *shows* the panel when unlocked; `:1357` hides only the inner form,
  leaving the heading and help paragraph. Verified live:
  `vaultUnlockPanel_visible: true` while `vaultNavState: "Unlocked"`.
- **Desired behaviour.** Hide `#vaultUnlockPanel` entirely when unlocked. One lock
  control, in the sidebar. When unlocked, My Cards shows an unobtrusive
  *"Cards unlocked · locks after 10 min idle"* line.
- **Acceptance test.** With the vault unlocked, `#vaultUnlockPanel.hidden === true`
  and exactly one element with accessible name matching `/lock/i` is visible.
- **Class.** Technical defect / design.

---

**P1-8 · "Activated locally for your review" reads as "switched on"**

- **Harm.** 55 of 61 rows carry this badge. "Activated" is the single most
  misleading word available for an unverified claim.
- **Screen.** Benefits → review library.
- **Source.** `app.js:634`.
- **Desired behaviour.** Per D2: **"Check before use"** (amber). Reserve
  "Verified" (mint) for reviewed-active, "Sources differ" (red) for conflicts.
  Three chips, three colours, plus a date. Supporting note: *"From <issuer>'s own
  page, <date>. Confirm the current terms before you rely on it."*
- **Acceptance test.** No rendered consumer string contains "Activated"; every
  library row shows exactly one state chip with an as-of date.
- **Class.** Content / UX copy.

---

**P1-9 · Mobile overflow and sub-44px trust links**

- **Harm.** At 375px the page scrolls sideways (document 406px). The 13 "Open
  official source" links — the app's core trust action — are 21–32px tall. A
  benefits app is used one-handed at a counter.
- **Screen.** Benefits (detail + library) at ≤375px.
- **Source.** `article.benefit-card` measured right edge 405px inside a 375px
  viewport; `static/app.css` `.benefit-card` / `.benefit-match-card` sizing.
- **Desired behaviour.** No horizontal overflow at 320px. Source links become
  ≥44px tap targets (`.button.secondary` treatment on mobile).
- **Acceptance test.** At 320/375/414px, `documentElement.scrollWidth <= clientWidth`;
  every anchor whose text matches `/source|terms/i` has a bounding height ≥44px.
- **Class.** Design / technical.

---

**P1-10 · "Common questions" buttons are decorative**

- **Harm.** Seven affordances — *"How many uses remain?"*, *"What expires soon?"*,
  *"What changed?"*, *"Why does eligibility fail?"* — all set the same free-text
  box and all return *"No matching benefit found."* The user reads that as "I have
  nothing", when the app never attempted the question.
- **Screen.** Which card?.
- **Source.** `app.js:296` — every `[data-which-question]` button just writes its
  label into `#whichCardQuery` and calls the token matcher.
- **Desired behaviour.** Either implement each as a real query type against the
  unified index, or ship only the ones that work. A button that cannot be answered
  must not exist. Where an answer is genuinely unknowable (*"uses remaining"*
  without usage tracking), say so specifically: *"MyCard doesn't track your usage,
  so it can't count remaining visits. Here's the allowance and the condition."*
- **Acceptance test.** Every shortcut button produces a distinct, non-"no match"
  response, or is removed.
- **Class.** Product.

---

**P1-11 · Headline benefit values are chosen alphabetically**

- **Harm.** The Tata lounge headline is *"Claim within 120 days"* instead of
  *"2 vouchers per quarter"*. Millennia base and accelerated earn **both** headline
  as *"Calendar month cap: 1,000"*, hiding the rate that distinguishes them.
  Regalia Gold's fee waiver headlines *"Waived fee: renewal membership fee"*.
- **Screen.** Every review-library row.
- **Source.** `candidates/router.py:596-610` — `_allowance_details` iterates
  `sorted(allowance)`; `_primary_allowance` returns `details[0]`.
- **Desired behaviour.** A per-benefit-type priority order for the headline field
  (lounge → visits/vouchers per period; movie → discount or free ticket; rewards →
  earn rate; fee → the amount). Never alphabetical.
- **Acceptance test.** Tata lounge headline is the voucher count; the two Millennia
  earn rows have different headlines.
- **Class.** Content/data.

---

**P1-12 · "Add this card" is offered for cards already owned**

- **Harm.** Every library row shows "Add this card", including Regalia Gold, Tata
  Neu, Millennia and Axis NEO, which Hari already holds. Invites duplicates.
- **Screen.** Benefits → review library.
- **Source.** `app.js:683-686` — `if (offering)` with no ownership check.
- **Desired behaviour.** If owned → *"You have this card"* linking to the record.
  If owned-but-archived → *"You have an archived one"*. Only otherwise → "Add this card".
- **Acceptance test.** No "Add this card" button renders for an offering present in
  the private card list.
- **Class.** Product.

---

**P1-13 · "80 saved cards are ready to use" overstates the wallet**

- **Harm.** Today says *"80 saved cards are ready to use with the benefit
  library."* 60 are archived and 55 of 68 owned products have zero benefit
  references. Both halves are misleading.
- **Screen.** Today.
- **Source.** `app.js` `renderTodaySummary()`; verified `active: 20 / archived: 60`.
- **Desired behaviour.** *"20 cards in use, 60 archived. 13 of them have benefits
  recorded so far."* Honest, and it makes the coverage gap visible instead of
  hiding it.
- **Acceptance test.** Today's summary states active count, archived count, and
  count-with-benefits separately.
- **Class.** Content / product.

---

### P2 — worthwhile follow-ups

- **P2-1 · Duplicate, contradictory Tata lounge entries.** The library carries both
  the reviewed rule (₹50,000 condition) *and* `"Tata Neu Infinity domestic lounge
  access — Cap: 2, Period: quarter, Unit: visit"` with no condition. A user
  scanning sees "2 visits a quarter, no strings". Two near-identical RuPay Select
  international lounge entries also coexist. Dedupe or explicitly supersede.
  *Class: content/data.*
- **P2-2 · `_consumer_number` is dead code.** `candidates/router.py:502-503` —
  both branches return `f"{value:,}"`. Harmless, but it looks like a decimal
  handler and is not one; remove it while fixing P0-3 so nobody trusts it.
  *Class: technical debt.*
- **P2-3 · "Search benefits" button contrast** is 4.15:1 in dark theme (needs 4.5).
  *Class: design.*
- **P2-4 · Library search ignores the card name.** `ownerReviewMatchesSearch`
  (`app.js:642-648`) omits the offering display name and `allowance_details`.
  Searching "Regalia" works only because titles happen to contain it.
  *Class: technical.*
- **P2-5 · Generic placeholder offerings** ("HDFC Bank RuPay Credit Card", "ICICI
  Bank Debit Card", "YES BANK Credit Card") sit alongside real variants in the
  72-item add-card select. They can never carry accurate benefits.
  *Class: content/data.*
- **P2-6 · 213 focusable elements on Benefits.** Long tab journey; the 61-item
  library needs pagination or grouping. *Class: design.*
- **P2-7 · `CONTINUE-HERE.md:9` and this checkout disagree on the branch.**
  *Class: technical debt.*

---

## 8. Benefit-content coverage

**Counts (live API, 2026-08-10):**

| Layer | Count |
| --- | --- |
| Public offerings in catalog | **72** |
| Reviewed **active** catalog benefits | **1** (Tata Neu Infinity domestic lounge voucher milestone) |
| Local review library, total | **61** |
| — active catalog rule | 1 |
| — terms to check | 55 |
| — source conflict | 5 |
| Offerings with **any** benefit reference | **18 of 72** |
| Offerings with **zero** | **54 of 72** |
| Owned card records | 80 (`active 20 / archived 60`) |
| Distinct owned products | 68 |
| Owned products with **any** benefit reference | **13 of 68** |
| Owned records carrying an active rule | **1** — and it is **archived** |

**Owned card variants with useful coverage** (all reachable from Hari's wallet):

| Card | Refs | Note |
| --- | --- | --- |
| HDFC Regalia Gold Credit Card | 17 | Best covered; 2 of the 5 conflicts are here |
| Tata Neu Infinity HDFC RuPay Select | 9 | Includes the only reviewed-active rule |
| HDFC Millennia Credit Card | 8 | Rewards/cashback depth |
| RBL Play, IndusInd Legend ×2, IndusInd Nexxt, EazyDiner IndusInd, Axis NEO, HPCL ICICI Coral, ICICI Coral ×3, ICICI Sapphiro Mastercard | 1–2 each | Mostly single BookMyShow / movie entries |

Note the mismatch: the DBS family holds 15 references but appears in Hari's wallet
only as a generic "DBS Bank Debit Card" (0 refs) — the research went to variants he
may not hold, while 55 products he *does* hold have nothing.

**Missing high-value categories.** By review-library category:
`other 15 · movie 12 · reward_points 9 · lounge 8 · voucher 5 · conversion 4 ·
food 4 · cashback 2 · priority_pass 2`. Absent entirely: **fuel surcharge**
(beyond one Millennia row), **forex markup** (only DBS), **insurance** (only DBS +
Regalia), **golf**, **concierge**, **hotel**, **milestone/spend-threshold** across
most cards.

**Capabilities Hari named that have no data model at all:**

| Ask | State |
| --- | --- |
| *"which card gives me meet-and-greet"* | `meet_and_greet` exists **only** as a schema enum in `catalog/schema/catalog.schema.json`. **Zero** seeded benefits. Content gap. |
| *"lounge access for me and my guests"* | **No guest/companion dimension exists anywhere.** The allowance model has `unit`/`count`/`period` only. This is a **data-model** gap, not content. |
| *"maximum amount I will get per ticket"* | `valuations` is **never populated** in any seed file. Caps exist (`cap_inr` ×12, `ticket_cap_inr` ×6) but are never surfaced as a comparable figure. Model exists, unused. |
| *"copy card number, CVV, expiry to clipboard"* | `POST /cards/{card_id}/reveal-authorize` returns **HTTP 410 "plaintext reveal is disabled"** (`vault/router.py:1474-1486`). No reveal UI. Permitted by `AGENTS.md` boundary 3, but entirely unbuilt. |

**No invented claims found in the reviewed catalog layer.** The one active rule's
`not_claimed` list is exemplary discipline. The invention (P0-1) happens in the
*projection* layer, not the data. Fix the projection and the data stands.

---

## 9. Consumer vs contributor information architecture

**This is the part that is genuinely finished, and it is good.** Five consumer nav
items; contributor mode is one Settings toggle that adds four nav items and reveals
seven regions. No internal IDs, UUIDs, or content hashes reach consumer copy —
I scanned for all three. Research queue, sources, updates, evidence tiers, refresh
ledger, and route diagnostics all sit correctly behind the toggle.

**Three corrections:**

1. **The owned/all switch is on the wrong side of the boundary.**
   `#benefitOwnedOnly` lives inside `.discovery-filters.contributor-only`
   (`index.html:197`). Filtering to the cards you own is *the* consumer action; it
   must be a primary control. This single misplacement is a large part of why the
   app feels catalog-first.
2. **The review library is a third audience with no name.** It is neither reviewed
   catalog nor contributor pipeline — it is "things I've decided are good enough
   for me". Per D1 that is now the main benefit index. Name the three layers
   explicitly in the UI: **Checked** / **Check before use** / **Sources differ**.
   Keep *publishable* as a separate contributor-only concept.
3. **Contributor mode correctly cannot approve** — consistent with `AGENTS.md`
   rule 5. Make that visible rather than merely absent: a line saying why there is
   no Approve button is a feature worth showing.

---

## 10. Mobile, accessibility, error-state and privacy assessment

**Mobile — FAIL.** 31px horizontal overflow at 375px from `article.benefit-card`;
13 sub-44px trust links. H1 correctly reduced to 28px and the nav is no longer a
scroll strip — both earlier findings are fixed.

**Accessibility — STRONG.** 0 contrast failures in light, 1 marginal in dark
across 977 elements. Focus moves to the view heading on navigation with a polite
live announcement; 0 focusables inside hidden views; skip link, three
`:focus-visible` rule sets, `prefers-reduced-motion`, 42 live regions, real
`aria-labelledby`. This is better than most shipped consumer apps.

**Error states — MIXED, partly unverified.** Empty states read well in source
(`VAULT_DIAGNOSTICS`). But two "empty" states are really *unimplementable* states
masquerading as data gaps: Compare's "not ready yet" and the purchase form's
"not available yet" will never resolve. Those are lies of omission. Locked-vault
rendering was **not exercised** — I declined to lock Hari's vault.

**Privacy — STRONG, one gap.**
- Family Finance import: native picker server-side, browser sees counts only.
  Correct boundary.
- Plaintext reveal is refused at the API with 410 — no plaintext path to the
  browser exists today.
- Protected mutations require fresh passphrase reauth; CSRF tokens on all
  bodyless POSTs; `no-store` headers throughout.
- Discovery projection exposes only structural fields — no PAN, CVV, expiry, or
  names. I confirmed this by reading field *names* only.
- **The gap:** implementing Hari's clipboard request (WP-9) is the first feature
  that will move plaintext into the browser. It must be designed against
  `AGENTS.md` boundary 3 deliberately — reauth per reveal, one-use authorisation,
  auto-clear timer, no logging, no persistence, and never in a screenshot or agent
  prompt. Do not let it be added casually as "just a copy button".

---

## 11. Implementation plan — 14 work packages

Ordered by dependency and user value. Each is a coherent chunk, not a ticket.

| # | Package | Contains | Depends on |
| --- | --- | --- | --- |
| **1** | **Truthful projection layer** | Fix P0-1 (`not_claimed` suppression), P0-3 (decimal coercion), P1-11 (priority-ordered headline), P2-2 (dead `_consumer_number`). All in `candidates/router.py:487-610`. **Do this first — everything downstream renders through it.** | — |
| **2** | **Unified benefit index** | Per D1: one index over reviewed-active + locally-reviewed + conflicted, each row carrying a state (`checked` / `check_before_use` / `sources_differ`) and an as-of date. Serve it from one endpoint. Keep `local-live` and `publishable` as distinct flags. | 1 |
| **3** | **Lifecycle-aware ownership** | Fix P0-2. `isOwnedBenefit` returns `{owned, usable, lifecycle}`; every consumer string derives from it. Audit all uses of the word "active". | 2 |
| **4** | **Owned-first IA** | Fix P1-1. Benefits defaults to "Benefits on your cards", grouped by card, active first. "Look up any card" as an explicit second mode. Remove the catalog dump from Today (P1-13 copy included). Move the owned/all control out of `.contributor-only`. | 2, 3 |
| **5** | **Consumer language pass** | Fix P1-2 (closed label map + "no label → contributor-only" rule), P1-8 (three state chips, kill "Activated"), P1-12 (ownership-aware CTA), P2-1 (dedupe Tata lounge), P2-5 (flag generic placeholder offerings). | 1, 2 |
| **6** | **Faceted benefit search** | Hari's core ask. Consumer-grade filters over the unified index: category, merchant, card, value/cap, condition type, claim route, state. Fix P2-4 (search the card name and allowance details). This is what makes "find the benefits of my card" real. | 2, 4 |
| **7** | **Card recognition** | Fix P1-6 per D3: card-shaped object, issuer colourway, network mark, lifecycle pip, last-4 when present, graceful without. Group active above archived. | 4 |
| **8** | **Which card? as a real recommender** | Fix P1-3 and P1-4: parse amount/merchant/category, rank **all** eligible owned cards through the optimizer, return a list with value, cap, condition and state per card. Delete the hardcoded stub form. Resolve P1-10 (implement or remove each shortcut). | 2, 3, 6 |
| **9** | **Reveal and clipboard** | Hari's explicit ask. Replace the 410 with a reauth-gated, one-use reveal for PAN / expiry / CVV, plus copy-to-clipboard with an auto-clear timer and a visible countdown. **Security-critical — needs its own design note and counterpart review before code.** Never logged, never persisted, never in an agent prompt. | 7 |
| **10** | **Compare over the unified index** | Fix P1-5: aligned category rows (Lounge, Movie, Dining, Rewards, Fees), per-cell value + condition + state chip, no composite score, "nothing recorded yet" where true. | 2, 6 |
| **11** | **Value and cap model** | Populate `valuations` / surface `cap_inr` and `ticket_cap_inr` as a comparable "most you can get" figure with its own uncertainty. Unlocks Hari's IMAX-₹800 question. | 1, 10 |
| **12** | **Guest / companion dimension** | New allowance dimension (`guests_included`, `guest_fee`, `guest_conditions`) in schema + seeds + UI. Unlocks "lounge access for me and my guests". Schema change — sequence deliberately. | 2 |
| **13** | **Mobile and state correctness** | Fix P1-9 (overflow at 320/375/414, 44px source links), P1-7 (`app.js:1355` unlock panel), P2-3 (dark button contrast), P2-6 (paginate the 61-item list). | 4, 7 |
| **14** | **Content expansion for owned cards** | Content, not code. Close the biggest coverage gaps on cards Hari actually holds; add `meet_and_greet` benefits; re-point DBS research at the variant he owns. Ordered by owned-card frequency. | 1, 12 |

---

## 12. Release acceptance checklist

Run against the served app at `127.0.0.1:8777`. Every line is pass/fail.

**Truth**
- [ ] No rendered text contains an unqualified `8 vouchers per year` (or any
      `not_claimed` value from its linked rule).
- [ ] No `allowance_details` string matches `/\d+ \d+/` (decimal corruption).
- [ ] No consumer-visible text matches `/\b(gte|lte|equals|not_in|exists)\b/` or
      `/[a-z]+_[a-z_]+/` with contributor mode off.
- [ ] No consumer text says "active" about a card whose matched record is not `active`.
- [ ] Every benefit row shows exactly one state chip and an as-of date.
- [ ] The word "Activated" appears nowhere in consumer copy.

**Journeys** (Hari's four)
- [ ] Open app → My Cards → two cards from different issuers are distinguishable
      with text hidden.
- [ ] Benefits opens on *your* cards, grouped by card, active first — not the catalog.
- [ ] Filter to lounge → only owned lounge-capable cards, each with condition + state.
- [ ] `INR 8,000 at Amazon` returns a ranked list, or an explicit reason no card qualifies.
- [ ] Regalia Gold vs Tata Neu renders ≥4 aligned category rows, no composite score.
- [ ] Every "Common question" button returns a distinct, non-"no match" answer.

**Hari's scenarios**
- [ ] "Which of my cards has meet-and-greet?" → a real answer or an explicit
      "nothing recorded yet for your cards".
- [ ] IMAX-style query returns a per-card maximum value with its cap.
- [ ] A lounge benefit states whether guests are covered, or says it is unknown.
- [ ] Card number / expiry / CVV can be revealed and copied after reauth, with a
      visible auto-clear countdown.

**Craft**
- [ ] `scrollWidth <= clientWidth` at 320, 375, 414, 768, 1280px.
- [ ] Every source/terms link ≥44px tall on mobile.
- [ ] 0 WCAG AA contrast failures in both themes.
- [ ] Unlocked vault shows no "Unlock your cards" panel and exactly one lock control.
- [ ] Full keyboard traversal of all five views; focus lands on each view's `<h1>`.
- [ ] Locked, empty, loading and offline states verified on desktop and mobile.

**Boundaries**
- [ ] `uv run ruff check .`, `uv run pytest`, `uv run mypy src` all pass.
- [ ] Startup test proves loopback-only bind.
- [ ] No PAN/CVV/PIN/identity in tracked files, logs, or fixtures; synthetic
      fixtures remain `SYNTHETIC-ONLY-` and non-Luhn.
- [ ] Living artifacts updated in the same change.

---

## 13. Instructions for Codex

**Before you start:** work on `agent/luna-final-integration` @ `7787548`. There is
no branch question — see the note at the top of this report. An early reading of
`git branch` said `main` @ `24f8122`, but that HEAD was stale: the tree I read and
the app I exercised were `7787548` throughout (verified by file contents, not by
`git branch`). Every line number below is against `7787548`.

### Implement now (in this order)

1. **WP-1 truthful projection** — `candidates/router.py:487-610`. Three defects:
   suppress `not_claimed`-contradicted derived values; coerce numeric strings
   before `_consumer_label` (this is the `"0.5"` → `"0 5"` bug at `:512-513`
   reaching `:495-499`); replace `sorted()`-then-`[0]` headline selection with a
   per-benefit-type priority. Delete the dead `_consumer_number` at `:502-503`.
   **Nothing else ships until this is green.**
2. **WP-2 unified benefit index** — per Hari's decision, locally-reviewed benefits
   go live in Benefits, Which card? and Compare, each carrying a **"Check before
   use"** chip. Keep `local-live` distinct from `publishable`; publication still
   requires the `AGENTS.md` rule-5 gate.
3. **WP-3 lifecycle-aware ownership** — `app.js:138-145` and `:290`. An archived
   card must never be described as active.
4. **WP-4 owned-first IA** — Benefits defaults to the user's own cards. Remove the
   72-tile catalog dump from Today. Move `#benefitOwnedOnly` out of
   `.contributor-only` (`index.html:197`).
5. **WP-5 consumer language** and **WP-6 faceted search** — together these are
   what Hari actually asked for.
6. **WP-7 card recognition**, then **WP-8 Which card?**, **WP-10 Compare**,
   **WP-13 mobile/state**.

### Retain as designed — do not touch

- The five-item consumer nav and the Contributor-mode toggle. Verified clean.
- The provenance chip and the evidence/as-of model.
- The Tata rule's `not_claimed` discipline — this is the reference standard for
  every future claim.
- Accessibility: focus management, live regions, skip link, reduced motion, the
  light-theme palette. Do not regress these while restyling.
- The Family Finance import boundary (server-side picker, counts-only to browser).
- The refusal to produce a single composite comparison score.
- Loopback bind, CSRF, `no-store`, fresh-passphrase reauth on protected mutations.

### Remove or hide

- The hardcoded `renderPurchaseLimitation()` stub (`app.js:2623-2633`).
- The badge string "Activated locally for your review" (`app.js:634`).
- "Add this card" on offerings the user already owns (`app.js:683-686`).
- The duplicate unqualified Tata lounge library entry (P2-1).
- Any "Common question" shortcut you do not implement (P1-10) — do not leave a
  button that cannot answer.
- Machine field paths and operators from all consumer copy; if a field has no
  consumer label, render it in contributor mode only.

### Defer

- WP-11 value/cap model and WP-12 guest dimension — both are real product needs
  from Hari's interview, but both are schema-level and should follow the IA work.
- WP-14 content expansion — content, not code; ordered by owned-card frequency.
- PWA / phone-at-the-counter access. Note the tension: loopback-only bind plus
  gateway friction makes the app's most important moment its most awkward. Worth a
  decision, not worth blocking release.

### Requires Hari's local action or approval

- **Last-4 digits.** All 80 records show "Last four unavailable". Card recognition
  (WP-7) is limited until Hari fills these in locally. Design the card component
  to look correct without them.
- **WP-9 reveal/clipboard design note.** Plaintext to the browser is the one place
  this build's security posture materially changes. Needs Hari's explicit approval
  of the reauth model, the auto-clear duration, and the audit behaviour — and a
  counterpart review before implementation. Never ask Hari to type a password into
  a chat; only into the local UI.
- **Content approval** for anything promoted from `check_before_use` to `checked`.
  Agents propose; Hari approves. Unchanged.
- **Branch reconciliation** and any publication/push — separate gates, unchanged.

### Standing rules for this work

- No decrypted vault value ever reaches an agent, a log, a screenshot, a prompt, or
  a tracked file.
- Do not report a feature complete because tests pass. Every package above has a
  rendered acceptance line in §12; exercise it in the served app on desktop and
  mobile, both themes, with the keyboard.
- Separate content gaps from software bugs in every status update. "0 benefits on
  this card" is coverage, not rendering.
- Update the living artifacts in the same change. Note `CONTINUE-HERE.md` still
  describes the Family Finance import and the Today view — both are now removed.

### Repos, branch, and execution order

**Repos.** Primary: `<repo>` on
`agent/luna-final-integration` @ `7787548`. Secondary:
`<family-finance-repo>` on `main` — Family Finance removal
only; its integration surface includes `mycard_export.py` and
`docs/MYCARD-BENEFITS.md`, plus the companion button, pairing endpoint and
card-export path (grep `mycard`, `companion`, `pairing`; exclude `.venv`). Touch
no other directory. No worktrees. Local commits within scope only — **no push, no
publication**, those are separately gated.

**There is no branch discrepancy to investigate.** An early `git branch` reading
said `main` @ `24f8122`; that HEAD was stale and `main` is an ancestor missing ~20
feature commits. Verified by file contents. Work on `7787548`.

**Five stages. Stop and report after each — do not do all five silently.** Each
report: what changed, diff summary, and acceptance results measured against the
served app at `127.0.0.1:8777`.

1. **The three truth defects** — `candidates/router.py:487-610`. Decimal
   corruption, fabricated entitlement, alphabetical headlines, plus the dead
   `_consumer_number`. Nothing else ships until these are green.
2. **Removals** — Family Finance out of both repos; Today view out; private card
   vault wiped to clean first-run state (public catalog untouched).
3. **New auth model** — no credential on first run, cards unlocked by default,
   credential gates full-detail reveal only, set on first reveal, PIN (6+ digits)
   or passphrase, Argon2id + throttling + lockout, current-credential required to
   change. Write the security design note **before** coding it.
4. **IA rework** — My Cards (sortable/filterable), Benefits by category with owned
   first, one unified search. Move `#benefitOwnedOnly` out of `.contributor-only`.
5. **Everything else** — consumer language map, dead-end removal, Which card? and
   Compare over the unified index, mobile fixes.

### Kickoff

From the Codex app or an interactive `codex` session in
`<projects-root>`:

> Read `mycard-benefits/docs/CLAUDE-FINAL-PRODUCT-REVIEW-2026-08-10.md` — Section 0
> (ADDENDUM) first, it overrides anything later that conflicts, then Section 13 for
> repos, branch and execution order, then the rest for the verified defect list with
> exact file:line citations. Implement it in the five stages listed, stopping to
> report after each.
