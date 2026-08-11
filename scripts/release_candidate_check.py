"""Run local-only release-candidate checks over an exact Git range."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import io
import json
import re
import subprocess
import sys
import tokenize
import unicodedata
from pathlib import PurePosixPath
from typing import Any, NamedTuple


def _join(*parts: str) -> str:
    """Keep detector policy tokens out of the detector's own scan input."""

    return "".join(parts)


_key_marker = _join("-----BEGIN ", "(?:RSA|OPENSSH|EC|", "PRIVATE", ") KEY-----")
_cloud_key = _join(r"\b(?:", "AK", "IA|AS", "IA)") + r"[A-Z0-9]{16}\b"
_api_key = _join(r"\b(?:gh[pousr]_", "|sk-", r")[A-Za-z0-9_-]{12,}\b")
_credential_names = _join(
    "password", "|", "passphrase", "|", "client", "_", "secret", "|",
    "access", "_", "token", "|", "api", "_", "key",
)
SECRET_PATTERNS = (
    re.compile(_key_marker),
    re.compile(_cloud_key),
    re.compile(_api_key),
    # Match concrete credential assignments, not Python type annotations or
    # value-free synthetic fixtures. Quoted values and long token-shaped values
    # remain covered; identifiers such as ``passphrase: str`` do not.
    re.compile(
        r"(?i)(?:\b(?:" + _credential_names + r")[ \t]*[:=][ \t]*(?:['\"][^'\"\r\n]{8,}['\"]|[A-Za-z0-9-]{16,})"
        r"|['\"](?:" + _credential_names + r")[ '\"]*:[ \t]*['\"][^'\"\r\n]{8,}['\"])",
    ),
)
_VALUE_FREE_COMMENT_MARKER = re.compile(
    r'''(?i)["']<(?:value omitted|redacted|placeholder)>["']\s*$'''
)
PRIVATE_PATH_PATTERNS = (
    re.compile(r"(?i)(?:[A-Z]:\\" + _join("Users") + r"\\|/" + _join("Users") + r"/|/" + _join("home") + r"/|\\" + _join("Users") + r"\\)[^\r\n]*"),
    re.compile(r"(?i)(?<![\w.])(?:\.env(?!\.example)(?:[./\\]|$)|private[\s/\\]+vault\.json|data[\s/\\]+finances\.json)"),
)
MACHINE_PATH_PATTERNS = (
    re.compile(r"(?i)\b[A-Z]:[\\/]"),
    re.compile(r"(?i)(?<![A-Za-z0-9_])/(?:Users|home)/"),
    re.compile(r"(?i)(?<![A-Za-z0-9_])" + _join(r"\\") + "Users" + _join(r"\\")),
)
PRIVATE_DIR_PARTS = {".env", "data", "demo-data", "imports", "backups", "evidence-private"}
RAW_SOURCE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".zip"}
_MAX_CONSTANT_SIZE = 8192
_CREDENTIAL_TARGET_NAMES = {"api_key", "access_token", "client_secret", "password", "passphrase", "secret"}


