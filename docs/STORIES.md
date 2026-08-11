# User stories and acceptance criteria

Scope and staging references: `docs/REBUILD-BRIEF-2026-08-10.md` and
`docs/CLAUDE-FINAL-PRODUCT-REVIEW-2026-08-10.md` (verified defects, with
`file:line` citations).

Visual specification: **https://claude.ai/code/artifact/3e3d9358-9fed-42a1-92b7-6a90eceb89d7**

Written to be executed hands-off. Every acceptance criterion is checkable against
the served app at `127.0.0.1:8777` or by a test. "Works on my machine" and "tests
pass" are not evidence — the app must be exercised rendered, on desktop and
mobile, in both themes, with the keyboard.

**Global rule for every story below:** if the app does not know something, it says
so. It never guesses, never rounds a condition away, and never states a number the
source does not support.

---

## Epic A — Onboarding: get a real wallet in

### A1 · Add many cards in one pass
**As** someone who owns 20+ cards, **I want** to tick the ones I hold and add them
together, **so that** setup is one action rather than eighty.

- [ ] Landing on an empty vault shows "Add your cards", not a dashboard of zeros.
- [ ] Issuer chips filter the 72 products; multiple issuers can be active at once.
- [ ] Products are multi-select; a single submit creates every ticked card.
- [ ] The submit button states the count: "Add 5 cards".
- [ ] **No credential is requested anywhere in this flow.** The vault is created
      unlocked.
- [ ] Skipping entirely is allowed and lands on a browsable catalog.
- [ ] Adding 20 cards takes one submit and completes in under 2 seconds.

### A2 · Optional identifying details
**As** someone with two cards of the same product, **I want** to add the last four
digits, **so that** I can tell them apart later.

- [ ] Last-4 is prompted *after* cards are added, as an optional follow-up list.
- [ ] It is never required, and never blocks completion.
- [ ] A card with no last-4 renders an "Add last 4" affordance — **never** the
      string "Last four unavailable", which the previous build showed on all 80
      records.
- [ ] PAN, CVV, PIN, expiry and nickname are all optional, behind a disclosure.

---

## Epic B — My Cards: recognisable at a glance

### B1 · Cards look like cards
**As** a returning user, **I want** to recognise my card instantly, **so that** I
don't have to read 80 near-identical rows.

- [ ] Each card renders at `aspect-ratio: 1.586` with issuer colourway, network
      mark, lifecycle pip and product name.
- [ ] The colourway is **generated from the issuer id**, so an unknown issuer gets
      a stable distinct colour with no code change.
- [ ] Two cards from different issuers are distinguishable with all text hidden.
- [ ] Last-4 renders in a tabular monospace face when present.
- [ ] The face shows a benefit count, including the honest **"No benefits
      recorded"** — a content gap, not an error state.
- [ ] Archived cards desaturate and sort last, labelled "kept for history".

### B2 · Sort and filter by many aspects
**As** someone with a large wallet, **I want** to narrow by what I care about,
**so that** I can find a card by any attribute I remember.

- [ ] Filters: lifecycle, card type (credit / debit / prepaid / membership),
      issuer, network, and "has benefits in category X".
- [ ] Free-text search matches product name, issuer, network and nickname.
- [ ] Filters combine, and the result count is always visible.
- [ ] **Every filter is a primary control.** None sits behind a mode toggle — the
      previous build buried `#benefitOwnedOnly` inside `.contributor-only`.
- [ ] The header states active / archived / with-benefits counts separately, never
      one conflated "80 cards ready".

### B3 · Card detail
- [ ] Opening a card lists its benefits grouped by category, each with a state chip.
- [ ] Lifecycle, added date and updated date are shown; exact expiry is not shown
      unless revealed under Epic E.
- [ ] A card with no benefits says the research is missing and offers the official
      issuer page — it does not imply the card has no benefits.

---

## Epic C — Benefits: by category, mine first

### C1 · Category browsing
**As** someone deciding what to use, **I want** benefits grouped by category with
mine first, **so that** I can scan the thing I actually own.

- [ ] Groups: lounge, movie, dining, rewards, cashback, vouchers, fuel, forex,
      insurance, meet-and-greet.
- [ ] Within each group, benefits on owned cards come first, visually separated
      from the rest of the catalog.
- [ ] A scope control switches "My cards" ↔ "All 72 cards" and is always visible.
- [ ] **Never one flat alphabetical list.** The previous build rendered all 72
      offering tiles flat on the home screen; that is the pattern being rejected.

### C2 · Every claim carries its evidence
- [ ] Every benefit row, everywhere in the app, shows exactly one state chip:
      **Verified** / **Check before use** / **Sources differ**.
- [ ] Every row shows an as-of date and a link to the official source.
- [ ] The word "Activated" never appears — it reads as "switched on".
- [ ] All three states are live and usable in search, filtering and detail. This is
      the owner's explicit decision: *"I want them to be live right away; if I see a
      mistake I will tell the agent to fix it."*
- [ ] Source links are ≥44px tall on mobile.

### C3 · Honest values
- [ ] The headline value is chosen by a **per-category priority order**, never
      `sorted(allowance)[0]`. Lounge leads with visits/vouchers; rewards with the
      earn rate; fees with the amount.
- [ ] Decimals survive: `5%`, `0.5 airmiles per point`, `$3.25`. A rendered value
      matching `/\d+ \d+/` is a test failure.
- [ ] A derived figure the source does not promise is either suppressed or
      qualified in the same sentence — e.g. *"Up to 8 vouchers per year — only if
      you qualify in all four quarters"*, never a bare "8 vouchers per year".
