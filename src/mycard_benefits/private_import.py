"""Strict, offline, crash-recoverable private-source consolidation.

All parser results are kept in memory until they are sealed below the local
private data root.  The only public result is a count-only receipt.  In
particular, this module has no source discovery, network, browser, or logging
integration.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import os
import secrets
import stat
import time
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .vault import (
    CardLifecycle,
    ConsolidationAuthorization,
    ReconciliationCard,
    VaultError,
    VaultSession,
    secure_private_path,
    validate_offering_id,
    validate_reconciliation_pan,
    validate_secret_fields,
)

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_DOCUMENTS = 256
MAX_ROWS = 1_000
MAX_DEPTH = 4
MAX_XLSX_MEMBERS = 256
MAX_XLSX_UNCOMPRESSED = 32 * 1024 * 1024
MAX_XLSX_RATIO = 200
PARSER_VERSION = "mc206-v2"
PARSER_POLICY_VERSION = "mc206-policy-v1"
_FIELDS = frozenset({
    "source_record_id", "issuer", "bank", "product", "variant", "network", "co_brand",
    "offering_id", "cardholder", "owner", "pan", "last_four", "expiry", "expiry_month",
    "expiry_year", "lifecycle", "status", "replacement", "predecessor", "cvv", "pin",
    "nickname", "notes", "billing_postcode",
})
_SECRET_FIELDS = frozenset({
    "pan", "expiry_month", "expiry_year", "cvv", "pin", "cardholder_name", "owner_alias", "nickname",
    "notes", "billing_postcode", "reconciliation_id", "reconciliation_metadata",
})
_LIFECYCLES = {item.value for item in CardLifecycle}
_NETWORKS = {
    "visa": "visa",
    "mastercard": "mastercard",
    "amex": "amex",
    "american-express": "amex",
    "rupay": "rupay",
    "diners": "diners",
    "discover": "discover",
    "unknown": "unknown",
}


class ImportRejected(VaultError):
    """A safe, value-free source validation or recovery failure."""


@dataclass(frozen=True)
class SourceInput:
    kind: str
    path: Path


@dataclass
class ImportCounts:
    parsed: int = 0
    imported: int = 0
    existing: int = 0
    conflict: int = 0
    unmatched: int = 0
    needs_local_review: int = 0
    rejected: int = 0


@dataclass(frozen=True)
class CountReceipt:
    schema_version: int
    run_id: str
    state: str
    source_counts: dict[str, int]
    counts: ImportCounts
    input_hash: str
    preview_digest: str
    artifact_hashes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "state": self.state,
            "source_counts": dict(sorted(self.source_counts.items())),
            "counts": self.counts.__dict__.copy(),
            "input_hash": self.input_hash,
            "preview_digest": self.preview_digest,
            "artifact_hashes": list(self.artifact_hashes),
        }


@dataclass(frozen=True)
class _ParsedRecord:
    source_identity: str
    fields: dict[str, str]


@dataclass(frozen=True)
class _ParsedSources:
    records: tuple[_ParsedRecord, ...]
    counts: ImportCounts
    source_counts: dict[str, int]
    sources: tuple[dict[str, str], ...]
    input_hash: str


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _safe_path(path: Path, *, directory: bool = False) -> Path:
    """Reject reparse points before opening a path by descriptor."""
    candidate = Path(os.path.abspath(os.fspath(path)))
    current = Path(candidate.anchor)
    try:
        parts = candidate.relative_to(current).parts
    except ValueError:
        raise ImportRejected("source path is unavailable") from None
    for part in parts:
        current /= part
        try:
            info = os.lstat(current)
        except OSError:
            raise ImportRejected("source path is unavailable") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ImportRejected("source path is not a regular local path")
    if directory:
        if not candidate.is_dir():
            raise ImportRejected("source directory is invalid")
    elif not candidate.is_file():
        raise ImportRejected("source file is invalid")
    return candidate


def _read_bounded(path: Path) -> bytes:
    """Read one regular file through a descriptor, not a checked pathname."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ImportRejected("source cannot be read") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise ImportRejected("source is invalid or too large")
        # On platforms without O_NOFOLLOW, compare the live pathname to the
        # opened handle before reading.  The handle is then the immutable
        # source object used for parsing even if a later rename occurs.
        current = os.lstat(path)
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)
        ):
            raise ImportRejected("source changed while opening")
        with os.fdopen(fd, "rb", closefd=True) as handle:
            fd = -1
            raw = handle.read(MAX_INPUT_BYTES + 1)
    except OSError:
        raise ImportRejected("source cannot be read") from None
    finally:
        if fd >= 0:
            os.close(fd)
    if len(raw) > MAX_INPUT_BYTES:
        raise ImportRejected("source is too large")
    return raw


