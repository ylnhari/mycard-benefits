# Tasks

Manager protocol: a worker owns only its named scope; the manager validates
evidence before advancing; no worker may push unless the task explicitly
authorizes it. Every task is grounded in `PRODUCT_REQUIREMENTS.md`,
`docs/QUESTIONNAIRE-DECISIONS.md`, `docs/IDEA-LOG.md`, `DECISIONS.md`,
`PROJECT_STATUS.md`, and `ROADMAP.md`. Superseded worker briefs and reviews stay
in Git history. Private records are never referenced, and acceptance criteria
name objective evidence only.

## Final release ledger — 2026-08-10

This register has 221 unique task rows: 165 technically checked, 18 active or
reopened by owner user testing, 20 deliberately owner-blocked, 8 externally
blocked, and 10 deliberately deferred beyond v1. The checked rows include the
integrated technical baseline and completed release-closing analysis; they do
not mean that the consumer product has passed acceptance. Owner testing on
2026-08-10 reopened the failed journeys below even though automated gates had
passed. Checked status is not approval to activate, publish, or push.

| Disposition | Rows | Meaning |
| --- | ---: | --- |
| `CHECKED` | 165 | Integrated technical work whose stated acceptance remains supported. |
| `ACTIVE_OR_REOPENED` | 18 | Six consumer-redesign tasks plus twelve earlier tasks reopened by owner testing. |
| `BLOCKED_OWNER` | 20 | Requires an exact owner decision or owner-confirmed private mapping/coverage. |
| `BLOCKED_EXTERNAL` | 8 | Requires an external counterpart, provider, or separately gated integration. |
| `DEFERRED_POST_V1` | 10 | Deliberately deferred beyond v1. |

The explicit IDs are authoritative: 165 checked rows plus 56 unchecked rows
account for all 221 tasks. MC-033 is the core one-use
authorization, not a browser plaintext-reveal feature. MC-034 and MC-035 remain
blocked. MC-211 and MC-212 require owner-confirmed real offering mappings and
coverage. Live adapters/provider execution and publication remain blocked. The
catalog contains one owner-approved Tata Neu Infinity domestic lounge rule;
all other identities and review candidates remain non-active until approved.

## Active

### Consumer redesign — reopened by owner testing on 2026-08-10

Automated and synthetic gates proved many underlying mechanisms, but the live
walkthrough did not pass consumer acceptance. The redesign must make the first
useful result obvious, keep maintainer machinery out of normal navigation, and
be validated as a product rather than as a collection of routes.

- [ ] **MC-217: Replace the maintainer-first information architecture with consumer navigation** [ACTIVE] - Default navigation must focus on Home, My Cards, Benefits, Ask, Compare, and Settings. Sources, Updates, Research Queue, candidate review, provenance operations, and other maintainer tools must be absent unless an explicit Maintainer mode is enabled.
  - Acceptance: a normal first-run user never sees research or release-governance surfaces; a maintainer can deliberately enable the separate area; direct routes remain protected; desktop/mobile navigation is verified.
  - Evidence: owner walkthrough on 2026-08-10 and `docs/DESIGN-REVIEW-2026-08.md`; adopt consumer job patterns without copying proprietary UI or text.
  - Progress: owned conditional benefits now appear on Today only after local card access is available, with a visible requirement and a direct "Check eligibility and terms" action; the UI never invents a remaining-use count.
  - Depends on: MC-042, MC-091
  - Suggested runner: Luna implementation, Terra independent review

- [ ] **MC-218: Deliver first-run My Cards device-held bootstrap, reveal credential, and recovery** [ACTIVE] - Replace "Vault unavailable" and imported-card assumptions with silent local-storage bootstrap, safe wrong-data-directory diagnosis, and one clear "Add my first card" action. On first use the app generates and stores a device-held key through the OS-keyring boundary, with the guarded ignored local fallback when keyring support is unavailable.
  - Acceptance: a blank device silently creates and opens an empty vault without a credential form; an existing device-held vault opens without a prompt; passphrase-only or wrong-data-directory states explain what happened without exposing a key; no password/key is stored in browser storage, source, logs, or API responses; the owner can add a card without CLI knowledge; full PAN/CVV/PIN reveal remains behind the separate first-reveal credential flow.
  - Progress: the default setup/unlock/sidebar controls and card-management password fields are removed, device-held card actions use the existing encrypted vault reauthentication path and now reuse the active browser session after first-run bootstrap, and fresh served-page verification shows an empty My Cards state with no console errors. First-reveal UI and legacy passphrase-only recovery remain open; served owner acceptance remains under MC-222.
  - Progress: reveal implementation is blocked on the existing route contract: it accepts only an existing 12-character-or-longer vault passphrase and currently returns 410 without a token or plaintext. No client-only or parallel path was added.
  - Progress: onboarding now multi-selects catalog products through one `Add N cards` submit with an optional post-add last-4 follow-up; the synthetic batch harness covers three additions alongside eighteen existing summaries without sending a credential.
  - Depends on: MC-001, MC-007, MC-009, MC-028
  - Suggested runner: Luna implementation, Terra security and UX review

- [ ] **MC-219: Make every catalog card useful and comparison meaningful** [ACTIVE] - Every public card tile opens a plain-language product detail with known benefits, official terms, and an "Add this card" action. Compare must use aligned category rows and must not present two empty cards as a useful comparison.
  - Acceptance: catalog tiles are keyboard/click/touch operable; detail routes work; zero-data comparisons are prevented with a helpful next action; populated comparison remains aligned on desktop/mobile and shows differences by category and condition.
  - Progress: benefit cards/details now lead with what the user gets, conditional state, requirement, usage route, and official source; technical rule/evidence data is collapsed. Which Card no longer falls back to an unrelated result and gives owned matches priority.
  - Progress: exact-product public candidate hints now appear only inside the relevant card/benefit detail, cached per product and labelled “Being verified”; they never enter active benefits, Today, rankings, or Compare. Compare defaults to two mapped owned products when available and prevents the same card being compared with itself.
  - Progress: the owner-approved local review library now exposes all 61 seeded public benefit references in the Benefits screen. One remains the reviewed active Tata rule; 55 are visibly activated only for local owner review with official-term links, and five source conflicts are labelled separately. These items are never used for Compare, Which Card, purchase ranking, or recommendations.
  - Progress: the public catalog browser now renders all 72 offerings without private storage, filters by issuer and network, and opens shared cardface-style product details with the three consumer benefit states.
  - Depends on: MC-002, MC-039, MC-046
  - Suggested runner: Luna implementation, Terra independent review

- [ ] **MC-220: Reframe Ask, Planner, and Travel around plain-language user jobs** [ACTIVE] - Ask must answer questions about owned-card benefits, purchase guidance must start with merchant/category/amount, and Travel must start with a destination/airport/date use case. Hide any workflow that cannot produce a useful result.
  - Acceptance: each visible workflow states what the user can do, starts with a concrete input or example, and ends in an actionable result with conditions and an official source; internal terms such as offering, candidate, and workflow are absent from normal copy.
  - Progress: Travel is hidden from the normal Benefits screen unless an active reviewed travel rule exists; candidate-only or empty travel workflow machinery is no longer a consumer destination.
  - Depends on: MC-068, MC-099, MC-194, MC-195
  - Suggested runner: Luna implementation, Terra product review

- [ ] **MC-221: Move trust, privacy, and financial education into contextual progressive disclosure** [ACTIVE] - Remove governance lectures and generic EMI/utilization/business-use warnings from Home and My Cards. Keep concise protection, condition, and risk information beside the action or benefit it affects, with details available on demand.
  - Acceptance: Home has no release-state, candidate-state, imported-record, or general-education essay; My Cards has a short expandable "How your data is protected" explanation; relevant benefit and purchase-result screens retain accurate conditions and warnings.
  - Progress: My Cards now uses a short consumer explanation with privacy details collapsed; lifecycle/private-progress tools are secondary disclosures rather than the first product surface.
  - Progress: Today now shows one useful saved-card summary. It uses only the vault’s coarse expired/expiring-soon signal and never displays exact expiry, invented allowance use, or synthetic “Unknown” metrics.
  - Depends on: MC-080, MC-141
  - Suggested runner: Luna implementation, Terra UX-copy review

- [ ] **MC-222: Pass a real consumer acceptance gate before calling the product ready** [ACTIVE] - Validate the exact served application through first-run, add-first-card, unlock-owned-card, browse-card-detail, benefit search, Ask, Compare, and no-benefit recovery journeys.
  - Acceptance: owner-visible desktop/mobile walkthrough evidence covers blank, locked, populated, and no-benefit states; each top-level screen has a clear job and successful path; no inert controls, misleading completion copy, raw maintainer surface, or broken alignment remains; one final full suite runs only after focused UI gates pass.
  - Progress: the latest connected-browser slice verified three category counts against rendered rows, all 72 public offerings, public product detail states, both themes, 320/375/414 widths, target sizes, and a clean console. The owner-only live scope was not rechecked because its private endpoint was unavailable in that session.
  - Depends on: MC-217, MC-218, MC-219, MC-220, MC-221
  - Suggested runner: Luna focused tests, Terra independent rendered review, Sol final acceptance decision

### Broken user experience — first

