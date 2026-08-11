# Private migration safety

Private metadata migrations are numbered under `migrations/versions/` and run
only against a user-selected local database. The production entry point is
`mycard-vault migrate --database PATH`; it requires an existing vault and an
interactive passphrase, or the existing local OS-keyring entry when invoked
with `--keyring`. The command performs this sequence:

1. Acquire a real SQLite `BEGIN IMMEDIATE` writer lock before taking any
   snapshot. This blocks unrelated SQLite writers, not merely MyCard's
   advisory lock.
2. Use SQLite's backup/checkpoint APIs to make a WAL-consistent rehearsal and
   durable prior last-known-good (LKG) image.
3. Apply `head` to the rehearsal and validate its required metadata tables and
   authenticated vault readability.
4. Apply the same migration through the still writer-locked live SQLite
   connection, then commit it as one SQLite transaction. The live database is
   deliberately not filesystem-replaced: closing it to replace it is unsafe on
   Windows and could lose an external writer.
5. Build, validate, fsync, and atomically replace the LKG only after the live
   transaction commits. If LKG promotion fails, the old LKG is retained and the
   committed live database is never overwritten with stale data.

The runner fails closed if either input is missing, if the rehearsal schema is
wrong, or if the authenticated vault cannot be opened. A failure before the
live commit rolls SQLite back; it does not overwrite the live database from a
filesystem copy. The command creates and verifies a separate encrypted vault
backup only after the successful metadata commit. It is local-only and does
not contact a remote service.

The card vault itself remains an authenticated JSON envelope. Alembic stores
only non-secret local metadata and never receives decrypted card fields. The
current audit and attachment service implementations remain file-backed; this
runner does not claim that those files are SQLAlchemy rows.