def _text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportRejected("source encoding is unsupported") from None


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ImportRejected("JSON source has duplicate keys")
        result[key] = value
    return result


def _normalise(item: dict[Any, Any], *, structured: bool) -> dict[str, str]:
    if not isinstance(item, dict) or not item or any(not isinstance(key, str) for key in item):
        raise ImportRejected("source record is invalid")
    if set(item) - _FIELDS:
        raise ImportRejected("source record has unsupported fields")
    result: dict[str, str] = {}
    for key, value in item.items():
        if not isinstance(value, str):
            raise ImportRejected("source field is invalid")
        text = value.strip()
        if not text or len(text) > 4096 or any(ord(char) < 32 for char in text):
            raise ImportRejected("source field is invalid")
        if text[0] in "=+-@" and key not in {"pan", "expiry", "expiry_month", "expiry_year", "last_four"}:
            raise ImportRejected("formula-like source value is unsupported")
        if key in {"cvv", "pin"} and not structured:
            raise ImportRejected("protected field requires an authorized structured source")
        result[key] = text
    if "source_record_id" not in result:
        raise ImportRejected("source record is missing its identifier")
    if "network" in result:
        network = _NETWORKS.get(result["network"].casefold())
        if network is None:
            raise ImportRejected("network is invalid")
        result["network"] = network
    if "offering_id" in result:
        try:
            validate_offering_id(result["offering_id"])
        except VaultError:
            raise ImportRejected("offering is invalid") from None
    return result


def _json_records(raw: bytes) -> list[dict[str, str]]:
    try:
        value: Any = json.loads(_text(raw), object_pairs_hook=_json_object)
    except (ImportRejected, json.JSONDecodeError):
        raise ImportRejected("JSON source is invalid") from None
    if not isinstance(value, dict) or set(value) - {"schema_version", "cards", "records"}:
        raise ImportRejected("JSON source is invalid")
    if value.get("schema_version", 1) != 1 or ("cards" in value) == ("records" in value):
        raise ImportRejected("JSON source is invalid")
    records = value.get("cards", value.get("records"))
    if not isinstance(records, list) or not records or len(records) > MAX_ROWS:
        raise ImportRejected("JSON source is invalid")
    return [_normalise(item, structured=True) for item in records]




def _csv_records(raw: bytes) -> list[dict[str, str]]:
    text = _text(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect, strict=True)
        headers = reader.fieldnames
        if (
            not headers
            or any(not isinstance(header, str) or not header or header not in _FIELDS for header in headers)
            or len(set(headers)) != len(headers)
        ):
            raise ImportRejected("CSV headers are invalid")
        rows = list(reader)
    except (ImportRejected, csv.Error):
        raise ImportRejected("CSV source is invalid") from None
    if not rows or len(rows) > MAX_ROWS:
        raise ImportRejected("CSV source is invalid")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ImportRejected("CSV source is invalid")
    return [_normalise(dict(row), structured=False) for row in rows]


def _column(reference: str) -> int:
    letters = "".join(char for char in reference if "A" <= char <= "Z")
    if not letters or len(letters) > 3:
        raise ImportRejected("workbook cell reference is invalid")
    result = 0
    for char in letters:
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _xlsx_value(cell: ElementTree.Element, shared: list[str]) -> str:
    if any(node.tag.endswith("f") for node in cell):
        raise ImportRejected("workbook formulas are unsupported")
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if node.tag.endswith("t"))
    value = next((node.text or "" for node in cell if node.tag.endswith("v")), "")
    if kind == "s":
        if not value.isdigit() or int(value) >= len(shared):
            raise ImportRejected("workbook shared string is invalid")
        return shared[int(value)]
    if kind not in (None, "str"):
        raise ImportRejected("workbook cell type is unsupported")
    return value