- [ ] **MC-001: Make the owned-card list clearly visible and useful** [REOPENED_USER_TEST] - After setup or unlock, My Cards must immediately show every owned card as readable rows (catalog product, bank, network, status, record dates) with no secret values and no ambiguous placeholder text.
  - Acceptance: rendered list verified desktop/mobile and dark/light with populated, empty, and vault-unavailable states; search and status filter return correct subsets; response remains `no-store` and contains only envelope fields per `PROJECT_STATUS.md` "Next planned slice".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-002: Add a useful card detail view reachable from My Cards** [REOPENED_USER_TEST] - Selecting an owned card opens a consumer-readable detail panel showing the product, benefits, lifecycle state, record dates, and any replacement link without revealing secrets.
  - Acceptance: each row navigates to a detail view; envelope-only fields verified; keyboard reachable; covered by `tests/test_private_cards_api.py` and UI tests; no secret field appears in the response.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [x] **MC-003: Remove production-visible synthetic example.invalid links** - The catalog and dashboard must never render synthetic/example `.invalid` links or synthetic-only URLs in non-demo production views.
  - Acceptance: grep of rendered production catalog views finds no `example.invalid` or synthetic host; a test asserts public catalog records carry only real or explicitly-absent URLs; demo content is labeled demo only.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-004: Decouple MyCard from the personal Rover launcher while keeping loopback-only safety** - Remove any session or sign-in coupling to the personal launcher so MyCard is self-contained and remains loopback-bound; the launcher stays an optional external tool.
  - Acceptance: no launcher cookie/session is required or consumed by the app; startup test proves default bind is `127.0.0.1` and cannot widen to `0.0.0.0`; running the app without the launcher works fully; external-tool configuration stays outside the app per `AGENTS.md` boundary 7.
  - Depends on: none
  - Suggested runner: Antigravity

- [x] **MC-005: Keep MyCard wording neutral and launcher-free** - MyCard's own UI and docs must carry only neutral MyCard-local branding. Rover is the owner's personal external start-stop/mobile-access launcher, not part of MyCard and not an external-dashboard identity; remove Rover-branded and old-dashboard-branded sign-in language from user-facing templates, API error text, README, and guide so MyCard reads as self-contained.
  - Acceptance: grep of templates, static assets, README, and guide finds no Rover sign-in or old-dashboard wording in active MyCard surfaces; rendered states use neutral MyCard-local copy; historical coordination evidence (`coordination/events.jsonl`) stays historical; docs updated in the same change.
  - Depends on: MC-004
  - Suggested runner: OpenCode

- [x] **MC-177: Document and verify MyCard is self-contained and launcher-independent** - MyCard's app, UI, and docs state that it binds loopback-only and that any personal external launcher (including the owner's Rover) is an optional start-stop/mobile-access tool, never a MyCard dependency, identity, or configuration requirement.
  - Acceptance: README, user guide, and app copy keep any external launcher optional and separate, with no launcher secret, identity, or config in MyCard source, browser storage, or docs; loopback-only startup test passes.
  - Depends on: MC-004, MC-005
  - Suggested runner: OpenCode

- [x] **MC-006: Render unmatched offering identifiers as a clear state, never a bare slug dump** - Cards whose offering id has no catalog slug must show a labeled "unmatched variant" state with guidance, not raw identifiers.
  - Acceptance: unmatched rows display explanatory text and a documented path (fix import or request a variant) per `docs/USER-GUIDE.md` section 6; UI test covers the unmatched state.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [ ] **MC-007: Support passphrase-only vaults in the browser My Cards view** [REOPENED_USER_TEST] - The browser must not stop at "Vault unavailable"; provide a supported setup/unlock/recovery flow with one clear next action.
  - Acceptance: passphrase-only vault is either unlockable via a protected local prompt or clearly documented with the CLI path; no secret crosses the HTTP boundary in plaintext; guide section 6 updated; test covers the unavailable state honestly.
  - Depends on: MC-001, MC-038
  - Suggested runner: Manager

- [x] **MC-008: Resolve the --demo versus real-data surprise for My Cards** - Starting with `--demo` must not silently show the wrong data folder; the UI and guide must make the demo/real boundary obvious.
  - Acceptance: demo runs display a persistent demo banner and point at `demo-data`; guide explains the boundary (`docs/USER-GUIDE.md` section 3); UI test asserts demo vs non-demo data folders differ.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [ ] **MC-009: Explain and recover from every unavailable vault state** [REOPENED_USER_TEST] - My Cards must tell the user which known cause applies (demo mode, no vault, locked vault, passphrase-only, wrong data directory) and provide a working in-product fix or setup action.
  - Acceptance: each unavailable cause maps to a distinct rendered message and fix step per `docs/USER-GUIDE.md` section 12; covered by UI tests.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [x] **MC-207: Inventory the usable agent/model routes and document low-cost session reuse** - Verify which models the Codex parent session can select, which model overrides its sub-agent API actually accepts, and which authenticated Claude, OpenCode, Gemini CLI, and Antigravity routes can resume an existing session without creating a second history.
  - Acceptance: `AGENTS.md` and `docs/AGENT-OPERATIONS.md` record verified routing rules without account identifiers, credentials, quotas, private data, or speculative model claims; CLI reuse requires an exact verified session id, checkout, model, and permission scope.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-209: Publish the post-project agentic-system and model benchmark** - After every implementation branch is integrated/rejected and temporary worktrees/artifacts are cleaned, produce an evidence-based benchmark and routing guide for Codex Sol/Terra/Luna, Claude models and retained sessions, OpenCode free routes, and Google Antigravity/Gemini. Compare correctness, architecture judgment, implementation quality, review defect discovery, browser/tool use, session retention, setup/permission friction, latency, token/quota use, retry/rework cost, and total cost-to-accepted-change. Recommend when to use CLI, a retained interactive app session, or app control, prioritizing token efficiency without choosing a model whose rework makes it more expensive.
  - Acceptance: a dated snapshot report plus a concise living routing guide; every rating cites project commits/reviews/gates or is labeled observational; model identity is runtime-verified and never inferred from task names; failed/self-verified work is not counted as accepted; no account IDs, credentials, private data, raw transcripts, machine paths, or unsupported price/quota claims; a different capable model reviews the final report.
  - Depends on: completion/rejection reconciliation of all active branches, release-candidate cleanup, and final task/evidence reconciliation.
  - Suggested runner: Luna for evidence collection, Terra for counterpart review, Sol for final routing decision

- [x] **MC-210: Audit whether multi-agent delegation actually saved premium tokens and total effort** - After cleanup and MC-209 evidence collection, measure the full coordination cost of using Codex subagents, local Luna CLI workers, Claude, OpenCode, and Antigravity: task briefs, worktrees, monitor/polling output, session reconstruction, README/result artifacts, merge conflicts, independent reviews, blocked branches, duplicated implementation, retries, and final integration. Compare accepted-change output, elapsed time, paid/premium model usage, free-tier usage, and rework against a transparent Sol-only/direct-implementation counterfactual range; conclude whether this project saved or spent more Codex tokens and which orchestration patterns should be retained or removed.
  - Acceptance: use runtime usage receipts/logs where available; separate cached input, uncached input, output, and unverifiable usage; distinguish subscription marginal cost from token volume; count only reviewed/integrated output as benefit; quantify duplicate/rejected work; state uncertainty and avoid false precision; include break-even guidance for when delegation is worthwhile; independent review by a different capable model.
  - Depends on: MC-209, final branch disposition, cleanup, and release-candidate reconciliation.
  - Suggested runner: Luna for ledger extraction, Terra for methodology review, Sol for the final counterfactual judgment

- [ ] **MC-211: Build complete source-backed benefit coverage for every locally held card variant** [BLOCKED_OWNER] - Resolve each private card envelope to a canonical public offering without exposing owner, last-four, expiry, or ownership to a model; then research and catalogue every discoverable benefit for that public variant, including rare one-card benefits and all applicable issuer, network, co-brand, merchant, membership, and portal layers. Aggregators such as CardExpert or SaveSage are discovery leads only; verified facts require the most authoritative official source available.
  - Acceptance: each locally held canonical offering has a coverage ledger by benefit category and source document; every assertion has structured conditions, exclusions, caps, effective dates, claim/use steps, official links, provenance/hash/retrieval time, owner party, review state, and conflicts; absent/blocked/unknown categories remain explicit; no candidate auto-activates; source agents receive only one public offering identifier at a time and never receive the private ownership list; human review gates remain enforced.
  - Depends on: MC-053 through MC-071, MC-083 through MC-097, MC-111 through MC-120, and reviewed Nine Router integration.
  - Suggested runner: Luna/9Router Gemini for bounded public extraction, Terra for sampled source review, human approval for activation

- [ ] **MC-212: Deliver card-wise and benefit-wise search, filtering, and detail views** [BLOCKED_OWNER] - Let a user browse one held card and see all known benefits, or search/filter across cards by free text and structured dimensions such as movie, BookMyShow, ticket credit, merchant, category, bank, network, status, date, cap, spend condition, and claim channel. Queries such as “₹600 off one ticket” must return the exact matching rule when supported, not a generic movie category.
  - Acceptance: locally held eligible cards appear first using a server-side safe join on canonical offering ID; other public alternatives are visibly separate; needs-review/conflicting/expired/personalized states never appear as verified eligibility; every result opens a detail view with what/how/where/conditions/exclusions/caps/dates/status/last verification/official links; empty and unique-one-card results are useful; keyboard/mobile/light/dark/rendered tests pass; no raw private card values reach catalog/search/model APIs.
  - Depends on: MC-039, MC-040, MC-043, MC-044, MC-046, MC-065, MC-075, MC-076, MC-200, and MC-211.
  - Suggested runner: Luna implementation, Terra review, Sol product/integration decision

- [ ] **MC-213: Integrate governed 9Router/Gemini public-web extraction** [BLOCKED_EXTERNAL] - Fetch only admitted official public sources under source-specific cadence, retain restricted raw evidence locally, and send only bounded redacted public text plus a typed extraction contract to the local 9Router Gemini route. Cache by content hash, use daily request/token budgets, record runtime model identity, and create immutable `needs_review` candidates with no implicit provider fallback.
  - Acceptance: disabled by default; exact loopback endpoint/model/budget must be configured and separately approved for a live run; direct source fetch enforces robots/access/rate/cadence policy before transport; credentials/query tokens/private fields never enter prompts/logs/artifacts; strict response validation and hostile tests fail closed; retries are bounded and do not duplicate candidates; dashboard shows last run/next run/failures/quota/candidate counts; an offline fixture path and one separately gated public smoke path are both verified.
  - Depends on: MC-089, MC-094, MC-111 through MC-120, and independently approved Nine Router adapter.
  - Suggested runner: verified Luna CLI for implementation, 9Router Gemini for admitted public extraction, Terra for security/source-policy review

