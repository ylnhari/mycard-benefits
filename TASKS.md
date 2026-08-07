# Tasks

Manager protocol: tasks are assigned one at a time; a worker owns only its named task; the manager independently reviews evidence before advancing; no worker may commit/push unless its individual task explicitly authorizes it. Every task is grounded in `PRODUCT_REQUIREMENTS.md`, `docs/QUESTIONNAIRE-DECISIONS.md`, `docs/IDEA-LOG.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, `ROADMAP.md`, and the coordination task records. Source-document headings are cross-referenced; private records are never referenced. Acceptance criteria name objective evidence only.

## Active

### Broken user experience — first

- [ ] **MC-001: Make the imported card list clearly visible** - The My Cards view must immediately show every imported card as readable rows (catalog product, bank, network, status, record dates) with no secret values and no ambiguous placeholder text.
  - Acceptance: rendered list verified desktop/mobile and dark/light with populated, empty, and vault-unavailable states; search and status filter return correct subsets; response remains `no-store` and contains only envelope fields per `PROJECT_STATUS.md` "Next planned slice".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-002: Add a card record detail view reachable from My Cards** - Selecting an imported card opens a detail panel showing its offering, lifecycle state, created/updated timestamps, and any replacement link, without revealing secrets.
  - Acceptance: each row navigates to a detail view; envelope-only fields verified; keyboard reachable; covered by `tests/test_private_cards_api.py` and UI tests; no secret field appears in the response.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [ ] **MC-003: Remove production-visible synthetic example.invalid links** - The catalog and dashboard must never render synthetic/example `.invalid` links or synthetic-only URLs in non-demo production views.
  - Acceptance: grep of rendered production catalog views finds no `example.invalid` or synthetic host; a test asserts public catalog records carry only real or explicitly-absent URLs; demo content is labeled demo only.
  - Depends on: none
  - Suggested runner: OpenCode

- [x] **MC-004: Decouple MyCard from the personal Rover launcher while keeping loopback-only safety** - Remove any session or sign-in coupling to the personal launcher so MyCard is self-contained and remains loopback-bound; the launcher stays an optional external tool.
  - Acceptance: no launcher cookie/session is required or consumed by the app; startup test proves default bind is `127.0.0.1` and cannot widen to `0.0.0.0`; running the app without the launcher works fully; external-tool configuration stays outside the app per `AGENTS.md` boundary 7.
  - Depends on: none
  - Suggested runner: Antigravity

- [ ] **MC-005: Keep MyCard wording neutral and launcher-free** - MyCard's own UI and docs must carry only neutral MyCard-local branding. Rover is the owner's personal external start-stop/mobile-access launcher, not part of MyCard and not a "Companion Dashboard"; remove Rover-branded and Companion-Dashboard-branded sign-in language from user-facing templates, API error text, README, and guide so MyCard reads as self-contained.
  - Acceptance: grep of templates, static assets, README, and guide finds no Rover sign-in or Companion Dashboard wording in active MyCard surfaces; rendered states use neutral MyCard-local copy; historical coordination evidence (`coordination/events.jsonl`) stays historical; docs updated in the same change.
  - Depends on: MC-004
  - Suggested runner: OpenCode

- [ ] **MC-177: Document and verify MyCard is self-contained and launcher-independent** - MyCard's app, UI, and docs state that it binds loopback-only and that any personal external launcher (including the owner's Rover) is an optional start-stop/mobile-access tool, never a MyCard dependency, identity, or configuration requirement.
  - Acceptance: README, user guide, and app copy describe the external launcher as optional and external with no launcher secret, identity, or config in MyCard source, browser storage, or docs; loopback-only startup test passes; verified per `PRODUCT_REQUIREMENTS.md` "Family Finance and remote access" and `docs/FAMILY-FINANCE-INTEGRATION.md`.
  - Depends on: MC-004, MC-005
  - Suggested runner: OpenCode

- [x] **MC-006: Render unmatched offering identifiers as a clear state, never a bare slug dump** - Cards whose offering id has no catalog slug must show a labeled "unmatched variant" state with guidance, not raw identifiers.
  - Acceptance: unmatched rows display explanatory text and a documented path (fix import or request a variant) per `docs/USER-GUIDE.md` section 6; UI test covers the unmatched state.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [ ] **MC-007: Support passphrase-only vaults in the browser My Cards view** - The browser must not report passphrase-only vaults as permanently unavailable; add a supported flow to unlock them or an explicit documented alternative.
  - Acceptance: passphrase-only vault is either unlockable via a protected local prompt or clearly documented with the CLI path; no secret crosses the HTTP boundary in plaintext; guide section 6 updated; test covers the unavailable state honestly.
  - Depends on: MC-001, MC-038
  - Suggested runner: Manager

- [x] **MC-008: Resolve the --demo versus real-data surprise for My Cards** - Starting with `--demo` must not silently show the wrong data folder; the UI and guide must make the demo/real boundary obvious.
  - Acceptance: demo runs display a persistent demo banner and point at `demo-data`; guide explains the boundary (`docs/USER-GUIDE.md` section 3); UI test asserts demo vs non-demo data folders differ.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [x] **MC-009: Explain why the vault is unavailable with actionable diagnostics** - My Cards must tell the user which of the known causes applies (demo mode, no vault, passphrase-only, wrong data dir) and how to fix it.
  - Acceptance: each unavailable cause maps to a distinct rendered message and fix step per `docs/USER-GUIDE.md` section 12; covered by UI tests.
  - Depends on: MC-001
  - Suggested runner: OpenCode

### Variant, lifecycle, expiry, replacement, and owner reconciliation

- [ ] **MC-010: Build the previewed owner/variant/lifecycle/replacement reconciliation workflow** - Deliver the next delivery gate in `PROJECT_STATUS.md`: a human-confirmed reconciliation flow for owner, exact variant, expiry, lifecycle, and old-to-replacement relationships without secret-field reveal or direct browser writes.
  - Acceptance: previewed confirmation flow renders and is keyboard/screen-reader usable; confirmations persist as non-secret private metadata; no reveal or write of secret fields; tests cover confirmation, deferral, and rejection paths.
  - Depends on: MC-001
  - Suggested runner: Manager

- [ ] **MC-011: Confirm the seven unconfirmed imported card variants** - Resolve every ambiguous product-variant match in the private inventory through the reconciliation flow instead of guessing.
  - Acceptance: each of the seven variants is either confirmed to a catalog offering or left as `unverified_match` with candidate variants per `docs/QUESTIONNAIRE-DECISIONS.md` item 15; confirmation state visible without secrets.
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-012: Map anonymous owner aliases to family roles** - Assign the private owner aliases from the import to family roles through the confirmation flow.
  - Acceptance: each alias maps to a role or remains unmapped and visible as needing confirmation; no real person name or record content appears in tracked files; state persisted as non-secret metadata.
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-013: Assign the 49 unassigned imported records to owners** - Let the owner attribute every currently unassigned card record to a mapped owner role.
  - Acceptance: after confirmation, zero records are unassigned or each remaining one is explicitly marked unresolved; counts verifiable without revealing secret fields.
  - Depends on: MC-012
  - Suggested runner: Manager

- [ ] **MC-014: Establish old-to-replacement relationships for imported records** - Build replacement links between prior and current card instances through the confirmation flow.
  - Acceptance: replacement links are recorded as private lineage; linked instances show "replaced by/replaces" metadata in My Cards; history survives reissue per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-015: Reconcile the 60 archived imported records with true lifecycle state** - Confirm whether each archived record is truly expired, closed, or still active so reminders and views are accurate.
  - Acceptance: each archived record resolves to a confirmed lifecycle state or remains explicitly pending confirmation; the UI never presents archived as expired.
  - Depends on: MC-010, MC-016
  - Suggested runner: Manager

- [ ] **MC-016: Treat archived as distinct from expired in UI and reminders** - Change every surface so archived records are not assumed expired and never produce expiry reminders.
  - Acceptance: UI text and reminder logic distinguish archived from expired; test asserts archived records do not trigger expiry reminders; guide wording reflects the distinction per `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: MC-026
  - Suggested runner: OpenCode