class TreeEntry(NamedTuple):
    """One immutable path/blob pair observed in an event commit tree."""

    mode: str
    kind: str
    object_id: str
    path: str


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8", stderr=subprocess.STDOUT).strip()


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _require_sha(value: str, label: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be an exact 40-hex object ID")


def _object_exists(value: str, kind: str) -> None:
    actual = git("cat-file", "-t", value)
    if actual != kind:
        raise ValueError(f"{value} is not a {kind}")


def changed_files(base: str, head: str) -> list[str]:
    _require_sha(head, "head")
    if base != EMPTY_TREE:
        _require_sha(base, "base")
    output = git("diff", "--name-only", f"{base}..{head}")
    return [line for line in output.splitlines() if line]


def _commit_ids(base: str, head: str, initial: bool) -> list[str]:
    _require_sha(head, "head")
    _object_exists(head, "commit")
    if initial:
        if base != EMPTY_TREE:
            raise ValueError("initial scan requires the Git empty-tree base")
        return [line for line in git("rev-list", "--topo-order", "--reverse", head).splitlines() if line]
    if base == EMPTY_TREE:
        raise ValueError("empty-tree base requires --initial")
    _require_sha(base, "base")
    _object_exists(base, "commit")
    # --not gives an exact immutable object set for both normal and force-push ranges.
    return [line for line in git("rev-list", "--topo-order", "--reverse", head, "--not", base).splitlines() if line]


def _tree_entries(commit: str) -> list[TreeEntry]:
    """Return every recursive tree entry, retaining modes and object IDs.

    ``git diff --name-only`` cannot see a path that was later removed, a pure
    mode change, or an arbitrary binary blob.  The event scanner therefore
    enumerates every tree recorded by every newly reachable commit.
    """
    raw = subprocess.check_output(["git", "ls-tree", "-r", "-z", commit], stderr=subprocess.STDOUT)
    entries: list[TreeEntry] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        header, name = item.split(b"\t", 1)
        mode, kind, object_id = header.split(b" ")
        entries.append(
            TreeEntry(
                mode.decode(),
                kind.decode(),
                object_id.decode(),
                name.decode("utf-8", "surrogateescape"),
            )
        )
    return entries


def _blob_bytes(object_ids: set[str]) -> dict[str, bytes]:
    """Read the event's unique blobs in one bounded Git batch.

    This deliberately does not use ``rev-list --objects``: that command also
    feeds commit/tree serialization to a blob reader and can turn a complete
    range check into an unnecessarily large scan.  Every blob is instead
    reached through the fully enumerated event trees above.
    """
    if not object_ids:
        return {}
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=("\n".join(sorted(object_ids)) + "\n").encode(),
        capture_output=True,
        check=True,
    )
    blobs: dict[str, bytes] = {}
    cursor = 0
    while cursor < len(result.stdout):
        line_end = result.stdout.index(b"\n", cursor)
        header = result.stdout[cursor:line_end].split()
        cursor = line_end + 1
        if len(header) != 3 or header[1] != b"blob":
            raise ValueError("event tree contains a missing or non-blob object")
        object_id = header[0].decode()
        size = int(header[2])
        body = result.stdout[cursor : cursor + size]
        if len(body) != size:
            raise ValueError("blob disappeared during scan")
        blobs[object_id] = body
        cursor += size
        if cursor >= len(result.stdout) or result.stdout[cursor : cursor + 1] != b"\n":
            raise ValueError("malformed Git batch output")
        cursor += 1
    if set(blobs) != object_ids:
        raise ValueError("incomplete blob batch")
    return blobs


def _history_text(commit_ids: list[str], entries: list[TreeEntry]) -> str:
    chunks: list[str] = []
    for commit in commit_ids:
        # Commit metadata and raw parent deltas retain path-only and mode-only
        # violations as well as content that was introduced then deleted,
        # renamed, copied, or hidden by a merge result.
        chunks.append(git("cat-file", "commit", commit))
        raw_delta = git(
            "diff-tree",
            "--root",
            "-r",
            "-m",
            "--no-commit-id",
            "--raw",
            "-z",
            "-M",
            "-C",
            commit,
        )
        # ``--raw -z`` is deliberately NUL-delimited so unusual path names
        # are unambiguous.  Restore a scan boundary for line-local compacting;
        # otherwise two independent raw records are concatenated as one.
        chunks.append(raw_delta.replace("\0", "\n"))
    chunks.extend(f"{entry.mode} {entry.kind} {entry.path}" for entry in entries)
    return "\n".join(chunks)


def _final_tree_text(entries: list[TreeEntry], blobs: dict[str, bytes]) -> tuple[list[str], str]:
    paths = [entry.path for entry in entries]
    # Scan the final tree's actual blobs, not commit/tree serialization.
    text_parts: list[str] = []
    for entry in entries:
        if entry.kind != "blob":
            continue
        body = blobs[entry.object_id]
        if b"\0" in body:
            continue
        text_parts.append(entry.path + "\n" + body.decode("utf-8"))
    return paths, "\n".join(text_parts)


def _ast_target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for element in node.elts for name in _ast_target_names(element)}
    return set()