- [ ] **MC-214: Make every benefit and evidence assertion independently refreshable** [BLOCKED_EXTERNAL] - Ship per-source, per-benefit, per-offering, and due-only refresh planning/execution with durable cadence, conditional validators, budgets, immutable change history, review-required candidate drafting, dashboard status, and clone-safe operator instructions. Named examples never limit category coverage.
  - Acceptance: every catalog assertion resolves to a stable updater/source adapter or an explicit blocked/manual state; one-benefit, one-card-variant, source-wide, and due-only dry-run/execute commands are tested; unchanged/changed/304/disappeared/conflicting/blocked/restart/concurrent/budget-exhausted paths are deterministic; Gemini-derived fields cite admitted official evidence spans and remain `needs_review`; no private ownership or secret reaches fetch/provider state.
  - Depends on: MC-111 through MC-120, MC-211, MC-213, and approved source admissions.
  - Suggested runner: Luna implementation, 9Router Gemini extraction, Terra security/cadence review, human catalog approval

- [x] **MC-215: Unify the canonical benefit/evidence graph and promotable citations** - Use one versioned lossless schema across catalog, candidates, provider output, APIs, migrations, and release snapshots; retain exact admitted official-document spans for every model-derived field.
  - Acceptance: stable IDs link offering -> rule -> assertion -> source version -> observation -> span -> candidate; candidates round-trip every catalog field; span hashes/offsets/anchors/redaction/extraction versions revalidate before promotion; unsupported future versions and malformed/ambiguous spans fail closed; backward migration and forward-incompatibility tests pass.
  - Depends on: MC-053 through MC-071, MC-092, MC-094, MC-211, MC-213, MC-214.
  - Suggested runner: Luna implementation, Terra schema/security review, human promotion gate

- [x] **MC-216: Enforce effective-state projection and atomic human promotion** - Prevent stale/conflicted/expired/future/changed/disappeared/source-blocked/personalized-unknown rules from appearing usable, and promote reviewed candidates through one evidence-bound atomic transaction.
  - Acceptance: every consumer uses one deterministic as-of effective state; unresolved conflicts cannot be usable; promotion binds exact payload/evidence/source/span hashes, reviewer approvals, conflict/supersession records, coverage updates, compiled snapshot, audit and rollback receipt; any drift or partial write fails with no activation; agents/providers cannot approve or promote.
  - Depends on: MC-095 through MC-099, MC-211, MC-214, MC-215.
  - Suggested runner: Luna implementation, Terra adversarial review, human activation only

### Variant, lifecycle, expiry, replacement, and owner reconciliation

- [ ] **MC-010: Build the previewed owner/variant/lifecycle/replacement reconciliation workflow** [BLOCKED_OWNER] - Deliver the next delivery gate in `PROJECT_STATUS.md`: a human-confirmed reconciliation flow for owner, exact variant, expiry, lifecycle, and old-to-replacement relationships without secret-field reveal or direct browser writes.
  - Acceptance: previewed confirmation flow renders and is keyboard/screen-reader usable; confirmations persist as non-secret private metadata; no reveal or write of secret fields; tests cover confirmation, deferral, and rejection paths.
  - Depends on: MC-001
  - Suggested runner: Manager

- [ ] **MC-011: Confirm the seven unconfirmed imported card variants** [BLOCKED_OWNER] - Resolve every ambiguous product-variant match in the private inventory through the reconciliation flow instead of guessing.
  - Acceptance: each of the seven variants is either confirmed to a catalog offering or left as `unverified_match` with candidate variants per `docs/QUESTIONNAIRE-DECISIONS.md` item 15; confirmation state visible without secrets.
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-012: Map anonymous owner aliases to family roles** [BLOCKED_OWNER] - Assign the private owner aliases from the import to family roles through the confirmation flow.
  - Acceptance: each alias maps to a role or remains unmapped and visible as needing confirmation; no real person name or record content appears in tracked files; state persisted as non-secret metadata.
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-013: Assign the 49 unassigned imported records to owners** [BLOCKED_OWNER] - Let the owner attribute every currently unassigned card record to a mapped owner role.
  - Acceptance: after confirmation, zero records are unassigned or each remaining one is explicitly marked unresolved; counts verifiable without revealing secret fields.
  - Depends on: MC-012
  - Suggested runner: Manager

- [ ] **MC-014: Establish old-to-replacement relationships for imported records** [BLOCKED_OWNER] - Build replacement links between prior and current card instances through the confirmation flow.
  - Acceptance: replacement links are recorded as private lineage; linked instances show "replaced by/replaces" metadata in My Cards; history survives reissue per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-015: Reconcile the 60 archived imported records with true lifecycle state** [BLOCKED_OWNER] - Confirm whether each archived record is truly expired, closed, or still active so reminders and views are accurate.
  - Acceptance: each archived record resolves to a confirmed lifecycle state or remains explicitly pending confirmation; the UI never presents archived as expired.
  - Depends on: MC-010, MC-016
  - Suggested runner: Manager

- [x] **MC-016: Treat archived as distinct from expired in UI and reminders** - Change every surface so archived records are not assumed expired and never produce expiry reminders.
  - Acceptance: UI text and reminder logic distinguish archived from expired; test asserts archived records do not trigger expiry reminders; guide wording reflects the distinction per `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: MC-026
  - Suggested runner: OpenCode

- [ ] **MC-017: Confirm provisional active status of the 20 active records** [BLOCKED_OWNER] - Validate each provisionally-active imported record's lifecycle through the confirmation flow.
  - Acceptance: every provisional active record is confirmed, corrected, or explicitly marked unresolved; count-only verification unaffected.
  - Depends on: MC-010
  - Suggested runner: Manager

- [x] **MC-018: Support multiple instances of one offering per owner** - Allow one owner to hold several instances of the same offering as separate private card instances.
  - Acceptance: schema/API/UI accept and render duplicate-offering instances; each keeps a distinct private UUID per `docs/QUESTIONNAIRE-DECISIONS.md` item 16.
  - Depends on: MC-028
  - Suggested runner: OpenCode

- [x] **MC-019: Model primary, add-on, supplementary, physical, virtual, and tokenized instances as linked** - Represent every instance role as a separate linked card instance.
  - Acceptance: instance-role field exists with the enumerated roles and link relationships; verified in add/edit flows and My Cards metadata per item 17.
  - Depends on: MC-028, MC-029
  - Suggested runner: OpenCode

- [x] **MC-020: Preserve renewal, reissue, upgrade, downgrade, and network migration as immutable lineage** - Record each private lifecycle transition as immutable history joined by a private lineage identifier.
  - Acceptance: each transition creates an immutable history entry; lineage id links prior and successor instances; no rewrite of prior history per item 19.
  - Depends on: MC-031
  - Suggested runner: Manager

- [x] **MC-021: Add a reviewed relationship graph for renamed, legacy, cloned, and reskinned products** - Model public product relationships from a reviewed graph, never inferred from names alone.
  - Acceptance: catalog relationship entries are reviewed data with provenance; loader validates graph integrity; names never auto-infer inheritance per item 14.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-022: Store uncertain matches as unverified_match with candidate variants** - When a card cannot be mapped exactly, store the state as `unverified_match` and show candidate variants while withholding unsupported entitlements.
  - Acceptance: the state persists; candidates render; benefits for the uncertain match are not treated as active per item 15 and `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: MC-010
  - Suggested runner: OpenCode

- [x] **MC-023: Select exact network, co-brand, market, product generation, and benefit cohort** - Let a user pick the precise variant dimensions when they matter.
  - Acceptance: variant selection UI exposes network, co-brand, market, generation, and cohort when the offering declares them; selection stored on the instance per item 12.
  - Depends on: MC-028
  - Suggested runner: OpenCode

- [x] **MC-024: Model child records for Priority Pass, lounge credentials, memberships, vouchers, and associated card credentials** - Represent attached credentials as child records of the issuing card.
  - Acceptance: child-record model with parent linkage, expiry, and lifecycle; rendered in detail views without secrets per item 22.
  - Depends on: MC-002
  - Suggested runner: OpenCode

- [x] **MC-025: Make private expiry usable for reminders without exposing secrets** - Compute expiry-driven reminder signals server-side so the browser never receives an expiry value.
  - Acceptance: reminder API returns signals, not values; no expiry in any response; tests verify the vault-expiry boundary; Expiring Soon view uses only these signals.
  - Depends on: MC-041
  - Suggested runner: Manager

- [x] **MC-026: Support the full lifecycle state set in protected flows** - Add, edit, archive, and replace flows must support applied, pending, active, frozen, lost, stolen, expired, renewed, replaced, upgraded, downgraded, closed, and archived states.
  - Acceptance: every enumerated state is representable and transitions are validated; covered by API and UI tests per item 18.
  - Depends on: MC-028, MC-029
  - Suggested runner: OpenCode

- [x] **MC-027: Add explicit purge with typed confirmation and encrypted-backup warning** - Permanent deletion requires typed confirmation and a warning that encrypted backups may still hold the record.
  - Acceptance: purge requires typed text; confirmation text warns about encrypted backups; purge is logged without field values; tests cover the flow per item 20 and 21.
  - Depends on: MC-032
  - Suggested runner: Manager

### Protected write controls and secret reveal

- [ ] **MC-028: Add a protected consumer add-card flow** [REOPENED_USER_TEST] - Let a user search/select a card product, confirm the variant, create the private instance, and optionally add encrypted fields without exposing internal vault concepts.
  - Acceptance: add flow gated by reauthentication; offering selection, variant confirmation, and instance creation work; secret fields encrypted; no secret in any log/URL per item 90.
  - Depends on: MC-038
  - Suggested runner: Manager

