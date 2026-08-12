# Decisions

## Derived catalog index keeps JSON authoritative — 2026-08-12

- The normalized quantity and reward JSON remains the reviewed, diffable source
  of truth. A SQLite index is only a runtime projection under the ignored data
  root and is rebuilt atomically by one builder.
- The index stores a fingerprint of the catalog inputs. A changed source makes
  the index stale and unusable until rebuilt; query code opens it immutably and
  read-only.
- Ranking accepts an explicit category, metric, and unit so unlike quantities
  are never compared. Missing quantities, missing earning rates, and null
  reward valuations remain unknown and are counted as excluded candidates, not
  converted to zero.

## Family Finance unlink and integration removal — 2026-08-11

- On 2026-08-11, the owner required MyCard Benefits and Family Finance to be
  fully unlinked. The Family Finance repository was inspected and verified to
  contain no MyCard references.
- MyCard's remaining pairing and companion surfaces were removed. The earlier
  Family Finance pairing, import, count-bridge, and companion-launch decisions
  below remain only as historical records and do not describe current
  capability.

## Owner review rule and first local activation — 2026-08-10

- The owner changed the catalog activation rule: one dated human approval is
  sufficient at every review tier. Enhanced, ambiguous, and high-impact tiers
  remain risk and UI context; a second independent human review is recommended
  when available but is not mandatory.
- Agents cannot approve candidates, authors cannot approve their own work, and
  approved evidence must still be current, attributable, and supported by the
  exact public source metadata.
- The owner approved the narrow Tata Neu Infinity HDFC Bank RuPay Select
  domestic lounge voucher milestone for local activation. This is the only real
  benefit activated by this change; no private vault data, live provider call,
  remote push, or public publication is included.

## Fresh-install vault diagnosis — 2026-08-10

- A safe explicit data root whose vault target is absent must remain a truthful
  `vault_missing` first-run state. The shared path predicate may tolerate a
  missing trailing target only after checking all existing prefixes for
  symlinks, junctions, reparse points, and other path-swap hazards. Unsafe or
  ambiguous locations remain `generic`; a readable keyring with no vault
  remains `wrong_data_dir`.

## Consumer benefit candidate pack remains review-only — 2026-08-10

- The BookMyShow, DBS debit, and HDFC Millennia reports are converted only to
  offline public research manifests and immutable `needs_review` candidates.
  No candidate is active, approved, or a substitute for the official body.
- Because the reports contain no local official-body captures, evidence uses a
  labeled reproducible snapshot-manifest hash rather than a fabricated body
  hash. A later human review must fetch or otherwise validate the exact source
  before activation.
- DBS identity expansion is additive: `dbs-debit` remains an ambiguous
  compatibility placeholder and exact benefits attach only to the four exact
  public variants established by the report. No private ownership or provider
  state is involved.

## Consumer acceptance overrides technical release evidence — 2026-08-10

- The 221-row `TASKS.md` register has 165 technically checked tasks, 18 active
  or reopened by owner testing, 20 `BLOCKED_OWNER`, 8 `BLOCKED_EXTERNAL`, and
  10 `DEFERRED_POST_V1`. MC-209 and MC-210 remain closed analyses.
- Exact head `c6a9081` retains its passed technical evidence, but the owner's
  live walkthrough is authoritative for product acceptance and rejected the
  maintainer-first dashboard. It must not be described as release-ready.
- Normal navigation becomes consumer-first. Sources, Updates, Research Queue,
  candidate review, and similar operations move behind explicit Maintainer
  mode. Privacy, provenance, and financial education use progressive
  disclosure at the relevant action instead of dominating Home.
- MC-033 is the core one-use authorization. It is not a browser plaintext-reveal
  feature. MC-034 and MC-035 remain blocked. MC-211 and MC-212 require
  owner-confirmed real offering mappings and coverage.
- The active benefit catalog contains the single owner-approved Tata Neu
  Infinity domestic lounge voucher rule. Public product identities and all
  other research candidates are not active benefits; live adapters/provider
  execution, further candidate activation, merge, remote push, and publication
  remain separately owner-gated.

## Real-browser bootstrap Origin policy — 2026-08-10 (historical; superseded 2026-08-11)

