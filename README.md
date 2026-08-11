# MyCard Benefits

Know what a card offers before you rely on it, while keeping your own card
records private on your computer.

MyCard Benefits is local-first: the public catalog records card products,
benefit evidence, dates, and review status; your encrypted vault holds your
private card records separately. There is no MyCard account, cloud copy, or
automatic sharing of card data.

**New here? Start with the [plain-language user guide](docs/USER-GUIDE.md).**
It explains setup, private vaults, benefits, recovery, and the features that
are not ready yet.

## Start a safe demo

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then use Windows PowerShell in this project folder:

```powershell
uv sync --locked
uv run mycard-benefits --demo
```

Open the local address printed by the command. The demo is clearly marked,
uses separate demo data, and never opens a private vault. Press `Ctrl+C` to
stop it. When your private vault is ready, start the regular app with:

```powershell
uv run mycard-benefits
```

The app listens only on `127.0.0.1` (this computer). A phone or other-device
setup needs an authenticated gateway or launcher that you control; it is
separate software and does not change the app's local-only bind.

## What is available now

- Search public card products; browse reviewed catalog material and inspect its
  conditions, dates, evidence, and review state.
- Use **My Cards** to search and filter a safe summary of imported cards, then
  use fresh-passphrase protected local controls to add, edit, transition,
  replace, or delete records. Private fields never return to the browser.
- Compare public card products, ask local catalog questions, and use the
  temporary purchase Planner.
- Use local, privacy-preserving expiry reminders and an optional calendar export
  when a compatible vault is available.

## Important current limits

- Protected card controls are local-only and require fresh passphrase
  reauthentication for every action. They never reveal or copy plaintext.
  Do not edit vault files by hand.
  The supported first-time import and technical reconciliation reference are in
  [Vault import](docs/VAULT-IMPORT.md).
- An **archived** card record is retained history. It is not a statement that the physical card has expired.
- A catalog product is not a verified benefit. `needs_review` is not a promise;
  check the official issuer, network, or merchant terms before using a benefit.
- The app does not automatically refresh live issuer pages or send network
  notifications. It never pays, applies, books, redeems, or tracks spending.
- Planner entries are your assumptions, not verified benefit claims. Affiliate
  routes are disclosed and cannot improve a ranking.

## What this release does and does not claim

The public catalog contains a small reviewed set of active benefit claims. A
candidate or `needs_review` item is not an approved benefit. A human reviewer
must approve the evidence before a benefit can become active.

The `c6a9081` baseline passed integrated, broad-review, clean-clone, scanner,
and synthetic rendered gates, but owner user testing rejected the current
consumer experience. The app is undergoing a consumer-first redesign and is
not release-ready. Live source
adapters and provider execution are disabled or separately gated. Owner-confirmed
real offering mappings and coverage, candidate activation, remote push, and
publication remain unperformed and owner-gated. No model, provider, or external
service was invoked by this documentation checkpoint.

## Private vault quick start

Use the operating-system keyring option if you want the browser's protected
**My Cards** view:

```powershell
uv sync --locked --extra keyring
uv run mycard-vault --keyring import --manifest imports/cards.json --create
uv run mycard-vault --keyring verify
```

`verify` reports a count and nothing else. For a typed passphrase instead, drop
`--keyring`; this remains the explicit CLI alternative. My Cards also provides
a protected loopback-only unlock for the current browser session. It never
stores the passphrase or unlocked session, and locks on timeout or restart.
Keep real manifests in the ignored `imports/` folder. If you lose your
passphrase the vault cannot be recovered; there is no server to reset it from.
Full walkthrough: [docs/VAULT-IMPORT.md](docs/VAULT-IMPORT.md); the tracked
[samples/card-import.example.json](samples/card-import.example.json) is
synthetic only.

## How benefit review works

Catalog entries carry source links, dates, evidence, and a review state. A
changed or conflicting source is not silently treated as a usable benefit.
This release does not automatically fetch issuer pages or send notifications.
When a benefit matters, open its official source and confirm the current terms
yourself before relying on it.

## Privacy and safety

The public catalog contains no personal card records. The private vault is
encrypted and local. My Cards exposes only a safe summary such as public product
match, lifecycle, and record dates; it never returns PAN, CVV, PIN, cardholder
name, nickname, notes, or exact expiry to the browser. Automated helpers never
receive decrypted vault values.

This is not a bank, payment service, wallet, or financial adviser, and it makes
no PCI-compliance claim. Read [SECURITY.md](SECURITY.md) before reporting an
issue, and never include real card data in a report.

## For maintainers and contributors

The detailed operator, source, migration, and architecture runbooks remain in
the documentation index: [docs/README.md](docs/README.md). Read
[AGENTS.md](AGENTS.md), [PROJECT_STATUS.md](PROJECT_STATUS.md), and
[DECISIONS.md](DECISIONS.md) before changing the project.

Offline quality gates:

```powershell
uv run --offline ruff check .
uv run --offline pytest
uv run --offline mypy src
```

## License

MIT.