- [x] **MC-029: Add a protected edit flow** - Edit non-secret and encrypted fields of a card instance through the protected UI.
  - Acceptance: edits persist through the vault API; immutable history unchanged; reauthentication enforced; edits logged without values per item 33.
  - Depends on: MC-038
  - Suggested runner: Manager

- [x] **MC-030: Add a protected archive, retire, close, and restore flow** - Move a card between archived, closed, retired, and active states without losing lineage.
  - Acceptance: transitions validated and persisted; restored records reappear; tests cover each transition per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: MC-029
  - Suggested runner: OpenCode

- [x] **MC-031: Add a protected replace flow** - Create a new immutable instance linked to the prior instance so history survives expiry, loss, or reissue.
  - Acceptance: replace creates a successor instance with lineage to the prior one; prior history untouched; UI surfaces the link per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: MC-020, MC-029
  - Suggested runner: Manager

- [x] **MC-032: Add a protected delete flow with typed confirmation** - Delete a card instance only with typed confirmation and the encrypted-backup warning.
  - Acceptance: delete requires typed confirmation; warning shown; action logged without values; tests cover confirm and cancel per item 21.
  - Depends on: MC-029
  - Suggested runner: Manager

- [x] **MC-033: Add a one-use reveal authorization for PAN, CVV, and PIN** - Each reveal requires a fresh, one-use confirmation and never returns a value twice or to any agent.
  - Acceptance: one-use token model; second use rejected; agents and remote models can never trigger reveal; tests cover reuse and agent boundaries per item 26 and `AGENTS.md` boundary 3.
  - Depends on: MC-038
  - Suggested runner: Manager

- [ ] **MC-034: Add a protected copy action with reauthentication** [BLOCKED_OWNER] - Copying a secret to the clipboard requires the same one-use human confirmation as reveal.
  - Acceptance: copy gated identically to reveal; no background agent can initiate it; tests cover the gate per `docs/USER-GUIDE.md` section 10.
  - Depends on: MC-033
  - Suggested runner: Manager

- [ ] **MC-035: Clear the clipboard after 30 seconds** [BLOCKED_OWNER] - Attempt clipboard clearing 30 seconds after a copy and explain operating-system/browser limits.
  - Acceptance: timer implemented; limits documented to the user; deterministic-testable timer hook per item 27.
  - Depends on: MC-034
  - Suggested runner: OpenCode

- [x] **MC-036: Mask secrets to the final four digits only** - Any displayed secret shows only the last four digits.
  - Acceptance: masking applied at every display point; no full value in DOM, storage, or logs per item 28.
  - Depends on: MC-033
  - Suggested runner: OpenCode

- [x] **MC-037: Prompt to erase CVV/PIN after expiry, loss, or closure** - After such a lifecycle event, offer to erase stored CVV/PIN while preserving non-secret lineage and history.
  - Acceptance: prompt appears on the relevant lifecycle transitions; erasure removes only the secret values; lineage survives per item 32.
  - Depends on: MC-031, MC-033
  - Suggested runner: Manager

- [x] **MC-038: Add a reauthentication gate for every protected private action** - Add, edit, delete, reveal, copy, export, and purge require fresh reauthentication.
  - Acceptance: every protected action verifies a fresh credential; failures are logged without values; auto-lock still applies per item 25 and `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: none
  - Suggested runner: Manager

### User-first UI and documentation

- [x] **MC-039: Build the benefits detail view** - Each benefit explains what it is, How to use, Where to use, What to verify, eligible cards, conditions, exclusions, caps, dates, status, last verification, and official links.
  - Acceptance: detail view renders all fields; indirect benefits show steps, document checklist, official link, deadline, and reminder; links open official destinations only per items 58, 80, 93, 94.
  - Depends on: MC-052, MC-083
  - Suggested runner: OpenCode

- [ ] **MC-040: Add useful benefit-first browsing** [REOPENED_USER_TEST] - Browse and search by benefit, showing eligible owned cards first and other public alternatives separately, with usable details instead of empty catalog records.
  - Acceptance: benefit-first view groups owned-eligible cards separately; uses only envelope metadata plus catalog matches per item 92.
  - Progress: category chips now count the selected scope, featured categories form a compact row with a More categories group, and each category renders owned matches before other public benefits.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [x] **MC-041: Build the Expiring Soon view** - Show urgent expiries, allowance resets, and actions computed from private signals, never raw values.
  - Acceptance: view renders priority-ordered signals; no secret value appears; empty and populated states verified per items 89 and `docs/USER-GUIDE.md` section 2.
  - Depends on: MC-025
  - Suggested runner: OpenCode

- [x] **MC-042: Build the Updates view** - Show recently changed and pending catalog updates with their review states.
  - Acceptance: update list reflects approved and needs-review changes; links to candidate records; empty state verified per `ROADMAP.md` milestone 5 and item 89.
  - Depends on: MC-091
  - Suggested runner: OpenCode

- [ ] **MC-043: Build a consumer-first Home landing page** [REOPENED_USER_TEST] - Home prioritizes adding or unlocking cards, finding a benefit, choosing a card for a purchase, and truly user-relevant alerts; it must not lead with governance or implementation status.
  - Acceptance: overview aggregates these priorities from public and non-secret private data; verified desktop/mobile per item 89.
  - Depends on: MC-041, MC-040
  - Suggested runner: OpenCode

- [x] **MC-044: Polish My Cards filters and search** - Filter by lifecycle status and search by bank, card, or product name with clear empty results.
  - Acceptance: filters combine correctly; search matches bank/network/product; empty and no-result states verified per `docs/USER-GUIDE.md` section 6.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [x] **MC-045: Extend the Settings page beyond theme** - Surface local display and future privacy/reminder controls that never share vault state.
  - Acceptance: settings cover documented local preferences only; no settings value enters vault or catalog; per item 98.
  - Depends on: MC-141
  - Suggested runner: OpenCode

- [ ] **MC-046: Make Compare aligned, understandable, and useful** [REOPENED_USER_TEST] - Comparison must show aligned category-by-category differences without combining conditional or estimated value into one misleading number, and it must not render an empty two-card comparison as a result.
  - Acceptance: compare renders per-benefit rows with separate value classes; no single-number headline per `PRODUCT_REQUIREMENTS.md` "Discovery, comparison, and answers".
  - Depends on: MC-074
  - Suggested runner: OpenCode

- [ ] **MC-047: Provide useful empty, demo, error, and populated states for every consumer view** [REOPENED_USER_TEST] - Every visible consumer view must explain its purpose, why it is empty, and the next action; technical availability text alone is not sufficient.
  - Acceptance: a fresh clone renders all views with sensible empty/demo states; no cloud/network dependency; verified per item 99 and `AGENTS.md` quality gates.
  - Depends on: MC-043
  - Suggested runner: OpenCode

- [x] **MC-048: Update the user guide with new flows** - Reflect add/edit/replace/reveal/reconciliation behavior honestly as it lands.
  - Acceptance: `docs/USER-GUIDE.md` matches shipped behavior; "Working now" vs "Not working yet" lists accurate; updated in the same change as each feature per `AGENTS.md` "Living artifacts".
  - Depends on: MC-028, MC-039
  - Suggested runner: Claude

- [x] **MC-049: Keep the living artifacts current** - `PRODUCT_REQUIREMENTS.md`, `ROADMAP.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, `docs/DECISION-TRACE.md`, `docs/QUESTIONNAIRE-DECISIONS.md`, `docs/IDEA-LOG.md`, and coordination files update in the same change as implementation.
  - Acceptance: no stale living artifact after any task; tracked in the same commit per `AGENTS.md` "Living artifacts".
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-050: Make text, dates, and currencies localization-ready** - Structure all user-facing strings, date formats, and currency handling for future translation.
  - Acceptance: no hard-coded user-facing text in templates/JS; dates/currencies use locale-aware formatting; document the localization path per item 5.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-051: Add clear in-product error recovery guidance** [REOPENED_USER_TEST] - Every error state tells the user what happened and provides a working recovery or setup action without revealing machine paths or secrets.
  - Acceptance: error copy is actionable and secret-free; catalog-unavailable and vault-unavailable states match `docs/USER-GUIDE.md` section 12; no absolute path or private identifier in any message.
  - Depends on: MC-009
  - Suggested runner: OpenCode

### Benefit discovery

- [x] **MC-052: Model movie benefits including BookMyShow** - Represent movie offer/credit benefits for BookMyShow and comparable providers as structured catalog facts.
  - Acceptance: catalog schema models the benefit type; fixture records pass validation; UI renders them; confirmed meaning per item 40.
  - Depends on: none
  - Suggested runner: Luna

- [x] **MC-053: Model hotels, flights, dining, fuel, shopping, vouchers, and coupons** - Add structured catalog coverage for these benefit categories.
  - Acceptance: each category has a validated catalog shape and fixture; rendered in Benefits view per item 39 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-054: Model lounge, Priority Pass, meet-and-greet, concierge, and travel assistance** - Represent these airport and travel benefits including partner/child-credential edges.
  - Acceptance: catalog facts validate; lounge/meet-and-greet render with provider and steps per item 39 and 118.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-055: Model insurance, golf, subscriptions, and railway lounge benefits** - Add structured coverage for these remaining benefit categories.
  - Acceptance: each has a validated catalog shape and fixture per item 39.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-056: Model rewards, miles, and cashback earn rates** - Represent base and accelerated earn, caps, exclusions, rounding, reversals, and expiry.
  - Acceptance: earn-rule model validates all listed attributes; tests cover each per item 41.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-057: Model conversions and transfers** - Represent transfer partners, ratios, fees, minimums, increments, expiry, and redemption options with value assumptions.
  - Acceptance: transfer-rule model validates all attributes; tests cover each per item 41.
  - Depends on: MC-056
  - Suggested runner: OpenCode

- [x] **MC-058: Express point value as a range tied to a named redemption path** - Never present one universal point value.
  - Acceptance: point-value display is a range with the redemption path named; tests enforce no single-value path per item 42.
  - Depends on: MC-057
  - Suggested runner: OpenCode

