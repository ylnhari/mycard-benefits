# MyCard Benefits user guide

MyCard Benefits is a local, private place to keep track of card benefits and
the cards you hold. It runs on your computer and opens in your browser. You do
not need an account, and your card data is not uploaded to a MyCard service.

This is the guide for using the app. The other files in this repository are
maintainer documentation; you do not need them for normal use.

## Current release status

The active benefit catalog contains only individually approved public claims.
The first local activation is the Tata Neu Infinity HDFC Bank RuPay Select
domestic lounge voucher milestone. Other candidates and `needs_review` items
are not approved benefits. The technical baseline passed automated and
independent engineering gates, but the current consumer interface did not pass
owner user testing and is being redesigned. It is not release-ready. Remote
push and public publication remain separate human gates and have not occurred.

## What MyCard Benefits does

It keeps two kinds of information separate:

- **The public catalog** lists card products and benefits with their source,
  dates, and review status. It is not personal information.
- **Your private vault** holds your own card records in encrypted local storage.
  It is separate from the catalog and stays on this computer.

Use the catalog to find the exact variant of a card and to check the conditions
and evidence behind a listed benefit. Use **My Cards** to see safe metadata and,
after unlocking, manage local records through fresh-passphrase protected forms.

MyCard Benefits is not a bank, wallet, payment app, card application service,
or financial adviser. It does not log in to a bank, store an OTP, make a
payment, redeem an offer, or track your spending. Always confirm a benefit with
the issuer, network, or merchant before relying on it.

## Start it for the first time

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Open Windows PowerShell, go to the folder containing this project, and run:

```powershell
cd path\to\mycard-benefits
uv sync --locked
uv run mycard-benefits --demo
```

The first command prepares the app. The second starts a clearly labelled demo
and prints an address such as `http://127.0.0.1:8777`. Open the address it
prints. `127.0.0.1` means this computer only.

The demo lets you explore public screens without opening a private vault. It
uses a separate `demo-data` folder and keeps **My Cards** off. Stop the app
with `Ctrl+C`. Start it later with the same command; you only need to run
`uv sync --locked` again after updating the project.

When you are ready to use your own vault, stop the demo and run:

```powershell
uv run mycard-benefits
```

Useful options:

| What you want | Command |
| --- | --- |
| Start without opening a browser tab | `uv run mycard-benefits --no-browser` |
| Use a chosen local port | `uv run mycard-benefits --port 9123` |
| Use a chosen app data folder | `uv run mycard-benefits --data-dir <data-dir>` |

Do not change the app to listen on your network or the internet. If you choose
to use it from another device, use an authenticated gateway or launcher you
control. That is separate software, not part of MyCard Benefits; this app still
listens only on this computer.

## Get around the dashboard

- **My Cards** shows safe card metadata only. Search by product, bank, network,
  or status, and filter by lifecycle.
- **Benefits** lets you search reviewed benefits and public card products. Open
  a benefit to read its conditions, cap, dates, evidence, and public card
  matches.
- **Which card?** combines local catalog questions, comparison, and the
  temporary purchase planner. These actions use only the information visible
  in the public catalog and any safe local card summary.
- **Settings** contains the theme choice, optional reminder education, and a
  reminder that remote access is separate from this app.

The sidebar works with a keyboard: use `Tab` to move, `Enter` to open a
control, and the **Skip to content** link at the top to skip the sidebar.

## Add and manage cards safely

### What the dashboard can do today

The dashboard shows safe card metadata. After **Unlock My Cards**, protected
forms can add a card, edit private nickname/notes, change a lifecycle, replace a record, or delete/purge a record. Every write asks for a fresh passphrase;
secret inputs are cleared after submission and plaintext is never returned.
Do not edit `vault.json` in a text editor.

### Create and import a vault

The supported first-time write path is the local `mycard-vault` command. Copy
the synthetic sample `samples/card-import.example.json` to the ignored
`imports` folder, replace its sample entries locally, and then run:

```powershell
uv run mycard-vault import --manifest imports/cards.json --create
uv run mycard-vault verify
```

The import command asks you to choose a passphrase. `verify` reports only a
card count. Keep the real manifest private and store no more than you need; you
usually do not need to store a full card number, CVV, or PIN.

For the browser's **My Cards** list, use the operating-system keyring option:

```powershell
uv sync --locked --extra keyring
uv run mycard-vault --keyring import --manifest imports/cards.json --create
uv run mycard-vault --keyring verify
```