def _xlsx_records(raw: bytes) -> list[dict[str, str]]:
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ImportRejected("workbook is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            infos = book.infolist()
            names = [info.filename for info in infos]
            name_set = set(names)
            compressed = sum(info.compress_size for info in infos)
            uncompressed = sum(info.file_size for info in infos)
            if (
                len(infos) > MAX_XLSX_MEMBERS
                or len(name_set) != len(names)
                or uncompressed > MAX_XLSX_UNCOMPRESSED
                or any(
                    info.flag_bits & 1
                    or info.file_size > MAX_XLSX_UNCOMPRESSED
                    or (info.file_size and (not info.compress_size or info.file_size > info.compress_size * MAX_XLSX_RATIO))
                    or ".." in Path(info.filename).parts
                    or Path(info.filename).drive != ""
                    or info.filename.startswith(("/", "\\"))
                    for info in infos
                )
                or (compressed and uncompressed > compressed * MAX_XLSX_RATIO)
                or any(name.endswith("vbaProject.bin") or "externalLinks" in name for name in name_set)
            ):
                raise ImportRejected("workbook archive is unsafe")
            if "xl/workbook.xml" not in name_set:
                raise ImportRejected("workbook is invalid")
            workbook = ElementTree.fromstring(book.read("xl/workbook.xml"))
            sheet_nodes = [node for node in workbook.iter() if node.tag.endswith("sheet")]
            if len(sheet_nodes) != 1 or sheet_nodes[0].attrib.get("state") in {"hidden", "veryHidden"}:
                raise ImportRejected("workbook must contain one visible worksheet")
            sheets = sorted(name for name in name_set if name.startswith("xl/worksheets/") and name.endswith(".xml"))
            if len(sheets) != 1:
                raise ImportRejected("workbook must contain one worksheet")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in name_set:
                root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root if node.tag.endswith("si")]
            sheet_root = ElementTree.fromstring(book.read(sheets[0]))
            if any(node.tag.endswith("mergeCell") for node in sheet_root.iter()):
                raise ImportRejected("workbook merged cells are unsupported")
            rows: list[dict[int, str]] = []
            for xml_row in (node for node in sheet_root.iter() if node.tag.endswith("row")):
                current: dict[int, str] = {}
                for cell in (node for node in xml_row if node.tag.endswith("c")):
                    reference = cell.attrib.get("r")
                    if reference is None:
                        raise ImportRejected("workbook cell reference is invalid")
                    position = _column(reference)
                    if position in current:
                        raise ImportRejected("workbook duplicate cell is invalid")
                    current[position] = _xlsx_value(cell, shared)
                if current:
                    rows.append(current)
            if len(rows) < 2 or len(rows) > MAX_ROWS + 1:
                raise ImportRejected("workbook is invalid")
            header_positions = rows[0]
            if sorted(header_positions) != list(range(max(header_positions) + 1)):
                raise ImportRejected("workbook headers are sparse")
            headers = [header_positions[index] for index in range(len(header_positions))]
            if any(not header or header not in _FIELDS for header in headers) or len(set(headers)) != len(headers):
                raise ImportRejected("workbook headers are invalid")
            result: list[dict[str, str]] = []
            for data_row in rows[1:]:
                if any(position >= len(headers) for position in data_row):
                    raise ImportRejected("workbook row exceeds headers")
                result.append(_normalise({headers[position]: value for position, value in data_row.items()}, structured=True))
            return result
    except (OSError, KeyError, ValueError, ElementTree.ParseError, zipfile.BadZipFile, ImportRejected):
        raise ImportRejected("workbook is invalid") from None


def _document_files(root: Path) -> list[Path]:
    found: list[Path] = []
    pending: list[tuple[Path, int]] = [(root, 0)]
    while pending:
        directory, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise ImportRejected("document directory is too deep")
        try:
            entries = sorted(list(os.scandir(directory)), key=lambda entry: entry.name.casefold())
        except OSError:
            raise ImportRejected("document directory is unavailable") from None
        for entry in entries:
            path = Path(entry.path)
            try:
                info = os.lstat(path)
            except OSError:
                raise ImportRejected("document path is unavailable") from None
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ImportRejected("document path is not regular")
            if stat.S_ISDIR(info.st_mode):
                pending.append((path, depth + 1))
            elif stat.S_ISREG(info.st_mode):
                found.append(path)
            else:
                raise ImportRejected("document path is not regular")
            if len(found) > MAX_DOCUMENTS:
                raise ImportRejected("document directory is too large")
    return sorted(found, key=lambda path: str(path).casefold())


