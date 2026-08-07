# MyCard Benefits

Know what your cards actually offer — with the evidence attached.

Card benefits change quietly. Lounge access gets restricted, a voucher program
ends, a blog post from two years ago still says otherwise. MyCard Benefits keeps
a catalog of card benefits where every statement carries its source, the dates it
covers, and whether a human has verified it — and keeps your own card records in
an encrypted file on your own computer, separate from all of that.

Everything runs locally. No account, no server, no upload, no cloud copy of your
cards.

**New here? Read the [User Guide](docs/USER-GUIDE.md).** It covers setup, the
dashboard, importing your cards, phone access, and what stays private, without
assuming you write software.

## Try it in five minutes

You need Python 3.12+ and [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
In Windows PowerShell, from your clone of this repository:

```powershell
uv sync --locked
uv run mycard-benefits --demo
```

The app prints the address to open and binds only to `127.0.0.1`, meaning this
computer only:

```
MyCard Benefits [DEMO]
App: http://127.0.0.1:8777
Private data remains local. The application binds only to 127.0.0.1.
```

Use the address it prints. Press `Ctrl+C` to stop. Drop `--demo` once you have
imported your own cards — the demo flag points at a separate data folder, so your
cards will not appear there.

## What works today

This is an early release, and the list is deliberately honest.

**Working:** the local dashboard (desktop and phone, dark and light, keyboard
navigable); a public catalog of **69 card variants** — real Indian credit cards,
debit cards, lounge memberships, and pay-later products identified by bank,
product, and network, plus one labelled synthetic fixture — searchable by bank,
card, or network; **My Cards**, a read-only list of your imported cards matched to
their catalog product; browsing benefits with their dates and evidence; **Ask**, a
deterministic question box answered from catalog facts with no AI model involved;
**Compare** for two cards side by side; **Sources** for the evidence trail; and a
command-line tool that creates your encrypted vault and imports your cards.

**Not working yet:**

- **Most cards have no benefits listed.** A variant existing is not a claim about
  what it offers — only benefits checked against current official terms and
  approved by a human appear, and that review work is at an early stage. Expect a
  long card list and a short benefit list. Nothing fetches live issuer pages
  automatically.
- **You cannot add, edit, delete, or reveal a card in the browser or through the
  HTTP API.** My Cards is read-only, and secret values are never sent to it. Add,
  edit, delete, reveal/copy, and owner/expiry/replacement reconciliation are all
  future protected work with their own security reviews. The `mycard-vault`
  command line remains the only write path; type nothing sensitive into the
  dashboard.
- **Expiring Soon**, **Updates**, and **Research Queue** appear in the sidebar but
  are intentionally empty.
- The purchase-route comparison engine exists in code but is not connected to
  any screen and cannot open a shopping link.

## Your cards

Card records go in through a command line. Use the keyring option if you want the
browser's My Cards view, which opens the vault through your OS keyring:

```powershell
uv sync --locked --extra keyring
uv run mycard-vault --keyring import --manifest imports/cards.json --create
uv run mycard-vault --keyring verify
```

`verify` reports a count and nothing else. For a typed passphrase instead, drop
`--keyring` — fully supported by the CLI, but the browser view cannot prompt for
it. Keep real manifests in the ignored `imports/` folder. If you lose your
passphrase the vault cannot be recovered; there is no server to reset it from.
Full walkthrough: [docs/VAULT-IMPORT.md](docs/VAULT-IMPORT.md); the tracked
[samples/card-import.example.json](samples/card-import.example.json) is
synthetic only.

## My Cards, read-only

`GET /api/v1/private/cards` and the **My Cards** screen require a current signed
browser session cookie from the authenticated gateway. The check runs before the
vault is touched and fails closed on a missing, expired, future-dated, malformed,
or wrongly-signed cookie. On success the app opens the OS-keyring-encrypted vault
server-side and returns envelope metadata only — card UUID, catalog offering,
lifecycle, created and updated timestamps, and a linked replacement card
identifier — sent `no-store`, and refused outright if the vault yields any
unexpected field. PAN, CVV, PIN, nickname, notes, cardholder name, and expiry are
never returned.

## Public versus private

- **Public catalog:** card variants, reward rules, conversions, lounges, movies,
  hotels, dining, vouchers, meet-and-greet, network programs, evidence, history.
  Shareable; contains nothing about you.
- **Private vault:** your card instances, lifecycle, PAN/CVV/PIN, notes,
  allowances, reminders, attachments — encrypted, local, never uploaded.
- **Never included:** spending ledger, bank login, OTP storage, payments, card
  applications, bookings, redemptions, automatic document submission.

The core works without an LLM. Optional agents see only public catalog facts and
safe identifiers, never a decrypted value.

## Using it from your phone

The app answers only on `127.0.0.1`. Remote access goes through a separate
authenticated gateway on the same machine (this project uses an authenticated
Rover proxy): you open the gateway's URL, sign in there, and it forwards the
request locally. The app's bind never changes — do not set it to `0.0.0.0`, your
LAN address, or a forwarded router port.

Signing in to the gateway is also what unlocks **My Cards**, on the phone and on
the desktop alike: opening the loopback address directly gets you the public
catalog and a *Rover sign-in required* notice. See
[the User Guide](docs/USER-GUIDE.md#8-using-it-from-your-phone).

The app receives Rover's matching signing secret only through its configuration
boundary (`ROVER_SECRET` in the process environment or ignored local `.env`). A
registered Rover launch supplies it on this workstation. It is never a browser
setting and must never be placed in a URL or committed file.

## Family Finance

The separate My Family Finance app stays fully standalone and keeps its own Cards
page. Its optional **MyCard Benefits companion** button opens this app if you
point it at the printed address; if this app is not installed or not running, the
button opens setup documentation instead. The button sends no card, owner, or
finance data. A one-time encrypted import is a later milestone with its own
review — the two apps do not synchronize.
See [docs/FAMILY-FINANCE-INTEGRATION.md](docs/FAMILY-FINANCE-INTEGRATION.md).

## Verified versus needs review

Every catalog statement carries its source and tier, a content fingerprint,
retrieval time, effective dates, a confidence level, and a review state.
**Approved** means a human checked the source; ambiguous or high-impact claims
need two independent reviewers, and no agent can approve anything. **Needs
review** means the evidence is missing, changed, or unchecked — such a statement
is never treated as active, and is shown with its status rather than hidden.
Expired benefits are kept as history. Before relying on a benefit, check its
review state and dates.

This is why the catalog lists many more cards than benefits: a card variant is a
public product identity, while a benefit is a claim that has to earn its place. An
empty benefit list means "not verified here yet," never "this card offers
nothing." Details:
[docs/SOURCE-POLICY.md](docs/SOURCE-POLICY.md) and
[docs/CATALOG-GOVERNANCE.md](docs/CATALOG-GOVERNANCE.md).

## Safety

This is not a bank, payment processor, wallet, or financial adviser. It makes no
PCI compliance claim. Always verify current eligibility and fulfillment with the
official issuer, network, or merchant before relying on a benefit. Threat model
and reporting: [SECURITY.md](SECURITY.md).

## Files regular users can ignore

`coordination/` is the maintainers' audit and resume trail: task briefs under
`coordination/tasks/`, append-only `jobs.jsonl` / `events.jsonl`, and code-review
results under `coordination/evidence/`. It exists because sensitive actions in
this project require a dated written human approval that can be audited later,
and because work spans sessions and must be resumable from disk rather than from
someone's memory of a conversation. Files named like `*-review-001.md` are review
records, not features or settings. Nothing there affects how the app behaves, and
nothing there is a to-do list for you. The same goes for `tests/`, `.venv/`, and
the raw files under `catalog/` — read the catalog through the dashboard instead.

## For maintainers and contributors

```powershell
uv run ruff check .
uv run pytest
uv run mypy src
```

Port resolution is `--port`, then `MYCARD_BENEFITS_PORT`, then the nearest
`ports.json` entry, then the documented clone fallback; the app never hunts for a
free port. Optional OS-keyring support installs with
`uv sync --locked --extra keyring`.

Read [AGENTS.md](AGENTS.md), [PROJECT_STATUS.md](PROJECT_STATUS.md), and
[DECISIONS.md](DECISIONS.md) before contributing, plus
[CONTRIBUTING.md](CONTRIBUTING.md) for the workflow. Product intent and new ideas
live in [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md),
[ROADMAP.md](ROADMAP.md), and [docs/IDEA-LOG.md](docs/IDEA-LOG.md); the accepted
questionnaire trace is in [docs/DECISION-TRACE.md](docs/DECISION-TRACE.md) with
the complete numbered matrix in
[docs/QUESTIONNAIRE-DECISIONS.md](docs/QUESTIONNAIRE-DECISIONS.md), so
implementation never depends on chat history. The full documentation index is
[docs/README.md](docs/README.md).

## License

MIT.
