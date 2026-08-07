# Private vault import

The supported one-time import path accepts a bounded JSON manifest and writes
all records to the encrypted local vault in one revision. The manifest, vault,
and backups are private runtime files: keep real manifests under ignored
`imports/` and never commit them.

## Install

For an interactive passphrase:

```powershell
uv sync --locked
```

For Windows Credential Manager or another operating-system keyring:

```powershell
uv sync --locked --extra keyring
```

## Prepare the manifest

Copy `samples/card-import.example.json` into ignored `imports/` and replace the
synthetic entries locally. Each card has:

- `offering_id`: a stable public product identifier or temporary local slug;
  use 1-128 lowercase letters, digits, dots, underscores, or hyphens, starting
  with a letter or digit;
- `lifecycle`: `active`, `expired`, `lost`, `stolen`, `closed`, or `archived`;
- `secret_fields`: one or more supported encrypted values such as `nickname`,
  `cardholder_name`, expiry, notes, PAN, CVV, PIN, or billing postcode.

Prefer metadata-only imports. Do not copy PAN, CVV, PIN, or full document text
from scans unless the owner specifically needs those values in the vault.

## Create and import

Interactive, portable passphrase:

```powershell
uv run mycard-vault import --manifest imports/cards.json --create
```

Operating-system keyring with a generated device-local passphrase:

```powershell
uv run mycard-vault --keyring import --manifest imports/cards.json --create
```

To use another app-owned data root, place the global option before the command:

```powershell
uv run mycard-vault --data-dir D:\MyCardData --keyring import --manifest imports/cards.json --create
```

The tool always owns and restricts the `<data-dir>/private` child directory. Do
not point `--data-dir` at a location whose existing `private` child contains
unrelated files.

The keyring mode does not print or write the generated passphrase. It is tied
to the operating-system account and the resolved vault path. Keep the original
private manifest or a separate secure recovery source; losing the keyring can
make that vault unrecoverable.

If vault creation succeeds but a later batch import fails, keep the vault and
retry the corrected manifest without `--create`; the stored unlock credential
is deliberately preserved.

Verify integrity and the non-secret record count without revealing fields:

```powershell
uv run mycard-vault --keyring verify
```

The browser dashboard and HTTP API still do not expose real-card records. This
CLI is the deliberately narrow initial import surface.