def _parse_payload(path: Path, raw: bytes) -> list[dict[str, str]]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return _csv_records(raw)
    if suffix == ".xlsx":
        return _xlsx_records(raw)
    if suffix == ".json":
        return _json_records(raw)
    raise ImportRejected("source type is unsupported")


def _parse_sources(inputs: Iterable[SourceInput]) -> _ParsedSources:
    selected = tuple(inputs)
    if not selected:
        raise ImportRejected("at least one source is required")
    records: list[_ParsedRecord] = []
    counts = ImportCounts()
    source_counts: dict[str, int] = {}
    sources: list[dict[str, str]] = []
    aliases: set[str] = set()
    for ordinal, source in enumerate(selected):
        if source.kind not in {"workbook", "documents"}:
            raise ImportRejected("source kind is invalid")
        path = _safe_path(source.path, directory=source.kind == "documents")
        alias = os.path.normcase(os.path.abspath(path))
        if alias in aliases:
            raise ImportRejected("duplicate source alias")
        aliases.add(alias)
        path_id = _sha(alias.encode("utf-8"))
        files = _document_files(path) if source.kind == "documents" else [path]
        if source.kind == "documents":
            source_counts[source.kind] = len(files)
        for file_ordinal, file in enumerate(files):
            raw = _read_bounded(file)
            fingerprint = _sha(raw)
            file_id = _sha(str(file.relative_to(path) if source.kind == "documents" else file.name).encode("utf-8"))
            source_descriptor = {
                "ordinal": str(ordinal), "file_ordinal": str(file_ordinal), "kind": source.kind,
                "path_identity": path_id, "file_identity": file_id, "fingerprint": fingerprint,
            }
            sources.append(source_descriptor)
            try:
                parsed = _parse_payload(file, raw)
            except ImportRejected:
                if source.kind == "documents" and file.suffix.casefold() not in {".json", ".csv", ".xlsx"}:
                    counts.needs_local_review += 1
                    continue
                counts.rejected += 1
                raise
            seen_ids: set[str] = set()
            for item in parsed:
                record_id = item["source_record_id"]
                if record_id in seen_ids:
                    raise ImportRejected("duplicate source record")
                seen_ids.add(record_id)
                identity = _sha(_canonical({"source": source_descriptor, "source_record_id": record_id}))[:32]
                records.append(_ParsedRecord(identity, item))
            if source.kind != "documents":
                source_counts[source.kind] = source_counts.get(source.kind, 0) + len(parsed)
    counts.parsed = len(records)
    if not records:
        raise ImportRejected("sources contain no admitted card records")
    input_hash = _sha(_canonical(sources))
    return _ParsedSources(tuple(records), counts, source_counts, tuple(sources), input_hash)


def parse_sources(inputs: Iterable[SourceInput]) -> tuple[list[dict[str, str]], ImportCounts, dict[str, int], str]:
    """Compatibility projection for synthetic parser tests; it exposes no receipt."""
    parsed = _parse_sources(inputs)
    return [dict(record.fields) for record in parsed.records], parsed.counts, parsed.source_counts, parsed.input_hash


def _pan_digits(value: str) -> str:
    digits = "".join(character for character in value if character.isascii() and character.isdigit())
    try:
        validate_reconciliation_pan(value)
    except VaultError:
        raise ImportRejected("PAN is invalid") from None
    return digits