- [ ] **MC-017: Confirm provisional active status of the 20 active records** - Validate each provisionally-active imported record's lifecycle through the confirmation flow.
  - Acceptance: every provisional active record is confirmed, corrected, or explicitly marked unresolved; count-only verification unaffected.
  - Depends on: MC-010
  - Suggested runner: Manager

- [ ] **MC-018: Support multiple instances of one offering per owner** - Allow one owner to hold several instances of the same offering as separate private card instances.
  - Acceptance: schema/API/UI accept and render duplicate-offering instances; each keeps a distinct private UUID per `docs/QUESTIONNAIRE-DECISIONS.md` item 16.
  - Depends on: MC-028
  - Suggested runner: OpenCode

- [ ] **MC-019: Model primary, add-on, supplementary, physical, virtual, and tokenized instances as linked** - Represent every instance role as a separate linked card instance.
  - Acceptance: instance-role field exists with the enumerated roles and link relationships; verified in add/edit flows and My Cards metadata per item 17.
  - Depends on: MC-028, MC-029
  - Suggested runner: OpenCode

- [ ] **MC-020: Preserve renewal, reissue, upgrade, downgrade, and network migration as immutable lineage** - Record each private lifecycle transition as immutable history joined by a private lineage identifier.
  - Acceptance: each transition creates an immutable history entry; lineage id links prior and successor instances; no rewrite of prior history per item 19.
  - Depends on: MC-031
  - Suggested runner: Manager

- [x] **MC-021: Add a reviewed relationship graph for renamed, legacy, cloned, and reskinned products** - Model public product relationships from a reviewed graph, never inferred from names alone.
  - Acceptance: catalog relationship entries are reviewed data with provenance; loader validates graph integrity; names never auto-infer inheritance per item 14.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-022: Store uncertain matches as unverified_match with candidate variants** - When a card cannot be mapped exactly, store the state as `unverified_match` and show candidate variants while withholding unsupported entitlements.
  - Acceptance: the state persists; candidates render; benefits for the uncertain match are not treated as active per item 15 and `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: MC-010
  - Suggested runner: OpenCode

- [ ] **MC-023: Select exact network, co-brand, market, product generation, and benefit cohort** - Let a user pick the precise variant dimensions when they matter.
  - Acceptance: variant selection UI exposes network, co-brand, market, generation, and cohort when the offering declares them; selection stored on the instance per item 12.
  - Depends on: MC-028
  - Suggested runner: OpenCode

- [ ] **MC-024: Model child records for Priority Pass, lounge credentials, memberships, vouchers, and companion credentials** - Represent attached credentials as child records of the issuing card.
  - Acceptance: child-record model with parent linkage, expiry, and lifecycle; rendered in detail views without secrets per item 22.
  - Depends on: MC-002
  - Suggested runner: OpenCode

- [ ] **MC-025: Make private expiry usable for reminders without exposing secrets** - Compute expiry-driven reminder signals server-side so the browser never receives an expiry value.
  - Acceptance: reminder API returns signals, not values; no expiry in any response; tests verify the vault-expiry boundary; Expiring Soon view uses only these signals.
  - Depends on: MC-041
  - Suggested runner: Manager

- [ ] **MC-026: Support the full lifecycle state set in protected flows** - Add, edit, archive, and replace flows must support applied, pending, active, frozen, lost, stolen, expired, renewed, replaced, upgraded, downgraded, closed, and archived states.
  - Acceptance: every enumerated state is representable and transitions are validated; covered by API and UI tests per item 18.
  - Depends on: MC-028, MC-029
  - Suggested runner: OpenCode

- [ ] **MC-027: Add explicit purge with typed confirmation and encrypted-backup warning** - Permanent deletion requires typed confirmation and a warning that encrypted backups may still hold the record.
  - Acceptance: purge requires typed text; confirmation text warns about encrypted backups; purge is logged without field values; tests cover the flow per item 20 and 21.
  - Depends on: MC-032
  - Suggested runner: Manager

### Protected write controls and secret reveal

- [ ] **MC-028: Add a protected add-card flow** - Add a card by selecting a canonical offering, confirming variant details, creating a private instance, and optionally adding encrypted fields.
  - Acceptance: add flow gated by reauthentication; offering selection, variant confirmation, and instance creation work; secret fields encrypted; no secret in any log/URL per item 90.
  - Depends on: MC-038
  - Suggested runner: Manager

- [ ] **MC-029: Add a protected edit flow** - Edit non-secret and encrypted fields of a card instance through the protected UI.
  - Acceptance: edits persist through the vault API; immutable history unchanged; reauthentication enforced; edits logged without values per item 33.
  - Depends on: MC-038
  - Suggested runner: Manager

- [ ] **MC-030: Add a protected archive, retire, close, and restore flow** - Move a card between archived, closed, retired, and active states without losing lineage.
  - Acceptance: transitions validated and persisted; restored records reappear; tests cover each transition per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: MC-029
  - Suggested runner: OpenCode

- [ ] **MC-031: Add a protected replace flow** - Create a new immutable instance linked to the prior instance so history survives expiry, loss, or reissue.
  - Acceptance: replace creates a successor instance with lineage to the prior one; prior history untouched; UI surfaces the link per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: MC-020, MC-029
  - Suggested runner: Manager

- [ ] **MC-032: Add a protected delete flow with typed confirmation** - Delete a card instance only with typed confirmation and the encrypted-backup warning.
  - Acceptance: delete requires typed confirmation; warning shown; action logged without values; tests cover confirm and cancel per item 21.
  - Depends on: MC-029
  - Suggested runner: Manager

- [ ] **MC-033: Add a one-use reveal authorization for PAN, CVV, and PIN** - Each reveal requires a fresh, one-use confirmation and never returns a value twice or to any agent.
  - Acceptance: one-use token model; second use rejected; agents and remote models can never trigger reveal; tests cover reuse and agent boundaries per item 26 and `AGENTS.md` boundary 3.
  - Depends on: MC-038
  - Suggested runner: Manager

- [ ] **MC-034: Add a protected copy action with reauthentication** - Copying a secret to the clipboard requires the same one-use human confirmation as reveal.
  - Acceptance: copy gated identically to reveal; no background agent can initiate it; tests cover the gate per `docs/USER-GUIDE.md` section 10.
  - Depends on: MC-033
  - Suggested runner: Manager

- [ ] **MC-035: Clear the clipboard after 30 seconds** - Attempt clipboard clearing 30 seconds after a copy and explain operating-system/browser limits.
  - Acceptance: timer implemented; limits documented to the user; deterministic-testable timer hook per item 27.
  - Depends on: MC-034
  - Suggested runner: OpenCode

- [ ] **MC-036: Mask secrets to the final four digits only** - Any displayed secret shows only the last four digits.
  - Acceptance: masking applied at every display point; no full value in DOM, storage, or logs per item 28.
  - Depends on: MC-033
  - Suggested runner: OpenCode

- [ ] **MC-037: Prompt to erase CVV/PIN after expiry, loss, or closure** - After such a lifecycle event, offer to erase stored CVV/PIN while preserving non-secret lineage and history.
  - Acceptance: prompt appears on the relevant lifecycle transitions; erasure removes only the secret values; lineage survives per item 32.
  - Depends on: MC-031, MC-033
  - Suggested runner: Manager

- [ ] **MC-038: Add a reauthentication gate for every protected private action** - Add, edit, delete, reveal, copy, export, and purge require fresh reauthentication.
  - Acceptance: every protected action verifies a fresh credential; failures are logged without values; auto-lock still applies per item 25 and `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: none
  - Suggested runner: Manager

