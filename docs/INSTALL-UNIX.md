# Linux and macOS setup

Python 3.12+ and `uv` are required. From a fresh clone, run:

```sh
uv sync --locked
uv run mycard-benefits --demo --no-browser
```

Open the printed `http://127.0.0.1:8777` address. The server is loopback-only;
do not replace the bind with a LAN address. `--extra keyring` is optional and
is only needed for the browser's local OS-keyring vault view. No network,
account, credential, or cloud service is required after dependencies are
available locally. Stop with Ctrl-C.
