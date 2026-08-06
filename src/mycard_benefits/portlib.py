"""Resolve this project's port.

Self-contained and stdlib-only: copy this file into a project and it works with
no shared dependency, no configuration and no assumptions about the machine.

PRECEDENCE (highest wins):

  1. explicit      a --port passed on the command line. User intent always wins.
  2. env var       e.g. MYAPP_PORT. What containers, CI and systemd units set.
  3. ports.json    a registry file found by walking up from the project
                   directory. Optional: if you don't keep one, this tier is
                   simply skipped.
  4. default       the project's documented port, so a fresh clone runs with no
                   setup. Pass default=None to make the port mandatory instead.

The registry, when present, looks like:

    {
      "registry": {
        "my-project": {"port": 8080, "status": "active"}
      },
      "next_available": 8081
    }

It lets several projects on one machine agree on who owns which port, without
any of them hardcoding a number.

TWO THINGS THIS DELIBERATELY WILL NOT DO:

  * It never reads `next_available`. That field is a hint for whoever allocates
    the NEXT project; consuming it would let two projects independently decide
    they own the same number, which is the exact collision the registry exists
    to prevent.
  * It never hunts for a free port. Tools that map a project to a fixed port -
    reverse proxies, service discovery, dashboards, OAuth redirect URLs - all
    break subtly when a process quietly moves to port+1: the port still answers,
    just as the wrong service. Failing to bind is noisy and obvious; drifting is
    neither.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REGISTRY_NAME = "ports.json"
SEARCH_DEPTH = 4


class PortError(Exception):
    """No port could be resolved, and guessing one would be worse."""


def _port(value: object, label: str) -> int:
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        raise PortError(f"{label}={value!r} is not a port number.")
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise PortError(f"{label}={value!r} is not a port number.") from None
    if not 1 <= port <= 65535:
        raise PortError(f"{label}={value!r} is outside the valid range 1-65535.")
    return port


def find_registry(start: Path | None = None, depth: int = SEARCH_DEPTH) -> Path | None:
    """Nearest ports.json at or above `start`, or None."""
    here = Path(start or Path(__file__).resolve().parent).resolve()
    for candidate in [here, *here.parents][: depth + 1]:
        path = candidate / REGISTRY_NAME
        if path.is_file():
            return path
    return None


def registry_port(
    project_key: str,
    registry: Path | None = None,
    start: Path | None = None,
) -> int | None:
    """Return the registered port or None; reject malformed configuration."""
    path = registry or find_registry(start)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortError(f"{path} is unreadable or not valid JSON: {exc}") from None
    entry = (data.get("registry") or {}).get(project_key)
    if not entry or entry.get("port") in (None, ""):
        return None
    return _port(entry["port"], f"{path}: registry.{project_key}.port")


def resolve_port(
    project_key: str,
    *,
    explicit: int | None = None,
    env_var: str | None = None,
    default: int | None = None,
    registry: Path | None = None,
    start: Path | None = None,
) -> int:
    """Apply the documented precedence and return a port or raise PortError."""
    if explicit is not None:
        return _port(explicit, "--port")
    if env_var:
        raw = os.environ.get(env_var)
        if raw is not None and raw != "":
            return _port(raw, env_var)
    found = registry_port(project_key, registry=registry, start=start)
    if found is not None:
        return found
    if default is not None:
        return _port(default, "default port")
    where = registry or find_registry(start) or f"any {REGISTRY_NAME} above this project"
    raise PortError(
        f"No port for {project_key!r}. Checked: "
        f"{'--port, ' if explicit is None else ''}"
        f"{env_var + ', ' if env_var else ''}{where}.\n"
        f"Either add a {REGISTRY_NAME} entry:\n"
        f'    "{project_key}": {{"port": <n>, "status": "active"}}\n'
        "or pass --port explicitly. This project has no default port on purpose."
    )