def _credential_target_names(node: ast.AST) -> set[str]:
    """Return credential names from names, attributes, and constant keys."""
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr, *_credential_target_names(node.value)}
    if isinstance(node, ast.Subscript):
        names = _credential_target_names(node.value)
        key = _constant_string_expression(node.slice)
        if key is not None:
            names.add(key)
        return names
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for element in node.elts for name in _credential_target_names(element)}
    return set()


def _bounded_constant(node: ast.AST | None) -> Any:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes, int, float, bool, type(None))):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _bounded_constant(node.operand)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return +value if isinstance(node.op, ast.UAdd) else -value
        return None
    if isinstance(node, (ast.Tuple, ast.List)):
        values = tuple(_bounded_constant(item) for item in node.elts)
        return values if all(value is not None for value in values) else None
    if isinstance(node, ast.BinOp):
        left = _bounded_constant(node.left)
        right = _bounded_constant(node.right)
        try:
            if isinstance(node.op, ast.Add) and type(left) is type(right) and isinstance(left, (str, bytes)):
                result = left + right
            elif isinstance(node.op, ast.Mult) and isinstance(left, (str, bytes)) and isinstance(right, int):
                result = left * right
            elif isinstance(node.op, ast.Mult) and isinstance(right, (str, bytes)) and isinstance(left, int):
                result = right * left
            elif isinstance(node.op, ast.Mod) and isinstance(left, str) and right is not None:
                result = left % right
            else:
                return None
        except (ArithmeticError, LookupError, TypeError, ValueError):
            return None
        return result if isinstance(result, (str, bytes)) and len(result) <= _MAX_CONSTANT_SIZE else None
    if isinstance(node, ast.JoinedStr):
        pieces: list[str] = []
        for item in node.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                pieces.append(item.value)
                continue
            if not isinstance(item, ast.FormattedValue):
                return None
            value = _bounded_constant(item.value)
            if value is None or isinstance(value, (bytes, tuple)):
                return None
            spec = ""
            if item.format_spec is not None:
                spec_value = _bounded_constant(item.format_spec)
                if not isinstance(spec_value, str):
                    return None
                spec = spec_value
            try:
                pieces.append(format(value, spec))
            except (ArithmeticError, TypeError, ValueError):
                return None
        result = "".join(pieces)
        return result if len(result) <= _MAX_CONSTANT_SIZE else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        receiver = _bounded_constant(node.func.value)
        if node.func.attr == "join" and isinstance(receiver, str) and len(node.args) == 1 and not node.keywords:
            values = _bounded_constant(node.args[0])
            if isinstance(values, tuple) and all(isinstance(value, str) for value in values):
                result = receiver.join(values)
                return result if len(result) <= _MAX_CONSTANT_SIZE else None
        if node.func.attr == "format" and isinstance(receiver, str):
            args = tuple(_bounded_constant(arg) for arg in node.args)
            keywords = {
                keyword.arg: _bounded_constant(keyword.value)
                for keyword in node.keywords
                if keyword.arg is not None
            }
            if all(value is not None for value in args) and all(value is not None for value in keywords.values()):
                try:
                    result = receiver.format(*args, **keywords)
                except (IndexError, KeyError, ValueError):
                    return None
                return result if len(result) <= _MAX_CONSTANT_SIZE else None
        if node.func.attr == "encode" and isinstance(receiver, str) and len(node.args) <= 1 and not node.keywords:
            encoding = _bounded_constant(node.args[0]) if node.args else "utf-8"
            if encoding in {"utf-8", "utf8", "ascii"}:
                try:
                    return receiver.encode(str(encoding))
                except UnicodeEncodeError:
                    return None
        if node.func.attr == "decode" and isinstance(receiver, bytes) and len(node.args) <= 1 and not node.keywords:
            encoding = _bounded_constant(node.args[0]) if node.args else "utf-8"
            if encoding in {"utf-8", "utf8", "ascii"}:
                try:
                    return receiver.decode(str(encoding))
                except UnicodeDecodeError:
                    return None
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "base64" and node.func.attr in {"b64decode", "urlsafe_b64decode"} and len(node.args) == 1 and not node.keywords:
            encoded = _bounded_constant(node.args[0])
            if isinstance(encoded, str):
                encoded = encoded.encode("ascii", errors="ignore")
            if isinstance(encoded, bytes) and len(encoded) <= _MAX_CONSTANT_SIZE:
                try:
                    result = getattr(base64, node.func.attr)(encoded)
                except (binascii.Error, ValueError, TypeError):
                    return None
                return result if len(result) <= _MAX_CONSTANT_SIZE else None
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "bytes" and node.func.attr == "fromhex" and len(node.args) == 1 and not node.keywords:
            encoded = _bounded_constant(node.args[0])
            if isinstance(encoded, str) and len(encoded) <= _MAX_CONSTANT_SIZE:
                try:
                    return bytes.fromhex(encoded)
                except ValueError:
                    return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "chr" and len(node.args) == 1 and not node.keywords:
        value = _bounded_constant(node.args[0])
        if isinstance(value, int) and 0 <= value <= 0x10FFFF:
            return chr(value)
    return None


