# MyCard Benefits

MyCard Benefits is an India-first, globally extensible, local-first companion
for recording cards and understanding their verified benefits. It deliberately
separates public card knowledge from private card records.

## Status

Local alpha. The public synthetic catalog, traceable Q&A, review stores,
research queue, optimizer core, and encrypted vault core are implemented and
tested. A bounded local CLI can create and import a private encrypted vault;
real-card browser/API controls remain disabled until a protected human-facing
surface is independently reviewed.

## Product boundaries

- Public: card variants, reward rules, conversions, lounges, movies, hotels,
  dining, vouchers, meet-and-greet, network programs, evidence, and history.
- Private: card instances, lifecycle, PAN/CVV/PIN, notes, allowances, reminders,
  and attachments in an encrypted local vault.
- Not included: spending ledger, bank login, OTP storage, payments, applications,
  bookings, redemptions, or automatic document submission.

The core works without an LLM. Optional agents operate only on public catalog
facts and safe identifiers.

## Local setup

Requirements: Python 3.12+ and `uv`.

```powershell
uv sync
uv run mycard-benefits --demo
```

The application binds to `127.0.0.1`. Port precedence is `--port`,
`MYCARD_BENEFITS_PORT`, nearest `ports.json`, then the documented clone
fallback. Remote access must use an authenticated gateway.

## Private card import

Real manifests belong only under ignored `imports/`. The importer validates the
complete batch and persists it in one encrypted vault revision; it never prints
decrypted fields. Interactive passphrases work with the base install. Optional
operating-system keyring support is installed with `uv sync --locked --extra
keyring`.

See [docs/VAULT-IMPORT.md](docs/VAULT-IMPORT.md). The tracked
[samples/card-import.example.json](samples/card-import.example.json) contains
synthetic data only.

## Family Finance

Family Finance remains independent. Its existing Cards page has an optional
MyCard Benefits companion button. If this repository is not installed or is not
running, the button opens setup documentation. An encrypted, previewed one-time
import is planned for a later security milestone; the two stores will not
synchronize afterward.

See [docs/FAMILY-FINANCE-INTEGRATION.md](docs/FAMILY-FINANCE-INTEGRATION.md).

## Safety

This software is not a bank, payment processor, wallet, or financial adviser.
Always verify current eligibility and fulfillment with the official issuer,
network, or merchant before relying on a benefit. See [SECURITY.md](SECURITY.md).

## Development

```powershell
uv run ruff check .
uv run pytest
```

Read [AGENTS.md](AGENTS.md), [PROJECT_STATUS.md](PROJECT_STATUS.md), and
[DECISIONS.md](DECISIONS.md) before contributing. Product intent and new ideas
live in [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) and
[docs/IDEA-LOG.md](docs/IDEA-LOG.md); the accepted questionnaire trace lives in
[docs/DECISION-TRACE.md](docs/DECISION-TRACE.md) and the complete numbered
matrix in [docs/QUESTIONNAIRE-DECISIONS.md](docs/QUESTIONNAIRE-DECISIONS.md), so
implementation does not depend on chat history.

## License

MIT.