The keyring keeps the vault's unlock credential in your operating-system
account. It is optional.

### Unlock and lock

The operating-system keyring is optional. If the vault is passphrase-only, My
Cards shows a protected local unlock form. The passphrase is sent only to this
loopback app process, is not placed in browser storage or URLs, and unlocks only
an in-memory session. The session locks explicitly, after a short idle/absolute
timeout, or whenever the app process restarts. The browser cannot reveal, copy,
add, edit, or delete private fields from this unlock; those remain separately
reauthenticated actions.

If you prefer not to enter a passphrase in the browser, use the CLI instead:

```text
uv run mycard-vault verify
uv run mycard-vault import --manifest imports/cards.json
```

Python and browser runtimes may retain immutable string copies temporarily. The
app uses a dedicated bounded request boundary and clears mutable request
buffers on a best-effort basis, but cannot promise forensic zeroization of every
runtime allocation.

The dashboard provides protected local **Unlock** and **Lock** controls for a
passphrase-only vault. A keyring-backed vault can open its safe metadata without
that prompt. In both modes, **My Cards** never sends secret field values to the
browser. The command-line tool remains available and locks its session when the
command ends.

If My Cards says it is unavailable, first confirm that you are not in demo
mode, that you started the app with the same data folder used for the vault, and
that your operating-system keyring is available. Then run the keyring `verify`
command above. It reports a count, not card values.

### Lifecycle words

When you prepare an import, each card has one lifecycle value: `active`,
`expired`, `lost`, `stolen`, `closed`, or `archived`.

- **Expired** means the card is known to be expired.
- **Lost** or **stolen** records the reason it should not be used.
- **Closed** records a closed account.
- **Archived** keeps history. It does **not** mean that a physical card expired.

In the import source, `archived` retains a historical record. An **archived** row means the record is kept as history; it is not an expiry claim.

For safety, lifecycle, replacement, and deletion are destructive vault actions.
Use the protected local forms after unlocking My Cards; each action requires a
fresh passphrase and preserves the encrypted vault boundary. Do not work around
the forms by editing the encrypted vault.

An **Unmatched variant** row means MyCard Benefits cannot match the stored
product identifier to a public catalog product. It does not expose the raw
identifier. Correct the identifier in your private source when a supported
update flow is available, or request that the public variant be added.

For the full private-manifest format and the separate reconciliation path, see
[Vault import](VAULT-IMPORT.md). That is a technical reference; normal use does
not require reading it first.

## Browse benefits and read their status

Start in **Benefits** to search by bank, card name, or network. Exact variants
matter: cards with similar names can have different networks and benefits.

For every result, check:

1. **Conditions and cap** — many benefits apply only to certain purchases or
   have a limit.
2. **Dates** — a historical benefit is kept so you can see what changed; do not
   treat it as current.
3. **Evidence and review state** — follow the official reference before you
   use a benefit.

The app deliberately lists far more card products than benefits. A product in
the catalog is only an identity; it does not prove any perk. An empty benefits
list means “not verified here yet,” not “this card has no benefits.”

### Verification states

- **Approved** means the supporting source was checked and approved by a human
  reviewer. A second review may be recommended for higher-risk claims, but it
  is not required for activation.
  It is still wise to check current issuer, network, or merchant terms before
  use.
- **Needs review** (`needs_review`) means evidence is missing, changed,
  incomplete, or awaiting review. It is not a live promise and is never treated
  as an active benefit.
- **Historical, expired, or superseded** information is kept for context. Read
  its dates; it is not a current offer.

## Reminders and alerts

This release does not automatically fetch issuer pages, refresh live benefits,
or send network notifications. The optional reminder-education setting is a
local check for due-date alignment and autopay; it is general education, not a
payment tracker or instruction to pay. Exact expiry dates, owner names, and
card details stay out of the browser, logs, and notifications.

No reminder sends money, submits a payment, or proves eligibility. If a local
vault problem prevents a reminder from loading, fix the vault first; no alert
is sent while it is unavailable.

## Planner and affiliate disclosure

Planner is a private, temporary worksheet for a planned purchase. It uses the
merchant or site, category, amount, date, and card assumptions that **you**
type. It is not a transaction record, is not saved, and never opens a shopping
site or makes a purchase.

At present, user-entered routes are labelled **User-entered assumption** rather
than verified. The app will not present them as proven card benefits. If you
allow an **Affiliate or compensated link** channel, that is disclosed plainly;
affiliate status cannot improve a recommendation or ranking. You can leave
that channel unchecked. Check official terms yourself before acting.