- Before the 2026-08-11 unlinking, the non-mutating
  `GET /api/v1/private/unlock/bootstrap` and `GET /api/v2/pairing/bootstrap`
  routes were allowed to omit `Origin` for a same-origin browser fetch, but
  still required one loopback `Host`, `Sec-Fetch-Site: same-origin`, and
  `Sec-Fetch-Mode: cors`.
- At that time, a present Origin was validated and tied to the loopback Host.
  Duplicate, forwarded, hostile, malformed, cross-site, none, non-cors, and
  non-loopback metadata was rejected before a capability was issued. Mutating
  POST routes retained exact Origin/Host, one-use CSRF, and existing body/state
  checks.
- Bootstrap successes and errors remained `no-store`/`no-cache`; the only
  bootstrap capability exposed was the short-lived process-local CSRF token.
  Browser fetches remained standard and did not manufacture an Origin header.

## Pairing issuance and rotation owner gate — 2026-08-10 (historical; superseded 2026-08-11)

- Before the 2026-08-11 unlinking, MyCard pairing issuance was POST-only. The
  legacy `GET /api/v2/pairing` route had been non-mutating and had returned an
  uncached method rejection.
- Local issuance and rotation had required a fresh one-use process-local CSRF
  bootstrap token, exact matching loopback Host/Origin, and same-origin Fetch
  Metadata. Validation had completed before a request body was read or pairing
  state was changed. Pairing responses and errors had remained
  `no-store`/`no-cache`.
- The Settings actions had displayed a code only in the current page. They had
  never put it in a URL, log, browser storage, or clipboard, and had explained
  its short lifetime and one-time use.
- Before removal, `/api/v2/pairing/consume` had been the separately configured
  Family Finance protocol boundary: its one-time credential, exact-origin
  binding, replay, expiry, transcript, and state validation had been unchanged.
  The Family Finance counterpart had remained separately gated and had not been
  integrated. The pairing protocol and counterpart were removed on 2026-08-11
  under the unlink decision above.

## Accepted product decisions — 2026-08-06 (historical; superseded for Family Finance integration)

- The Family Finance, companion, and import decisions in this entry were
  subsequently superseded and removed on 2026-08-11; the bullets below preserve
  what the owner accepted at that time.
- The owner accepted the recommended defaults from the initial product
  questionnaire except where a later decision explicitly replaces one.
- Questionnaire item 40 was confirmed: the phrase “Book My Short Accredits”
  means BookMyShow offers or credits.
- Unattended agents may continue while the owner is offline. They still may not
  bypass authentication, CAPTCHA, access controls, robots restrictions, or rate
  limits; a blocked source is paused and reported instead.
- Name: MyCard Benefits; repository slug: `mycard-benefits`.
- MIT-licensed, local-first, India-first/global-ready, English/localization-ready.
- Public reviewed benefit catalog plus private encrypted local card vault.
- Full card fields are supported locally; issuer credentials and OTPs are not.
- Agents never receive payment secrets; reveal/copy is a human-facing action.
- At that time, Family Finance retained its existing Cards page and remained
  fully standalone.
- Companion launch had been optional and had opened separately; absence had
  shown setup docs.
- Existing Family Finance cards could be imported once through an encrypted,
  previewed bundle; no continuous synchronization had followed.
- The companion import contract had been transport-agnostic and local-only:
  previews had exposed masked field comparisons, approval had been bound to the
  exact bundle, the destination write had completed before import state was
  recorded, and source cleanup had been a later distinct approval. A failed
  destination write had left the import replayable and had not authorized
  cleanup.
- No count bridge had been enabled at that time.
- Theme had remained browser-local under `docs/THEME-CONTRACT.md`; it had not
  been part of the vault or identity contracts.
- Remote access could use an owner-chosen authenticated external launcher or
  gateway, never a widened MyCard bind. MyCard did not identify, configure, or
  depend on that external tool.
- Source work may run unattended but may not bypass CAPTCHA, authentication,
  robots restrictions, access controls, rate limits, or terms.
- Deterministic behavior works without an LLM. Paid calls require explicit
  provider configuration and budget.