def _secret_fields(record: _ParsedRecord) -> tuple[CardLifecycle, str | None, dict[str, str]]:
    item = record.fields
    lifecycle_value = item.get("lifecycle", item.get("status", "active"))
    if item.get("lifecycle") is not None and item.get("status") is not None and item["lifecycle"] != item["status"]:
        raise ImportRejected("lifecycle is ambiguous")
    if lifecycle_value not in _LIFECYCLES:
        raise ImportRejected("lifecycle is invalid")
    lifecycle = CardLifecycle(lifecycle_value)
    if "pan" not in item:
        raise ImportRejected("card record is missing PAN")
    pan = _pan_digits(item["pan"])
    if "last_four" in item and (len(item["last_four"]) != 4 or not item["last_four"].isdigit() or item["last_four"] != pan[-4:]):
        raise ImportRejected("last four does not match PAN")
    fields: dict[str, str] = {"pan": item["pan"], "reconciliation_id": record.source_identity}
    for key in ("cvv", "pin", "nickname", "notes", "billing_postcode"):
        if key in item:
            fields[key] = item[key]
    if "cardholder" in item:
        fields["cardholder_name"] = item["cardholder"]
    if "owner" in item:
        fields["owner_alias"] = item["owner"]
    expiry = item.get("expiry")
    if expiry is not None:
        if len(expiry) != 7 or expiry[4] != "-" or not expiry.replace("-", "").isdigit():
            raise ImportRejected("expiry is ambiguous")
        year, month = expiry.split("-")
        if not 1 <= int(month) <= 12 or not 1900 <= int(year) <= 9999:
            raise ImportRejected("expiry is invalid")
        item_month, item_year = month, year
        if ("expiry_month" in item and item["expiry_month"] != item_month) or ("expiry_year" in item and item["expiry_year"] != item_year):
            raise ImportRejected("expiry is ambiguous")
        fields["expiry_month"], fields["expiry_year"] = item_month, item_year
    elif "expiry_month" in item or "expiry_year" in item:
        if "expiry_month" not in item or "expiry_year" not in item or not item["expiry_month"].isdigit() or not item["expiry_year"].isdigit():
            raise ImportRejected("expiry is ambiguous")
        if not 1 <= int(item["expiry_month"]) <= 12 or len(item["expiry_year"]) != 4 or not 1900 <= int(item["expiry_year"]) <= 9999:
            raise ImportRejected("expiry is invalid")
        fields["expiry_month"], fields["expiry_year"] = item["expiry_month"], item["expiry_year"]
    metadata_fields = {key: item[key] for key in ("issuer", "bank", "product", "variant", "network", "co_brand", "replacement", "predecessor") if key in item}
    if metadata_fields:
        fields["reconciliation_metadata"] = json.dumps(
            {"schema_version": 1, "source_profile": metadata_fields}, sort_keys=True, separators=(",", ":")
        )
    try:
        validate_secret_fields(fields)
    except VaultError:
        raise ImportRejected("normalized private fields are invalid") from None
    return lifecycle, item.get("offering_id"), fields


def _cards(parsed: _ParsedSources) -> tuple[ReconciliationCard, ...]:
    """Merge compatible observations of one card before atomic persistence."""
    grouped: dict[str, list[tuple[str, CardLifecycle, str | None, dict[str, str]]]] = {}
    for record in sorted(parsed.records, key=lambda item: item.source_identity):
        lifecycle, offering_id, fields = _secret_fields(record)
        grouped.setdefault(_pan_digits(fields["pan"]), []).append(
            (record.source_identity, lifecycle, offering_id, fields)
        )

    cards: list[ReconciliationCard] = []
    for pan, observations in sorted(grouped.items()):
        _, lifecycle, offering_id, merged = observations[0]
        conflict = False
        for _, observed_lifecycle, observed_offering, fields in observations[1:]:
            if observed_lifecycle is not lifecycle:
                conflict = True
            if offering_id is not None and observed_offering is not None and offering_id != observed_offering:
                conflict = True
            offering_id = offering_id or observed_offering
            for key, value in fields.items():
                if key == "reconciliation_id":
                    continue
                if key in merged and merged[key] != value:
                    conflict = True
                else:
                    merged.setdefault(key, value)
        if conflict:
            parsed.counts.conflict += 1
            parsed.counts.needs_local_review += 1
            continue
        merged_identity = _sha(_canonical({
            "merged_source_identities": sorted(item[0] for item in observations),
            "pan": pan,
        }))[:32]
        merged["reconciliation_id"] = merged_identity
        cards.append(ReconciliationCard(merged_identity, offering_id, lifecycle, merged))
    if not cards:
        raise ImportRejected("sources contain no compatible card observations")
    return tuple(cards)


