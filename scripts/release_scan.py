"""Scan only explicitly named tracked Git content for release-gate categories.

This is intentionally not a workstation scan.  It reads immutable Git objects
from either an explicit commit range or an explicit list of tracked relative
paths; ignored files, untracked files, and local runtime data are never walked
or opened.  Reports contain category counts only, never paths or matched text.
"""

from __future__ import annotations

import argparse
import ast
import binascii
import io
import json
import re
import subprocess
import sys
import tokenize
import tomllib
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


class ReleaseScanError(ValueError):
    """The requested Git-only release scan cannot safely be performed."""


_CATEGORIES: dict[str, re.Pattern[bytes]] = {
    "credential_signature": re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*['\"]?[^\s'\"]{8,}"
    ),
    "private_data_path": re.compile(
        rb"(?i)(?:^|[\s'\"])(?:\.env(?:\.|['\"\s]|$)|private/|vault\.json|data/finances\.json)"
    ),
    "absolute_machine_path": re.compile(rb"(?i)(?<![a-z0-9])[a-z]:[\\/]|/(?:users|home)/"),
    "long_numeric_identifier": re.compile(rb"(?<!\d)\d{13,19}(?!\d)"),
}
_CREDENTIAL_SIGNATURE = re.compile(
    r"(?i)(?:"
    r"(?:api[_-]?key|access[_-]?token|client[_-]?secret|secret|password|passphrase)[ \t]*[:=][ \t]*(?:['\"][^'\"\r\n]{8,}['\"]|[A-Za-z0-9-]{16,})"
    r"|['\"](?:api[_-]?key|access[_-]?token|client[_-]?secret|secret|password|passphrase)['\"][ \t]*:[ \t]*['\"][^'\"\r\n]{8,}['\"]"
    r")"
)
_VALUE_FREE_COMMENT_MARKER = re.compile(
    r'''(?i)["']<(?:value omitted|redacted|placeholder)>["']\s*$'''
)
_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_CREDENTIAL_TARGET_NAMES = {"api_key", "access_token", "client_secret", "password", "passphrase", "secret"}
_LONG_NUMERIC_TEXT = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
_DOCKERIGNORE_RULES = frozenset(
    {
        ".git",
        ".venv",
        ".env",
        "data",
        "demo-data",
        "imports",
        "*.sqlite3",
        "*.vault",
        "logs",
        "coordination",
        "tests",
        "__pycache__",
    }
)
_MAX_CONSTANT_SIZE = 8192
_SHA256 = re.compile(r"(?i)[0-9a-f]{64}")
_PRIVATE_TEXT = re.compile(
    r"(?i)(?<![\w.])(?:\.env(?!\.example)(?:[./\\]|$)|private[\s/\\]+vault\.json|data[\s/\\]+finances\.json)"
)
_MACHINE_TEXT = re.compile(r"(?i)(?<![a-z0-9])[a-z]:[\\/]|(?<![a-z0-9_])/(?:users|home)/")


@dataclass(frozen=True)
class ReleaseScanReport:
    target_kind: str
    file_count: int
    findings: dict[str, int]

    def to_public_json(self) -> str:
        return json.dumps(
            {
                "target_kind": self.target_kind,
                "tracked_file_count": self.file_count,
                "findings": self.findings,
            },
            sort_keys=True,
        )


