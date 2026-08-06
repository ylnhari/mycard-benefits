"""Command-line entry point."""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from .app import create_app
from .config import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MyCard Benefits local server")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_environment(
        explicit_port=args.port,
        explicit_data_dir=args.data_dir,
        demo=args.demo,
    )
    url = f"http://127.0.0.1:{settings.port}"
    print("MyCard Benefits" + (" [DEMO]" if settings.demo else ""))
    print(f"App: {url}")
    print("Private data remains local. The application binds only to 127.0.0.1.")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port)