- Expired benefits remain as clearly historical structured facts.
- Pilot offerings: Tata Neu HDFC Infinity and HDFC Regalia Gold.
- Create and verify locally first; public remote creation/push is a later gate.
- Planned-purchase optimization compares whole routes (portal, coupon,
  issuer/network/merchant offer, card earn, milestone, and redemption) without
  becoming a spending ledger or executing a purchase.
- Guaranteed, conditional, and estimated values remain separate; unknown
  stackability is never inferred.
- Affiliate links are disclosed, hideable, paired with an official link, and
  cannot influence recommendation ranking.

## Companion import recovery — 2026-08-09 (historical; superseded 2026-08-11)

- The companion import had been a durable pending/committed transaction. A
  stable destination idempotency key and receipt had been supplied to the local
  writer; retries had queried destination commitment before writing. The
  transaction had bound the exact encrypted-manifest hash, preview/approval,
  and source and destination signed identities. Coordinators sharing a state
  path had serialized through an OS advisory lock. Source cleanup had remained
  a separate approval and had not been executed by MyCard's import flow.
- The integration and these companion/import surfaces were subsequently removed
  on 2026-08-11; this entry is historical only.

## Initial private migration and publication — 2026-08-07 (historical)

- The owner had authorized the first public repository push and synchronization
  of the optional Family Finance companion commit. That integration was
  subsequently removed on 2026-08-11 under the unlink decision above.
- The owner-authorized Drive inventory had been the source for the initial
  private migration. Newer consolidated credit/debit entries had been treated as
  current; legacy `CC`/`Dc`-only entries had been retained as archived history.
- Cardholder names from source metadata had been represented by private owner
  aliases where needed. Ambiguous product, owner, duplicate, and lifecycle
  matches had stayed marked for confirmation rather than being guessed.
- The migration had extracted card/product identity only. PAN, CVV, PIN,
  account numbers, scan bytes, and full document text had not been copied.
- This workstation had used an OS-keyring-generated vault passphrase. Real
  manifests, receipts, vault files, and backups had remained ignored and local.
- Claude Opus had been eligible for large end-to-end public-code tasks; its lower
  subscription quota had been a scheduling constraint, not a capability
  assumption.

## Useful catalog and protected UI — 2026-08-07

- Public product identity and private ownership remain separate. The India
  starter catalog may contain the public variants represented by the local
  import, but it never records who owns them or how many instances exist.
- My Cards may display non-secret envelope metadata only. The app stays
  loopback-bound, opens the vault through the OS keyring, returns a bounded
  allowlist of fields, and forbids caching. An owner-selected external access
  tool is responsible for any remote authentication and is not integrated into
  MyCard.
- Reveal/copy remain disabled. Owner aliases, exact expiry, uncertain variants,
  and replacement chains require explicit human confirmation rather than
  inference; current protected controls still never expose their plaintext.
- MyCardExpert and SaveSage are discovery-only sources. Current official issuer,
  administering-party, network, or merchant terms must support every confirmed
  benefit before the existing human review gate can activate it.
- Free or subscription-included runners are preferred when verified capable;
  primary integration and independent review remain required.

## Technical defaults

## Morning release consolidation — 2026-08-10

- Protected card management is exposed only through the human-facing local
  UI. Each write is reauthenticated with the current passphrase; decrypted
  values never enter a response, log, prompt, catalog, or agent boundary.
- Discovery cursors are opaque, one-use, short-lived, and bound to the public
  catalog revision, query, browser session, and public projection of local
  ownership. A changed result set requires a fresh search.
- MC-206 consolidation stays synthetic-only in this release. Compatible
  observations of one card merge before the single vault batch; contradictory
  fields are counted as explicit local-review conflicts. Parser limits,
  including XLSX compression ratio, are approval-bound. Successful applies
  write a durable count/hash-only receipt after commit.
- Refresh and research status remain local read-only views; scheduling and
  execution remain explicit offline CLI/fixture workflows. No live provider,
  approval, catalog promotion, merge, or publication is implied.

## MC-214 refresh correction — 2026-08-09

- Refresh scheduling is admission-scoped, not work-row-scoped. A daily source
  counter owns request, byte-reservation, and provider-token units; cadence and
  pause/block state carry across daily counter rows. A lease completion records
  the observation and source-wide state transition in one SQLite transaction.
