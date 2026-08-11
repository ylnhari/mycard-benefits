# Initial questionnaire decisions

Date accepted: 2026-08-06

The owner accepted every recommended default in the initial 120-item product
questionnaire, except where a later instruction revised a product or commercial
boundary. This is a compact, durable decision matrix rather than a chat
transcript. `PRODUCT_REQUIREMENTS.md`, `DECISIONS.md`, and `SECURITY.md` remain
normative when wording differs.

An accepted decision is product intent, not a claim that the feature is already
implemented. `PROJECT_STATUS.md` and `ROADMAP.md` are authoritative for delivery
state. Question numbers are stable identifiers; withdrawn decisions are not
renumbered.

## Product and release

1. Use **MyCard Benefits**, repository slug `mycard-benefits`, and the word
   “card” instead of “Codd.”
2. Support one person and households through local owner profiles.
3. Start with a responsive locally hosted desktop/mobile browser UI; remote
   phone use goes through an authenticated gateway.
4. Defer PWA installation until the vault and catalog are stable.
5. Start in English with localization-ready text, dates, and currencies.
6. Target WCAG 2.1 AA, keyboard and screen-reader use, reduced motion, and
   light/dark themes.
7. Use the MIT license.
8. Revised later: affiliate routes may exist, but must be disclosed, hideable,
   paired with an official link, and unable to affect ranking. No ads or sale of
   user data.
9. Exclude spending-ledger ingestion, bank login, payments, applications,
   booking, redemption, and automatic claims; eligibility rules and manual
   counters remain in scope.
10. The first real-data release target is end-to-end coverage of Tata Neu HDFC
    Infinity and HDFC Regalia Gold, including indirect and network benefits.

## Card identity and lifecycle

11. Give every public offering a readable stable slug and immutable UUID.
12. Model country, issuer, family, tier, co-brand, network, form, issuance
    cohort, and edition.
13. Treat network variants as distinct but related offerings.
14. Use a reviewed relationship graph for renamed, legacy, cloned, or reskinned
    products; never infer inheritance from names alone.
15. Store an uncertain match as `unverified_match`, show candidate variants,
    and withhold unsupported entitlements.
16. Allow one owner to hold multiple instances of the same offering.
17. Represent primary, add-on, supplementary, physical, virtual, and tokenized
    cards as separate linked instances.
18. Support applied, pending, active, frozen, lost, stolen, expired, renewed,
    replaced, upgraded, downgraded, closed, and archived states.
19. Preserve renewal, reissue, upgrade, downgrade, and network migration as
    immutable history joined by a private lineage identifier.
20. Retain archived cards until the user explicitly purges them.
21. Require typed confirmation and an encrypted-backup warning for permanent
    deletion.
22. Model Priority Pass, lounge credentials, memberships, vouchers, and
    companion credentials as child records of the issuing card.
23. The target supports encrypted custom fields and notes. The current vault
    remains schema-allowlisted; custom fields require a reviewed schema before
    exposure.
24. Do not store front/back card photographs in v1.

## Private vault and recovery

25. Default to a 10-minute idle lock and immediate lock on browser close or OS
    lock when the UI integration can observe those events.
26. Require a fresh, one-use confirmation for every PAN, CVV, or PIN reveal.
27. Attempt clipboard clearing after 30 seconds and explain OS/browser limits.
28. Mask secrets to the final four digits only.
29. Target a user-held recovery key and encrypted recovery export; there is no
    server-side reset.
30. Keep rotating encrypted local backups and manual encrypted export.
31. Do not add built-in cloud sync in v1; use user-controlled encrypted
    export/import between devices.
32. After expiry, loss, replacement, or closure, prompt to erase CVV/PIN while
    preserving non-secret lineage and history.
33. Log reveal, copy, edit, export, migration, and purge events locally without
    field values.
34. Retain private audit events for one year by default, configurable and
    purgeable.
35. Permit encrypted boarding passes, vouchers, enrollment confirmations, and
    membership documents with purpose, expiry, and retention controls; agents
    see metadata only.
36. Defend against casual household access, lost-device disk inspection,
    accidental logging, malicious catalog data, and network leakage. A fully
    compromised OS is outside the threat model.
## Benefit intelligence

39. Cover rewards, conversions, movies, hotels, dining, cashback, vouchers,
    meet-and-greet, lounges, Priority Pass, fee waivers, milestones, forex,
    fuel, insurance, golf, concierge, subscriptions, transfers, and railway
    lounges.