- [x] **MC-059: Model spend conditions with met, not_met, or unknown** - Track spend-condition state without ingesting transactions.
  - Acceptance: per-card condition state is user-set; none of the states implies a transaction record per item 43.
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [x] **MC-060: Support an optional manual aggregate toward a spend threshold** - Let the user enter one optional aggregate figure per threshold.
  - Acceptance: single manual aggregate per threshold, encrypted when private; no transaction ingestion per item 44.
  - Depends on: MC-059
  - Suggested runner: OpenCode

- [x] **MC-061: Model condition types for welcome, milestone, annual-fee waiver, renewal, spend-triggered, geography, currency, channel, MCC, and time-window** - Encode the full condition predicate set.
  - Acceptance: each condition type validates and evaluates correctly; tests cover each per item 50.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-062: Model monthly, quarterly, anniversary-year, and calendar-year counters and resets** - Track allowance counters and their reset boundaries.
  - Acceptance: counter model resets on the right boundary; tests cover all four periods per item 46.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-063: Record personal attempt outcomes without making them global truth** - Track successful, failed, rejected, or skipped attempts as private state only.
  - Acceptance: outcomes are private, never published, and never affect public eligibility per item 47.
  - Depends on: MC-002
  - Suggested runner: OpenCode

- [x] **MC-064: Keep personalized and login-only offers private** - Never publish login-only or personalized offers as general eligibility.
  - Acceptance: such offers are private or marked personalized; public catalog cannot contain them per item 48.
  - Depends on: MC-065
  - Suggested runner: OpenCode

- [x] **MC-065: Display benefit states correctly** - Show verified active, needs review, upcoming, expired, withdrawn, conflicting, unverified, and personalized states.
  - Acceptance: all eight states render distinctly; needs-review is never presented as active per item 52 and `docs/USER-GUIDE.md` section 9.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-066: Support historical and future "as of" questions** - Answer catalog questions for arbitrary effective dates through immutable versions.
  - Acceptance: as-of evaluation returns the version active on that date; expired rules remain searchable per item 53 and 69.
  - Depends on: MC-070
  - Suggested runner: OpenCode

- [x] **MC-067: Model indirect and inherited benefits** - Represent benefits supplied by a network, co-brand, merchant, membership tier, or event rather than the issuing bank.
  - Acceptance: indirect-benefit model with provider source and eligibility; rendered with steps and checklist; motivating example includes a boarding-pass-triggered destination benefit per `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [x] **MC-068: Build the boarding-pass-triggered destination benefit workflow** - Support benefits whose qualifying flight may be independent of the card used to buy it (Regalia Gold Travel Edge is the first pilot shape).
  - Acceptance: workflow models qualifying flight, evidence checklist, deadline, official link, and reminder; never uploads documents automatically per item 58 and `docs/IDEA-LOG.md` "2026-08-07".
  - Depends on: MC-067
  - Suggested runner: Manager

- [x] **MC-069: Make network inheritance opt-in per offering and date range** - A network tier alone must never prove that one issuer variant receives every network offer.
  - Acceptance: inheritance is explicit per offering with date range; evaluation does not infer network-wide offers per `docs/IDEA-LOG.md` "2026-08-07".
  - Depends on: MC-067
  - Suggested runner: OpenCode

- [x] **MC-070: Keep benefits temporal and versioned** - Expired rules stay historical, never silently disappear; a missing end date means unknown, not perpetual.
  - Acceptance: expired facts render as historical; missing end date shows "unknown" not "ongoing"; tests cover both per item 53 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-071: Preserve separate rule owners for issuer, network, co-brand, merchant, and membership** - Represent which party owns each benefit rule so verification responsibility and source authority stay attributable.
  - Acceptance: each rule retains its owner dimension; loader and UI display the owning party; tests cover multi-owner rules per item 49 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [x] **MC-072: Implement the reminder system** - Remind for enrollment, benefit/voucher expiry, allowance reset, renewal, fee-waiver checkpoints, expiring cards, and earn-and-burn expiry/devaluation.
  - Acceptance: all reminder kinds computed from private signals without exposing values; earn-and-burn reminders never promise future value per items 56 and `docs/IDEA-LOG.md`.
  - Depends on: MC-025
  - Suggested runner: OpenCode

- [x] **MC-073: Add ntfy and calendar export reminders** - Offer in-app reminders plus optional ntfy and calendar export; no email or SMS required in v1.
  - Acceptance: ntfy and ICS export work without email/SMS; per item 57.
  - Depends on: MC-072
  - Suggested runner: OpenCode

- [x] **MC-074: Keep guaranteed, conditional, and estimated value separate** - Every benefit surface distinguishes the three value classes; conditional and estimated values are never shown as guaranteed.
  - Acceptance: value-class labels render; no mixed-value headline; tests enforce separation per item 51 and `docs/PURCHASE-OPTIMIZER.md` "Value classes".
  - Depends on: MC-056
  - Suggested runner: OpenCode

- [x] **MC-075: Display conflicting benefits with explanation** - Preserve conflicting official assertions, explain the conflict, and reduce confidence rather than promising eligibility.
  - Acceptance: conflicts render with both assertions and reduced confidence; no positive eligibility promise per item 68.
  - Depends on: MC-065
  - Suggested runner: OpenCode

- [x] **MC-076: Add benefit-type search and filtering across the catalog** - Filter benefits by category, merchant, network, and conditions.
  - Acceptance: filters return correct subsets; combined filters tested per `PRODUCT_REQUIREMENTS.md` "Discovery, comparison, and answers".
  - Depends on: MC-052
  - Suggested runner: OpenCode

- [x] **MC-077: Support salary/spend-pattern and core-plus-specialists portfolios** - Explain when a broad core card or a merchant/fuel/dining/travel co-brand fits better rather than recommending one universal best card.
  - Acceptance: portfolio guidance renders for representative public variants using verified facts only; no unverified claim appears per `docs/IDEA-LOG.md` "2026-08-06".
  - Depends on: MC-056
  - Suggested runner: OpenCode

- [x] **MC-078: Model joining, renewal, annual-fee, fee-waiver, and milestone benefits** - Include these fee and lifecycle benefit types as first-class catalog benefits with their own conditions.
  - Acceptance: each benefit type has a validated catalog shape and fixture and renders with its conditions per item 45 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [x] **MC-079: Add optional non-spend safety reminders** - Due-date alignment and autopay checks as optional, education-only reminders, never a transaction ledger.
  - Acceptance: reminders are opt-in, education-only, and clearly separate from spend tracking per `docs/IDEA-LOG.md` "2026-08-06".
  - Depends on: MC-072
  - Suggested runner: OpenCode

- [ ] **MC-080: Show contextual education for EMI, utilization, and exclusions** [REOPENED_USER_TEST] - Keep accurate education without encouraging spending, but place it only beside affected benefits or purchase guidance and behind concise progressive disclosure rather than on Home.
  - Acceptance: warnings render with neutral education copy; no spending encouragement per `docs/IDEA-LOG.md` "2026-08-06".
  - Depends on: MC-077
  - Suggested runner: OpenCode

- [x] **MC-081: Support provisional missing offerings with unverified benefits** - Let a user add a provisional offering while benefits stay unverified until an agent prepares a research candidate.
  - Acceptance: provisional offering is representable; its benefits show unverified/needs-review state; candidates can be queued per item 91.
  - Depends on: MC-028, MC-091
  - Suggested runner: OpenCode

- [x] **MC-082: Rank cards only with assumptions, uncertainty, caps, and exclusions visible** - Any card-ranking or comparison surface must expose the assumptions and uncertainty behind a rank.
  - Acceptance: ranking output shows assumptions, uncertainty, caps, and exclusions inline; no rank is presented without them per item 54.
  - Depends on: MC-074
  - Suggested runner: OpenCode

### Official-source verification

- [x] **MC-083: Convert the Tata Neu Infinity pilot research into reviewable candidates** - Turn `docs/research/pilot-benefit-source-map-2026-08-07.md` findings for Tata Neu Infinity HDFC RuPay Select into immutable `needs_review` candidates (Awaiting Manager Review).
  - Acceptance: 3 supported official candidate rows become candidate-store records with hashes and diffs; unsupported, blocked, and linkage-uncertain items remain excluded and represented in the frozen evidence manifest.
  - Depends on: MC-085
  - Suggested runner: Claude

- [x] **MC-084: Convert the Regalia Gold pilot research into reviewable candidates** - Do the same conversion for HDFC Regalia Gold findings including Travel Edge and conflicting statement-credit values (Awaiting Manager Review).
  - Acceptance: 2 supported official candidate rows become candidate-store records; Travel Edge remains blocked and its statement-credit ambiguity is preserved without selecting a value.
  - Depends on: MC-085
  - Suggested runner: Claude

- [x] **MC-085: Verify lounge and meet-and-greet candidates for the pilots** - Confirm each airport-lounge and meet-and-greet candidate against current Priority Pass/DreamFolks, network, and issuer terms.
  - Acceptance: each candidate carries a current official tier-1-5 URL, retrieval time, hash, and effective dates; no candidate is active until human review per item 59.
  - Depends on: none
  - Suggested runner: Claude

- [x] **MC-086: Verify the trailing-period eligibility predicate (Visa Meet & Assist)** - Confirm the prior-12-months international in-person spend predicate against current official terms.
  - Acceptance: the recorded content-bearing Visa offer API hash, effective dates, spend predicate, and unproven pilot linkage are preserved as `not_found`; no pilot candidate is generated.
  - Depends on: MC-085
  - Suggested runner: Claude

- [x] **MC-087: Verify the boarding-pass/destination benefit candidates (Travel Edge)** - Confirm the boarding-pass-triggered destination benefit and its issuer-page statement-credit conflict.
  - Acceptance: the recorded URL/hash/locator, boarding-pass trigger, effective range, blocked classification, and unresolved statement-credit conflict are preserved; no candidate is activated.
  - Depends on: MC-086
  - Suggested runner: Claude

- [x] **MC-088: Create source admission records for all pilot sources** - Give every automated or monitored pilot source a reviewed admission record per `docs/SOURCE-POLICY.md`.
  - Acceptance: admission records state tier, URL scope, robots/terms permission, rate limits, cadence, and approver; none exists without review per `docs/SOURCE-POLICY.md` "Source admission".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-089: Classify sources as automated, manual, or excluded for automation** - Automate licensed feeds and admitted public sources conservatively; keep ambiguous/restrictive sources manual and exclude login/CAPTCHA/account-only sources from automation.
  - Acceptance: each admitted source carries an automation class; login/CAPTCHA/account-only sources are excluded from any adapter; admission and queue tests enforce the classes per item 62 and `docs/SOURCE-POLICY.md` "Source admission".
  - Depends on: MC-088
  - Suggested runner: OpenCode

- [ ] **MC-090: Require one or two independent human approvals before activation** [BLOCKED_OWNER] - Standard claims need one human reviewer; ambiguous or high-impact claims need two; agents can never approve their own candidates.
  - Acceptance: candidate-store transition rules enforce the reviewer counts; no agent identity can hold a reviewer role; fail-closed on violations per item 67 and `AGENTS.md` boundary 5.
  - Depends on: MC-083, MC-084
  - Suggested runner: Manager

- [x] **MC-091: Expose candidate review and research queue through protected local API/UI** - Show `needs_review` candidates, diffs, and queue state to an authenticated local reviewer (Implemented — Awaiting Manager Review).
  - Acceptance: review surface lists candidates with diffs and evidence; no direct catalog write; loopback-only per `PROJECT_STATUS.md` "Next planned slice".
  - Depends on: none
  - Suggested runner: Antigravity

- [x] **MC-092: Detect evidence change or disappearance and move assertions to needs_review** - When a source page changes or evidence disappears, affected assertions transition to `needs_review` rather than staying active.
  - Acceptance: hash comparison triggers the transition; withdrawal is never silent per item 66 and `docs/SOURCE-POLICY.md` "Provenance requirements".
  - Depends on: MC-093
  - Suggested runner: OpenCode

- [x] **MC-093: Attach full provenance metadata to every assertion** - Source URL and tier, effective dates, retrieval time, content hash, confidence, and review state on every catalog fact.
  - Acceptance: no approved assertion lacks full provenance; loader validates the invariant per `docs/SOURCE-POLICY.md` "Provenance requirements".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-094: Store raw fetched evidence in a restricted local maintainer store** - Raw captures stay outside the public repository and release.
  - Acceptance: raw evidence only under ignored, permission-restricted local paths; package/privacy scans prove exclusion per item 61 and `AGENTS.md` "Data boundaries".
  - Depends on: MC-093
  - Suggested runner: OpenCode

- [x] **MC-095: Acknowledge corrections and takedowns within seven days** - Process structured corrections with a tracked acknowledgment and immediately hide unsafe or infringing material.
  - Acceptance: acknowledgment SLA is tracked; unsafe/ infringing content hides immediately pending review per item 71.
  - Depends on: MC-096
  - Suggested runner: OpenCode

- [x] **MC-096: Accept structured pull requests with schema validation and conflict-of-interest disclosure** - Allow card/correction contributions only through validated PRs.
  - Acceptance: PR template requires sources and conflict-of-interest disclosure; schema validation blocks invalid records per item 70.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-097: Preserve conflicting official assertions** - Record disagreements rather than deleting the lower-tier source; the more authoritative source wins and the conflict is retained.
  - Acceptance: conflict records are visible and retained; higher-tier preference applied per `docs/SOURCE-POLICY.md` "Source tiers".
  - Depends on: MC-093
  - Suggested runner: OpenCode

### Reward and purchase optimization

- [x] **MC-098: Expose the optimizer core through a protected local API** - Wire the reviewed pure engine (`src/mycard_benefits/optimizer/`) to a narrowly scoped loopback API.
  - Acceptance: API accepts a planned-purchase scenario and returns ranked routes; rejects stale/unreviewed inputs; no persistence unless explicitly saved per `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-099: Build the optimizer UI** - Let a user enter merchant/site/app, category, amount, date, currency, channel, and held card names for an ephemeral planned purchase.
  - Acceptance: inputs render and submit; scenario is ephemeral by default; no spending record is created per `PRODUCT_REQUIREMENTS.md` "Purchase optimizer".
  - Depends on: MC-098
  - Suggested runner: OpenCode

