"""Minimal container bridge: public proxy, loopback-only application."""

from __future__ import annotations

import http.client
import os
import signal
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = 8778


class Proxy(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.forward()

    def do_HEAD(self) -> None:  # noqa: N802
        self.forward()

    def do_POST(self) -> None:  # noqa: N802
        self.forward()

    def forward(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        connection = http.client.HTTPConnection("127.0.0.1", UPSTREAM, timeout=10)
        connection.request(self.command, self.path, self.rfile.read(length),
                           {key: value for key, value in self.headers.items()
                            if key.lower() not in {"host", "connection"}})
        response = connection.getresponse()
        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() not in {"connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response.read())
        connection.close()

    def log_message(self, *_args: object) -> None:
        return


def main() -> None:
    app = subprocess.Popen(["uv", "run", "--no-dev", "mycard-benefits", "--no-browser", "--port", str(UPSTREAM)])
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("MYCARD_PROXY_PORT", "8777"))), Proxy)

    def stop(*_args: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    finally:
        app.terminate()
        app.wait(timeout=10)


if __name__ == "__main__":
    main()