40. Confirmed: “Book My Short Accredits” means BookMyShow offers or credits.
41. Model base/accelerated earn, caps, exclusions, rounding, reversals, expiry,
    transfer ratios, increments, and redemption options.
42. Express point value as a range tied to a named redemption path, never one
    universal value.
43. Model spend conditions while letting the user mark `met`, `not_met`, or
    `unknown`; do not ingest transactions.
44. Permit one optional manually entered aggregate toward a spend threshold.
45. Include joining, renewal, annual-fee, fee-waiver, and milestone benefits.
46. Model monthly, quarterly, anniversary-year, and calendar-year counters and
    resets.
47. Let users record successful, failed, rejected, or skipped attempts without
    treating personal outcomes as global truth.
48. Keep personalized/login-only offers private and never publish them as
    general eligibility.
49. Preserve separate issuer, network, co-brand, merchant, and membership rule
    owners.
50. Model spend definition, MCC/merchant, channel, geography, currency, booking
    and use windows, registration, quotas, holder/transaction type, and
    exclusions.
51. Represent stacking as `allowed`, `not_allowed`, or `unknown`; never infer it.
52. Show verified active, needs review, upcoming, expired, withdrawn,
    conflicting, unverified, and personalized states.
53. Support historical and future “as of” questions through immutable versions.
54. Rank cards only with assumptions, uncertainty, caps, and exclusions visible.
55. Optional manual realized-value totals stay disabled by default so this does
    not become a spending ledger.
56. Remind for enrollment, benefit/voucher expiry, allowance reset, renewal,
    fee-waiver checkpoints, and expiring cards.
57. Use in-app reminders plus optional ntfy and calendar export; do not require
    email or SMS in v1.
58. For indirect benefits, show steps, evidence, document checklist, official
    link, deadline, and reminder; never upload automatically.

## Sources, automation, and governance

59. Prefer administering-party terms, then issuer, network, merchant, regulator,
    and finally discovery-only aggregator/community sources.
60. Publish independently written structured facts, identifiers, dates,
    conditions, URLs, hashes, and verification metadata—not copied pages,
    screenshots, logos, PDFs, or long terms text.
61. Keep raw fetched evidence in a restricted local maintainer store, outside
    the public repository and release.
62. Automate licensed feeds and admitted public sources conservatively; keep
    ambiguous/restrictive sources manual and exclude login/CAPTCHA/account-only
    sources.
63. Aggregators and forums may discover candidates but cannot verify or publish.
64. The owner wants unattended continuity. Safety revision: agents may continue
    while the owner is offline but never bypass authentication, CAPTCHA, access
    controls, robots rules, rate limits, or source terms. They pause and report.
65. Use source-specific cadence: daily for short promotions, weekly for active
    products, monthly for durable documents, and immediate recheck after change.
66. When evidence changes or disappears, move affected assertions to
    `needs_review`; never silently retain them as active.
67. Agents produce candidates; one independent human approves ordinary claims
    and two approve ambiguous/high-impact claims.
68. Preserve conflicting official assertions, explain the conflict, reduce
    confidence, and avoid positive eligibility promises.
69. Keep expired/discontinued benefits searchable as historical structured
    versions while raw evidence stays restricted.
70. Accept cards/corrections through structured pull requests with schema
    validation, sources, and conflict-of-interest disclosure.
71. Target acknowledgement of corrections/takedowns within seven days and hide
    demonstrably unsafe or infringing material pending review immediately.
72. Add licensed or affiliate feeds only through isolated adapters with licence
    and redistribution limits documented.
73. Commercialization remains a separate governance/legal decision; the later
    affiliate-neutrality rule in item 8 applies.

## Agents and question answering

74. Keep provider-neutral adapters for OpenAI, Anthropic, Gemini, and local
    models; none is required for core operation.
75. Deterministic parsing and search must work without an LLM key.
76. Paid model calls need explicit provider configuration, enablement, and
    budget.
77. Research agents may fetch admitted public sources, detect changes, parse
    candidates, run tests, and draft reviewable changes.
78. Agents never publish, log in, redeem, apply, purchase, upload private
    documents, access vault secrets, or override gates.
79. Agents may propose non-secret private metadata changes but apply them only
    after user confirmation.
80. Answers contain the direct result, eligible cards, steps, conditions,
    exclusions, effective dates, confidence, official links, and verified date.