def _constant_string_expression(node: ast.AST | None) -> str | None:
    value = _bounded_constant(node)
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _python_string_credential_finding(
    tree: ast.AST, text: str, ignored_spans: list[tuple[int, int]]
) -> bool:
    """Scan parsed string values without treating Python source syntax as data."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.BinOp, ast.Call, ast.JoinedStr)):
            continue
        span = _node_span(text, node)
        if span is not None and any(span[0] < end and start < span[1] for start, end in ignored_spans):
            continue
        value = _constant_string_expression(node)
        if value is not None and SECRET_PATTERNS[3].search(_normalized_text(value)) is not None:
            return True
    return False


def _python_comment_credential_finding(text: str) -> bool:
    """Scan concrete credential signatures in Python comments only."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            normalized = _normalized_text(token.string)
            for match in SECRET_PATTERNS[3].finditer(normalized):
                if _VALUE_FREE_COMMENT_MARKER.search(match.group(0)) is None:
                    return True
    except (SyntaxError, tokenize.TokenError):
        return True
    return False


def _unknown_credential_material(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"getpass", "input", "prompt"}:
        return False
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, (str, bytes)) and len(item.value) >= 8:
            return True
        if isinstance(item, (ast.JoinedStr, ast.BinOp)):
            return True
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr in {"format", "decode", "b64decode", "urlsafe_b64decode", "fromhex"}:
            return True
    return False


def _python_credential_finding(text: str, *, path: str | None = None) -> bool:
    if _python_comment_credential_finding(text):
        return True
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        # Without a valid AST, no value-free Python context can be proven.
        return True
    ignored_spans = [
        *_policy_literal_spans(path or "", text),
        *_synthetic_test_spans(path or "", text),
        *_synthetic_credential_fixture_spans(path or "", text),
        *_synthetic_policy_test_spans(path or "", text),
        *_documentation_spans(path or "", text),
    ]
    masked = _mask_spans(text, ignored_spans)
    if any(pattern.search(masked) for pattern in SECRET_PATTERNS[:3]):
        return True
    if _python_string_credential_finding(tree, text, ignored_spans):
        return True
    for node in ast.walk(tree):
        value: str | None = None
        names: set[str] = set()
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign):
            names = {name.casefold() for target in node.targets for name in _credential_target_names(target)}
            value_node = node.value
            value = _constant_string_expression(value_node)
        elif isinstance(node, ast.AnnAssign):
            names = {name.casefold() for name in _credential_target_names(node.target)}
            value_node = node.value
            value = _constant_string_expression(value_node) if value_node is not None else None
        elif isinstance(node, ast.NamedExpr):
            names = {name.casefold() for name in _credential_target_names(node.target)}
            value_node = node.value
            value = _constant_string_expression(value_node)
        if (
            value_node is not None
            and any(name in _CREDENTIAL_TARGET_NAMES for name in names)
        ):
            if value is not None and (
                value.casefold().startswith("synthetic ")
                or (value.casefold().startswith("synthetic-only-") and "passphrase" in names)
            ):
                continue
            if value is not None or _unknown_credential_material(value_node):
                return True
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg and keyword.arg.casefold() in _CREDENTIAL_TARGET_NAMES:
                    value = _constant_string_expression(keyword.value)
                    if value is not None and "synthetic" in value.casefold():
                        continue
                    if value is not None or _unknown_credential_material(keyword.value):
                        return True
    return False