## Backups and recovery

Every vault write keeps up to three automatic encrypted backups alongside the
vault: `vault.json.bak.1` is the newest and `vault.json.bak.3` the oldest.
These backups are local and private.

Your recovery material matters:

- Keep your passphrase somewhere safe and offline. There is no reset link or
  server copy.
- If you use the operating-system keyring, keep the original private manifest
  or another secure recovery source. Losing that keyring can make the vault
  unavailable.
- Never edit the vault or its backup files while the app is running.

If the vault is damaged, stop the app first. There is no automatic restore
button. Make a separate copy of the damaged vault, then only if you trust the
backup, copy the newest working `vault.json.bak.N` over `vault.json` and start
the app again. If you are unsure which file is good, stop and seek help without
sharing card details, screenshots, or private paths.

## Privacy at a glance

- Your card vault, imports, and backups stay local and encrypted.
- The browser receives only a small safe summary for My Cards: product,
  lifecycle, record dates, and a replacement relationship when one exists.
- Card number, CVV, PIN, cardholder name, nickname, notes, and exact expiry
  remain encrypted and are not sent to the browser.
- The **Which card?** tools use local catalog facts. Questions are not saved,
  and automated helpers do not receive decrypted vault values.
- Theme preference stays in this browser. The app does not create an account or
  cloud copy.

No security tool can protect against malware running as you, a compromised
computer, screen recording, or clipboard-monitoring software. MyCard Benefits
does not claim PCI compliance. Read [Security](../SECURITY.md) before reporting
a problem, and never include card details in a report.

## 12. When something goes wrong

**The browser cannot reach the page.** The app is not running, or the browser
address differs from the address printed by PowerShell. Start it again and use
the printed address.

**`uv` is not recognised.** Install uv, close PowerShell, open a new window,
and try again.

**The catalog is unavailable.** Run the app from a complete project folder that
contains `catalog`, then restart it. It will not substitute private data.

**My Cards is unavailable.** The dashboard gives a safe reason. Work through
these in order:

1. **Demo mode** — you started with `--demo`. Stop it and start without that
   option; demo never opens a private vault.
2. **No vault yet** — create and verify the vault in the data folder you chose.
3. **Passphrase-only vault** — use the protected local unlock form in **My
   Cards**, or use the command-line alternative above.
4. **Wrong data folder** — start the app with the same `--data-dir` used when
   the vault was created.
5. **Keyring unavailable or vault did not unlock** — check your operating-system
   keyring, then run the keyring `verify` command from [Unlock and lock](#unlock-and-lock).

**The app says a card is unmatched.** This is a safe warning that the private
record has no matching public product. It does not mean the card is invalid.

**A benefit looks wrong or missing.** Check the official issuer, network, or
merchant terms. Do not use an unreviewed catalog proposal as proof of a benefit.

## What must happen before a wider release

These are release follow-ups, not actions the dashboard performs for you:

- The owner must confirm real private-to-public offering mappings and coverage
  for the reconciliation and held-card tasks (MC-010–015, MC-017, MC-206,
  MC-211, and MC-212). Keep private card values on the local computer.
- External or separately configured work remains required for live adapters,
  provider execution, and counterpart/release controls (MC-111, MC-118, MC-119,
  MC-148, MC-168, MC-173, MC-213, and MC-214).
- A human reviewer must approve candidate evidence before any benefit is
  activated. A second review may be recommended for higher-risk claims, but is
  not mandatory. Agents cannot approve their own work.
- Technical integrated and broad-review gates passed for the preserved
  baseline, but consumer acceptance is reopened. The ledger has 165 technically
  checked tasks, 18 active or reopened tasks, and 38 owner-blocked,
  external-blocked, or post-v1-deferred items. Publication still needs its own
  dated human approval.

Until those actions are complete, use the app for local organization and
evidence reading only. It does not apply for cards, make purchases, book,
redeem, upload, or publish anything.

## Remove the app

Stop the app with `Ctrl+C`. Before deleting anything, copy the private import
source, encrypted data folder, and recovery information somewhere safe if you
want to keep them. Deleting the project and its data permanently removes your
local vault; there is no account or cloud copy to recover from.

## More help

- [Vault import](VAULT-IMPORT.md) — private manifest format and technical
  import/reconciliation reference.
- [Security](../SECURITY.md) — threat model and safe issue reporting.