- [x] **MC-100: Render complete route layers independently** - Show coupon, shopping-portal, issuer/network offer, card earn, milestone, and redemption layers each with its own evidence and status.
  - Acceptance: route layers render as independent, conditionally-stackable components; no merged percentage per `docs/PURCHASE-OPTIMIZER.md` "Route graph".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [x] **MC-101: Require explicit pairwise stackability** - Show layers as stackable only when evidence supports every relevant combination.
  - Acceptance: compatibility edges are explicit; unknown compatibility is never treated as stackable per item 51 and `docs/PURCHASE-OPTIMIZER.md`.
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [x] **MC-102: Show guaranteed, conditional, and estimated totals separately** - The UI never headlines a single summed "return".
  - Acceptance: three separate totals render; no combined headline per `docs/PURCHASE-OPTIMIZER.md` "Value classes".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [x] **MC-103: Apply per-transaction and period caps without double counting** - Deduct caps correctly including shared caps across layers.
  - Acceptance: cap arithmetic tests cover shared caps; no double counting per `docs/PURCHASE-OPTIMIZER.md` "Ranking".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [x] **MC-104: Show at least one fallback route with rejection reasons** - Explain why every rejected card/path lost or could not be verified.
  - Acceptance: a fallback route always renders; rejection reasons are explicit per `docs/PURCHASE-OPTIMIZER.md` "Ranking".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [x] **MC-105: Add affiliate disclosure adjacent to actions with an official-links-only toggle** - Disclose compensation next to the action and offer a "show official links only" control; never hide or shorten redirect URLs.
  - Acceptance: disclosure renders adjacent to every compensated action; toggle hides affiliate routes; an official non-affiliate link is always available per item 8 and `docs/PURCHASE-OPTIMIZER.md` "Affiliate disclosure".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [x] **MC-106: Add pending, confirmed, rejected, and reversed portal tracking states** - Let users record portal cashback outcomes as personal state.
  - Acceptance: states are private per-card state and never global truth per `docs/PURCHASE-OPTIMIZER.md` "Portal example".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [x] **MC-107: Express redemption value as a range with a named valuation** - Derived points/miles value uses a disclosed valuation and a range.
  - Acceptance: redemption value renders as a range tied to a named valuation; never cash-guaranteed per `docs/PURCHASE-OPTIMIZER.md` "Value classes".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [x] **MC-108: Open tracking links only after explicit user choice** - The app never auto-navigates; a tracking/portal link opens only after the user selects it.
  - Acceptance: no auto-redirect; destination inspection is possible; tests assert no programmatic navigation per `PRODUCT_REQUIREMENTS.md` "Purchase optimizer".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [x] **MC-109: Reject stale, unreviewed, or ineligible optimizer inputs** - Drop inactive, expired, stale, unreviewed, incompatible, or ineligible components before ranking.
  - Acceptance: filtering tests cover each drop class per `docs/PURCHASE-OPTIMIZER.md` "Ranking".
  - Depends on: MC-098
  - Suggested runner: OpenCode

- [x] **MC-110: Ensure affiliate status never improves rank** - No affiliate compensation enters the score; equal-value ties prefer the non-affiliate path.
  - Acceptance: ranking tests prove affiliate status cannot raise rank and ties favor non-affiliate per item 8 and `docs/PURCHASE-OPTIMIZER.md`.
  - Depends on: MC-098
  - Suggested runner: OpenCode

### Live update scheduling

- [ ] **MC-111: Implement live source fetch adapters as admitted plugins** [BLOCKED_EXTERNAL] - Any future admitted source adapters need fixtures, rate limits, and deterministic tests under the source policy.
  - Acceptance: adapters register from admission records; fixtures drive CI; live requests honor cadence and rate limits; no adapter runs without an admission record per item 107.
  - Depends on: MC-088
  - Suggested runner: OpenCode

- [x] **MC-112: Provide a visible local job runner** - Show last run, next run, failures, and a pause control while the UI is closed.
  - Acceptance: runner surface renders queue state; pause works; state persists per item 84.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [x] **MC-113: Document Windows Task Scheduler integration** - Provide a documented schedule for unattended source work.
  - Acceptance: runbook has exact scheduler steps; no service or registry changes outside documented flow per item 108.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [x] **MC-114: Implement source-specific cadence scheduling** - Daily for short promotions, weekly for active products, monthly for durable documents, immediate recheck after change.
  - Acceptance: queue scheduling matches the cadence table; deterministic time-injection tests per item 65.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [x] **MC-115: Notify on failed or conflicting updates without exposing ownership** - Notification text never reveals private ownership or record contents.
  - Acceptance: notification copy is generic; tests assert no private identifiers per item 85.
  - Depends on: MC-112
  - Suggested runner: OpenCode

- [x] **MC-116: Pause and report blocked sources; never retry after blocks** - A blocked source stops, is logged, and is surfaced for follow-up; no retry after policy/access/CAPTCHA/rate-limit blocks.
  - Acceptance: queue transitions to `blocked` with no automatic retry; a human/manager action is required; deterministic tests cover the transition.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [x] **MC-117: Enforce adapter rate limits and deterministic tests** - Every adapter has documented limits and offline deterministic tests.
  - Acceptance: adapters use fixtures in CI; live checks are separate and non-blocking per item 111 and `AGENTS.md` quality gates.
  - Depends on: MC-111
  - Suggested runner: OpenCode

### Agent workflows

- [ ] **MC-118: Enable research agents that fetch, detect changes, parse candidates, run tests, and draft changes** [BLOCKED_EXTERNAL] - Agents perform admitted-source work and create reviewable candidates only.
  - Acceptance: agent pipeline ends in `needs_review` candidates with hashes and diffs; no agent can publish or approve per item 77.
  - Depends on: MC-111, MC-090
  - Suggested runner: OpenCode

