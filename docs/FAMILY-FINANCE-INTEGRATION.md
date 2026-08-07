# Family Finance integration

MyCard Benefits is an optional companion, not a replacement for the Cards page
inside My Family Finance. Both applications remain useful on their own and do
not share a database.

## Install and run the companion

From a clone of this repository:

```powershell
uv sync
uv run mycard-benefits
```

The application binds to loopback only. Its printed URL uses, in order, an
explicit `--port`, `MYCARD_BENEFITS_PORT`, the nearest `ports.json` entry, or
the documented clone fallback.

In My Family Finance, open **Cards**, choose **Companion setup**, and enter:

- On the same computer: the printed loopback URL, such as
  `http://127.0.0.1:8777`.
- From another device: a URL from an external authenticated gateway or project
  launcher you control. MyCard does not prescribe, identify, or configure that
  tool. A remote hostname or address must use an authenticated HTTPS gateway.

Then choose **MyCard Benefits companion**. If no URL is configured or the
configured app cannot be reached, Family Finance opens its bundled setup guide.

## Remote access boundary

Never expose MyCard Benefits directly or change its bind to `0.0.0.0`. If you
use a project launcher or reverse proxy, keep its authentication enabled and
use its assigned URL. That external tool is not a MyCard dependency; no launcher
secret belongs in either application's source, URL, browser storage, or docs.

## Data boundary

The launcher sends no card, owner, document, spending, or finance data. Its
reachability probe is a body-free, credential-free, no-referrer request to the
companion health endpoint. The destination URL is an explicit browser-local
setting and never enters the Family Finance data file or backups.

The approved one-time encrypted import is a later milestone. It is not present
in the current build, and the applications do not synchronize. Do not copy a
Family Finance data file into this repository or upload it to an issue, agent,
model, or public service.

## Removing the connection

Open **Companion setup**, clear the field, and save. This removes only the
browser-local launch URL. It does not stop either application or modify either
application's records.