- Refresh candidates enter only through the release-bound `CandidateStore` and
  remain `needs_review`; repeated identical payloads are suppressed by the
  immutable candidate payload. Read-only status and dry-run planning use an
  existing ledger snapshot and do not initialize storage.

- Python/FastAPI, SQLite/SQLAlchemy/Alembic, Jinja and browser JavaScript.
- Human-authored YAML catalog compiled to deterministic JSON snapshots.
- AES-256-GCM data encryption; Argon2id passphrase wrapping; optional OS keyring.
- Stable public offering slug plus immutable UUID; private UUIDv7 card instances.
- Source agents propose; independent reviewers approve.
- Candidate-store migrations are an explicit maintenance CLI action, never a
  web-app startup action. They target only the app-owned candidate store and a
  fixed app-owned backup child; on Windows, guarded handles and file identities
  bind backup, validation, write, lineage, and rollback to the same objects.
  Platforms without that facility fail closed rather than falling back to
  pathname validation.

## Catalog integrity — 2026-08-07

- **Public benefit schema coverage — 2026-08-09**: typed optional rule structures extend the
  compatible benefit record without changing existing positional fields. Categories, owners,
  conditions, earn/conversion details, valuations, value classes, and inheritance are explicit;
  network inheritance requires `opt_in: true` and a date range. A valuation must be a named range
  tied to a redemption path. Invalid or ambiguous structures fail closed, and synthetic fixtures
  remain non-production.

- Product relationships (renamed, legacy, cloned, reskinned) are modeled as
  explicit reviewed edges in a `relationships/` catalog directory with required
  evidence assertions and human review records. The loader validates graph integrity
  and evidence provenance: no self-references, no dangling offering references,
  no duplicate edges, DAG cycle enforcement for renamed/legacy edges, and approved
  relationships require approved medium/high-confidence evidence assertions. Names
  never auto-infer inheritance (enforces questionnaire decision item 14).
- Benefit rules are temporal and versioned (`rule_version`, `supersedes`).
  `end_date_known` is strictly derived from `effective_to` (`effective_to is not None`),
  preventing contradictory values. Expired and superseded rules remain stored as historical
  records; supersession links require matching offering_id, matching benefit_type, strictly
  increasing rule_version (`rule_version > prior_rule.rule_version`), and DAG cycle prevention.
  With `include_historical=true`, active rules still respect `as_of` date range filtering,
  while historical/superseded rules remain discoverable as history.
- Every catalog assertion requires complete provenance metadata: source URL, content SHA-256 hash,
  retrieved timestamp, confidence level, review state, and approved human reviews. The numeric
  `source_tier` (1–6) is strictly derived at runtime from `source_policy_class` and exposed in API
  responses; it is omitted from authoring JSON schemas. Loader enforces that no approved assertion
  lacks full provenance and rejects tier 6 (`discovery_only`) sources from ever holding an `approved` review state.

## Linked child records and remote-access UI copy — 2026-08-07

- The private vault has no SQLAlchemy/Alembic layer despite the architecture
  blurb above; card records are an encrypted, AEAD-authenticated JSON envelope
  with no database. Non-secret linked child records (Priority Pass, lounge
  credentials, memberships, vouchers, card-linked credentials) are added to that
  same envelope as an additive `child_records` list, protected by the existing
  envelope MAC rather than per-field encryption, since none of their fields
  are secret. Absent `child_records` on an older envelope means zero child
  records, not a parse failure, so an existing local vault opens unchanged
  and upgrades in place on its next write.
- Loopback-only startup and the remote-access boundary are stated in the app
  itself (a Settings panel), not only in docs, so a non-technical user sees
  the boundary without leaving the dashboard.