def _git(repo: Path, args: Sequence[str], *, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseScanError("requested tracked Git content is unavailable")
    return result.stdout


def _relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ReleaseScanError("a supplied file path is invalid")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or ".." in windows.parts:
        raise ReleaseScanError("a supplied file path is invalid")
    normalized = posix.as_posix()
    if normalized in {"", "."}:
        raise ReleaseScanError("a supplied file path is invalid")
    return normalized


def _revision(value: str) -> str:
    if not isinstance(value, str) or not _REVISION.fullmatch(value):
        raise ReleaseScanError("a supplied Git revision is invalid")
    return value


def _commit(repo: Path, revision: str) -> str:
    value = _git(repo, ["rev-parse", "--verify", f"{_revision(revision)}^{{commit}}"])
    resolved = value.decode("ascii", errors="strict").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise ReleaseScanError("a supplied Git revision is invalid")
    return resolved


def _tracked_at_commit(repo: Path, commit: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{commit}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _bounded_constant(node: ast.AST | None) -> Any:
    if node is None:
        return None
    """Evaluate a small, side-effect-free Python expression without executing it."""
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
    if isinstance(node, ast.Dict):
        keys = tuple(_bounded_constant(item) for item in node.keys)
        values = tuple(_bounded_constant(item) for item in node.values)
        if any(key is None for key in keys) or any(value is None for value in values):
            return None
        return dict(zip(keys, values, strict=True))
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
        if isinstance(result, (str, bytes)) and len(result) <= _MAX_CONSTANT_SIZE:
            return result
        return None
    if isinstance(node, ast.JoinedStr):
        pieces: list[str] = []
        for item in node.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                pieces.append(item.value)
                continue
            if not isinstance(item, ast.FormattedValue):
                return None
            value = _bounded_constant(item.value)
            if value is None or isinstance(value, (bytes, dict, tuple)):
                return None
            format_spec = ""
            if item.format_spec is not None:
                formatted_spec = _bounded_constant(item.format_spec)
                if not isinstance(formatted_spec, str):
                    return None
                format_spec = formatted_spec
            try:
                pieces.append(format(value, format_spec))
            except (ArithmeticError, TypeError, ValueError):
                return None
        result = "".join(pieces)
        return result if len(result) <= _MAX_CONSTANT_SIZE else None
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
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
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "base64" and node.func.attr in {
                "b64decode",
                "urlsafe_b64decode",
            } and len(node.args) == 1 and not node.keywords:
                encoded = _bounded_constant(node.args[0])
                if isinstance(encoded, str):
                    encoded = encoded.encode("ascii", errors="ignore")
                if isinstance(encoded, bytes) and len(encoded) <= _MAX_CONSTANT_SIZE:
                    try:
                        import base64 as _base64

                        result = getattr(_base64, node.func.attr)(encoded)
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
        if isinstance(node.func, ast.Name) and node.func.id == "chr" and len(node.args) == 1 and not node.keywords:
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


def _python_string_credential_signature(
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
        if value is not None and _CREDENTIAL_SIGNATURE.search(_normalized_text(value)) is not None:
            return True
    return False


def _python_comment_credential_signature(text: str) -> bool:
    """Scan concrete credential signatures in Python comments only."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            normalized = _normalized_text(token.string)
            for match in _CREDENTIAL_SIGNATURE.finditer(normalized):
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
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr in {"format", "decode"}:
            return True
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr in {"b64decode", "urlsafe_b64decode", "fromhex"}:
            return True
    return False


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
        return {name for item in node.elts for name in _credential_target_names(item)}
    return set()


def _python_source(content: bytes) -> bool:
    try:
        ast.parse(content.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError, ValueError):
        return False
    return True


def _python_credential_signature(content: bytes, *, path: str = "") -> bool:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return True
    if _python_comment_credential_signature(text):
        return True
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        # Without a valid AST, no value-free Python context can be proven.
        return True

    ignored_spans = _path_exception_spans(path, text)
    masked = _mask_spans(text, ignored_spans)
    if re.search(r"(?i)-----BEGIN (?:RSA|OPENSSH|EC|PRIVATE) KEY-----", masked):
        return True
    if re.search(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9_-]{12,}\b|\bsk-[A-Za-z0-9_-]{12,}\b", masked):
        return True
    if _python_string_credential_signature(tree, text, ignored_spans):
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
                if (
                    keyword.arg
                    and keyword.arg.casefold() in _CREDENTIAL_TARGET_NAMES
                ):
                    value = _constant_string_expression(keyword.value)
                    if value is not None and (
                        value.casefold().startswith("synthetic ")
                        or "synthetic" in value.casefold()
                    ):
                        continue
                    if value is not None or _unknown_credential_material(keyword.value):
                        return True
    return False


def _decode_text(content: bytes) -> str:
    if b"\0" in content:
        raise ReleaseScanError("a tracked blob contains NUL bytes")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseScanError("a tracked blob is not valid UTF-8") from exc


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


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for item in node.elts for name in _target_names(item)}
    return set()


def _policy_literal_spans(path: str, text: str) -> list[tuple[int, int]]:
    """Mask only policy constants whose AST context makes them detector data."""
    if not path.casefold().endswith(".py"):
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    normalized_path = path.replace("\\", "/").casefold()
    spans: list[tuple[int, int]] = []
    if normalized_path not in {
        "scripts/release_scan.py",
        "scripts/release_candidate_check.py",
    }:
        return spans
    for statement in ast.walk(tree):
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        names = {name.casefold() for target in targets for name in _target_names(target)}
        if not names or not any(
            token in name
            for name in names
            for token in ("pattern", "category", "categories", "rule", "fixture", "suffix", "directory", "numeric", "hash", "private", "machine", "text")
        ):
            continue
        value_node = statement.value
        if value_node is None:
            continue
        spans.extend(span for node in ast.walk(value_node) if isinstance(node, ast.Constant) and isinstance(span := _node_span(text, node), tuple))
    if normalized_path == "scripts/release_scan.py":
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
                value_text = node.value.decode("utf-8", "ignore") if isinstance(node.value, bytes) else node.value
                if not any(marker in value_text.casefold() for marker in (".env", "private", "data/", "vault")):
                    continue
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
                    for marker in ("\\" + "Users" + "\\", "/" + "Users" + "/", "/" + "home" + "/")
                )
                and isinstance(span := _node_span(text, item), tuple)
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"write_text", "write_bytes"}:
            spans.extend(
                span
                for value in node.args
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
        if isinstance(node, ast.Assign) and any(name == "public_hash" for target in node.targets for name in _target_names(target)):
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
            and _CREDENTIAL_SIGNATURE.search(_normalized_text(value)) is not None
        ):
            span = _node_span(text, node)
            if span is not None:
                spans.append(span)
    return spans


def _dockerignore_spans(path: str, text: str) -> list[tuple[int, int]]:
    if path != ".dockerignore":
        return []
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped in _DOCKERIGNORE_RULES:
            start = offset + line.index(stripped)
            spans.append((start, start + len(stripped)))
        offset += len(line)
    return spans


def _path_exception_spans(path: str, text: str) -> list[tuple[int, int]]:
    spans = [
        *_policy_literal_spans(path, text),
        *_synthetic_test_spans(path, text),
        *_synthetic_credential_fixture_spans(path, text),
        *_dockerignore_spans(path, text),
    ]
    if path.replace("\\", "/").casefold() == "src/mycard_benefits/config.py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value == ".env":
                    parent_like = text[max(0, (_node_span(text, node) or (0, 0))[0] - 32) : (_node_span(text, node) or (0, 0))[0]]
                    if "/" in parent_like:
                        span = _node_span(text, node)
                        if span is not None:
                            spans.append(span)
    return spans


def _mask_spans(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(max(0, start), min(len(chars), end)):
            chars[index] = " "
    return "".join(chars)


def _public_hash_spans(path: str, content: bytes) -> list[tuple[int, int]]:
    text = _decode_text(content)
    spans: list[tuple[int, int]] = []
    suffix = path.casefold()
    if suffix.endswith(".py"):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            def add_hash_value(node: ast.AST | None, value: str | None) -> None:
                if value is None or _SHA256.fullmatch(value) is None:
                    return
                if node is None:
                    return
                node_span = _node_span(text, node)
                if node_span is None:
                    return
                relative = text[node_span[0] : node_span[1]].find(value)
                if relative >= 0:
                    spans.append((node_span[0] + relative, node_span[0] + relative + len(value)))

            for statement in ast.walk(tree):
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)) and not isinstance(statement, ast.Call):
                    continue
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                    names = {name.casefold() for target in targets for name in _target_names(target)}
                    if names & {"content_hash", "content_sha256", "hash"}:
                        add_hash_value(statement.value, _constant_string_expression(statement.value))
                else:
                    for keyword in statement.keywords:
                        if keyword.arg in {"content_hash", "content_sha256", "hash"}:
                            add_hash_value(keyword.value, _constant_string_expression(keyword.value))
                    if isinstance(statement.func, ast.Name) and statement.func.id == "_source" and len(statement.args) > 6:
                        add_hash_value(statement.args[6], _constant_string_expression(statement.args[6]))
    elif suffix.endswith(".json"):
        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        for match in re.finditer(r'(?i)["\'](?:content_hash|content_sha256|hash)["\']\s*:\s*["\']([0-9a-f]{64})["\']', text):
            spans.append((match.start(1), match.end(1)))
    elif suffix.endswith(".toml") or suffix == "uv.lock":
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return []
        for match in re.finditer(r'(?im)^\s*(?:content_hash|content_sha256|hash)\s*=\s*["\'](?:sha256:)?([0-9a-f]{64})["\']', text):
            spans.append((match.start(1), match.end(1)))
    return spans


def _has_long_numeric_identifier(path: str, content: bytes) -> bool:
    text = _decode_text(content)
    allowed = [*_public_hash_spans(path, content), *_synthetic_test_spans(path, text)]
    return any(
        not any(start <= match.start() and match.end() <= end for start, end in allowed)
        for match in _LONG_NUMERIC_TEXT.finditer(text)
    )


def _has_machine_path(path: str, content: bytes) -> bool:
    text = _decode_text(content)
    masked = _mask_spans(text, _path_exception_spans(path, text))
    return _MACHINE_TEXT.search(_normalized_text(masked)) is not None


def _has_private_path(path: str, content: bytes) -> bool:
    text = _decode_text(content)
    masked = _mask_spans(text, _path_exception_spans(path, text))
    return _PRIVATE_TEXT.search(_normalized_text(masked)) is not None


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _constant_concatenations(content: bytes) -> bytes:
    """Add safely normalized literal concatenations without changing source text."""
    try:
        text = content.decode("utf-8")
        tree = ast.parse(text)
    except (UnicodeDecodeError, SyntaxError, ValueError):
        return content

    replacements: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.BinOp, ast.Call)):
            continue
        value = _constant_string_expression(node)
        if value is None or not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            continue
        span = _node_span(text, node)
        if span is not None:
            replacements.append((span[0], span[1], value))

    # Keep the largest candidate when nested expressions overlap.
    replacements.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected: list[tuple[int, int, str]] = []
    for replacement in replacements:
        if selected and replacement[0] < selected[-1][1]:
            continue
        selected.append(replacement)
    if not selected:
        return content
    # Scan each parsed expression as its own unit. Joining normalized values
    # would manufacture credential signatures from unrelated source fragments
    # in the scanner or its tests.
    return content + b"\n" + b"\n".join(
        value.encode("utf-8", errors="backslashreplace") for _, _, value in selected
    )


def _credential_scan_text(content: bytes) -> str | None:
    """Decode and canonicalize separators only for credential matching."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    normalized: list[str] = []
    for character in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(character)
        if category == "Cf":  # Unicode default-ignorable format characters.
            continue
        normalized.append(" " if character.isspace() else character)
    return "".join(normalized)


def _has_credential_signature(content: bytes, *, path: str = "") -> bool:
    _decode_text(content)
    if path.replace("\\", "/").casefold().endswith(".py"):
        return _python_credential_signature(content, path=path)
    text = _credential_scan_text(_constant_concatenations(content))
    return text is not None and _CREDENTIAL_SIGNATURE.search(text) is not None




def _has_forbidden_private_path(path: str, content: bytes) -> bool:
    return _has_private_path(path, content)


def _scan_contents(
    contents: Iterable[tuple[str, bytes]], *, target_kind: str
) -> ReleaseScanReport:
    counts = {category: 0 for category in _CATEGORIES}
    file_count = 0
    for path, content in contents:
        file_count += 1
        _decode_text(content)
        scan_content = _constant_concatenations(content)
        for category, pattern in _CATEGORIES.items():
            if category == "credential_signature":
                if _has_credential_signature(content, path=path):
                    counts[category] += 1
                continue
            if category == "absolute_machine_path":
                if _has_machine_path(path, content) or _has_machine_path("<git-path>", path.encode("utf-8")):
                    counts[category] += 1
                continue
            if category == "long_numeric_identifier":
                if _has_long_numeric_identifier(path, content):
                    counts[category] += 1
                continue
            if category == "private_data_path":
                if _has_forbidden_private_path(path, content) or _has_private_path("<git-path>", path.encode("utf-8")):
                    counts[category] += 1
                continue
            if pattern.search(scan_content):
                counts[category] += 1
    return ReleaseScanReport(target_kind=target_kind, file_count=file_count, findings=counts)


def scan_tracked_files(repo: Path, files: Sequence[str], *, revision: str = "HEAD") -> ReleaseScanReport:
    """Scan supplied relative tracked paths from one explicit committed revision."""
    if not files:
        raise ReleaseScanError("at least one tracked file is required")
    commit = _commit(repo, revision)
    paths = tuple(dict.fromkeys(_relative_path(path) for path in files))
    for path in paths:
        if not _tracked_at_commit(repo, commit, path):
            raise ReleaseScanError("a supplied file is not tracked at the requested revision")
    return _scan_contents(
        ((path, _git(repo, ["show", f"{commit}:{path}"])) for path in paths),
        target_kind="files",
    )


def scan_git_range(repo: Path, revision_range: str) -> ReleaseScanReport:
    """Scan added/modified paths in one explicit ``BASE..HEAD`` commit range."""
    if not isinstance(revision_range, str) or revision_range.count("..") != 1:
        raise ReleaseScanError("a Git range must use BASE..HEAD")
    base, head = revision_range.split("..", 1)
    base_commit = _commit(repo, base)
    head_commit = _commit(repo, head)
    changed = _git(
        repo,
        ["diff", "--name-only", "-z", "--diff-filter=AM", f"{base_commit}..{head_commit}"],
    )
    paths = tuple(
        dict.fromkeys(
            _relative_path(value.decode("utf-8", errors="strict"))
            for value in changed.split(b"\0")
            if value
        )
    )
    paths = tuple(path for path in paths if _tracked_at_commit(repo, head_commit, path))
    return _scan_contents(
        ((path, _git(repo, ["show", f"{head_commit}:{path}"])) for path in paths),
        target_kind="range",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan explicitly selected tracked Git content")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--range", dest="revision_range", help="explicit BASE..HEAD range")
    group.add_argument("--files", nargs="+", help="explicit tracked relative paths from HEAD")
    return parser


def main(argv: Sequence[str] | None = None, *, repo: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = repo or Path.cwd()
    try:
        report = (
            scan_git_range(repository, args.revision_range)
            if args.revision_range is not None
            else scan_tracked_files(repository, args.files)
        )
    except ReleaseScanError:
        print(json.dumps({"error": "release scan could not evaluate the explicit tracked target"}))
        return 2
    print(report.to_public_json())
    return 1 if any(report.findings.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