### User-first UI and documentation

- [ ] **MC-039: Build the benefits detail view** - Each benefit explains what it is, How to use, Where to use, What to verify, eligible cards, conditions, exclusions, caps, dates, status, last verification, and official links.
  - Acceptance: detail view renders all fields; indirect benefits show steps, document checklist, official link, deadline, and reminder; links open official destinations only per items 58, 80, 93, 94.
  - Depends on: MC-052, MC-083
  - Suggested runner: OpenCode

- [ ] **MC-040: Add benefit-first browsing** - Browse by benefit showing the user's eligible owned cards first and other public alternatives separately.
  - Acceptance: benefit-first view groups owned-eligible cards separately; uses only envelope metadata plus catalog matches per item 92.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [ ] **MC-041: Build the Expiring Soon view** - Show urgent expiries, allowance resets, and actions computed from private signals, never raw values.
  - Acceptance: view renders priority-ordered signals; no secret value appears; empty and populated states verified per items 89 and `docs/USER-GUIDE.md` section 2.
  - Depends on: MC-025
  - Suggested runner: OpenCode

- [ ] **MC-042: Build the Updates view** - Show recently changed and pending catalog updates with their review states.
  - Acceptance: update list reflects approved and needs-review changes; links to candidate records; empty state verified per `ROADMAP.md` milestone 5 and item 89.
  - Depends on: MC-091
  - Suggested runner: OpenCode

- [ ] **MC-043: Build the Overview landing page** - The landing page prioritizes urgent expiries/actions, available benefits, resets, uncertain card matches, and recent verified changes.
  - Acceptance: overview aggregates these priorities from public and non-secret private data; verified desktop/mobile per item 89.
  - Depends on: MC-041, MC-040
  - Suggested runner: OpenCode

- [ ] **MC-044: Polish My Cards filters and search** - Filter by lifecycle status and search by bank, card, or product name with clear empty results.
  - Acceptance: filters combine correctly; search matches bank/network/product; empty and no-result states verified per `docs/USER-GUIDE.md` section 6.
  - Depends on: MC-001
  - Suggested runner: OpenCode

- [ ] **MC-045: Extend the Settings page beyond theme** - Surface local display and future privacy/reminder controls that never share vault state.
  - Acceptance: settings cover documented local preferences only; no settings value enters vault or catalog; per item 98.
  - Depends on: MC-141
  - Suggested runner: OpenCode

- [ ] **MC-046: Improve the Compare view so it never collapses conditional value** - Comparison must show differences without combining conditional or estimated value into one misleading number.
  - Acceptance: compare renders per-benefit rows with separate value classes; no single-number headline per `PRODUCT_REQUIREMENTS.md` "Discovery, comparison, and answers".
  - Depends on: MC-074
  - Suggested runner: OpenCode

- [ ] **MC-047: Provide empty, demo, and populated states for every view** - Every dashboard view must have useful empty/demo/populated states with no required key or network service.
  - Acceptance: a fresh clone renders all views with sensible empty/demo states; no cloud/network dependency; verified per item 99 and `AGENTS.md` quality gates.
  - Depends on: MC-043
  - Suggested runner: OpenCode

- [ ] **MC-048: Update the user guide with new flows** - Reflect add/edit/replace/reveal/reconciliation behavior honestly as it lands.
  - Acceptance: `docs/USER-GUIDE.md` matches shipped behavior; "Working now" vs "Not working yet" lists accurate; updated in the same change as each feature per `AGENTS.md` "Living artifacts".
  - Depends on: MC-028, MC-039
  - Suggested runner: Claude

- [ ] **MC-049: Keep the living artifacts current** - `PRODUCT_REQUIREMENTS.md`, `ROADMAP.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, `docs/DECISION-TRACE.md`, `docs/QUESTIONNAIRE-DECISIONS.md`, `docs/IDEA-LOG.md`, and coordination files update in the same change as implementation.
  - Acceptance: no stale living artifact after any task; tracked in the same commit per `AGENTS.md` "Living artifacts".
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-050: Make text, dates, and currencies localization-ready** - Structure all user-facing strings, date formats, and currency handling for future translation.
  - Acceptance: no hard-coded user-facing text in templates/JS; dates/currencies use locale-aware formatting; document the localization path per item 5.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-051: Add clear error and recovery guidance to the UI** - Every error state tells the user what happened and how to recover, without revealing machine paths or secrets.
  - Acceptance: error copy is actionable and secret-free; catalog-unavailable and vault-unavailable states match `docs/USER-GUIDE.md` section 12; no absolute path or private identifier in any message.
  - Depends on: MC-009
  - Suggested runner: OpenCode

### Benefit discovery

- [ ] **MC-052: Model movie benefits including BookMyShow** - Represent movie offer/credit benefits for BookMyShow and comparable providers as structured catalog facts.
  - Acceptance: catalog schema models the benefit type; fixture records pass validation; UI renders them; confirmed meaning per item 40.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-053: Model hotels, flights, dining, fuel, shopping, vouchers, and coupons** - Add structured catalog coverage for these benefit categories.
  - Acceptance: each category has a validated catalog shape and fixture; rendered in Benefits view per item 39 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-054: Model lounge, Priority Pass, meet-and-greet, concierge, and travel assistance** - Represent these airport and travel benefits including partner/child-credential edges.
  - Acceptance: catalog facts validate; lounge/meet-and-greet render with provider and steps per item 39 and 118.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-055: Model insurance, golf, subscriptions, and railway lounge benefits** - Add structured coverage for these remaining benefit categories.
  - Acceptance: each has a validated catalog shape and fixture per item 39.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-056: Model rewards, miles, and cashback earn rates** - Represent base and accelerated earn, caps, exclusions, rounding, reversals, and expiry.
  - Acceptance: earn-rule model validates all listed attributes; tests cover each per item 41.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-057: Model conversions and transfers** - Represent transfer partners, ratios, fees, minimums, increments, expiry, and redemption options with value assumptions.
  - Acceptance: transfer-rule model validates all attributes; tests cover each per item 41.
  - Depends on: MC-056
  - Suggested runner: OpenCode

- [ ] **MC-058: Express point value as a range tied to a named redemption path** - Never present one universal point value.
  - Acceptance: point-value display is a range with the redemption path named; tests enforce no single-value path per item 42.
  - Depends on: MC-057
  - Suggested runner: OpenCode

- [ ] **MC-059: Model spend conditions with met, not_met, or unknown** - Track spend-condition state without ingesting transactions.
  - Acceptance: per-card condition state is user-set; none of the states implies a transaction record per item 43.
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [ ] **MC-060: Support an optional manual aggregate toward a spend threshold** - Let the user enter one optional aggregate figure per threshold.
  - Acceptance: single manual aggregate per threshold, encrypted when private; no transaction ingestion per item 44.
  - Depends on: MC-059
  - Suggested runner: OpenCode

- [ ] **MC-061: Model condition types for welcome, milestone, annual-fee waiver, renewal, spend-triggered, geography, currency, channel, MCC, and time-window** - Encode the full condition predicate set.
  - Acceptance: each condition type validates and evaluates correctly; tests cover each per item 50.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-062: Model monthly, quarterly, anniversary-year, and calendar-year counters and resets** - Track allowance counters and their reset boundaries.
  - Acceptance: counter model resets on the right boundary; tests cover all four periods per item 46.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-063: Record personal attempt outcomes without making them global truth** - Track successful, failed, rejected, or skipped attempts as private state only.
  - Acceptance: outcomes are private, never published, and never affect public eligibility per item 47.
  - Depends on: MC-002
  - Suggested runner: OpenCode

- [ ] **MC-064: Keep personalized and login-only offers private** - Never publish login-only or personalized offers as general eligibility.
  - Acceptance: such offers are private or marked personalized; public catalog cannot contain them per item 48.
  - Depends on: MC-065
  - Suggested runner: OpenCode

- [ ] **MC-065: Display benefit states correctly** - Show verified active, needs review, upcoming, expired, withdrawn, conflicting, unverified, and personalized states.
  - Acceptance: all eight states render distinctly; needs-review is never presented as active per item 52 and `docs/USER-GUIDE.md` section 9.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-066: Support historical and future "as of" questions** - Answer catalog questions for arbitrary effective dates through immutable versions.
  - Acceptance: as-of evaluation returns the version active on that date; expired rules remain searchable per item 53 and 69.
  - Depends on: MC-070
  - Suggested runner: OpenCode

- [ ] **MC-067: Model indirect and inherited benefits** - Represent benefits supplied by a network, co-brand, merchant, membership tier, or event rather than the issuing bank.
  - Acceptance: indirect-benefit model with provider source and eligibility; rendered with steps and checklist; motivating example includes a boarding-pass-triggered destination benefit per `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [ ] **MC-068: Build the boarding-pass-triggered destination benefit workflow** - Support benefits whose qualifying flight may be independent of the card used to buy it (Regalia Gold Travel Edge is the first pilot shape).
  - Acceptance: workflow models qualifying flight, evidence checklist, deadline, official link, and reminder; never uploads documents automatically per item 58 and `docs/IDEA-LOG.md` "2026-08-07".
  - Depends on: MC-067
  - Suggested runner: Manager