def _normalized_text(text: str) -> str:
    normalized: list[str] = []
    for character in unicodedata.normalize("NFKC", text):
        if unicodedata.category(character) == "Cf":
            continue
        if character in {"\u2044", "\u2215", "\u29f8", "\uFF0F"}:
            normalized.append("/")
        elif character.isspace():
            normalized.append(" ")
        else:
            normalized.append(character)
    return "".join(normalized)


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _node_span(text: str, node: ast.AST) -> tuple[int, int] | None:
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)
    col_offset = getattr(node, "col_offset", None)
    end_col_offset = getattr(node, "end_col_offset", None)
    if not (
        isinstance(lineno, int)
        and isinstance(end_lineno, int)
        and isinstance(col_offset, int)
        and isinstance(end_col_offset, int)
    ):
        return None
    offsets = _line_offsets(text)
    return (
        offsets[lineno - 1] + col_offset,
        offsets[end_lineno - 1] + end_col_offset,
    )


def _policy_literal_spans(path: str, text: str) -> list[tuple[int, int]]:
    normalized_path = path.replace("\\", "/").casefold()
    if normalized_path not in {
        "scripts/release_candidate_check.py",
        "scripts/release_scan.py",
    }:
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    spans: list[tuple[int, int]] = []
    for statement in ast.walk(tree):
        if not isinstance(statement, ast.Assign):
            continue
        names = {name.casefold() for target in statement.targets for name in _ast_target_names(target)}
        if not names or not any(
            token in name
            for name in names
            for token in ("pattern", "category", "part", "suffix", "directory", "numeric", "private", "machine", "text", "fixture")
        ):
            continue
        spans.extend(
            span
            for node in ast.walk(statement.value)
            if isinstance(node, ast.Constant) and isinstance(span := _node_span(text, node), tuple)
        )
    if normalized_path == "scripts/release_scan.py":
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
                value_text = node.value.decode("utf-8", "ignore") if isinstance(node.value, bytes) else node.value
                if any(marker in value_text.casefold() for marker in (".env", "private", "data/", "vault", "users", "home")):
                    span = _node_span(text, node)
                    if span is not None:
                        spans.append(span)
    return spans


def _synthetic_test_spans(path: str, text: str) -> list[tuple[int, int]]:
    if path.replace("\\", "/") != "tests/test_release_scan.py":
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "parametrize"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in {"source", "variant", "split_source"}
        ):
            for value in node.args[1:2]:
                spans.extend(
                    span
                    for item in ast.walk(value)
                    if isinstance(item, ast.Constant) and isinstance(span := _node_span(text, item), tuple)
                )
        if isinstance(node, ast.FunctionDef) and node.name == "test_candidate_machine_fixture_exception_is_exact_and_context_bound":
            spans.extend(
                span
                for item in ast.walk(node)
                if isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and any(
                    marker in unicodedata.normalize("NFKC", item.value)
                    for marker in (_join("\\", "Users", "\\"), _join("/", "Users", "/"), _join("/", "home", "/"))
                )
                and isinstance(span := _node_span(text, item), tuple)
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"write_text", "write_bytes"}:
            for value in node.args:
                spans.extend(
                    span
                    for item in ast.walk(value)
                    if isinstance(item, ast.Constant) and isinstance(span := _node_span(text, item), tuple)
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_git":
            spans.extend(
                span
                for value in node.args
                for item in ast.walk(value)
                if isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and any(marker in unicodedata.normalize("NFKC", item.value).casefold() for marker in (".env", "data", "private", "vault"))
                and isinstance(span := _node_span(text, item), tuple)
            )
        if isinstance(node, ast.Assign) and any(name == "public_hash" for target in node.targets for name in _ast_target_names(target)):
            span = _node_span(text, node.value)
            if span is not None:
                spans.append(span)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            normalized_value = unicodedata.normalize("NFKC", node.value).casefold()
            if any(marker in normalized_value for marker in (".env", "data", "private", "vault")):
                span = _node_span(text, node)
                if span is not None:
                    spans.append(span)
    return spans


def _synthetic_credential_fixture_spans(path: str, text: str) -> list[tuple[int, int]]:
    """Mask only parsed synthetic credential fixture values in tests."""
    if not path.replace("\\", "/").casefold().startswith("tests/"):
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.BinOp, ast.Call, ast.JoinedStr)):
            continue
        value = _constant_string_expression(node)
        if (
            value is not None
            and "SYNTHETIC-ONLY-" in value
            and SECRET_PATTERNS[3].search(_normalized_text(value)) is not None
        ):
            span = _node_span(text, node)
            if span is not None:
                spans.append(span)
    return spans


