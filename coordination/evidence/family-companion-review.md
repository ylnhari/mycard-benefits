# Family Finance companion review

Review date: 2026-08-06 to 2026-08-07

Scope: the optional launcher and setup guide in `family-finance-app`, compared
with this repository's integration and privacy boundaries. No finance data,
runtime database, backup, or browser storage value was delegated for review.

## Result

The final DeepSeek V4 Flash policy review and a separate Terra follow-up review
reported no unresolved High or Medium findings. The follow-up confirmed that
the original popup-blocker risk was resolved by creating the handoff window
synchronously in the click path before awaiting the health probe. The launcher:

- leaves the existing Family Finance Cards page and workflows intact;
- stores only an explicitly entered base URL in browser-local storage;
- accepts HTTP only for exact loopback hosts or literal Tailscale IPv4
  addresses in `100.64.0.0/10`, and requires HTTPS for other remote hosts;
- rejects credentials, paths, queries, fragments, and non-HTTP(S) schemes;
- probes only `/api/v1/health` with no body, cookies, credentials, cache, or
  referrer, and never references card/user data;
- severs the temporary handoff window's opener and installs a no-referrer
  policy before any remote navigation; direct guide links use
  `noopener,noreferrer`;
- uses an in-app setup form with invalid-input feedback and explicit clearing;
- opens setup documentation when unconfigured or unreachable and shows an
  error toast before the asynchronous failure fallback.

Rendered checks covered the Cards controls, invalid and valid configuration,
uninstalled fallback, successful launch to the running MyCard dashboard,
responsive stacking, accessible dialog semantics, cleanup, and no new browser
console errors. Browser checks also exercised synchronous successful navigation
and failure navigation to the bundled guide. The final complete suite passed:
207 Python tests and 51 Node tests, including the extracted pure URL-policy
boundary cases.

## Accepted gate

The no-CORS probe proves reachability, not destination identity; an unrelated
service on the configured origin could pass. This is disclosed in both setup
guides. Signed identity pinning is required before the integration is described
as verified, especially for remote URLs. No data is transmitted in the current
reachability-only design.