- [ ] **MC-069: Make network inheritance opt-in per offering and date range** - A network tier alone must never prove that one issuer variant receives every network offer.
  - Acceptance: inheritance is explicit per offering with date range; evaluation does not infer network-wide offers per `docs/IDEA-LOG.md` "2026-08-07".
  - Depends on: MC-067
  - Suggested runner: OpenCode

- [x] **MC-070: Keep benefits temporal and versioned** - Expired rules stay historical, never silently disappear; a missing end date means unknown, not perpetual.
  - Acceptance: expired facts render as historical; missing end date shows "unknown" not "ongoing"; tests cover both per item 53 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-071: Preserve separate rule owners for issuer, network, co-brand, merchant, and membership** - Represent which party owns each benefit rule so verification responsibility and source authority stay attributable.
  - Acceptance: each rule retains its owner dimension; loader and UI display the owning party; tests cover multi-owner rules per item 49 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [ ] **MC-072: Implement the reminder system** - Remind for enrollment, benefit/voucher expiry, allowance reset, renewal, fee-waiver checkpoints, expiring cards, and earn-and-burn expiry/devaluation.
  - Acceptance: all reminder kinds computed from private signals without exposing values; earn-and-burn reminders never promise future value per items 56 and `docs/IDEA-LOG.md`.
  - Depends on: MC-025
  - Suggested runner: OpenCode

- [ ] **MC-073: Add ntfy and calendar export reminders** - Offer in-app reminders plus optional ntfy and calendar export; no email or SMS required in v1.
  - Acceptance: ntfy and ICS export work without email/SMS; per item 57.
  - Depends on: MC-072
  - Suggested runner: OpenCode

- [ ] **MC-074: Keep guaranteed, conditional, and estimated value separate** - Every benefit surface distinguishes the three value classes; conditional and estimated values are never shown as guaranteed.
  - Acceptance: value-class labels render; no mixed-value headline; tests enforce separation per item 51 and `docs/PURCHASE-OPTIMIZER.md` "Value classes".
  - Depends on: MC-056
  - Suggested runner: OpenCode

- [ ] **MC-075: Display conflicting benefits with explanation** - Preserve conflicting official assertions, explain the conflict, and reduce confidence rather than promising eligibility.
  - Acceptance: conflicts render with both assertions and reduced confidence; no positive eligibility promise per item 68.
  - Depends on: MC-065
  - Suggested runner: OpenCode

- [ ] **MC-076: Add benefit-type search and filtering across the catalog** - Filter benefits by category, merchant, network, and conditions.
  - Acceptance: filters return correct subsets; combined filters tested per `PRODUCT_REQUIREMENTS.md` "Discovery, comparison, and answers".
  - Depends on: MC-052
  - Suggested runner: OpenCode

- [ ] **MC-077: Support salary/spend-pattern and core-plus-specialists portfolios** - Explain when a broad core card or a merchant/fuel/dining/travel co-brand fits better rather than recommending one universal best card.
  - Acceptance: portfolio guidance renders for representative public variants using verified facts only; no unverified claim appears per `docs/IDEA-LOG.md` "2026-08-06".
  - Depends on: MC-056
  - Suggested runner: OpenCode

- [ ] **MC-078: Model joining, renewal, annual-fee, fee-waiver, and milestone benefits** - Include these fee and lifecycle benefit types as first-class catalog benefits with their own conditions.
  - Acceptance: each benefit type has a validated catalog shape and fixture and renders with its conditions per item 45 and `PRODUCT_REQUIREMENTS.md` "Benefit scope".
  - Depends on: MC-061
  - Suggested runner: OpenCode

- [ ] **MC-079: Add optional non-spend safety reminders** - Due-date alignment and autopay checks as optional, education-only reminders, never a transaction ledger.
  - Acceptance: reminders are opt-in, education-only, and clearly separate from spend tracking per `docs/IDEA-LOG.md` "2026-08-06".
  - Depends on: MC-072
  - Suggested runner: OpenCode

- [ ] **MC-080: Add education-only warnings for EMI, high utilization, and business-use exclusions** - Prominent warnings that are education only and never encourage additional spending.
  - Acceptance: warnings render with neutral education copy; no spending encouragement per `docs/IDEA-LOG.md` "2026-08-06".
  - Depends on: MC-077
  - Suggested runner: OpenCode

- [ ] **MC-081: Support provisional missing offerings with unverified benefits** - Let a user add a provisional offering while benefits stay unverified until an agent prepares a research candidate.
  - Acceptance: provisional offering is representable; its benefits show unverified/needs-review state; candidates can be queued per item 91.
  - Depends on: MC-028, MC-091
  - Suggested runner: OpenCode

- [ ] **MC-082: Rank cards only with assumptions, uncertainty, caps, and exclusions visible** - Any card-ranking or comparison surface must expose the assumptions and uncertainty behind a rank.
  - Acceptance: ranking output shows assumptions, uncertainty, caps, and exclusions inline; no rank is presented without them per item 54.
  - Depends on: MC-074
  - Suggested runner: OpenCode

### Official-source verification

- [ ] **MC-083: Convert the Tata Neu Infinity pilot research into reviewable candidates** - Turn `docs/research/pilot-benefit-source-map-2026-08-07.md` findings for Tata Neu Infinity HDFC RuPay Select into immutable `needs_review` candidates.
  - Acceptance: 10 official candidates from the pilot map become candidate-store records with hashes and diffs; discovery-only and conflicting items remain unverified per `coordination/tasks/pilot-benefit-research-002.md`.
  - Depends on: MC-085
  - Suggested runner: Claude

- [ ] **MC-084: Convert the Regalia Gold pilot research into reviewable candidates** - Do the same conversion for HDFC Regalia Gold findings including Travel Edge and conflicting statement-credit values.
  - Acceptance: candidates created for official items; conflicts recorded, not resolved by guessing, per the pilot map and `docs/IDEA-LOG.md` "2026-08-07".
  - Depends on: MC-085
  - Suggested runner: Claude

- [ ] **MC-085: Verify lounge and meet-and-greet candidates for the pilots** - Confirm each airport-lounge and meet-and-greet candidate against current Priority Pass/DreamFolks, network, and issuer terms.
  - Acceptance: each candidate carries a current official tier-1-5 URL, retrieval time, hash, and effective dates; no candidate is active until human review per item 59.
  - Depends on: none
  - Suggested runner: Claude