- [ ] **MC-119: Add provider-neutral agent adapters** [BLOCKED_EXTERNAL] - Support OpenAI, Anthropic, Gemini, and local models; none required for core operation.
  - Acceptance: adapter layer is provider-neutral; deterministic Q&A works with no model configured per items 74 and 75.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-120: Gate paid model calls behind explicit provider configuration, enablement, and budget** - No paid call without explicit config and budget.
  - Acceptance: enablement and budget enforced; over-budget calls blocked; tests cover the gates per item 76.
  - Depends on: MC-119
  - Suggested runner: Manager

- [x] **MC-121: Expand the deterministic Q&A intents** - Cover what is usable now, which card works, how to claim, what expires, uses remaining, what changed, and why eligibility fails.
  - Acceptance: all seven first-class intents answer from approved catalog facts with citations; unknown/stale produces `unknown` or `needs_confirmation` per item 82.
  - Depends on: MC-066
  - Suggested runner: OpenCode

- [x] **MC-122: Add opt-in, local, encrypted conversation history scrubbed of secrets** - History is opt-in, local, encrypted when linked to private cards, and scrubbed of PAN/CVV/PIN.
  - Acceptance: history toggle defaults off; stored history contains no secret values; scrubbing tested per item 83.
  - Depends on: MC-121
  - Suggested runner: OpenCode

- [x] **MC-123: Verify agents never approve their own candidates** - A worker cannot be its own reviewer.
  - Acceptance: candidate-store enforcement tests assert author and reviewer identities are distinct per item 87 and `AGENTS.md` boundary 5.
  - Depends on: MC-090
  - Suggested runner: Manager

- [x] **MC-124: Verify agents never access vault secrets** - Background agents and remote models never receive decrypted vault values.
  - Acceptance: architecture-level tests prove agent code paths receive only public offering IDs and public rules per `AGENTS.md` boundary 3 and `docs/AGENT-OPERATIONS.md`.
  - Depends on: MC-033
  - Suggested runner: Manager

### Tests

- [x] **MC-125: Enable the strict mypy type-check gate** - Introduce `uv run mypy src` as a required quality gate.
  - Acceptance: strict mypy passes across `src/`; documented in quality gates per `AGENTS.md` "Quality gates".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-126: Add migration tests** - Cover backup, dry run, validation, and rollback for every schema migration.
  - Acceptance: each migration has tests proving backup/dry-run/validation/rollback behavior per item 105.
  - Depends on: MC-158
  - Suggested runner: OpenCode

- [x] **MC-127: Add parser and source-policy tests for adapters** - Every parser and admission rule has deterministic offline tests.
  - Acceptance: parser bounds, rate-limit, and policy tests pass with fixtures only per item 107 and `AGENTS.md`.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [ ] **MC-128: Add end-to-end UI tests for protected flows** [BLOCKED_OWNER] - Add, edit, archive, replace, reveal, and purge flows have full UI coverage.
  - Acceptance: e2e tests run offline against the synthetic catalog and temporary vaults per `AGENTS.md` "Quality gates".
  - Depends on: MC-028, MC-029, MC-031, MC-033
  - Suggested runner: OpenCode

- [x] **MC-129: Add accessibility tests for WCAG 2.1 AA** - Keyboard, focus, landmarks, contrast, and screen-reader semantics are covered.
  - Acceptance: automated a11y checks pass on desktop and mobile per item 6 and `AGENTS.md` quality gates.
  - Depends on: MC-149
  - Suggested runner: OpenCode

- [x] **MC-130: Add offline and clean-clone tests** - A fresh clone works with no network, key, or runtime data.
  - Acceptance: clean-clone test proves locked setup, offline operation, and no required key per item 99 and `coordination/events.jsonl` `clean_clone_passed`.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-131: Add a loopback startup test that cannot widen the bind** - Prove the default bind is loopback and can never silently widen.
  - Acceptance: startup test asserts `127.0.0.1` default and rejects a widen attempt per `AGENTS.md` quality gates and boundary 7.
  - Depends on: MC-004
  - Suggested runner: OpenCode

- [x] **MC-132: Keep live-source tests out of CI** - CI uses deterministic fixtures; live checks are separate and non-blocking.
  - Acceptance: no network test runs in normal CI; separate health-check surface exists per item 111.
  - Depends on: MC-117
  - Suggested runner: OpenCode

- [x] **MC-133: Add XSS, CSRF, and path-traversal tests** - Cover injection and hostile-input surfaces on new APIs and UI.
  - Acceptance: injection-like and traversal inputs are handled safely; tests pass per item 110.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-134: Add redaction tests for new surfaces** - No secret or private identifier appears in any new API, log, or error.
  - Acceptance: redaction tests cover every new surface per item 33 and `AGENTS.md` quality gates.
  - Depends on: MC-156
  - Suggested runner: OpenCode

- [x] **MC-135: Add mobile and responsive UI tests** - All views render correctly on phone-sized screens.
  - Acceptance: rendered mobile checks pass for new views per `AGENTS.md` quality gates.
  - Depends on: MC-149
  - Suggested runner: OpenCode

### Packaging and setup

- [x] **MC-136: Keep one-command Windows setup first-class** - Windows setup remains the primary documented install path.
  - Acceptance: `uv sync --locked` plus one run command works on a fresh Windows clone per item 103.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-137: Provide Linux and macOS instructions** - Document equivalent setup for Linux and macOS.
  - Acceptance: guide sections cover both platforms per item 103.
  - Depends on: none
  - Suggested runner: Claude

- [x] **MC-138: Add optional Docker installation** - Offer Docker as an optional, not only, install route.
  - Acceptance: Dockerfile and docs exist; local loopback binding preserved; not the primary path per item 103.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-139: Audit and scan the locked dependency set** - Keep a modest, audited, locked dependency set with security scanning.
  - Acceptance: lockfile is audited; vulnerability scan passes; extras stay optional (e.g. keyring) per item 102 and `PROJECT_STATUS.md`.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-140: Distribute signed, versioned catalog snapshots** - Snapshots with checksums, atomic update, rollback, and last-known-good fallback.
  - Acceptance: release snapshots are versioned with checksums; update is atomic; rollback restores last-known-good per item 112.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-141: Add no telemetry; explicit redacted diagnostics export** - No automatic telemetry; diagnostics are explicit, redacted, and manually exportable.
  - Acceptance: no telemetry call exists; diagnostics export is opt-in and redacted per item 113.
  - Depends on: none
  - Suggested runner: OpenCode

### Theme and state independence

- [x] **MC-147: Keep theme preferences independent with an explicit theme contract** - Theme is browser-local today; any future theme contract is explicit and never shares vault state.
  - Acceptance: current independence preserved; a future contract document exists if added per item 98.
  - Depends on: none
  - Suggested runner: OpenCode

### Accessibility

- [x] **MC-149: Complete the WCAG 2.1 AA keyboard and screen-reader audit of all views** - Every view works with keyboard and screen-reader.
  - Acceptance: audit passes for all views on desktop and mobile per item 6.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-150: Add reduced-motion support** - Honor reduced-motion preferences.
  - Acceptance: animations disable under reduced-motion; verified per item 6.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-151: Verify light and dark themes for all new views** - Every new view renders correctly in both themes.
  - Acceptance: rendered dark/light checks pass per `AGENTS.md` quality gates.
  - Depends on: MC-039
  - Suggested runner: OpenCode

- [x] **MC-152: Add focus management and skip links for new flows** - New dialogs and flows manage focus and expose skip links.
  - Acceptance: keyboard focus order and skip-to-content verified per `AGENTS.md` and `docs/USER-GUIDE.md` section 4.
  - Depends on: MC-149
  - Suggested runner: OpenCode

### Security and privacy

- [x] **MC-154: Add threat-model defense tests** - Cover casual household access, lost-device disk inspection, accidental logging, malicious catalog data, and network leakage.
  - Acceptance: each threat-model axis has a test; a fully compromised OS stays out of scope per item 36.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-155: Add a local audit event log** - Log reveal, copy, edit, export, migration, and purge events locally without field values.
  - Acceptance: events recorded with no values; log is local and purgeable per item 33.
  - Depends on: MC-029, MC-033
  - Suggested runner: Manager

- [x] **MC-156: Set one-year default audit retention, configurable and purgeable** - Retain private audit events for one year by default.
  - Acceptance: retention default is one year; config and purge controls work per item 34.
  - Depends on: MC-155
  - Suggested runner: OpenCode

- [x] **MC-157: Add a user-held recovery key and encrypted recovery export** - Provide a recovery key and encrypted export; there is no server-side reset.
  - Acceptance: recovery export works and reopens on a fresh machine; no reset path exists per item 29.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-158: Add rotating encrypted backups and manual encrypted export** - Keep rotating encrypted local backups plus manual encrypted export.
  - Acceptance: backup rotation is bounded and encrypted; manual export restores correctly per item 30.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-159: Add encrypted attachments with purpose, expiry, and retention controls** - Store boarding passes, vouchers, enrollment confirmations, and membership documents encrypted with metadata-only agent visibility.
  - Acceptance: attachments encrypt; purpose/expiry/retention enforced; agents see metadata only per item 35.
  - Depends on: MC-024
  - Suggested runner: Manager

- [x] **MC-160: Prove issuer credentials, OTPs, and cookies are never stored** - Bank usernames/passwords, OTPs, session cookies, and account-access tokens are never stored.
  - Acceptance: schema rejects these field types; tests assert absence per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-161: Sweep for secret values in logs, URLs, exceptions, and notifications** - No secret may enter any of these channels.
  - Acceptance: automated sweep and tests find no secret values in these channels per `SECURITY.md` "Hard rules".
  - Depends on: MC-036
  - Suggested runner: OpenCode

### Migration and backup/recovery