def _synthetic_policy_test_spans(path: str, text: str) -> list[tuple[int, int]]:
    normalized_path = path.replace("\\", "/").casefold()
    if normalized_path not in {
        "tests/test_claude_optimizer_and_education_batch.py",
        "tests/test_public_safety.py",
    }:
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {name.casefold() for target in node.targets for name in _ast_target_names(target)}
        if not any(token in name for name in names for token in ("forbidden", "pattern", "path")):
            continue
        spans.extend(
            span
            for item in ast.walk(node.value)
            if isinstance(item, ast.Constant) and isinstance(span := _node_span(text, item), tuple)
        )
    return spans


def _documentation_spans(path: str, text: str) -> list[tuple[int, int]]:
    if not path.casefold().endswith((".md", ".rst", ".txt")):
        return []
    return [
        (match.start(1), match.end(1))
        for match in re.finditer(r"`([^`\r\n]+)`", text)
        if any(marker in match.group(1).casefold() for marker in (".env", "private", "data/", "vault"))
    ]


def _mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(max(0, start), min(len(chars), end)):
            chars[index] = " "
    return "".join(chars)


def _valid_public_hash_spans(path: str, text: str) -> list[tuple[int, int]]:
    suffix = path.casefold()
    spans: list[tuple[int, int]] = []
    if suffix.endswith(".py"):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = {name.casefold() for target in targets for name in _ast_target_names(target)}
                if names & {"content_hash", "content_sha256", "hash"} and node.value is not None:
                    value = _constant_string_expression(node.value)
                    if value is not None and re.fullmatch(r"(?i)[0-9a-f]{64}", value):
                        span = _node_span(text, node.value)
                        if span is not None:
                            relative = text[span[0] : span[1]].find(value)
                            if relative >= 0:
                                spans.append((span[0] + relative, span[0] + relative + len(value)))
            elif isinstance(node, ast.Call):
                values = [keyword.value for keyword in node.keywords if keyword.arg in {"content_hash", "content_sha256", "hash"}]
                if isinstance(node.func, ast.Name) and node.func.id == "_source" and len(node.args) > 6:
                    values.append(node.args[6])
                for value_node in values:
                    value = _constant_string_expression(value_node)
                    if value is None or re.fullmatch(r"(?i)[0-9a-f]{64}", value) is None:
                        continue
                    span = _node_span(text, value_node)
                    if span is not None:
                        relative = text[span[0] : span[1]].find(value)
                        if relative >= 0:
                            spans.append((span[0] + relative, span[0] + relative + len(value)))
    elif suffix.endswith(".json"):
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        for match in re.finditer(r'(?i)["\'](?:content_hash|content_sha256|hash)["\']\s*:\s*["\']([0-9a-f]{64})["\']', text):
            spans.append((match.start(1), match.end(1)))
    elif suffix.endswith(".toml") or suffix == "uv.lock":
        try:
            import tomllib

            tomllib.loads(text)
        except (ValueError, tomllib.TOMLDecodeError):
            return []
        for match in re.finditer(r'(?im)^\s*(?:content_hash|content_sha256|hash)\s*=\s*["\'](?:sha256:)?([0-9a-f]{64})["\']', text):
            spans.append((match.start(1), match.end(1)))
    return spans