- [ ] **MC-086: Verify the trailing-period eligibility predicate (Visa Meet & Assist)** - Confirm the prior-12-months international in-person spend predicate against current official terms.
  - Acceptance: predicate shape modeled and verified against an official source; ambiguity recorded per `docs/IDEA-LOG.md` "2026-08-07".
  - Depends on: MC-085
  - Suggested runner: Claude

- [ ] **MC-087: Verify the boarding-pass/destination benefit candidates (Travel Edge)** - Confirm the boarding-pass-triggered destination benefit and its issuer-page statement-credit conflict.
  - Acceptance: exact current terms documented with provenance; conflicting values preserved; not activated without review per `coordination/events.jsonl` `pilot_research_complete`.
  - Depends on: MC-086
  - Suggested runner: Claude

- [ ] **MC-088: Create source admission records for all pilot sources** - Give every automated or monitored pilot source a reviewed admission record per `docs/SOURCE-POLICY.md`.
  - Acceptance: admission records state tier, URL scope, robots/terms permission, rate limits, cadence, and approver; none exists without review per `docs/SOURCE-POLICY.md` "Source admission".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-089: Classify sources as automated, manual, or excluded for automation** - Automate licensed feeds and admitted public sources conservatively; keep ambiguous/restrictive sources manual and exclude login/CAPTCHA/account-only sources from automation.
  - Acceptance: each admitted source carries an automation class; login/CAPTCHA/account-only sources are excluded from any adapter; admission and queue tests enforce the classes per item 62 and `docs/SOURCE-POLICY.md` "Source admission".
  - Depends on: MC-088
  - Suggested runner: OpenCode

- [ ] **MC-090: Require one or two independent human approvals before activation** - Standard claims need one human reviewer; ambiguous or high-impact claims need two; agents can never approve their own candidates.
  - Acceptance: candidate-store transition rules enforce the reviewer counts; no agent identity can hold a reviewer role; fail-closed on violations per item 67 and `AGENTS.md` boundary 5.
  - Depends on: MC-083, MC-084
  - Suggested runner: Manager

- [ ] **MC-091: Expose candidate review and research queue through protected local API/UI** - Show `needs_review` candidates, diffs, and queue state to an authenticated local reviewer.
  - Acceptance: review surface lists candidates with diffs and evidence; no direct catalog write; loopback-only per `PROJECT_STATUS.md` "Next planned slice".
  - Depends on: MC-090
  - Suggested runner: OpenCode

- [ ] **MC-092: Detect evidence change or disappearance and move assertions to needs_review** - When a source page changes or evidence disappears, affected assertions transition to `needs_review` rather than staying active.
  - Acceptance: hash comparison triggers the transition; withdrawal is never silent per item 66 and `docs/SOURCE-POLICY.md` "Provenance requirements".
  - Depends on: MC-093
  - Suggested runner: OpenCode

- [x] **MC-093: Attach full provenance metadata to every assertion** - Source URL and tier, effective dates, retrieval time, content hash, confidence, and review state on every catalog fact.
  - Acceptance: no approved assertion lacks full provenance; loader validates the invariant per `docs/SOURCE-POLICY.md` "Provenance requirements".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-094: Store raw fetched evidence in a restricted local maintainer store** - Raw captures stay outside the public repository and release.
  - Acceptance: raw evidence only under ignored, permission-restricted local paths; package/privacy scans prove exclusion per item 61 and `AGENTS.md` "Data boundaries".
  - Depends on: MC-093
  - Suggested runner: OpenCode

- [ ] **MC-095: Acknowledge corrections and takedowns within seven days** - Process structured corrections with a tracked acknowledgment and immediately hide unsafe or infringing material.
  - Acceptance: acknowledgment SLA is tracked; unsafe/ infringing content hides immediately pending review per item 71.
  - Depends on: MC-096
  - Suggested runner: OpenCode

- [ ] **MC-096: Accept structured pull requests with schema validation and conflict-of-interest disclosure** - Allow card/correction contributions only through validated PRs.
  - Acceptance: PR template requires sources and conflict-of-interest disclosure; schema validation blocks invalid records per item 70.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-097: Preserve conflicting official assertions** - Record disagreements rather than deleting the lower-tier source; the more authoritative source wins and the conflict is retained.
  - Acceptance: conflict records are visible and retained; higher-tier preference applied per `docs/SOURCE-POLICY.md` "Source tiers".
  - Depends on: MC-093
  - Suggested runner: OpenCode

### Reward and purchase optimization

- [ ] **MC-098: Expose the optimizer core through a protected local API** - Wire the reviewed pure engine (`src/mycard_benefits/optimizer/`) to a narrowly scoped loopback API.
  - Acceptance: API accepts a planned-purchase scenario and returns ranked routes; rejects stale/unreviewed inputs; no persistence unless explicitly saved per `PROJECT_STATUS.md` "Not yet safe".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-099: Build the optimizer UI** - Let a user enter merchant/site/app, category, amount, date, currency, channel, and held card names for an ephemeral planned purchase.
  - Acceptance: inputs render and submit; scenario is ephemeral by default; no spending record is created per `PRODUCT_REQUIREMENTS.md` "Purchase optimizer".
  - Depends on: MC-098
  - Suggested runner: OpenCode

- [ ] **MC-100: Render complete route layers independently** - Show coupon, shopping-portal, issuer/network offer, card earn, milestone, and redemption layers each with its own evidence and status.
  - Acceptance: route layers render as independent, conditionally-stackable components; no merged percentage per `docs/PURCHASE-OPTIMIZER.md` "Route graph".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [ ] **MC-101: Require explicit pairwise stackability** - Show layers as stackable only when evidence supports every relevant combination.
  - Acceptance: compatibility edges are explicit; unknown compatibility is never treated as stackable per item 51 and `docs/PURCHASE-OPTIMIZER.md`.
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [ ] **MC-102: Show guaranteed, conditional, and estimated totals separately** - The UI never headlines a single summed "return".
  - Acceptance: three separate totals render; no combined headline per `docs/PURCHASE-OPTIMIZER.md` "Value classes".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [ ] **MC-103: Apply per-transaction and period caps without double counting** - Deduct caps correctly including shared caps across layers.
  - Acceptance: cap arithmetic tests cover shared caps; no double counting per `docs/PURCHASE-OPTIMIZER.md` "Ranking".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [ ] **MC-104: Show at least one fallback route with rejection reasons** - Explain why every rejected card/path lost or could not be verified.
  - Acceptance: a fallback route always renders; rejection reasons are explicit per `docs/PURCHASE-OPTIMIZER.md` "Ranking".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [ ] **MC-105: Add affiliate disclosure adjacent to actions with an official-links-only toggle** - Disclose compensation next to the action and offer a "show official links only" control; never hide or shorten redirect URLs.
  - Acceptance: disclosure renders adjacent to every compensated action; toggle hides affiliate routes; an official non-affiliate link is always available per item 8 and `docs/PURCHASE-OPTIMIZER.md` "Affiliate disclosure".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [ ] **MC-106: Add pending, confirmed, rejected, and reversed portal tracking states** - Let users record portal cashback outcomes as personal state.
  - Acceptance: states are private per-card state and never global truth per `docs/PURCHASE-OPTIMIZER.md` "Portal example".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [ ] **MC-107: Express redemption value as a range with a named valuation** - Derived points/miles value uses a disclosed valuation and a range.
  - Acceptance: redemption value renders as a range tied to a named valuation; never cash-guaranteed per `docs/PURCHASE-OPTIMIZER.md` "Value classes".
  - Depends on: MC-100
  - Suggested runner: OpenCode

- [ ] **MC-108: Open tracking links only after explicit user choice** - The app never auto-navigates; a tracking/portal link opens only after the user selects it.
  - Acceptance: no auto-redirect; destination inspection is possible; tests assert no programmatic navigation per `PRODUCT_REQUIREMENTS.md` "Purchase optimizer".
  - Depends on: MC-099
  - Suggested runner: OpenCode

