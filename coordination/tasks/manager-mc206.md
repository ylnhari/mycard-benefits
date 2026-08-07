# Manager task - MC-206 private inventory consolidation

Status: in progress
Worker: Manager
Branch: `manager/concurrent-integration`
Push authorized: no

Consolidate the owner's explicitly authorized local card sources into one
ignored, encrypted inventory without changing or repeatedly re-reading the
source systems. The inputs are the local Family Finance card data, the connected
Drive card workbook, and the mounted Drive card-document folders. Preserve raw
source values only inside Windows-user-bound encrypted snapshots. Any OCR or
source-to-catalog match is provisional until confirmed.

Implement an idempotent, non-destructive reconciliation/import path. It must
retain existing vault records and history, produce a count-only receipt, and
fail closed on conflicting or malformed source data. Add a validated `last4`
projection derived server-side from encrypted PAN data. The private API and UI
may return/render only a masked last-four value alongside the existing safe
envelope fields. They must never return full PAN, CVV, PIN, cardholder name,
expiry, raw OCR text, or local source paths.

Use synthetic fixtures for every tracked test. Verify the API allowlist,
`Cache-Control: no-store`, migration/backward compatibility, idempotence,
non-destructive behavior, secret redaction, and desktop/mobile plus dark/light
rendering. Run all repository gates, inspect the diff and unpushed history for
private values and paths, commit locally, and do not push or publish.