def _pattern_findings(
    text: str, *, path: str | None = None, history: bool = False
) -> list[str]:
    masked = _mask_spans(text, [
        *_policy_literal_spans(path or "", text),
        *_synthetic_test_spans(path or "", text),
        *_synthetic_credential_fixture_spans(path or "", text),
        *_synthetic_policy_test_spans(path or "", text),
        *_documentation_spans(path or "", text),
    ])
    normalized = _normalized_text(masked)
    findings: list[str] = []
    if history:
        patterns: tuple[re.Pattern[str], ...] = SECRET_PATTERNS[:3]
    elif path is not None and path.casefold().endswith(".py"):
        if _python_credential_finding(text, path=path):
            findings.append("prohibited diff pattern: credential signature")
        patterns = (*SECRET_PATTERNS[:3], *PRIVATE_PATH_PATTERNS, *MACHINE_PATH_PATTERNS)
    else:
        patterns = (*SECRET_PATTERNS, *PRIVATE_PATH_PATTERNS, *MACHINE_PATH_PATTERNS)
    for pattern in patterns:
        if pattern.search(normalized):
            findings.append(f"prohibited diff pattern: {pattern.pattern}")
    return findings


def _path_findings(entries: list[TreeEntry]) -> list[str]:
    findings: list[str] = []
    for entry in entries:
        normalized_path = _normalized_text(entry.path).replace("\\", "/")
        parts = {part.casefold() for part in normalized_path.split("/")}
        if any("\udc80" <= character <= "\udcff" for character in entry.path):
            findings.append("invalid Git path encoding")
        if entry.kind != "blob":
            findings.append(f"non-blob tree entry: {entry.path}")
        if entry.mode == "120000":
            findings.append(f"symlink tree entry: {entry.path}")
        if PurePosixPath(normalized_path).suffix.casefold() in RAW_SOURCE_SUFFIXES or "raw" in parts:
            findings.append(f"raw-source-or-binary path: {entry.path}")
        if parts & PRIVATE_DIR_PARTS:
            findings.append(f"private-runtime path: {entry.path}")
        findings.extend(_pattern_findings(entry.path))
    return findings


def _blob_findings(entries: list[TreeEntry], blobs: dict[str, bytes]) -> list[str]:
    findings: list[str] = []
    paths_by_blob: dict[str, list[str]] = {}
    for entry in entries:
        if entry.kind == "blob":
            paths_by_blob.setdefault(entry.object_id, []).append(entry.path)
    for object_id, paths in paths_by_blob.items():
        body = blobs[object_id]
        if b"\0" in body:
            findings.append("invalid textual blob")
            continue
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            findings.append("invalid textual blob")
            continue
        findings.extend(_pattern_findings(text, path=paths[0]))
    return findings


def scan(base: str, head: str, *, initial: bool = False) -> list[str]:
    findings: list[str] = []
    commits = _commit_ids(base, head, initial)
    history_entries = [entry for commit in commits for entry in _tree_entries(commit)]
    final_entries = _tree_entries(head)
    entries = [*history_entries, *final_entries]
    blobs = _blob_bytes({entry.object_id for entry in entries if entry.kind == "blob"})
    _final_files, _final_text = _final_tree_text(final_entries, blobs)
    findings.extend(_path_findings(entries))
    findings.extend(_blob_findings(entries, blobs))
    findings.extend(_pattern_findings(_history_text(commits, history_entries), history=True))
    try:
        subprocess.check_output(["git", "diff", "--check", f"{base}..{head}"], text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        findings.append("diff hygiene: git diff --check failed")
        if exc.output and len(exc.output.splitlines()) > 20:
            findings.append("diff hygiene: more than 20 whitespace findings")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="exact base commit or the Git empty-tree ID")
    parser.add_argument("--head", required=True, help="exact head commit ID; mutable refs are rejected")
    parser.add_argument("--initial", action="store_true", help="scan all commits reachable from an initial push head")
    args = parser.parse_args()
    try:
        files = changed_files(args.base, args.head)
        findings = scan(args.base, args.head, initial=args.initial)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL unable to inspect local range: {exc.__class__.__name__}")
        return 1
    print(f"RANGE {args.base}..{args.head} ({len(files)} changed paths)")
    if findings:
        for finding in dict.fromkeys(findings):
            print(f"FAIL {finding}")
        return 1
    print("PASS secret/private-path/raw-source/diff-hygiene scan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