- [ ] **MC-109: Reject stale, unreviewed, or ineligible optimizer inputs** - Drop inactive, expired, stale, unreviewed, incompatible, or ineligible components before ranking.
  - Acceptance: filtering tests cover each drop class per `docs/PURCHASE-OPTIMIZER.md` "Ranking".
  - Depends on: MC-098
  - Suggested runner: OpenCode

- [ ] **MC-110: Ensure affiliate status never improves rank** - No affiliate compensation enters the score; equal-value ties prefer the non-affiliate path.
  - Acceptance: ranking tests prove affiliate status cannot raise rank and ties favor non-affiliate per item 8 and `docs/PURCHASE-OPTIMIZER.md`.
  - Depends on: MC-098
  - Suggested runner: OpenCode

### Live update scheduling

- [ ] **MC-111: Implement live source fetch adapters as admitted plugins** - Admitted source adapters with fixtures, rate limits, and deterministic tests per `docs/SOURCE-ADAPTER-RUNBOOK.md`.
  - Acceptance: adapters register from admission records; fixtures drive CI; live requests honor cadence and rate limits; no adapter runs without an admission record per item 107.
  - Depends on: MC-088
  - Suggested runner: OpenCode

- [ ] **MC-112: Provide a visible local job runner** - Show last run, next run, failures, and a pause control while the UI is closed.
  - Acceptance: runner surface renders queue state; pause works; state persists per item 84.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [ ] **MC-113: Document Windows Task Scheduler integration** - Provide a documented schedule for unattended source work.
  - Acceptance: runbook has exact scheduler steps; no service or registry changes outside documented flow per item 108.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [ ] **MC-114: Implement source-specific cadence scheduling** - Daily for short promotions, weekly for active products, monthly for durable documents, immediate recheck after change.
  - Acceptance: queue scheduling matches the cadence table; deterministic time-injection tests per item 65.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [ ] **MC-115: Notify on failed or conflicting updates without exposing ownership** - Notification text never reveals private ownership or record contents.
  - Acceptance: notification copy is generic; tests assert no private identifiers per item 85.
  - Depends on: MC-112
  - Suggested runner: OpenCode

- [ ] **MC-116: Pause and report blocked sources; never retry after blocks** - A blocked source stops, is logged, and is surfaced for follow-up; no retry after policy/access/CAPTCHA/rate-limit blocks.
  - Acceptance: queue transitions to `blocked` with no automatic retry; a human/manager action is required; tests cover the transition per `coordination/tasks/research-queue-001.md`.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [ ] **MC-117: Enforce adapter rate limits and deterministic tests** - Every adapter has documented limits and offline deterministic tests.
  - Acceptance: adapters use fixtures in CI; live checks are separate and non-blocking per item 111 and `AGENTS.md` quality gates.
  - Depends on: MC-111
  - Suggested runner: OpenCode

### Agent workflows

- [ ] **MC-118: Enable research agents that fetch, detect changes, parse candidates, run tests, and draft changes** - Agents perform admitted-source work and create reviewable candidates only.
  - Acceptance: agent pipeline ends in `needs_review` candidates with hashes and diffs; no agent can publish or approve per item 77.
  - Depends on: MC-111, MC-090
  - Suggested runner: OpenCode

- [ ] **MC-119: Add provider-neutral agent adapters** - Support OpenAI, Anthropic, Gemini, and local models; none required for core operation.
  - Acceptance: adapter layer is provider-neutral; deterministic Q&A works with no model configured per items 74 and 75.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-120: Gate paid model calls behind explicit provider configuration, enablement, and budget** - No paid call without explicit config and budget.
  - Acceptance: enablement and budget enforced; over-budget calls blocked; tests cover the gates per item 76.
  - Depends on: MC-119
  - Suggested runner: Manager

- [ ] **MC-121: Expand the deterministic Q&A intents** - Cover what is usable now, which card works, how to claim, what expires, uses remaining, what changed, and why eligibility fails.
  - Acceptance: all seven first-class intents answer from approved catalog facts with citations; unknown/stale produces `unknown` or `needs_confirmation` per item 82.
  - Depends on: MC-066
  - Suggested runner: OpenCode

- [ ] **MC-122: Add opt-in, local, encrypted conversation history scrubbed of secrets** - History is opt-in, local, encrypted when linked to private cards, and scrubbed of PAN/CVV/PIN.
  - Acceptance: history toggle defaults off; stored history contains no secret values; scrubbing tested per item 83.
  - Depends on: MC-121
  - Suggested runner: OpenCode

- [ ] **MC-123: Verify agents never approve their own candidates** - A worker cannot be its own reviewer.
  - Acceptance: candidate-store enforcement tests assert author and reviewer identities are distinct per item 87 and `AGENTS.md` boundary 5.
  - Depends on: MC-090
  - Suggested runner: Manager

- [ ] **MC-124: Verify agents never access vault secrets** - Background agents and remote models never receive decrypted vault values.
  - Acceptance: architecture-level tests prove agent code paths receive only public offering IDs and public rules per `AGENTS.md` boundary 3 and `docs/AGENT-OPERATIONS.md`.
  - Depends on: MC-033
  - Suggested runner: Manager

### Tests

- [ ] **MC-125: Enable the strict mypy type-check gate** - Introduce `uv run mypy src` as a required quality gate.
  - Acceptance: strict mypy passes across `src/`; documented in quality gates per `AGENTS.md` "Quality gates".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-126: Add migration tests** - Cover backup, dry run, validation, and rollback for every schema migration.
  - Acceptance: each migration has tests proving backup/dry-run/validation/rollback behavior per item 105.
  - Depends on: MC-158
  - Suggested runner: OpenCode

- [ ] **MC-127: Add parser and source-policy tests for adapters** - Every parser and admission rule has deterministic offline tests.
  - Acceptance: parser bounds, rate-limit, and policy tests pass with fixtures only per item 107 and `AGENTS.md`.
  - Depends on: MC-111
  - Suggested runner: OpenCode

- [ ] **MC-128: Add end-to-end UI tests for protected flows** - Add, edit, archive, replace, reveal, and purge flows have full UI coverage.
  - Acceptance: e2e tests run offline against the synthetic catalog and temporary vaults per `AGENTS.md` "Quality gates".
  - Depends on: MC-028, MC-029, MC-031, MC-033
  - Suggested runner: OpenCode

- [ ] **MC-129: Add accessibility tests for WCAG 2.1 AA** - Keyboard, focus, landmarks, contrast, and screen-reader semantics are covered.
  - Acceptance: automated a11y checks pass on desktop and mobile per item 6 and `AGENTS.md` quality gates.
  - Depends on: MC-149
  - Suggested runner: OpenCode

- [ ] **MC-130: Add offline and clean-clone tests** - A fresh clone works with no network, key, or runtime data.
  - Acceptance: clean-clone test proves locked setup, offline operation, and no required key per item 99 and `coordination/events.jsonl` `clean_clone_passed`.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-131: Add a loopback startup test that cannot widen the bind** - Prove the default bind is loopback and can never silently widen.
  - Acceptance: startup test asserts `127.0.0.1` default and rejects a widen attempt per `AGENTS.md` quality gates and boundary 7.
  - Depends on: MC-004
  - Suggested runner: OpenCode

- [ ] **MC-132: Keep live-source tests out of CI** - CI uses deterministic fixtures; live checks are separate and non-blocking.
  - Acceptance: no network test runs in normal CI; separate health-check surface exists per item 111.
  - Depends on: MC-117
  - Suggested runner: OpenCode

- [ ] **MC-133: Add XSS, CSRF, and path-traversal tests** - Cover injection and hostile-input surfaces on new APIs and UI.
  - Acceptance: injection-like and traversal inputs are handled safely; tests pass per item 110.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-134: Add redaction tests for new surfaces** - No secret or private identifier appears in any new API, log, or error.
  - Acceptance: redaction tests cover every new surface per item 33 and `AGENTS.md` quality gates.
  - Depends on: MC-156
  - Suggested runner: OpenCode

