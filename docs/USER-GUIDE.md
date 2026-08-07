# MyCard Benefits — User Guide

This guide is for the person who just wants to use the app. You do not need to
be a programmer. You will need to run two commands in a terminal window once,
and after that everything happens in your web browser.

If you maintain or contribute to this project, read this guide first anyway —
it is the honest description of what the software actually does today — then
move on to [AGENTS.md](../AGENTS.md) and [PROJECT_STATUS.md](../PROJECT_STATUS.md).

---

## 1. What this app is

Credit and debit cards come with benefits — lounge access, movie vouchers,
reward points, dining discounts, hotel perks. The terms change quietly, blogs
repeat outdated claims, and by the time you are at the airport counter it is too
late to find out a benefit ended last quarter.

MyCard Benefits is two things kept deliberately apart:

- **A public benefits catalog.** Plain, structured statements about what a card
  offers, each one carrying its source link, the dates it applies to, and
  whether a human has reviewed it. This part is shareable and contains nothing
  about you.
- **A private card vault.** Your own cards, encrypted, stored only in a file on
  your own computer. Nothing is uploaded anywhere, ever.

Everything runs on your machine. There is no MyCard Benefits account, no
server, no sign-up, and no cloud copy of your cards.

### What it is not

It is not a bank, a wallet, a payment app, or a financial adviser. It never
logs in to your bank, never stores an OTP, never makes a payment, never applies
for a card, and never books or redeems anything. It does not track your
spending. It will not tell you what to buy.

Always confirm a benefit with the issuer, network, or merchant before you rely
on it. This app helps you know what to check and how current the information
is; it is not a guarantee.

---

## 2. What works today, honestly

This is an early release. The list below is accurate — please do not assume a
feature works because it appears in the sidebar.

**Working now:**

- The local dashboard opens in your browser and works on a phone-sized screen,
  in dark and light themes, and with keyboard-only navigation.
- **A public catalog of 68 card variants** — real Indian credit cards, debit
  cards, lounge memberships, and pay-later products, identified by bank, product
  name, and network. Search it by bank, card, or network name.
