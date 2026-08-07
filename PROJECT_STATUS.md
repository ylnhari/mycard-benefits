# Project Status

Last updated: 2026-08-07

## Current milestone

Published local-first alpha: reviewed public-data foundations plus a narrow,
encrypted private-import path.

## Completed

- Clone-safe loopback FastAPI application, signed installation identity, port
  resolution, public dashboard, synthetic demo catalog, and offline test suite.
- Versioned public catalog loader/API, source policy, evidence governance,
  immutable candidate/diff store, and resumable SQLite research queue.
- Deterministic public catalog Q&A API/UI and a pure purchase-route optimizer;
  neither requires an LLM or private card values.
- Encrypted vault core with Argon2id key wrapping, AES-GCM records, complete
  envelope authentication, bounded persistence, locking, backups, lifecycle,
  auto-lock, reauthentication, and one-use reveal authorization.
- Strict one-time JSON manifest import with atomic batch persistence,
  cleartext-identifier validation, optional OS-keyring unlock, and count-only
  integrity verification. The owner-authorized local migration completed; its
  data and receipt remain ignored.
- Optional, data-isolated Family Finance launcher and bundled setup guide.
- Discovery-only pilot source map for Tata Neu HDFC Infinity and HDFC Regalia
  Gold. No real claim has been activated.
- Rendered desktop/mobile and dark/light checks for the public dashboard and
  companion flow; DeepSeek module reviews and a separate Terra companion
  follow-up report no unresolved High/Medium findings for completed public-data
  modules and the companion launcher.
- Final Claude Sonnet core review and Claude Opus importer review report no
  unresolved High/Medium finding after remediation and live compatibility
  verification.
- The complete initial 120-question decision matrix, later owner revisions, and
  video/purchase-optimizer ideas are persisted in repository documentation.
- A dependency-cold clean clone of commit `c037ccf` passed locked setup without
  the optional keyring extra, Ruff, strict mypy, all 201 tests, and both package
  builds.
- The public MyCard repository is live at
  `https://github.com/ylnhari/mycard-benefits`; Family Finance companion commit
  `e90f073` is pushed and synchronized on its public `main` branch.

## Next planned slice

- Expose synthetic-only candidate review, research queue, and optimizer
  contracts through protected local API/UI surfaces.
- Add a protected human-facing private-card API/UI over the reviewed vault;
  the current CLI remains the only real-card write surface.
- Keep real source retrieval and remote identity pinning behind their separate
  gates.

## Not yet safe

- Do not enter or reveal real card data through the browser/API. The reviewed
  local CLI is the only supported private write path in this release.
- No live source adapter or scheduler is connected to the network. The queue is
  offline orchestration only, and the catalog contains synthetic facts only.
- The optimizer core is not exposed through the UI and cannot open purchase or
  affiliate routes.
- Family Finance performs a privacy-preserving reachability check only; signed
  companion identity pinning remains a later gate.
- Family Finance one-time import, notifications, and Rover verification are not
  implemented. The new Drive-manifest import is local to MyCard Benefits and is
  not a continuous synchronization bridge.
- Initial publication and companion synchronization are complete. Future
  catalog publication, releases, and remote-access changes retain their own
  review gates.

## Next delivery gate

Complete a synthetic-only UI/API contract for the candidate, queue, and
optimizer cores. Protected real-card browser/API controls remain a later gate.