- [ ] No consumer-visible text contains a machine field path, `gte`/`lte`/`equals`,
      or a bare `snake_case` token. If a field has no consumer label, it does not
      render.

---

## Epic D — Search: one box, both axes

### D1 · Search everything
**As** someone with a specific need, **I want** one search across my cards and the
catalog, **so that** I can ask "movie ticket discount" and get an answer.

- [ ] One input searches benefit titles, categories, merchants, conditions and
      claim routes.
- [ ] Scope toggle: "My cards" / "Everything". Result counts shown for both.
- [ ] Filters: category, merchant, value or cap, condition type, claim route, state.
- [ ] Results are ranked with owned-card matches first.

### D2 · Feature detail on every result
- [ ] Selecting a result answers, in plain language: **most you get · to qualify ·
      how to claim · guests · evidence**.
- [ ] The source's `not_claimed` list renders under a **"This is not claimed"**
      heading. This is the product's spine.
- [ ] Evidence shows the source, retrieval date and that a content hash is recorded.

### D3 · Honest emptiness
**As** someone asking about meet-and-greet, **I want** to know whether the answer
is "your cards don't have it" or "nobody has looked yet", **so that** I don't
wrongly conclude I have no benefit.

- [ ] Those two cases produce **different** messages. The previous build collapsed
      both into "No matching benefit found."
- [ ] "Not researched" states that research is missing, not that the benefit is absent.
- [ ] Every empty state offers one next action.
- [ ] **No control exists that cannot succeed.** The previous build shipped a
      purchase form that always answered "not available yet" and seven shortcut
      buttons that always returned "no match". If it cannot answer, it is not built.

---

## Epic E — Full details: the only locked door

### E1 · No credential until the first reveal
**As** a new user, **I want** to use the whole app without a password, **so that**
nothing blocks me on day one.

- [ ] A fresh clone opens with cards unlocked. Browsing, sorting, filtering, search
      and benefit detail all work with **no credential at all**.
- [ ] **No default credential ships in the repository.** A grep of the tree for a
      hardcoded default is part of the release check.
- [ ] There is no lock/unlock state anywhere in the UI outside Epic E.

### E2 · Create once, reuse after
- [ ] The first attempt to reveal a full card number, CVV, PIN or exact expiry
      prompts the user to create a code, inline, in one step.
- [ ] The user chooses **6-digit PIN or passphrase**.
- [ ] Argon2id at high cost; escalating delay and lockout on repeated failure.
- [ ] Every subsequent reveal asks for that code and nothing more.
- [ ] Changing it requires the current one.
- [ ] Copy is explained honestly: if lost, card details are unrecoverable and the
      rest of the app keeps working.

### E3 · Reveal and copy safely
- [ ] Revealed values re-hide on a timer, and on tab blur.
- [ ] Copy to clipboard auto-clears, with the countdown visible to the user.
- [ ] Plaintext never reaches a log, a tracked file, an agent prompt, or a
      screenshot.
- [ ] A security design note covering the reauth model, auto-clear duration and
      audit behaviour is written **before** this epic is implemented.

---

## Epic F — Removals and integrity (cross-cutting)

- [ ] `research/`, `candidates/`, `agents/`, `sources/`, `qa/`, `optimizer/`,
      `lifecycle/` are gone, along with their routers and tests.
- [ ] Contributor mode, Updates, Sources, Research Queue, Local reminders and route
      diagnostics are gone.
- [ ] The Today view is gone.
- [ ] All private card records are wiped; the public catalog is intact.
- [ ] The 60 deduplicated benefit records from 61 source references and 30
      distinct source URLs survive in `catalog/benefits/*.json`.
- [ ] No dead imports, dead routes or stale docs. `AGENTS.md`, `PROJECT_STATUS.md`,
      `TASKS.md`, `DECISIONS.md` and `CONTINUE-HERE.md` describe the app that now
      exists.

---

## Definition of done — every story

- [ ] `uv run --no-sync ruff check .`, `uv run --no-sync pytest`,
      `uv run --no-sync mypy src` pass. (Plain `uv run` fails while the app is
      served — it holds the venv executable.)
- [ ] Exercised rendered at 320 / 375 / 768 / 1280px. No horizontal overflow at any
      width; `scrollWidth <= clientWidth`.
- [ ] Zero WCAG AA contrast failures in **both** themes.
- [ ] Full keyboard traversal; focus moves to the view heading on navigation; no
      focusable elements inside hidden views.
- [ ] Touch targets ≥44px, especially official-source links.
- [ ] Empty, loading and error states all verified.
- [ ] App binds to `127.0.0.1` only.
- [ ] No real card data in any tracked file; synthetic fixtures stay
      `SYNTHETIC-ONLY-` and non-Luhn.

## The seven regressions

Verified in the previous build. Each is easy to recreate by accident.

| Never | What happened before |
| --- | --- |
| Invent an entitlement | Rendered "8 vouchers per year" while that rule's `not_claimed` rejected exactly that |
| Mangle a number | `"0.5"` printed as `0 5` — readable as 5, a tenfold overstatement |
| Call archived "active" | Said "an active local card matches" about an archived card |
| Leak machine language | `calendar_quarter.eligible_net_posted_spend_inr gte 50000`, `Cap: 2` |
| Pick a headline alphabetically | Lounge led with "Claim within 120 days" instead of the voucher count |
| Ship a control that can't work | A purchase form that always answered "not available yet" |
| Claim a remaining count | Implied visits remained when usage was never tracked |