def _source_binding(parsed: _ParsedSources, cards: tuple[ReconciliationCard, ...]) -> str:
    parser_policy = {
        "input_bytes": MAX_INPUT_BYTES,
        "documents": MAX_DOCUMENTS,
        "rows": MAX_ROWS,
        "depth": MAX_DEPTH,
        "xlsx_members": MAX_XLSX_MEMBERS,
        "xlsx_uncompressed": MAX_XLSX_UNCOMPRESSED,
        "xlsx_ratio": MAX_XLSX_RATIO,
    }
    return _sha(_canonical({
        "parser_version": PARSER_VERSION,
        "parser_policy_version": PARSER_POLICY_VERSION,
        "limits": parser_policy,
        "sources": parsed.sources,
        "records": [
            {"identity": card.source_identity, "offering": card.offering_id, "lifecycle": card.lifecycle.value, "fields": card.secret_fields}
            for card in cards
        ],
        "warnings": {"needs_local_review": parsed.counts.needs_local_review},
    }))


def _vault_identity(session: VaultSession) -> str:
    # The path itself remains private.  Its digest prevents applying a preview
    # made for a different vault without placing an identifier in a receipt.
    store = getattr(session, "_store", None)
    path = getattr(store, "path", None)
    if not isinstance(path, Path):
        raise ImportRejected("vault identity is unavailable")
    return _sha(os.path.normcase(os.path.abspath(path)).encode("utf-8"))


def _plan_digest(parsed: _ParsedSources, cards: tuple[ReconciliationCard, ...], session: VaultSession | None) -> str:
    if session is None:
        target: dict[str, str] | None = None
    else:
        target = {"vault_identity": _vault_identity(session), "vault_revision": session.revision_hex}
    return _sha(_canonical({
        "parser_version": PARSER_VERSION,
        "action": "consolidate_apply",
        "source_binding": _source_binding(parsed, cards),
        "target": target,
    }))


def _seal(payload: bytes, key: bytes | bytearray, aad: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(hashlib.sha256(key).digest()).encrypt(nonce, payload, aad)


def _open(payload: bytes, key: bytes | bytearray, aad: bytes) -> dict[str, Any]:
    try:
        raw = AESGCM(hashlib.sha256(key).digest()).decrypt(payload[:12], payload[12:], aad)
        value: Any = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, InvalidTag, json.JSONDecodeError):
        raise ImportRejected("private import recovery state is invalid") from None
    if not isinstance(value, dict):
        raise ImportRejected("private import recovery state is invalid")
    return value


def _secure_local(path: Path, *, directory: bool) -> None:
    secure_private_path(path, directory=directory)


@contextmanager
def _consolidation_lock(root: Path) -> Iterator[None]:
    """An OS-released cross-process lock for source revalidation and commit."""
    root.mkdir(parents=True, exist_ok=True)
    _secure_local(root, directory=True)
    lock_path = root / ".consolidate.lock"
    with lock_path.open("a+b") as handle:
        _secure_local(lock_path, directory=False)
        deadline = time.monotonic() + 5
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl_module = cast(Any, fcntl)
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX | fcntl_module.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ImportRejected("private import is busy") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                with contextlib.suppress(OSError):
                    fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