- **My Cards** — a read-only list of the cards you imported, matched to their
  catalog product. It shows product, status, and record dates only.
  See [section 6](#6-your-own-cards-import-and-view).
- **Benefits** — browse benefits, filtered by card, each with its dates and
  evidence.
- **Ask** — type a plain question and get an answer built only from catalog
  facts. No AI model is involved; the same question always gives the same
  answer, and your question is not saved or sent anywhere.
- **Compare** — put two cards side by side with their active benefit counts.
- **Sources** — see where each stated fact came from.
- **Overview** — catalog totals, a card-variant search, and your private-access
  status.
- A separate command-line tool (`mycard-vault`) creates your encrypted vault and
  imports your cards from a file you write yourself.
- The optional button inside the Family Finance app that opens this companion.

**Not working yet — do not rely on these:**

- **Most cards do not have benefits listed yet.** A card variant existing in the
  catalog is not a claim about what it offers. A benefit only appears once it has
  been checked against current official terms and approved by a human, and that
  review work has barely started — so today the **Benefits** list is nearly
  empty even though the card list is not. This is deliberate: the app would
  rather show you nothing than show you an unverified perk. Nothing in this
  release fetches live issuer pages automatically.
- **You cannot add, edit, delete, or reveal a card in the browser.** My Cards is
  read-only. Adding a card, correcting one, removing one, revealing a stored
  secret value, and reconciling owner, expiry, or replacement details are all
  future protected work with their own security review still to come. The
  **Add or edit** button is visibly disabled. Type nothing sensitive into the
  dashboard; the `mycard-vault` command line remains the only way in.
- **Expiring Soon, Updates, and Research Queue** are visible in the sidebar but
  intentionally empty. Expiry dates in particular are private vault values that
  the browser is not given, so no reminders can be produced yet.
- The purchase-route comparison engine exists in code but is not wired to any
  screen, and it cannot open a shopping link.
- The Family Finance button only checks whether this app is reachable. It does
  not import or sync anything.

---

## 3. Five-minute setup

You need two things installed first:

1. **Python 3.12 or newer.**
2. **`uv`**, a small tool that installs everything else for you. Installation
   instructions: <https://docs.astral.sh/uv/getting-started/installation/>

Open **Windows PowerShell**, go to the folder where you cloned or unpacked this
project, and run:

```powershell
cd path\to\mycard-benefits
uv sync --locked
uv run mycard-benefits --demo
```

The first command downloads the app's dependencies. The second starts the app
and opens your browser. You will see something like:

```
MyCard Benefits [DEMO]
App: http://127.0.0.1:8777
Private data remains local. The application binds only to 127.0.0.1.
```

Use whatever address it prints. In a fresh clone with no other configuration
that is `http://127.0.0.1:8777`, but do not memorise it — read the printed line.

`127.0.0.1` means "this computer only". Nobody else on your home network, your
office network, or the internet can reach the app at that address.

**To stop the app:** press `Ctrl+C` in the PowerShell window.

**To start it again later:** `uv run mycard-benefits --demo` from the same
folder. You do not need `uv sync` again unless the project has been updated.

### Useful variations

| You want to | Run |
| --- | --- |
| Start without the demo label and demo folder | `uv run mycard-benefits` |
| Not have a browser tab open automatically | `uv run mycard-benefits --no-browser` |
| Use a specific port | `uv run mycard-benefits --port 9123` |
| Keep your data somewhere else | `uv run mycard-benefits --data-dir D:\MyCardData` |

`--demo` is a clearly labelled dry run. The page shows a **permanent banner**
saying so on every screen, demo activity lives in a separate `demo-data` folder,
and **My Cards is switched off** — a demo run never even opens your real vault.
The public catalog is the same either way. Start the app without `--demo` when
you want to see My Cards; your imported cards live under the normal `data`
folder and only appear there.

If you pass an explicit data folder with `--data-dir`, the app uses that folder
even with `--demo`, so choose the `--data-dir` deliberately in that case.

If you do not pass `--port`, the app picks one in this order: the
`MYCARD_BENEFITS_PORT` environment variable, the nearest `ports.json` entry if
your setup has one, then the built-in fallback. It never hunts around for a
free port, so the address stays predictable.

---

## 4. Getting around the dashboard

The left sidebar is the whole app. On a phone the layout stacks vertically; the
same links are there.

- **Overview** — three counts (card variants in the catalog, active benefits, and
  your own card records), a search box for finding a card variant by bank, card,
  or network, and a panel telling you whether this browser can see your private
  list.
- **My Cards** — your imported cards, read-only. Filter by status or search by
  bank or card name. See [section 6](#6-your-own-cards-import-and-view).
- **Benefits** — pick a card from the dropdown, or leave it on *All offerings*.
  Each benefit shows what it is, the dates it applies to, and its evidence.
  Expect this list to be short for now.
- **Ask** — a question box. Try the example buttons first to see the shape of an
  answer. Answers cite the catalog records behind them.
- **Compare** — two dropdowns, two cards side by side, each with how many active
  benefits it has.
- **Sources** — the evidence trail for the catalog as a whole.
- **Settings** — a light/dark theme switch. Your choice is remembered only in
  this browser and is stored nowhere else.

There is also a **Use light theme / Use dark theme** button at the bottom of the
sidebar.

Every page is reachable with the keyboard alone: `Tab` moves between links and
controls, `Enter` activates them, and a *Skip to content* link at the very top
jumps past the sidebar. In the Ask box, `Enter` asks and `Escape` clears.

If the top of the page says the catalog is unavailable, the app could not read
its catalog files. It will say so plainly rather than showing you stale or
invented numbers, and it will never fall back to your private data.

---

## 5. Browsing cards and benefits

**To find a card:** go to **Overview** and type into the search box under *Find a
card variant* — a bank name, a card name, or a network works. The catalog holds
68 variants, so it is worth searching rather than scrolling. Each result shows
the bank, the network, and the full product name.

Getting the exact variant right matters more than it sounds. "ICICI Coral" is
several different products on different networks, and their benefits differ. The
catalog keeps them apart on purpose.

**To read benefits:** open **Benefits**, choose a card, and read down the list.
For each benefit look at three things:

1. **The dates.** A benefit that ended is kept in the catalog as history rather
   than deleted, so check that today falls inside its range.
2. **The evidence status.** See [section 9](#9-verified-versus-needs-review)
   below — this is the most important habit to build.
3. **The conditions.** Many benefits only apply to certain transaction types,
   and many have a cap. Both are shown.

Expired benefits are on purpose. Knowing a perk existed until March is more
useful than the perk silently vanishing from your screen.

**If a card shows no benefits, that is expected right now** and does not mean the
card has none. Only benefits that have been checked against current official
terms and approved by a human are shown, and that review work is at an early
stage — the card list is far ahead of the benefit list. An empty list means "not
verified here yet," never "this card offers nothing." Check with the issuer.

---

## 6. Your own cards: import and view

Your cards go **in** through a command-line tool. You can then **read them back**
in the browser, but only in a list that deliberately contains no secret values.

### Importing

Full step-by-step instructions, including every field and every option, are in
[VAULT-IMPORT.md](VAULT-IMPORT.md). The short version:

1. Copy the sample file
   [`samples/card-import.example.json`](../samples/card-import.example.json)
   into a folder named `imports/` inside the project. That folder is ignored by
   version control, so nothing in it can be committed by accident.
2. Edit your copy and replace the sample entries with your own cards. For each
   card you give a product identifier, a status (`active`, `expired`, `lost`,
   `stolen`, `closed`, or `archived`), and the details you want encrypted — a
   nickname, cardholder name, expiry, notes, and, if you genuinely want them
   stored, the card number, CVV, or PIN.

   **Tip:** for the product identifier, use the catalog slug of the matching card
   variant — the identifier shown in the catalog, such as
   `hdfc-regalia-gold-credit`. When it matches, My Cards shows the card's proper
   product name, bank, and network. A card whose identifier has no match appears
   under the clearly labeled "Unmatched variant" row, never as a raw slug or
   identifier, until the identifier is fixed or the variant is added to the
   catalog. The row tells you exactly how: correct the identifier in your import
   file, or request the missing variant in the catalog.
3. Create the vault and import the file in one step:

   ```powershell
   uv run mycard-vault import --manifest imports/cards.json --create
   ```

   You will be asked for a passphrase twice. This passphrase protects
   everything. Write it down somewhere safe and offline.

4. Check it worked, without revealing anything:

   ```powershell
   uv run mycard-vault verify
   ```

   This prints a card count and nothing else.

**Recommended:** store as little as possible. A nickname, the last few digits,
the expiry, and the benefits you care about are enough for most people. You do
not have to put your full card number, CVV, or PIN into the vault, and the tool
does not need them to be useful.

**Two warnings worth repeating:**

- If you lose your passphrase, the vault cannot be recovered. There is no reset
  link, because there is no server to reset it from. Keep your original import
  file or another secure record.
- Never open the vault file in a text editor and never edit it by hand. Use
  these commands only.

### The keyring option, and why it matters for My Cards

You can have Windows Credential Manager generate and hold a device-specific
passphrase instead of typing one. Install the extra component once, then add
`--keyring` to the commands:

```powershell
uv sync --locked --extra keyring
uv run mycard-vault --keyring import --manifest imports/cards.json --create
uv run mycard-vault --keyring verify
```

This is convenient but ties the vault to this Windows account, so read the
recovery warning in [VAULT-IMPORT.md](VAULT-IMPORT.md) before choosing it.

**One thing to know before you decide:** the **My Cards** screen opens your vault
using the operating-system keyring. A vault protected only by a passphrase you
type is fully supported by the command-line tool, but the browser view has no way
to ask you for that passphrase yet, so it will report the vault as unavailable.
If you want the My Cards list, choose the keyring option.

### Viewing your cards in My Cards

**My Cards is read-only, and it never receives a secret value.** It exists to
answer "which cards do I have, which are still active, and which catalog product
is each one?" — not to show you a card number.

**What you need for it to work:**

1. The vault must exist and be unlockable through the OS keyring (above).
2. The app must be started **without** `--demo`, so it reads your real data
   folder.
3. **The app must be running against your real local data folder.** If you use
   a separate tool to access MyCard from a phone, that tool is responsible for
   its own sign-in and remote-access rules; it is not part of MyCard. See
   [section 8](#8-using-it-from-your-phone).

**What it shows, per card:** a readable row with the product it maps to (bank,
network, and full product name, pulled from the public catalog), its status, when
the record was added and last updated, and a note if a replacement card is linked
to it. A card whose identifier has no catalog match appears in a clearly labeled
"Unmatched variant" row — never as a bare identifier or slug — with guidance on
the two ways to fix it (correct the import identifier, or request the catalog
variant). There are also a
status filter and a search box that matches product, bank, network, status, and
the record's safe identifiers.

**Viewing a card's details.** Every row has a **View details** button. Pressing
it (with the mouse or the keyboard) expands a read-only detail panel showing the
same safe facts: product name, issuer/bank, network, lifecycle, when the record
was added and updated, and the replacement relationship — whether this card was
replaced by another one, or replaced an earlier card, named when both records
are present. The panel never adds a new field and never shows a secret; Escape
or the button closes it and returns focus to the row. An unmatched card's panel
says so honestly under an "Unmatched variant" heading, without printing the raw
identifier or slug, and points at the two
ways to fix it (fix the import identifier, or request the catalog variant).

**What it never shows, and never sends to your browser:** the card number, CVV,
PIN, cardholder name, your nickname for the card, notes, and expiry date. Those
stay encrypted. The list is built from the record's outer envelope only — a local
random identifier, which catalog product it points at, its status, and its
timestamps. Responses are marked not to be cached, so they are not written to
your browser's disk cache. If the app ever receives an unexpected extra field
from the vault, it refuses to answer rather than risk passing something through.

**What is not there yet.** Adding a card, editing one, deleting one, and revealing
or copying a stored secret value are all future protected work, each needing its
own security review — the **Add or edit** button is visibly disabled. So is
reconciling owner, expiry, and replacement details: linking cards to people,
tracking when each one expires, and confirming which card replaced which are
planned, not built. Until then, corrections mean editing your import file and
re-importing.

---

## 7. The optional Family Finance button

If you also use the separate **My Family Finance** app, its **Cards** page can
show a **MyCard Benefits companion** button that opens this app.

The two apps stay completely independent. They do not share a database, and
turning this button on does not merge anything.

**To set it up:** start MyCard Benefits, note the address it prints, then in
Family Finance open **Cards → Companion setup** and paste that address. Save,
and use the companion button.

**If MyCard Benefits is not running or not installed,** the button opens setup
documentation instead of failing silently.

**What the button sends:** nothing about you. Before opening the companion,
Family Finance makes one small request to check the app is actually there. That
check carries no card details, no owner details, no finance data, and no
credentials. The address you pasted is stored only in your browser's local
settings — never in the Family Finance data file and never in its backups.

**To remove it:** open **Companion setup**, clear the field, and save. That
removes only the link. Neither app's records are touched.

A one-time encrypted import from Family Finance is planned for a later release
with its own security review. It does not exist yet, and even when it arrives
the two apps will not continuously sync. Details:
[FAMILY-FINANCE-INTEGRATION.md](FAMILY-FINANCE-INTEGRATION.md).

---

## 8. Using it from your phone

The app answers only on `127.0.0.1`, which means only the computer it runs on.
So how do you read it on your phone?

**Through an authenticated gateway or launcher you control** — a separate piece
of software that can forward your phone's request to the local app. You
configure and sign in to that tool independently; it is not a MyCard account or
part of MyCard Benefits.

The important part is what does *not* happen: the app's own address never
changes. It keeps listening on `127.0.0.1` only. The gateway reaches it from
the same machine, which is allowed; your phone never talks to the app directly.

To set this up: register MyCard Benefits in your chosen access tool, keep that
tool's authentication switched on, and open the URL it issues for it. If that
tool's address is not itself on a private, authenticated network, put it behind
HTTPS. MyCard stays a loopback-only app either way.

**Do not do these things**, even if a guide somewhere suggests them:

- Do not change the app's bind address to `0.0.0.0` or your machine's LAN IP.
  There is no supported configuration for this, and adding one would expose an
  app that has no login screen of its own to your entire network.
- Do not forward a port on your router to it.
- Do not paste your gateway's secret or token into a URL you share, a browser
  bookmark, a config file in this project, or a chat message.

Gateway addresses can be reassigned when the gateway restarts. If the phone
link stops working, check the current URL in your gateway and update the
address you saved.

---

## 9. Verified versus needs-review

This is the single most valuable habit the app can teach you. Every statement
in the catalog carries its own paperwork, and you should glance at it before
acting on a benefit.

Each benefit shows:

- **Where it came from,** ranked by how authoritative the source is. The best
  source is the exact page or document from the party that actually administers
  the benefit; then issuer documents; then card network rules; then the
  merchant's own terms; then regulatory guidance. Blogs, forums, and aggregator
  sites sit at the bottom and can only ever point toward a real source — they
  can never be the basis of a verified claim on their own.
- **A content fingerprint and retrieval time,** so a later check can tell
  whether the source page has changed since it was read.
- **The dates the terms cover.**
- **A confidence level.**
- **A review state** — the one to look at.

**Approved** means a human read the source and confirmed the statement. For
claims that are ambiguous or would matter a lot if wrong, two independent
people have to agree before it can be approved. Software cannot approve a
catalog claim, and neither can the person who wrote it.

**Needs review** means something is unsettled: the source page changed, the
evidence is missing, the dates are unclear, or nobody has checked it yet. A
statement in this state is **not treated as active**. It is shown to you, with
its status visible, rather than quietly hidden — but treat it as a lead to
verify yourself, not as a fact.

When two sources disagree, the more authoritative one wins and the
disagreement is recorded rather than deleted.

**In practice:** before you rely on a benefit, look at its review state and its
dates. If it says needs review, or the source is old, confirm with the issuer
before you count on it. This is exactly how you would check any perk — the app
just makes the state of the evidence visible instead of hiding it behind
confident-sounding prose.

---

## 10. What stays private

- **Your card details never leave your computer.** There is no upload, no
  telemetry, no analytics, no crash reporting, and no cloud sync. The app has
  no way to send them anywhere.
- **Your cards are encrypted with strong, standard cryptography**, unlocked by
  your passphrase. Someone who copies the vault file off your machine without
  your passphrase cannot read it.
- **The unencrypted part of a card record is deliberately minimal:** a local
  random identifier, which catalog product it refers to, its status, a schema
  version, and timestamps. No name, no number, no nickname.
- **The My Cards screen only ever receives that minimal part.** Your vault is
  opened and read on the server side, inside the app on your own machine, and
  only those envelope fields — identifier, catalog product, status, created and
  updated times, and a linked replacement record if there is one — are sent to the
  browser. Card number, CVV, PIN, cardholder name, nickname, notes, and expiry are
  never included in the response. The response is also marked not to be cached,
  so it is not saved into your browser's disk cache, and it is refused entirely
  unless your gateway session is valid.
- **The app never prints decrypted values.** Not to the screen, not to a log
  file, not into an error message.
- **Automated helpers never see your card values.** Any AI or background
  process involved in this project works only on public catalog data and safe
  identifiers. By design, revealing or copying a stored value can only ever be a
  deliberate human action taken after re-entering your passphrase — never
  something a script or agent can trigger. (That screen is future protected work;
  today nothing in the app reveals a stored secret value at all.)
- **Your questions in the Ask box are not saved** and are answered locally from
  catalog files.
- **Your theme choice** lives in your browser and nowhere else.

Your vault, backups, imports, and logs live in local folders that version
control ignores, so they cannot be committed or published by accident.

Honest limits, since a security promise without limits is worth little: this
design protects against accidental leaks, other people casually using your
computer, and someone inspecting copied files. It cannot protect you from
malware running as you, a compromised operating system, screen recording, or
clipboard-monitoring software. The project makes no PCI compliance claim. See
[SECURITY.md](../SECURITY.md).

---

## 11. Folders you can safely ignore

A clone of this project contains working notes that exist for the people
maintaining it. **If you are just using the app, you never need to open any of
these, and nothing in them affects how the app behaves.**

- **`coordination/`** — the maintainers' audit and resume trail. It holds task
  briefs under `coordination/tasks/`, append-only activity records
  (`jobs.jsonl`, `events.jsonl`), and, under `coordination/evidence/`, the
  written results of code reviews of each part of the project. This exists for
  two reasons. First, sensitive actions in this project require a dated, written
  human approval before they happen, and this is where that record lives — so
  it can be audited later rather than trusted on someone's word. Second, work
  here is often done in pieces across sessions, sometimes by automated helpers,
  and writing the state to disk means the next session can pick it up from the
  files rather than from someone's memory of a conversation. Files named like
  `*-review-001.md` or the contents of `coordination/evidence/` are code-review
  records, not features, settings, or instructions for you.
- **`tests/`** — automated checks that the app behaves correctly.
- **`catalog/`** — the raw catalog source files. Read them through the
  dashboard instead; it is the same data, presented properly.
- **`docs/`** other than this guide — mostly policy for contributors: how
  sources are admitted, how evidence is recorded, how a claim gets reviewed,
  what automated helpers may and may not do.
- **`.venv/`, `data/`, `demo-data/`, `imports/`** — machine-generated or private
  local folders. Your vault lives under `data\private\`. Do not edit anything
  in there by hand.

Nothing in `coordination/` is a to-do list for you, and nothing there is
required for the app to run.

---

## 12. When something goes wrong

**The browser shows "can't reach this page".** The app is not running. Check
the PowerShell window is still open and shows the `App:` line, and that the
address in your browser matches the one it printed.

**The page loads but says the catalog is unavailable.** The app could not read
its catalog files. Make sure you are running the command from inside the
project folder, and that the `catalog` folder is present in your copy.

**`uv` is not recognised.** `uv` is not installed, or your PowerShell window
was opened before it was installed. Close and reopen PowerShell, then try
again.

**A vault command says the vault must exist / must not exist.** Use `--create`
only the first time. After the vault exists, leave `--create` off.

**An import failed after the vault was created.** The vault is kept on purpose.
Fix your file and run the import again without `--create`.

**My Cards says the private vault is unavailable.** The app reached the vault step
but could not complete it. The dashboard tells you which cause applies and what
to do about it. The causes, in order:

1. **Demo mode** — you started the app with `--demo`. Demo runs stay in the
   `demo-data` folder, never open your real vault, and switch My Cards off.
   Stop the run and start again without `--demo`.
2. **No vault yet** — the data folder the app is using contains no vault. If
   your vault lives in a different data folder, start the app with that
   `--data-dir`. Otherwise create the vault once with
   `uv run mycard-vault --create`, then import.
3. **Passphrase-only vault** — the vault exists but was created without the
   operating-system keyring, which this read-only browser view needs. Either
   store the passphrase in your operating-system keyring or open and import
   from the command line. Confirm with `uv run mycard-vault --keyring verify`.
4. **Wrong data folder** — a keyring passphrase is stored for this data folder
   but no vault file is there, so the app is looking in the wrong place. Start
   the app with the data folder that actually holds your vault.
5. **Keyring unavailable or vault did not unlock** — the operating-system
   credential manager or keychain could not be read, or the vault file is
   present with a stored passphrase but will not open (damaged file or stale
   passphrase). Check your credential manager, then run
   `uv run mycard-vault --keyring verify`.

**My Cards shows "Unmatched variant" instead of a card's real name.** That
card's product identifier does not match a catalog slug. The row is clearly
labeled so you can still tell the record apart, and no raw identifier is shown.
Fix the identifier in your import file, or ask for the missing card variant to be
added to the catalog; the product name appears once the match succeeds.

**Something looks wrong in the numbers.** Do not edit any file under `data\` to
fix it. Report it instead, and never include your card details, a screenshot of
them, or a file path from your machine in a report. See
[SECURITY.md](../SECURITY.md).

---

## 13. Removing it

Stop the app with `Ctrl+C`. To remove everything, delete the project folder —
but understand that this permanently destroys your vault along with it. If you
want to keep your card records, copy your own import file and the `data` folder
somewhere safe first, and keep your passphrase.

There is nothing to uninstall elsewhere: no service, no registry entry, no
account, and no cloud data.

---

## Where to go next

- [FAMILY-FINANCE-INTEGRATION.md](FAMILY-FINANCE-INTEGRATION.md) — the optional
  companion button in full detail.
- [VAULT-IMPORT.md](VAULT-IMPORT.md) — every import option and field.
- [../SECURITY.md](../SECURITY.md) — the threat model, stated plainly.
- [../README.md](../README.md) — the short project overview.
- [README.md](README.md) — the documentation index, including the contributor
  and policy documents.