- [ ] **MC-135: Add mobile and responsive UI tests** - All views render correctly on phone-sized screens.
  - Acceptance: rendered mobile checks pass for new views per `AGENTS.md` quality gates.
  - Depends on: MC-149
  - Suggested runner: OpenCode

### Packaging and setup

- [ ] **MC-136: Keep one-command Windows setup first-class** - Windows setup remains the primary documented install path.
  - Acceptance: `uv sync --locked` plus one run command works on a fresh Windows clone per item 103.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-137: Provide Linux and macOS instructions** - Document equivalent setup for Linux and macOS.
  - Acceptance: guide sections cover both platforms per item 103.
  - Depends on: none
  - Suggested runner: Claude

- [ ] **MC-138: Add optional Docker installation** - Offer Docker as an optional, not only, install route.
  - Acceptance: Dockerfile and docs exist; local loopback binding preserved; not the primary path per item 103.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-139: Audit and scan the locked dependency set** - Keep a modest, audited, locked dependency set with security scanning.
  - Acceptance: lockfile is audited; vulnerability scan passes; extras stay optional (e.g. keyring) per item 102 and `PROJECT_STATUS.md`.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-140: Distribute signed, versioned catalog snapshots** - Snapshots with checksums, atomic update, rollback, and last-known-good fallback.
  - Acceptance: release snapshots are versioned with checksums; update is atomic; rollback restores last-known-good per item 112.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-141: Add no telemetry; explicit redacted diagnostics export** - No automatic telemetry; diagnostics are explicit, redacted, and manually exportable.
  - Acceptance: no telemetry call exists; diagnostics export is opt-in and redacted per item 113.
  - Depends on: none
  - Suggested runner: OpenCode

### Family Finance optional linking

- [ ] **MC-142: Build the previewed one-time encrypted import from Family Finance** - A future migration is a previewed, encrypted, one-time import followed by independent stores.
  - Acceptance: import previews a bundle, imports once, and leaves both stores independent; no continuous sync per `DECISIONS.md` and `docs/FAMILY-FINANCE-INTEGRATION.md`.
  - Depends on: MC-143
  - Suggested runner: Manager

- [ ] **MC-143: Add import field comparison and approval step** - The owner compares fields and approves before import.
  - Acceptance: field-comparison preview and approval gate exist; no import without approval per item 37.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-144: Require a separate cleanup approval after import** - Cleanup of source data happens only after a separate approval.
  - Acceptance: cleanup is gated by a distinct approval; nothing is deleted without it per item 37.
  - Depends on: MC-142
  - Suggested runner: Manager

- [ ] **MC-145: Pin the signed companion identity** - The companion verifies the health endpoint's signed installation identity.
  - Acceptance: identity pinning verifies; a wrong service at a configured address is refused; closes the known risk in `SECURITY.md`.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-146: Add a separately reviewed optional count bridge** - Any safe count bridge to Family Finance is its own reviewed feature.
  - Acceptance: feature ships only with its own decision record and review per item 95.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-147: Keep theme preferences independent with an explicit theme contract** - Theme is browser-local today; any future theme contract is explicit and never shares vault state.
  - Acceptance: current independence preserved; a future contract document exists if added per item 98.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-148: Keep the bundled setup documentation fallback verified** - When the companion is absent or stopped, open bundled setup documentation.
  - Acceptance: unconfigured/stopped states open setup docs; Family Finance remains fully usable per item 97.
  - Depends on: none
  - Suggested runner: OpenCode

### Accessibility

- [ ] **MC-149: Complete the WCAG 2.1 AA keyboard and screen-reader audit of all views** - Every view works with keyboard and screen-reader.
  - Acceptance: audit passes for all views on desktop and mobile per item 6.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-150: Add reduced-motion support** - Honor reduced-motion preferences.
  - Acceptance: animations disable under reduced-motion; verified per item 6.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-151: Verify light and dark themes for all new views** - Every new view renders correctly in both themes.
  - Acceptance: rendered dark/light checks pass per `AGENTS.md` quality gates.
  - Depends on: MC-039
  - Suggested runner: OpenCode

- [ ] **MC-152: Add focus management and skip links for new flows** - New dialogs and flows manage focus and expose skip links.
  - Acceptance: keyboard focus order and skip-to-content verified per `AGENTS.md` and `docs/USER-GUIDE.md` section 4.
  - Depends on: MC-149
  - Suggested runner: OpenCode

### Security and privacy

- [ ] **MC-153: Pin the signed installation identity from the companion side** - The external launcher/companion verifies MyCard's signed identity.
  - Acceptance: pinning verified with a wrong-service test; loopback-only preserved per `SECURITY.md` and `AGENTS.md` boundary 7.
  - Depends on: MC-145
  - Suggested runner: Manager

- [ ] **MC-154: Add threat-model defense tests** - Cover casual household access, lost-device disk inspection, accidental logging, malicious catalog data, and network leakage.
  - Acceptance: each threat-model axis has a test; a fully compromised OS stays out of scope per item 36.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-155: Add a local audit event log** - Log reveal, copy, edit, export, migration, and purge events locally without field values.
  - Acceptance: events recorded with no values; log is local and purgeable per item 33.
  - Depends on: MC-029, MC-033
  - Suggested runner: Manager

- [ ] **MC-156: Set one-year default audit retention, configurable and purgeable** - Retain private audit events for one year by default.
  - Acceptance: retention default is one year; config and purge controls work per item 34.
  - Depends on: MC-155
  - Suggested runner: OpenCode

- [ ] **MC-157: Add a user-held recovery key and encrypted recovery export** - Provide a recovery key and encrypted export; there is no server-side reset.
  - Acceptance: recovery export works and reopens on a fresh machine; no reset path exists per item 29.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-158: Add rotating encrypted backups and manual encrypted export** - Keep rotating encrypted local backups plus manual encrypted export.
  - Acceptance: backup rotation is bounded and encrypted; manual export restores correctly per item 30.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-159: Add encrypted attachments with purpose, expiry, and retention controls** - Store boarding passes, vouchers, enrollment confirmations, and membership documents encrypted with metadata-only agent visibility.
  - Acceptance: attachments encrypt; purpose/expiry/retention enforced; agents see metadata only per item 35.
  - Depends on: MC-024
  - Suggested runner: Manager

- [ ] **MC-160: Prove issuer credentials, OTPs, and cookies are never stored** - Bank usernames/passwords, OTPs, session cookies, and account-access tokens are never stored.
  - Acceptance: schema rejects these field types; tests assert absence per `PRODUCT_REQUIREMENTS.md` "Private card lifecycle".
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-161: Sweep for secret values in logs, URLs, exceptions, and notifications** - No secret may enter any of these channels.
  - Acceptance: automated sweep and tests find no secret values in these channels per `SECURITY.md` "Hard rules".
  - Depends on: MC-036
  - Suggested runner: OpenCode

### Migration and backup/recovery

- [ ] **MC-162: Add Alembic migrations before exposing private APIs** - Introduce numbered database migrations prior to protected private API surfaces.
  - Acceptance: Alembic is wired with the current schema; migration path documented per item 104.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-163: Enforce numbered migrations with pre-migration backup, dry run, validation, and rollback documentation** - Every migration follows the documented safety sequence.
  - Acceptance: runbook and enforcement match per item 105.
  - Depends on: MC-162
  - Suggested runner: OpenCode

- [ ] **MC-164: Add encrypted full backup export** - Export a full encrypted backup for user-held recovery.
  - Acceptance: backup exports, restores, and verifies on a fresh machine per item 100.
  - Depends on: MC-157
  - Suggested runner: Manager

