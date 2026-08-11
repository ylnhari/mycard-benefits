# Optional Docker setup

Docker is an optional packaging route. The Windows PowerShell `uv sync
--locked` path remains the primary setup and Docker is not required.

```sh
docker build -t mycard-benefits:local .
docker run --rm --publish 127.0.0.1:8777:8777 mycard-benefits:local
```

The container proxy listens on the container port while the application itself
still binds only to its own loopback interface. This image contains only the public catalog and runs as a non-root user. It
does not copy `.env`, local vaults, imports, logs, or runtime data. Published
host traffic is explicitly bound to loopback.