- [x] **MC-162: Add Alembic migrations before exposing private APIs** - Introduce numbered database migrations prior to protected private API surfaces.
  - Acceptance: Alembic is wired with the current schema; migration path documented per item 104.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-163: Enforce numbered migrations with pre-migration backup, dry run, validation, and rollback documentation** - Every migration follows the documented safety sequence.
  - Acceptance: runbook and enforcement match per item 105.
  - Depends on: MC-162
  - Suggested runner: OpenCode

- [x] **MC-164: Add encrypted full backup export** - Export a full encrypted backup for user-held recovery.
  - Acceptance: backup exports, restores, and verifies on a fresh machine per item 100.
  - Depends on: MC-157
  - Suggested runner: Manager

- [x] **MC-165: Add redacted JSON export** - Export a redacted JSON of non-secret metadata.
  - Acceptance: export contains only non-secret fields; redaction tests pass per item 100.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-166: Add CSV export for non-secret metadata** - Provide CSV export of non-secret card metadata.
  - Acceptance: CSV columns are non-secret only per item 100.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-167: Add public catalog JSON export** - Make the public catalog JSON exportable.
  - Acceptance: export matches the reviewed release snapshot per item 100.
  - Depends on: MC-140
  - Suggested runner: OpenCode

### Release governance

- [ ] **MC-168: Maintain protected main, reviewed pull requests, automated checks, and no force pushes** [BLOCKED_EXTERNAL] - Enforce branch protection and review workflow.
  - Acceptance: branch protection is active; PR checks run; force-push is blocked per item 115.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-169: Record future publication and push gates before execution** [BLOCKED_OWNER] - Any future remote/push requires a dated human approval naming the commit range and destination, recorded in `coordination/events.jsonl` first.
  - Acceptance: no push occurs without the recorded gate per item 116 and `AGENTS.md` "Repository and publication".
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-170: Run the release-candidate secret/identity/path scan** - Before any commit or release, scan tracked changes for secrets, real identifiers, absolute user paths, and raw source content.
  - Acceptance: scan checklist passes with no findings per `AGENTS.md` quality gates.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-171: Keep living artifacts current on every change** - Update the living artifacts in the same change as implementation.
  - Acceptance: no implementation commit leaves living artifacts stale per `AGENTS.md` "Living artifacts".
  - Depends on: MC-049
  - Suggested runner: Manager

- [x] **MC-172: Sequence milestones so each is independently usable and testable** - Deliver independently usable milestones rather than a monolith.
  - Acceptance: milestone boundaries match `ROADMAP.md` and item 119; each leaves the prior usable.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-173: Complete the public-deployment threat-model and compliance review** [BLOCKED_EXTERNAL] - Any public deployment requires a separate threat-model and compliance review.
  - Acceptance: review record exists before deployment; findings closed per `SECURITY.md` "Hard rules".
  - Depends on: none
  - Suggested runner: Manager

## Waiting On

- [ ] **MC-174: Owner decision on commercialization and affiliate-revenue strategy** [BLOCKED_OWNER] - Commercialization remains a separate governance/legal decision.
  - Acceptance: a dated owner decision naming the exact strategy; the affiliate-neutrality rule in item 8 continues to apply; recorded in `coordination/events.jsonl`.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-175: Owner decision on a private vulnerability reporting channel** [BLOCKED_OWNER] - Publish a private reporting channel.
  - Acceptance: a channel exists and is documented; until then, high-level owner notification remains the only route per `SECURITY.md` "Reporting".
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-176: Owner decision on public-deployment threat-model and compliance review** [BLOCKED_OWNER] - Approval to run and accept the deployment review.
  - Acceptance: owner approval recorded before any public deployment per `SECURITY.md` "Hard rules".
  - Depends on: MC-173
  - Suggested runner: Manager

- [ ] **MC-179: Owner decision on licensing terms for future affiliate or licensed feeds** [BLOCKED_OWNER] - Affiliate/licensed feeds enter only through isolated adapters with documented licence and redistribution limits.
  - Acceptance: a dated owner decision and an admission record exist before any licensed feed per item 72.
  - Depends on: none
  - Suggested runner: Manager

## Someday

- [ ] **MC-180: Add PWA installation support** [DEFERRED_POST_V1] - Deferred until the vault and catalog are stable.
  - Acceptance: PWA work starts only after vault and catalog stability criteria are met per item 4.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-181: Add built-in cloud sync** [DEFERRED_POST_V1] - Explicitly deferred; v1 uses user-controlled encrypted export/import between devices.
  - Acceptance: reopens only under a reviewed design decision; item 31 stands until then.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-182: Add front and back card photograph support** [DEFERRED_POST_V1] - Excluded from v1.
  - Acceptance: reopens only with a reviewed schema and storage design per item 24.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-183: Add email and SMS reminders** [DEFERRED_POST_V1] - Not required in v1.
  - Acceptance: reopens only under a reviewed design per item 57.
  - Depends on: MC-073
  - Suggested runner: OpenCode

- [ ] **MC-185: Add spending-ledger ingestion, bank login, payments, applications, booking, redemption, and automatic claims** [DEFERRED_POST_V1] - Excluded by product scope.
  - Acceptance: stays excluded; eligibility rules and manual counters remain the boundary per item 9.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-186: Add generalized affiliate stacking with explicit uncertainty and complete purchase-route optimization** [DEFERRED_POST_V1] - A later addition beyond the current disclosure-only optimizer.
  - Acceptance: reopens only with reviewed evidence rules per item 120.
  - Depends on: MC-101
  - Suggested runner: Manager

- [ ] **MC-187: Generalize network-inherited and unusual boarding-pass-triggered benefits beyond the pilots** [DEFERRED_POST_V1] - Later additions; the pilots come first.
  - Acceptance: pilot implementations are active before generalization per item 120.
  - Depends on: MC-068, MC-069
  - Suggested runner: OpenCode

- [ ] **MC-188: Implement general encrypted custom fields and notes** [DEFERRED_POST_V1] - Requires a reviewed schema before exposure.
  - Acceptance: schema review (documented) completes first; current vault remains schema-allowlisted per item 23.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-189: Add optional manual realized-value totals** [DEFERRED_POST_V1] - Kept disabled by default so this does not become a spending ledger.
  - Acceptance: if built, defaults to disabled and never aggregates spend per item 55.
  - Depends on: MC-107
  - Suggested runner: OpenCode

## Done

- [x] **MC-190: Foundation local alpha** - Loopback FastAPI application, signed installation identity, deterministic port resolution, public dashboard, synthetic demo catalog, and offline test suite.
  - Acceptance: `PROJECT_STATUS.md` "Completed" and clean-clone evidence `c037ccf`.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-191: Versioned public catalog loader/API** - Stable offering identity, temporal rules, evidence governance, and API with synthetic tests.
  - Acceptance: catalog loader/API tests and current release gates pass; historical task evidence remains in Git history.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-192: Immutable candidate and diff store** - Needs-review-only candidates, deterministic diffs, append-only review decisions.
  - Acceptance: immutable-candidate tests and independent review passed; historical task evidence remains in Git history.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-193: Resumable offline research queue** - SQLite job queue with leases, honest transitions, and bounded listing; no network I/O.
  - Acceptance: resumable queue tests passed; historical task evidence remains in Git history.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-194: Deterministic traceable Q&A** - Bounded interpreter over approved public records with citations; no LLM required.
  - Acceptance: deterministic Q&A tests and rendered checks passed.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-195: Purchase-route optimizer core** - Pure ranking engine with separate value classes and affiliate-neutral scoring; not yet UI-exposed.
  - Acceptance: optimizer tests and independent review passed.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-196: Encrypted vault core** - Argon2id wrapping, AES-GCM records, envelope authentication, locking, backups, lifecycle, auto-lock, reauthentication, one-use reveal authorization.
  - Acceptance: 49 focused vault tests and independent review passed; historical task evidence remains in Git history.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-197: One-time JSON manifest import CLI** - Strict manifest parsing, atomic batch persistence, optional OS-keyring unlock, count-only integrity verification.
  - Acceptance: strict import tests and owner-authorized migration completed; historical review evidence remains in Git history.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-199: India starter catalog** - 68 real product-variant identities plus one synthetic fixture; presence is not benefit verification.
  - Acceptance: deterministic 68-file regeneration byte-identical; `owned-catalog-and-mobile-002.md`.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-200: Loopback-only read-only My Cards API/UI** - Envelope-only fields, `no-store`, keyring vault open, replacement metadata.
  - Acceptance: `PROJECT_STATUS.md` "Completed"; protected read-only API reviewed and verified.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-201: Pilot official-source map** - Discovery-only source mapping for Tata Neu Infinity and Regalia Gold; no claim activated.
  - Acceptance: `docs/research/pilot-benefit-source-map-2026-08-07.md`; `pilot-benefit-research-002.md` completion record.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-202: User-first README and user guide** - Setup, daily use, privacy, phone access, verification states, and maintainer-audit documentation.
  - Acceptance: `README.md` and `docs/USER-GUIDE.md` shipped and reviewed.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-203: Rendered consumer acceptance and independent review verification** [REOPENED_USER_TEST] - Desktop/mobile and dark/light checks must validate real user journeys and usefulness, not only synthetic mechanics, plus an independent review with no unresolved High/Medium findings.
  - Acceptance: `coordination/events.jsonl` review checkpoints; final gates at 208 MyCard tests.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-204: Clean-clone verification and initial publication** - Dependency-cold clone passed; public repository created and v0.1.0 tag placed.
  - Acceptance: `coordination/events.jsonl` `clean_clone_passed` and `publication_complete`.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-205: Repository backlog and task dashboard** - Comprehensive TASKS.md backlog and the standard task dashboard added at repository root.
  - Acceptance: this task's validation: at least 120 unchecked IDs, unique MC IDs, `git diff --check` clean, no worker changes outside TASKS.md and dashboard.html.
  - Depends on: none
  - Suggested runner: OpenCode