@dataclass
class Consolidator:
    data_dir: Path
    # This is a short-lived, vault-derived artifact key.  Callers must wipe a
    # bytearray after this consolidator instance is no longer in use.
    user_key: bytes | bytearray
    version: str = PARSER_VERSION

    def run(
        self,
        inputs: Iterable[SourceInput],
        *,
        apply: bool = False,
        approved_digest: str | None = None,
        session: VaultSession | None = None,
        authorization: ConsolidationAuthorization | None = None,
    ) -> CountReceipt:
        parsed = _parse_sources(inputs)
        cards = _cards(parsed)
        preview_digest = _plan_digest(parsed, cards, session)
        root = self.data_dir / "private" / "imports"
        if not apply:
            previous = self._load_journal(root) if root.exists() else None
            if (
                previous is not None
                and previous.get("state") == "pending"
                and session is not None
                and previous.get("vault_revision") not in {None, session.revision_hex}
            ):
                # A post-write crash has advanced the target revision. Keep
                # the pending recovery pointer intact; the CLI can compare its
                # opaque digest before offering a fresh recovery authorization.
                return CountReceipt(
                    2, secrets.token_hex(16), "preview", parsed.source_counts,
                    parsed.counts, parsed.input_hash, preview_digest, (),
                )
            hashes = self._write_plan_artifacts(
                root, parsed, cards, preview_digest, state="preview",
                vault_revision=session.revision_hex if session is not None else None,
            )
            return CountReceipt(2, secrets.token_hex(16), "preview", parsed.source_counts, parsed.counts, parsed.input_hash, preview_digest, hashes)
        if session is None or authorization is None or approved_digest is None:
            raise ImportRejected("apply requires an exact approved preview and fresh authorization")
        with _consolidation_lock(root):
            # Re-open every source through guarded descriptors under the import
            # lock.  This turns an observed path swap or source modification
            # into a digest mismatch before the vault write.
            current = _parse_sources(inputs)
            current_cards = _cards(current)
            current_digest = _plan_digest(current, current_cards, session)
            pending = self._load_journal(root)
            active_digest = preview_digest
            authorization_action = "consolidate_apply"
            if pending is not None and pending.get("state") == "pending":
                if (
                    pending.get("plan_digest") != approved_digest
                    or pending.get("source_binding") != _source_binding(current, current_cards)
                ):
                    raise ImportRejected("pending private import requires exact recovery plan")
                active_digest = approved_digest
                authorization_action = "consolidate_recover"
            elif not secrets.compare_digest(approved_digest, preview_digest) or not secrets.compare_digest(preview_digest, current_digest):
                raise ImportRejected("sources or target changed after preview")
            # Write immutable LKG snapshots and durable pending intent before
            # touching the vault.  A later crash is replayed idempotently from
            # the same source identities, never treated as partial success.
            hashes = self._write_plan_artifacts(
                root, current, current_cards, active_digest, state="pending",
                vault_revision=session.revision_hex,
            )
            session.consume_consolidation(authorization, active_digest, authorization_action)
            result = session.reconcile_cards(current_cards)
            current.counts.imported = result.imported
            current.counts.existing = result.bound_existing + result.unchanged
            receipt = CountReceipt(
                2, secrets.token_hex(16), "applied", current.source_counts,
                current.counts, current.input_hash, active_digest, hashes,
            )
            self._write_journal(root, {
                "state": "committed", "plan_digest": active_digest,
                "source_binding": _source_binding(current, current_cards),
                "vault_revision": session.revision_hex,
            })
            self._write_receipt(root, receipt)
            return receipt

    def pending_digest(self) -> str | None:
        """Return an opaque pending-plan digest for an explicit reauth recovery."""
        journal = self._load_journal(self.data_dir / "private" / "imports")
        value = journal.get("plan_digest") if journal and journal.get("state") == "pending" else None
        return value if isinstance(value, str) and len(value) == 64 else None

    def _artifact_root(self, root: Path) -> Path:
        target = _safe_path(root, directory=True) if root.exists() else root
        target.mkdir(parents=True, exist_ok=True)
        _secure_local(target, directory=True)
        return target

    def _write_plan_artifacts(
        self, root: Path, parsed: _ParsedSources, cards: tuple[ReconciliationCard, ...], plan_digest: str, *, state: str,
        vault_revision: str | None = None,
    ) -> tuple[str, ...]:
        root = self._artifact_root(root)
        snapshot = {"version": self.version, "input_hash": parsed.input_hash, "sources": parsed.sources}
        plan: dict[str, Any] = {
            "version": self.version, "plan_digest": plan_digest, "source_binding": _source_binding(parsed, cards),
            "records": [{"identity": card.source_identity, "offering": card.offering_id, "lifecycle": card.lifecycle.value, "fields": card.secret_fields} for card in cards],
        }
        snapshot_hash = self._install_artifact(root, "snapshot", _canonical(snapshot), parsed.input_hash)
        plan_hash = self._install_artifact(root, "vault-import", _canonical(plan), plan_digest)
        previous = self._load_journal(root)
        if state == "preview" and previous is not None and previous.get("state") == "pending":
            previous_revision = previous.get("vault_revision")
            if vault_revision is None or previous_revision not in {None, vault_revision}:
                raise ImportRejected("pending private import requires exact recovery before target changes")
        if state != "preview" or previous is None or previous.get("state") != "pending" or previous.get("vault_revision") == vault_revision:
            journal: dict[str, str] = {
                "state": state, "plan_digest": plan_digest,
                "source_binding": str(plan["source_binding"]),
            }
            if vault_revision is not None:
                journal["vault_revision"] = vault_revision
            self._write_journal(root, journal)
        return snapshot_hash, plan_hash

    def _write_receipt(self, root: Path, receipt: CountReceipt) -> None:
        """Persist a count/hash-only receipt after the vault commit."""
        receipts = root / "receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        _secure_local(receipts, directory=True)
        path = receipts / f"{receipt.run_id}.json"
        staging = receipts / f".{receipt.run_id}.staging"
        payload = _canonical(receipt.as_dict())
        try:
            with staging.open("xb") as handle:
                _secure_local(staging, directory=False)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staging, path)
            _secure_local(path, directory=False)
        finally:
            staging.unlink(missing_ok=True)

    def _install_artifact(self, root: Path, stem: str, payload: bytes, binding: str) -> str:
        root = self._artifact_root(root)
        encrypted = _seal(payload, self.user_key, f"mc206:{self.version}:{stem}:{binding}".encode())
        digest = _sha(encrypted)
        staging = root / f".{stem}.{secrets.token_hex(12)}.staging"
        lkg = root / f"{stem}.lkg.{digest}.bin"
        current = root / f"{stem}.current.bin"
        try:
            with staging.open("xb") as handle:
                _secure_local(staging, directory=False)
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            if not lkg.exists():
                os.replace(staging, lkg)
                _secure_local(lkg, directory=False)
            else:
                staging.unlink()
            # Copy instead of moving the LKG.  Both the immutable generation
            # and a readable current pointer survive every replacement point.
            current_staging = root / f".{stem}.{secrets.token_hex(12)}.current"
            with current_staging.open("xb") as handle:
                _secure_local(current_staging, directory=False)
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(current_staging, current)
            _secure_local(current, directory=False)
            return digest
        finally:
            staging.unlink(missing_ok=True)

    def _journal_aad(self) -> bytes:
        return f"mc206:{self.version}:journal".encode()

    def _write_journal(self, root: Path, journal: dict[str, str]) -> None:
        if (
            set(journal) - {"state", "plan_digest", "source_binding", "vault_revision"}
            or journal.get("state") not in {"preview", "pending", "committed"}
            or not isinstance(journal.get("plan_digest"), str)
            or len(journal["plan_digest"]) != 64
            or not isinstance(journal.get("source_binding"), str)
            or len(journal["source_binding"]) != 64
            or ("vault_revision" in journal and (not isinstance(journal["vault_revision"], str) or len(journal["vault_revision"]) != 64))
        ):
            raise ImportRejected("private import journal is invalid")
        self._install_artifact(root, "journal", _canonical(journal), "journal")

    def _load_journal(self, root: Path) -> dict[str, Any] | None:
        current = root / "journal.current.bin"
        if not current.exists():
            return None
        raw = _read_bounded(_safe_path(current))
        journal = _open(raw, self.user_key, f"mc206:{self.version}:journal:journal".encode())
        try:
            self._write_journal_validation(journal)
        except ImportRejected:
            raise
        return journal

    @staticmethod
    def _write_journal_validation(journal: dict[str, Any]) -> None:
        if (
            set(journal) - {"state", "plan_digest", "source_binding", "vault_revision"}
            or journal.get("state") not in {"preview", "pending", "committed"}
            or not isinstance(journal.get("plan_digest"), str)
            or len(journal["plan_digest"]) != 64
            or not isinstance(journal.get("source_binding"), str)
            or len(journal["source_binding"]) != 64
            or ("vault_revision" in journal and (not isinstance(journal["vault_revision"], str) or len(journal["vault_revision"]) != 64))
        ):
            raise ImportRejected("private import recovery state is invalid")