81. Stale/incomplete evidence produces `unknown` or `needs_confirmation` plus
    the official verification path.
82. First-class questions include what is usable now, which card works, how to
    claim, what expires, uses remaining, what changed, and why eligibility fails.
83. Conversation history is opt-in/local, encrypted when linked to private
    cards, and scrubbed of PAN/CVV/PIN.
84. A future optional local scheduler shows last run, next run, failures, and a
    pause control while the UI is closed.
85. Notify on failed/conflicting updates without revealing private ownership in
    notification text.
86. Persist roadmap, decisions, status, jobs, source registry, evidence, and
    append-only activity in the repository; issues may mirror but not replace it.
87. Route bounded public work to the lowest-cost capable worker; the primary
    owns intent, security, integration, and verification; workers never approve
    their own catalog changes.

## Dashboard and local use

88. Navigate among My Cards, Benefits, Compare, Expiring Soon, Updates, Sources,
    Research Queue, and Settings, with an overview landing page.
89. Prioritize urgent expiries/actions, available benefits, resets, uncertain
    card matches, and recent verified changes.
90. Add a card by selecting a canonical offering, confirming variant details,
    creating a private instance, and optionally adding encrypted fields.
91. Allow provisional missing offerings, but keep benefits unverified while an
    agent prepares a research candidate.
92. Benefit-first browsing shows eligible owned cards first and other public
    alternatives separately.
93. Every benefit provides How to use, Where to use, What to verify, and official
    action links.
94. Never submit applications or redemptions; open the official destination and
    provide instructions only.
99. Support an empty clone with useful empty/demo states and no required key or
    network service.
100. Target encrypted full backup, redacted JSON, public catalog JSON, and CSV
     for non-secret metadata.

## Engineering and delivery

101. Use option A: Python/FastAPI, SQLite, server-rendered HTML, and browser
     JavaScript modules.
102. Permit a modest audited, locked dependency set with security scanning.
103. Ship one-command Windows setup first, Linux/macOS instructions, and optional
     Docker rather than Docker-only installation.
104. Target SQLite for private operations, version-controlled YAML authoring,
     and immutable JSON catalog releases. The current alpha begins with JSON and
     adds database migrations before exposing private APIs.
105. Use numbered migrations, pre-migration backup, dry run, validation, and
     rollback documentation.
106. Expose a narrowly scoped loopback-only versioned `/api/v1` with generated
     schema documentation.
107. Implement source adapters as admitted plugins with fixtures, rate limits,
     and deterministic tests.
108. Provide a visible local job runner and documented Windows Task Scheduler
     integration.
109. Use the verified workspace port registry locally; clones get configurable
     fallback behavior and no dependency on this machine's path or port.
110. Gate on unit, API/schema, migration, parser, source-policy, vault,
     XSS/CSRF/path, redaction, end-to-end UI, mobile, accessibility, offline,
     migration, and clean-clone tests as their surfaces are introduced.
111. Keep live-source tests out of normal CI; use deterministic fixtures and
     separate non-blocking health checks.
112. Distribute catalogs as signed/versioned snapshots with checksums, atomic
     update, rollback, and last-known-good fallback.
113. Add no telemetry; diagnostics are explicit, redacted, and manually
     exportable.
115. Target protected `main`, reviewed pull requests, automated checks, and no
     force pushes.
116. Stop before remote creation or push; audit history and obtain explicit
     approval naming the destination and commit range.
117. Pilot Tata Neu HDFC Infinity and HDFC Regalia Gold with exact variants and
     indirect benefits.
118. Acceptance scenarios include renewal/replacement, loss, add-on cards,
     Priority Pass children, expired/conflicting offers, spend-gated lounges,
     boarding-pass benefits, and unknown networks.
119. Deliver independently usable milestones: foundation/security, inventory,
     catalog/evidence, benefit engine, agents/Q&A, live-source pilots, then
     public-release audit.
120. Later additions include complete purchase-route optimization, affiliate
     stacking with explicit uncertainty, network-inherited offers, and unusual
     boarding-pass-triggered benefits. They are captured in the requirements and
     idea log; none is an approved live catalog claim yet.

## Later owner revision: catalog review rule — 2026-08-10

The owner changed item 67's activation rule: one dated human approval is
sufficient at every review tier. A second independent human reviewer remains a
recommended risk-control for enhanced, ambiguous, or high-impact claims, not a
mandatory gate. Agents cannot approve candidates, and authors cannot approve
their own work.
