# Project Status

Last updated: 2026-08-07

## Current milestone

Local alpha: reviewed public-data foundations and isolated private-vault core.

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
- Optional, data-isolated Family Finance launcher and bundled setup guide.
- Discovery-only pilot source map for Tata Neu HDFC Infinity and HDFC Regalia
  Gold. No real claim has been activated.
- Rendered desktop/mobile and dark/light checks for the public dashboard and
  companion flow; DeepSeek module reviews and a separate Terra companion
  follow-up report no unresolved High/Medium findings for completed public-data
  modules and the companion launcher.
- Final Claude Sonnet vault review reports no High/Medium finding; its three Low
  cleanup suggestions were applied and passed 49 focused vault tests.
- The complete initial 120-question decision matrix, later owner revisions, and
  video/purchase-optimizer ideas are persisted in repository documentation.
- Clean clone of commit `2bb07a0` completed locked setup, 189 tests, and package
  build; Family Finance companion commit `e90f073` is also locally verified.

## Next planned slice

- Expose synthetic-only candidate review, research queue, and optimizer
  contracts through protected local API/UI surfaces.
- Keep real source retrieval, real-card entry, remote identity pinning, and
  publication behind their separate gates.

## Not yet safe

- Do not enter real card data. The vault core is independently reviewed, but no
  protected vault API or real-card UI is enabled.
- No live source adapter or scheduler is connected to the network. The queue is
  offline orchestration only, and the catalog contains synthetic facts only.
- The optimizer core is not exposed through the UI and cannot open purchase or
  affiliate routes.
- Family Finance performs a privacy-preserving reachability check only; signed
  companion identity pinning remains a later gate.
- One-time encrypted import, notifications, Rover verification, and publication
  readiness are not implemented.
- No public remote, push, or publication has been performed.

## Next delivery gate

Complete a synthetic-only UI/API contract for the reviewed candidate, queue,
and optimizer cores, with rendered and API tests. Real source retrieval and
real-card entry stay behind separate gates.