- **Manager-review correction, same day**: a child record has no free-text
  display label at all — the browser always derives the shown name from the
  allowlisted `kind` enum, closing the path by which a real membership
  number or other secret could have been typed into a "safe display label"
  field and rendered back in cleartext. The private-cards API now also
  strictly enum-validates `kind`/`lifecycle`, uuid-validates every
  identifier, and fails closed (503) on a child record whose `parent_card_id`
  does not match its containing card or that duplicates another child's id —
  previously only the vault's own disk-parsing layer enforced this, not the
  HTTP boundary itself, so a bug in a future reader implementation would not
  have been caught. The exact child `expiry_date` no longer crosses the
  HTTP boundary in any form; the API computes a bounded `expiry_signal`
  (`expired` / `expiring_soon` / `active`) server-side and that is the only
  time-related value ever sent to the browser.

## Luna reconciliation batch — 2026-08-09

- Reconciliation is a protected local service, not a browser write endpoint.
  Preview payloads use anonymous aliases, catalog offering IDs/dimensions,
  lifecycle labels, bounded expiry signals, and explicit ambiguity markers.
- A human disposition is required for every proposed change. Confirm, defer,
  reject, and correct are distinct auditable actions; correct requires a new
  complete proposal and never infers missing fields.
- Applying a disposition requires fresh vault passphrase authorization bound to
  the exact action, record, final proposal digest, and current vault revision.
  The one-use authorization is server-side and consumed on use; confirm/correct
  validate complete replacement lineage before atomic persistence, while
  defer/reject append only bounded authenticated workflow events and do not
  mutate card state. Ambiguity is an allowlisted code with safe UI copy, never
  arbitrary text. MC-011 through MC-015 and MC-017 remain pending owner
  confirmation and this correction remains subject to independent review.

## Luna reconciliation correction 2 — 2026-08-09

- Protected reconciliation authorizations are canonical mutation envelopes,
  binding expected old values, vault revision, exact new fields, replacement
  lineage, and authenticated metadata.
- Unknown lineage remains non-destructive; changing it requires a separate
  explicit correction with no lineage ambiguity and its own authorization.
- Preview is session-bound and exposes only identifiers resolved from the
  protected local vault; unchecked caller identifiers are rejected silently.

## Reminder correction — 2026-08-09

- Reminder derivation uses a dedicated vault-internal reader with explicit
  derived inputs only. Unsupported due-date/autopay fields remain unknown;
  archived cards and child records never produce signals or calendar events.
- Reminder preferences are bounded local state in the data folder and require
  the existing OS-keyring vault unlock control for production mutations.
- Calendar exports use deterministic stable IDs, UTC `DTSTAMP`, all-day
  `VALUE=DATE` events, CRLF serialization, escaping, and folding. Scheduler
  failures/conflicts retain fixed generic copy without ownership data.
- Catalog conflicts now enter the local reminder response as deterministic,
  fixed-copy notification plans keyed by release, public offering, and rule
  identifiers. Unresolved and `needs_review` pairs remain review-only; no
  eligibility decision or automatic resolution is performed.
- Conflict resolution also validates the target offering's effective date at
  the requested `as_of`, alongside target rule status/interval and compatible
  catalog scope. Missing, inactive, future, expired, or incompatible targets
  remain explicit review-only declarations rather than ordinary resolutions.

## Consumer catalog contract migration — 2026-08-10

- The benefit list, offering-detail benefit, and discovery consumer payloads now
  expose only the safe state vocabulary `verified`, `check_before_use`, and
  `sources_differ`. Internal `status`, `review_tier`, evidence `review_state`,
  and discovery `evidence_status` are removed from those boundaries. The scalar
  governance values `needs_review`, `superseded`, `historical`, `approved`, and
  `stale` are forbidden in their response bodies.
- The replacement contract adds consumer `state`, evidence state, conflict
  state, `not_claimed`, and `source_divergence`, while retaining effective dates
  and provenance pointers. This is deliberate: consumer routes must not carry
  governance vocabulary that can mislead a reader about their own card through
  a label such as `needs_review`.
- The exact contract regression intentionally holds out pre-existing fields
  `category`, `owners`, `conditions`, `earn`, `conversion`, `valuations`,
  `value_class`, and `inheritance`. These fields were already declared on
  `BenefitSummary` and serialized by `_benefit_summary` before this migration,
  but were absent from the prior locked test. Their presence is reported as
  pre-existing drift rather than silently approved into the new lock; each
  requires separate approval before inclusion.