- [ ] **MC-165: Add redacted JSON export** - Export a redacted JSON of non-secret metadata.
  - Acceptance: export contains only non-secret fields; redaction tests pass per item 100.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-166: Add CSV export for non-secret metadata** - Provide CSV export of non-secret card metadata.
  - Acceptance: CSV columns are non-secret only per item 100.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-167: Add public catalog JSON export** - Make the public catalog JSON exportable.
  - Acceptance: export matches the reviewed release snapshot per item 100.
  - Depends on: MC-140
  - Suggested runner: OpenCode

### Release governance

- [ ] **MC-168: Maintain protected main, reviewed pull requests, automated checks, and no force pushes** - Enforce branch protection and review workflow.
  - Acceptance: branch protection is active; PR checks run; force-push is blocked per item 115.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-169: Record future publication and push gates before execution** - Any future remote/push requires a dated human approval naming the commit range and destination, recorded in `coordination/events.jsonl` first.
  - Acceptance: no push occurs without the recorded gate per item 116 and `AGENTS.md` "Repository and publication".
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-170: Run the release-candidate secret/identity/path scan** - Before any commit or release, scan tracked changes for secrets, real identifiers, absolute user paths, and raw source content.
  - Acceptance: scan checklist passes with no findings per `AGENTS.md` quality gates.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-171: Keep living artifacts current on every change** - Update the living artifacts in the same change as implementation.
  - Acceptance: no implementation commit leaves living artifacts stale per `AGENTS.md` "Living artifacts".
  - Depends on: MC-049
  - Suggested runner: Manager

- [ ] **MC-172: Sequence milestones so each is independently usable and testable** - Deliver independently usable milestones rather than a monolith.
  - Acceptance: milestone boundaries match `ROADMAP.md` and item 119; each leaves the prior usable.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-173: Complete the public-deployment threat-model and compliance review** - Any public deployment requires a separate threat-model and compliance review.
  - Acceptance: review record exists before deployment; findings closed per `SECURITY.md` "Hard rules".
  - Depends on: none
  - Suggested runner: Manager

## Waiting On

- [ ] **MC-174: Owner decision on commercialization and affiliate-revenue strategy** - Commercialization remains a separate governance/legal decision.
  - Acceptance: a dated owner decision naming the exact strategy; the affiliate-neutrality rule in item 8 continues to apply; recorded in `coordination/events.jsonl`.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-175: Owner decision on a private vulnerability reporting channel** - Publish a private reporting channel.
  - Acceptance: a channel exists and is documented; until then, high-level owner notification remains the only route per `SECURITY.md` "Reporting".
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-176: Owner decision on public-deployment threat-model and compliance review** - Approval to run and accept the deployment review.
  - Acceptance: owner approval recorded before any public deployment per `SECURITY.md` "Hard rules".
  - Depends on: MC-173
  - Suggested runner: Manager

- [ ] **MC-178: Owner decision on a separately reviewed Family Finance count bridge** - Any safe count bridge is its own reviewed feature.
  - Acceptance: a dated owner decision precedes any bridge work per item 95.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-179: Owner decision on licensing terms for future affiliate or licensed feeds** - Affiliate/licensed feeds enter only through isolated adapters with documented licence and redistribution limits.
  - Acceptance: a dated owner decision and an admission record exist before any licensed feed per item 72.
  - Depends on: none
  - Suggested runner: Manager

## Someday

- [ ] **MC-180: Add PWA installation support** - Deferred until the vault and catalog are stable.
  - Acceptance: PWA work starts only after vault and catalog stability criteria are met per item 4.
  - Depends on: none
  - Suggested runner: OpenCode

- [ ] **MC-181: Add built-in cloud sync** - Explicitly deferred; v1 uses user-controlled encrypted export/import between devices.
  - Acceptance: reopens only under a reviewed design decision; item 31 stands until then.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-182: Add front and back card photograph support** - Excluded from v1.
  - Acceptance: reopens only with a reviewed schema and storage design per item 24.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-183: Add email and SMS reminders** - Not required in v1.
  - Acceptance: reopens only under a reviewed design per item 57.
  - Depends on: MC-073
  - Suggested runner: OpenCode

- [ ] **MC-184: Add continuous Family Finance synchronization** - Excluded by the independence decision.
  - Acceptance: would require reversing `DECISIONS.md`; the one-time-import decision stands per items 37-38.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-185: Add spending-ledger ingestion, bank login, payments, applications, booking, redemption, and automatic claims** - Excluded by product scope.
  - Acceptance: stays excluded; eligibility rules and manual counters remain the boundary per item 9.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-186: Add generalized affiliate stacking with explicit uncertainty and complete purchase-route optimization** - A later addition beyond the current disclosure-only optimizer.
  - Acceptance: reopens only with reviewed evidence rules per item 120.
  - Depends on: MC-101
  - Suggested runner: Manager

- [ ] **MC-187: Generalize network-inherited and unusual boarding-pass-triggered benefits beyond the pilots** - Later additions; the pilots come first.
  - Acceptance: pilot implementations are active before generalization per item 120.
  - Depends on: MC-068, MC-069
  - Suggested runner: OpenCode

- [ ] **MC-188: Implement general encrypted custom fields and notes** - Requires a reviewed schema before exposure.
  - Acceptance: schema review (documented) completes first; current vault remains schema-allowlisted per item 23.
  - Depends on: none
  - Suggested runner: Manager

- [ ] **MC-189: Add optional manual realized-value totals** - Kept disabled by default so this does not become a spending ledger.
  - Acceptance: if built, defaults to disabled and never aggregates spend per item 55.
  - Depends on: MC-107
  - Suggested runner: OpenCode

## Done

- [x] **MC-190: Foundation local alpha** - Loopback FastAPI application, signed installation identity, deterministic port resolution, public dashboard, synthetic demo catalog, and offline test suite.
  - Acceptance: `PROJECT_STATUS.md` "Completed" and clean-clone evidence `c037ccf`.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-191: Versioned public catalog loader/API** - Stable offering identity, temporal rules, evidence governance, and API with synthetic tests.
  - Acceptance: `coordination/tasks/catalog-001.md` completed.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-192: Immutable candidate and diff store** - Needs-review-only candidates, deterministic diffs, append-only review decisions.
  - Acceptance: `coordination/tasks/candidate-review-001.md` completed; 26 tests and re-review.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-193: Resumable offline research queue** - SQLite job queue with leases, honest transitions, and bounded listing; no network I/O.
  - Acceptance: `coordination/tasks/research-queue-001.md` completed; 24 tests.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-194: Deterministic traceable Q&A** - Bounded interpreter over approved public records with citations; no LLM required.
  - Acceptance: `coordination/tasks/qa-001.md` completed; 24 tests and rendered checks.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-195: Purchase-route optimizer core** - Pure ranking engine with separate value classes and affiliate-neutral scoring; not yet UI-exposed.
  - Acceptance: `coordination/tasks/optimizer-001.md` completed; 24 tests and review.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-196: Encrypted vault core** - Argon2id wrapping, AES-GCM records, envelope authentication, locking, backups, lifecycle, auto-lock, reauthentication, one-use reveal authorization.
  - Acceptance: `coordination/tasks/vault-001.md` and `vault-claude-final-001.md`; 49 focused tests and final Sonnet review.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-197: One-time JSON manifest import CLI** - Strict manifest parsing, atomic batch persistence, optional OS-keyring unlock, count-only integrity verification.
  - Acceptance: `coordination/tasks/release-import-001.md`; Claude Opus approval; owner-authorized migration completed.
  - Depends on: none
  - Suggested runner: Manager

- [x] **MC-198: Optional Family Finance companion launcher and setup guide** - Data-isolated companion launch and bundled setup documentation.
  - Acceptance: `coordination/events.jsonl` `family_companion_verified`; 206 Python and 47 JS tests.
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

- [x] **MC-203: Rendered and independent review verification** - Desktop/mobile and dark/light checks plus DeepSeek, Terra, and Claude reviews with no unresolved High/Medium findings.
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