- Relationship summaries retain their existing reviewed-edge contract in this
  bounded change; the migration lock covers the benefit consumer surfaces named
  above.

## Lifecycle preview boundary correction — 2026-08-09

- The lifecycle reconciliation preview remains an in-memory synthetic service
  seam and is not mounted in the normal application. Any future real flow
  requires the existing protected reauthentication/CSRF boundary and a new
  explicit human gate.
- The seam accepts only fixed synthetic ownership, canonical bounded IDs,
  exact enum-backed variant dimensions, bounded human display labels, and known
  keys; it rejects nested, numeric, PAN/account/secret-like, control/format,
  private, replay, and unknown values before persistence. Every success and
  error response is marked `Cache-Control: no-store`, `Pragma: no-cache`, and
  `Expires: 0`; response variants and lineage events use closed typed schemas,
  and errors never echo submitted values.

## MC-007 passphrase-only browser access — 2026-08-09

- A passphrase-only vault may be unlocked from My Cards only through a
  loopback-bound protected endpoint with one-use bootstrap CSRF, exact browser
  headers, bounded exact JSON, generic rate-limited failures, and no-store.
- The browser receives only a process-local in-memory session cookie. Idle,
  absolute, explicit-lock, expiry, and process-restart boundaries lock it;
  unlock never authorizes reveal, copy, or card mutation actions. Zeroization is
  best effort because Python/browser immutable allocations cannot be promised
  forensic erasure.

## MC-007 manual-unlock keyring fallback — 2026-08-10

- If keyring access fails while the vault file is present, private cards keep a
  truthful `keyring_unavailable` response and the protected manual passphrase
  flow remains available. If both keyring access and the vault file are absent,
  the response is `vault_missing`; readable keyring state with no vault remains
  `wrong_data_dir`.

## MC-007 raw-header correction — 2026-08-10

- Unlock and lock inspect raw ASGI header tuples rather than a merged framework
  header view. Duplicate, case-variant, comma-joined, or otherwise ambiguous
  CSRF and media framing are rejected before token consumption, rate accounting,
  body receipt or parsing, passphrase handling, and vault access. The lock route
  applies the same raw CSRF and ambiguous-media rejection without receiving a
  request body.

## Rebuild consumer contract and staged deletion — 2026-08-10

- After review, the pre-existing consumer fields `category`, `conditions`,
  `value_class`, `earn`, `conversion`, and `valuations` are explicitly approved
  in the locked response contract. They were not silently inherited from the
  old response shape. `owners` and `inheritance` are removed because they are
  governance/internal metadata rather than cardholder benefit content.
- `earn`, `conversion`, and `value_class` currently reach the legacy page as
  raw JSON or a snake_case token. That is recorded Stage 4 presentation work;
  the contract migration does not launder those values or claim the redesign
  is complete.
- The owner authorized the later data operation in his exact words: "i approve
  everything include wipe". This records authorization for permanent deletion
  of every private card record, without backup or recovery, while leaving the
  public catalog and committed research untouched. The wipe is Stage 2b and
  remains blocked until the Stage 2a machinery deletion is independently
  reviewed and approved; no wipe is performed by this decision entry.
- The self-contained design artifact is tracked at
  `docs/design/mycard-design.html`; it is the byte-for-byte source for the
  four-screen redesign and takes precedence over prose descriptions where they
  differ.

## Device-held vault bootstrap — 2026-08-11

- The normal My Cards path uses a high-entropy internally generated device key
  with the existing vault `create()` and `open()` methods. The user does not
  choose or see a vault credential during onboarding.
- The OS-keyring boundary is the first storage location. When it reports
  unavailable support, the guarded ignored local fallback is
  `<data-dir>/private/device-key`; the key value never enters logs, tracked
  files, prompts, or API responses.
- The default setup/unlock/sidebar controls and card-action password fields are
  removed. Card metadata actions use the device-held key; the existing
  `reveal-authorize` endpoint remains the separate credential gate for full PAN,
  CVV, and PIN reveal work. Cryptographic parameters and the Argon2id envelope
  are unchanged.
- Fresh empty-data browser verification created and opened the vault without
  reading or changing any existing card record. The first-reveal modal remains
  intentionally outside this slice.
