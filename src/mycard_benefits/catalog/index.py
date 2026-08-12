"""A rebuildable, read-only SQLite index over the public catalog.

The JSON catalog remains the reviewed source of truth.  This module has one
write boundary, :func:`build_catalog_index`; :class:`CatalogIndex` opens the
result through the repository's immutable SQLite reader and verifies the
catalog fingerprint before every query.  A changed catalog therefore makes
the old index stale instead of allowing it to answer with old facts.

The comparison methods require a normalized metric and unit.  That small bit
of explicitness is intentional: a percentage, a visit count, and an INR limit
are not a meaningful ranking just because they share a category.  Missing
quantities and unpriced rewards are represented by SQL ``NULL`` or absent
rows, never by a numeric zero; ranking results report how many candidates were
excluded for that reason.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .. import data_location
from ..sqlite_readonly import read_only_sqlite_connection
from .loader import Catalog, load_catalog

INDEX_FILENAME = "catalog.sqlite3"
INDEX_DIRECTORY = "derived"
INDEX_SCHEMA_VERSION = 2

_SOURCE_DIRECTORIES = ("schema", "offerings", "benefits", "relationships", "rewards")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CURRENT_STATE_SQL = "(b.state IN ('verified', 'check_before_use', 'sources_differ') OR (b.state IS NULL AND b.status = 'active'))"
_CURRENT_OFFERING_SQL = "(o.effective_from IS NULL OR o.effective_from <= ?) AND (o.effective_to IS NULL OR o.effective_to >= ?)"


class CatalogIndexError(RuntimeError):
    """Base error for catalog-index build and query failures."""


class CatalogIndexBuildError(CatalogIndexError):
    """The catalog could not be converted into a complete index."""


class CatalogIndexUnavailable(CatalogIndexError):
    """The runtime index is missing or cannot be read safely."""


class CatalogIndexStaleError(CatalogIndexError):
    """The JSON source changed after the runtime index was built."""


Number = int | float


@dataclass(frozen=True)
class RewardCategoryEarn:
    """One source-shaped category earning row in the derived index."""

    scope: str
    points_per_inr: Number | None
    percent_back: Number | None
    cap_value: Number | None
    cap_unit: str | None
    cap_period: str | None
    conditions_json: str


@dataclass(frozen=True)
class RewardRecord:
    """Validated reward data read from one public catalog file."""

    offering_id: str
    offering_slug: str
    currency_code: str
    currency_display_name: str
    base_points_per_inr: Number | None
    category_earn: tuple[RewardCategoryEarn, ...]
    valuation_inr_per_point: Number | None
    valuation_basis: str | None
    expiry_months: int | None
    expiry_from: str | None
    state: str
    review_state: str
    source_url: str
    source_policy_class: str
    content_sha256: str
    retrieved_at: str


@dataclass(frozen=True)
class RankedBenefit:
    """A known, comparable quantity returned to an optimizer caller."""

    offering_id: str
    offering_slug: str
    display_name: str
    benefit_id: str
    title: str
    category: str
    metric: str
    value: Number
    unit: str
    basis: str
    scope: str | None
    period: str
    cap_value: Number | None
    cap_unit: str | None
    cap_period: str | None
    effective_to: date | None


@dataclass(frozen=True)
class BenefitRanking:
    """Known rows plus the count omitted because their value was unknown."""

    rows: tuple[RankedBenefit, ...]
    excluded_unknown_count: int


@dataclass(frozen=True)
class RankedReward:
    """A reward earning row with a known rupee valuation."""

    offering_id: str
    offering_slug: str
    display_name: str
    currency_code: str
    points_per_inr: Number
    valuation_inr_per_point: Number
    value_inr_per_rupee: Number


@dataclass(frozen=True)
class RewardRanking:
    """Known reward rows plus candidates excluded for an unknown input."""

    rows: tuple[RankedReward, ...]
    excluded_unknown_count: int


@dataclass(frozen=True)
class ExpiringBenefit:
    """One current benefit with a known future end date."""

    offering_id: str
    offering_slug: str
    display_name: str
    benefit_id: str
    title: str
    category: str
    effective_to: date


_SCHEMA = """
PRAGMA application_id = 1296251713;
PRAGMA user_version = 1;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE offerings (
    offering_id TEXT PRIMARY KEY NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    issuer_id TEXT NOT NULL,
    product_variant_id TEXT NOT NULL,
    network TEXT,
    tier TEXT,
    acceptance_marks_json TEXT NOT NULL,
    lounge_programme TEXT,
    market TEXT NOT NULL,
    co_brand_id TEXT,
    cohort_id TEXT,
    effective_from TEXT,
    effective_to TEXT
);

CREATE TABLE benefits (
    benefit_id TEXT PRIMARY KEY NOT NULL,
    offering_id TEXT NOT NULL REFERENCES offerings(offering_id),
    benefit_type TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    state TEXT,
    category TEXT,
    effective_from TEXT,
    effective_to TEXT,
    quantity_count INTEGER NOT NULL CHECK (quantity_count >= 0)
);

CREATE TABLE quantities (
    benefit_id TEXT NOT NULL REFERENCES benefits(benefit_id),
    ordinal INTEGER NOT NULL,
    metric TEXT NOT NULL,
    value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    basis TEXT NOT NULL,
    scope TEXT,
    period TEXT NOT NULL,
    cap_value NUMERIC,
    cap_unit TEXT,
    cap_period TEXT,
    PRIMARY KEY (benefit_id, ordinal)
);

CREATE TABLE reward_records (
    offering_id TEXT PRIMARY KEY NOT NULL REFERENCES offerings(offering_id),
    offering_slug TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    currency_display_name TEXT NOT NULL,
    base_points_per_inr NUMERIC,
    valuation_inr_per_point NUMERIC,
    valuation_basis TEXT,
    expiry_months INTEGER,
    expiry_from TEXT,
    state TEXT NOT NULL,
    review_state TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_policy_class TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE reward_earnings (
    offering_id TEXT NOT NULL REFERENCES reward_records(offering_id),
    ordinal INTEGER NOT NULL,
    scope TEXT NOT NULL,
    points_per_inr NUMERIC,
    percent_back NUMERIC,
    cap_value NUMERIC,
    cap_unit TEXT,
    cap_period TEXT,
    conditions_json TEXT NOT NULL,
    PRIMARY KEY (offering_id, ordinal)
);

CREATE INDEX benefits_category_idx ON benefits(category, effective_to);
CREATE INDEX quantities_compare_idx ON quantities(metric, unit, scope, value);
CREATE INDEX reward_earnings_scope_idx ON reward_earnings(scope, points_per_inr);
"""


def catalog_index_path(data_dir: str | Path) -> Path:
    """Return the guarded runtime path for the derived public index."""

    root = data_location.validate_data_root(data_dir)
    directory = root / INDEX_DIRECTORY
    data_location.reject_reparse(directory, allow_missing=True)
    data_location.reject_reparse(directory / INDEX_FILENAME, allow_missing=True)
    return directory / INDEX_FILENAME


def build_catalog_index(catalog_root: str | Path, data_dir: str | Path) -> Path:
    """Build the runtime index atomically from the public JSON catalog.

    The destination is always ``<data_dir>/derived/catalog.sqlite3``.  The
    builder is the only function in this module that opens SQLite for writing;
    it builds a temporary database and replaces the destination only after a
    complete, deterministic transaction has been committed.
    """

    root = Path(catalog_root)
    if not root.is_dir():
        raise CatalogIndexBuildError("catalog source is unavailable")

    target = catalog_index_path(data_dir)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    data_location.reject_reparse(parent)
    data_location.reject_reparse(target, allow_missing=True)

    before = _source_manifest(root)
    catalog = load_catalog(root)
    rewards = _load_rewards(root, catalog)
    after = _source_manifest(root)
    if before != after:
        raise CatalogIndexBuildError("catalog changed during index build")

    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".catalog-index-", suffix=".tmp", dir=parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        connection = sqlite3.connect(temporary)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(_SCHEMA)
            _populate(connection, catalog, rewards, before)
            connection.commit()
            connection.execute("VACUUM")
        finally:
            connection.close()
        data_location.reject_reparse(parent)
        data_location.reject_reparse(target, allow_missing=True)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
    return target


class CatalogIndex:
    """A source-fingerprint-checked, read-only view of the runtime index."""

    def __init__(self, catalog_root: Path, path: Path, default_as_of: date) -> None:
        self.catalog_root = catalog_root
        self.path = path
        self.default_as_of = default_as_of

    @classmethod
    def open(cls, catalog_root: str | Path, data_dir: str | Path) -> CatalogIndex:
        """Open the index only if it still describes the current JSON source."""

        root = Path(catalog_root)
        path = catalog_index_path(data_dir)
        try:
            data_location.reject_reparse(path)
        except data_location.DataLocationError as exc:
            raise CatalogIndexUnavailable("catalog index is unavailable") from exc
        if not path.is_file():
            raise CatalogIndexUnavailable("catalog index is unavailable")
        index = cls(root, path, date.min)
        metadata = index._metadata()
        try:
            default_as_of = date.fromisoformat(metadata["catalog_default_as_of"])
        except (KeyError, ValueError) as exc:
            raise CatalogIndexUnavailable("catalog index metadata is invalid") from exc
        index.default_as_of = default_as_of
        index._assert_current(metadata)
        return index

    def best_for_category(
        self,
        category: str,
        *,
        metric: str,
        unit: str,
        scope: str | None = None,
        offering_ids: Iterable[str] | None = None,
        as_of: date | None = None,
    ) -> BenefitRanking:
        """Rank known quantities for one comparable category dimension.

        ``metric`` and ``unit`` are mandatory so a caller cannot accidentally
        compare unlike quantities.  ``offering_ids`` is the optimizer's
        ownership boundary: pass the owner's offering IDs for a personal
        ranking, or omit it to query the public catalog.
        """

        if not category or not metric or not unit:
            raise ValueError("category, metric and unit are required")
        selected_ids = _optional_ids(offering_ids)
        if selected_ids == ():
            return BenefitRanking((), 0)
        effective_date = as_of or self.default_as_of
        where = [
            "b.category = ?",
            "q.metric = ?",
            "q.unit = ?",
            _CURRENT_STATE_SQL,
            "(b.effective_from IS NULL OR b.effective_from <= ?)",
            "(b.effective_to IS NULL OR b.effective_to >= ?)",
            _CURRENT_OFFERING_SQL,
        ]
        params: list[Any] = [
            category,
            metric,
            unit,
            effective_date.isoformat(),
            effective_date.isoformat(),
            effective_date.isoformat(),
            effective_date.isoformat(),
        ]
        if scope is not None:
            where.append("(q.scope IS NULL OR q.scope = ?)")
            params.append(scope)
        _append_offering_filter(where, params, selected_ids)

        rows = self._query(
            """
            SELECT o.offering_id, o.slug, o.display_name,
                   b.benefit_id, b.title, b.category,
                   q.metric, q.value, q.unit, q.basis, q.scope, q.period,
                   q.cap_value, q.cap_unit, q.cap_period, b.effective_to
            FROM benefits AS b
            JOIN offerings AS o ON o.offering_id = b.offering_id
            JOIN quantities AS q ON q.benefit_id = b.benefit_id
            WHERE """
            + " AND ".join(where)
            + " ORDER BY q.value DESC, o.display_name, b.benefit_id, q.ordinal",
            params,
        )

        unknown_where = [
            "b.category = ?",
            _CURRENT_STATE_SQL,
            "(b.effective_from IS NULL OR b.effective_from <= ?)",
            "(b.effective_to IS NULL OR b.effective_to >= ?)",
            "EXISTS (SELECT 1 FROM offerings AS candidate_o WHERE candidate_o.offering_id = b.offering_id AND (candidate_o.effective_from IS NULL OR candidate_o.effective_from <= ?) AND (candidate_o.effective_to IS NULL OR candidate_o.effective_to >= ?))",
            "NOT EXISTS (SELECT 1 FROM quantities AS unknown_q WHERE unknown_q.benefit_id = b.benefit_id AND unknown_q.metric = ? AND unknown_q.unit = ?",
        ]
        unknown_params: list[Any] = [
            category,
            effective_date.isoformat(),
            effective_date.isoformat(),
            effective_date.isoformat(),
            effective_date.isoformat(),
            metric,
            unit,
        ]
        if scope is not None:
            unknown_where[-1] += " AND (unknown_q.scope IS NULL OR unknown_q.scope = ?)"
            unknown_params.append(scope)
        unknown_where[-1] += ")"
        _append_offering_filter(unknown_where, unknown_params, selected_ids, alias="b")
        unknown_row = self._query(
            "SELECT COUNT(DISTINCT b.benefit_id) AS count FROM benefits AS b WHERE "
            + " AND ".join(unknown_where),
            unknown_params,
        )[0]
        return BenefitRanking(
            rows=tuple(_ranked_benefit(row) for row in rows),
            excluded_unknown_count=int(unknown_row["count"]),
        )

    def rank_benefits(self, *args: Any, **kwargs: Any) -> BenefitRanking:
        """Compatibility name for the optimizer-facing category query."""

        return self.best_for_category(*args, **kwargs)

    def optimizer_candidates(self, *args: Any, **kwargs: Any) -> BenefitRanking:
        """Stable query boundary an optimizer can call without changing its engine."""

        return self.best_for_category(*args, **kwargs)

    def rank_rewards(
        self,
        *,
        offering_ids: Iterable[str] | None = None,
        scope: str | None = None,
        as_of: date | None = None,
    ) -> RewardRanking:
        """Rank rewards only when earning rate and rupee valuation are known."""

        selected_ids = _optional_ids(offering_ids)
        if selected_ids == ():
            return RewardRanking((), 0)
        effective_date = as_of or self.default_as_of
        where: list[str] = []
        params: list[Any] = [effective_date.isoformat(), effective_date.isoformat()]
        where.extend(["o.effective_from IS NULL OR o.effective_from <= ?", "o.effective_to IS NULL OR o.effective_to >= ?"])
        _append_offering_filter(where, params, selected_ids)
        if scope is None:
            earning = "r.base_points_per_inr"
            join = ""
        else:
            earning = "e.points_per_inr"
            join = "LEFT JOIN reward_earnings AS e ON e.offering_id = r.offering_id AND e.scope = ?"
            params.insert(0, scope)
        rows = self._query(
            """
            SELECT o.offering_id, o.slug, o.display_name,
                   r.currency_code, """
            + earning
            + " AS points_per_inr, r.valuation_inr_per_point FROM offerings AS o "
            "LEFT JOIN reward_records AS r ON r.offering_id = o.offering_id "
            + join
            + " WHERE " + " AND ".join(f"({item})" for item in where)
            + " ORDER BY o.display_name, o.offering_id",
            params,
        )
        known: list[RankedReward] = []
        for row in rows:
            points = _number_or_none(row["points_per_inr"])
            valuation = _number_or_none(row["valuation_inr_per_point"])
            if points is None or valuation is None or row["currency_code"] is None:
                continue
            known.append(
                RankedReward(
                    offering_id=str(row["offering_id"]),
                    offering_slug=str(row["slug"]),
                    display_name=str(row["display_name"]),
                    currency_code=str(row["currency_code"]),
                    points_per_inr=points,
                    valuation_inr_per_point=valuation,
                    value_inr_per_rupee=points * valuation,
                )
            )
        known.sort(key=lambda item: (-float(item.value_inr_per_rupee), item.display_name, item.offering_id))
        return RewardRanking(rows=tuple(known), excluded_unknown_count=len(rows) - len(known))

    def optimizer_reward_candidates(self, **kwargs: Any) -> RewardRanking:
        """Stable reward query boundary for the optimizer's future adapter."""

        return self.rank_rewards(**kwargs)

    def next_expiring_benefits(
        self, *, as_of: date | None = None, limit: int | None = None
    ) -> tuple[ExpiringBenefit, ...]:
        """Return current benefits whose known end date is next."""

        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        effective_date = as_of or self.default_as_of
        params: list[Any] = [
            effective_date.isoformat(),
            effective_date.isoformat(),
            effective_date.isoformat(),
            effective_date.isoformat(),
        ]
        where = [
            _CURRENT_STATE_SQL,
            "(o.effective_from IS NULL OR o.effective_from <= ?)",
            "(o.effective_to IS NULL OR o.effective_to >= ?)",
            "(b.effective_from IS NULL OR b.effective_from <= ?)",
            "b.effective_to IS NOT NULL",
            "b.effective_to >= ?",
        ]
        sql = (
            """
            SELECT o.offering_id, o.slug, o.display_name,
                   b.benefit_id, b.title, b.category, b.effective_to
            FROM benefits AS b
            JOIN offerings AS o ON o.offering_id = b.offering_id
            WHERE """
            + " AND ".join(where)
            + " ORDER BY b.effective_to, b.benefit_id"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return tuple(_expiring_benefit(row) for row in self._query(sql, params))

    def _metadata(self) -> dict[str, str]:
        try:
            with read_only_sqlite_connection(self.path) as connection:
                rows = connection.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
        except sqlite3.Error as exc:
            raise CatalogIndexUnavailable("catalog index is unavailable") from exc
        return {str(row[0]): str(row[1]) for row in rows}

    def _assert_current(self, metadata: dict[str, str] | None = None) -> None:
        metadata = metadata or self._metadata()
        if metadata.get("index_schema_version") != str(INDEX_SCHEMA_VERSION):
            raise CatalogIndexStaleError("catalog index schema is stale")
        actual_fingerprint, actual_count = _source_manifest(self.catalog_root)
        if metadata.get("source_fingerprint") != actual_fingerprint or metadata.get("source_file_count") != str(actual_count):
            raise CatalogIndexStaleError("catalog index is stale; rebuild it from the catalog")

    def _query(self, sql: str, params: Sequence[Any]) -> list[sqlite3.Row]:
        self._assert_current()
        try:
            with read_only_sqlite_connection(self.path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise CatalogIndexUnavailable("catalog index is unavailable") from exc
        self._assert_current()
        return rows


def _populate(
    connection: sqlite3.Connection,
    catalog: Catalog,
    rewards: tuple[RewardRecord, ...],
    source_manifest: tuple[str, int],
) -> None:
    fingerprint, file_count = source_manifest
    metadata = {
        "catalog_default_as_of": catalog.default_as_of.isoformat(),
        "catalog_release_id": catalog.release.release_id,
        "index_schema_version": str(INDEX_SCHEMA_VERSION),
        "source_file_count": str(file_count),
        "source_fingerprint": fingerprint,
    }
    connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(metadata.items()))

    offerings = sorted(catalog.offerings, key=lambda item: item.id)
    connection.executemany(
        """
        INSERT INTO offerings(
            offering_id, slug, display_name, issuer_id, product_variant_id,
            network, tier, acceptance_marks_json, lounge_programme,
            market, co_brand_id, cohort_id, effective_from, effective_to
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                offering.id,
                offering.slug,
                offering.display_name,
                offering.issuer_id,
                offering.product_variant_id,
                offering.network,
                offering.tier,
                json.dumps(offering.acceptance_marks, separators=(",", ":")),
                offering.lounge_programme,
                offering.market,
                offering.co_brand_id,
                offering.cohort_id,
                _date_text(offering.effective_from),
                _date_text(offering.effective_to),
            )
            for offering in offerings
        ],
    )

    benefits = sorted(catalog.benefits, key=lambda item: item.id)
    connection.executemany(
        """
        INSERT INTO benefits(
            benefit_id, offering_id, benefit_type, title, status, state, category,
            effective_from, effective_to, quantity_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                benefit.id,
                benefit.offering_id,
                benefit.benefit_type,
                benefit.title,
                benefit.status,
                benefit.state,
                benefit.category.value if benefit.category is not None else None,
                _date_text(benefit.effective_from),
                _date_text(benefit.effective_to),
                len(benefit.quantities),
            )
            for benefit in benefits
        ],
    )
    quantity_rows = []
    for benefit in benefits:
        for ordinal, quantity in enumerate(benefit.quantities):
            cap = quantity.cap or {}
            quantity_rows.append(
                (
                    benefit.id,
                    ordinal,
                    quantity.metric,
                    quantity.value,
                    quantity.unit,
                    quantity.basis,
                    quantity.scope,
                    quantity.period,
                    cap.get("value"),
                    cap.get("unit"),
                    cap.get("period"),
                )
            )
    connection.executemany(
        """
        INSERT INTO quantities(
            benefit_id, ordinal, metric, value, unit, basis, scope, period,
            cap_value, cap_unit, cap_period
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        quantity_rows,
    )

    connection.executemany(
        """
        INSERT INTO reward_records(
            offering_id, offering_slug, currency_code, currency_display_name,
            base_points_per_inr, valuation_inr_per_point, valuation_basis,
            expiry_months, expiry_from, state, review_state, source_url,
            source_policy_class, content_sha256, retrieved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                reward.offering_id,
                reward.offering_slug,
                reward.currency_code,
                reward.currency_display_name,
                reward.base_points_per_inr,
                reward.valuation_inr_per_point,
                reward.valuation_basis,
                reward.expiry_months,
                reward.expiry_from,
                reward.state,
                reward.review_state,
                reward.source_url,
                reward.source_policy_class,
                reward.content_sha256,
                reward.retrieved_at,
            )
            for reward in sorted(rewards, key=lambda item: item.offering_id)
        ],
    )
    earnings = []
    for reward in sorted(rewards, key=lambda item: item.offering_id):
        for ordinal, item in enumerate(reward.category_earn):
            earnings.append(
                (
                    reward.offering_id,
                    ordinal,
                    item.scope,
                    item.points_per_inr,
                    item.percent_back,
                    item.cap_value,
                    item.cap_unit,
                    item.cap_period,
                    item.conditions_json,
                )
            )
    connection.executemany(
        """
        INSERT INTO reward_earnings(
            offering_id, ordinal, scope, points_per_inr, percent_back,
            cap_value, cap_unit, cap_period, conditions_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        earnings,
    )


def _load_rewards(root: Path, catalog: Catalog) -> tuple[RewardRecord, ...]:
    directory = root / "rewards"
    if not directory.is_dir():
        return ()
    offering_by_id = {item.id: item for item in catalog.offerings}
    records: list[RewardRecord] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        record = _parse_reward(_read_json(path), path, offering_by_id)
        if record.offering_id in seen:
            raise CatalogIndexBuildError("duplicate reward record for an offering")
        seen.add(record.offering_id)
        records.append(record)
    return tuple(records)


def _parse_reward(raw: dict[str, Any], path: Path, offerings: dict[str, Any]) -> RewardRecord:
    required = {
        "offering_id", "offering_slug", "currency", "base_earn", "category_earn",
        "valuation", "expiry", "source_url", "source_policy_class", "content_sha256",
        "retrieved_at", "state", "review_state",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise CatalogIndexBuildError(f"reward record is missing required fields: {', '.join(missing)}")
    offering_id = _text(raw["offering_id"], "reward.offering_id")
    offering = offerings.get(offering_id)
    if offering is None:
        raise CatalogIndexBuildError("reward record refers to an unknown offering")
    offering_slug = _text(raw["offering_slug"], "reward.offering_slug")
    if offering_slug != offering.slug:
        raise CatalogIndexBuildError("reward record offering_slug disagrees with the catalog")
    currency = _object(raw["currency"], "reward.currency")
    currency_code = _text(currency.get("code"), "reward.currency.code")
    currency_display_name = _text(currency.get("display_name"), "reward.currency.display_name")
    base_earn = _object(raw["base_earn"], "reward.base_earn")
    base_points = _number(base_earn.get("points_per_inr"), "reward.base_earn.points_per_inr", allow_none=True)
    category_items = raw["category_earn"]
    if not isinstance(category_items, list):
        raise CatalogIndexBuildError("reward.category_earn must be a list")
    category_earn = tuple(_parse_reward_earn(item, path, index) for index, item in enumerate(category_items))

    valuation_raw = raw["valuation"]
    valuation = None if valuation_raw is None else _object(valuation_raw, "reward.valuation")
    valuation_points = None if valuation is None else _number(
        valuation.get("inr_per_point"), "reward.valuation.inr_per_point", allow_none=True
    )
    valuation_basis = None if valuation is None else _optional_text(valuation.get("basis"))

    expiry_raw = raw["expiry"]
    expiry = None if expiry_raw is None else _object(expiry_raw, "reward.expiry")
    expiry_months: int | None = None
    expiry_from: str | None = None
    if expiry is not None:
        months = expiry.get("months")
        if months is not None and (isinstance(months, bool) or not isinstance(months, int) or months < 0):
            raise CatalogIndexBuildError("reward.expiry.months must be a non-negative integer")
        expiry_months = months
        expiry_from = _optional_text(expiry.get("from"))

    source_url = _text(raw["source_url"], "reward.source_url")
    if not source_url.startswith("https://"):
        raise CatalogIndexBuildError("reward.source_url must use HTTPS")
    source_policy_class = _text(raw["source_policy_class"], "reward.source_policy_class")
    content_sha256 = _text(raw["content_sha256"], "reward.content_sha256")
    if _SHA256.fullmatch(content_sha256) is None:
        raise CatalogIndexBuildError("reward.content_sha256 must be a lowercase SHA-256 digest")
    retrieved_at = _text(raw["retrieved_at"], "reward.retrieved_at")
    try:
        datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogIndexBuildError("reward.retrieved_at must be an ISO timestamp") from exc
    return RewardRecord(
        offering_id=offering_id,
        offering_slug=offering_slug,
        currency_code=currency_code,
        currency_display_name=currency_display_name,
        base_points_per_inr=base_points,
        category_earn=category_earn,
        valuation_inr_per_point=valuation_points,
        valuation_basis=valuation_basis,
        expiry_months=expiry_months,
        expiry_from=expiry_from,
        state=_text(raw["state"], "reward.state"),
        review_state=_text(raw["review_state"], "reward.review_state"),
        source_url=source_url,
        source_policy_class=source_policy_class,
        content_sha256=content_sha256,
        retrieved_at=retrieved_at,
    )


def _parse_reward_earn(raw: Any, path: Path, index: int) -> RewardCategoryEarn:
    item = _object(raw, f"{path} category_earn[{index}]")
    scope = _text(item.get("scope"), f"{path} category_earn[{index}].scope")
    points = _number(item.get("points_per_inr"), f"{path} category_earn[{index}].points_per_inr", allow_none=True)
    percent = _number(item.get("percent_back"), f"{path} category_earn[{index}].percent_back", allow_none=True)
    cap_value, cap_unit, cap_period = _parse_cap(item.get("cap"), f"{path} category_earn[{index}].cap")
    conditions = item.get("conditions", [])
    if not isinstance(conditions, list) or not all(isinstance(value, str) for value in conditions):
        raise CatalogIndexBuildError(f"{path} category_earn[{index}].conditions must be a string list")
    conditions_json = json.dumps(conditions, ensure_ascii=False, separators=(",", ":"))
    return RewardCategoryEarn(scope, points, percent, cap_value, cap_unit, cap_period, conditions_json)


def _parse_cap(value: Any, label: str) -> tuple[Number | None, str | None, str | None]:
    if value is None:
        return None, None, None
    cap = _object(value, label)
    return (
        _number(cap.get("value"), f"{label}.value", allow_none=False),
        _text(cap.get("unit"), f"{label}.unit"),
        _text(cap.get("period"), f"{label}.period"),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogIndexBuildError("cannot read reward catalog JSON") from exc
    if not isinstance(value, dict):
        raise CatalogIndexBuildError("reward catalog JSON must contain an object")
    return value


def _source_manifest(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for directory_name in _SOURCE_DIRECTORIES:
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix().encode("utf-8")
            content = path.read_bytes()
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
            count += 1
    return digest.hexdigest(), count


def _optional_ids(values: Iterable[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    return tuple(dict.fromkeys(str(value) for value in values))


def _append_offering_filter(
    where: list[str],
    params: list[Any],
    offering_ids: tuple[str, ...] | None,
    *,
    alias: str = "o",
) -> None:
    if offering_ids is None:
        return
    placeholders = ", ".join("?" for _ in offering_ids)
    where.append(f"{alias}.offering_id IN ({placeholders})")
    params.extend(offering_ids)


def _ranked_benefit(row: sqlite3.Row) -> RankedBenefit:
    return RankedBenefit(
        offering_id=str(row["offering_id"]),
        offering_slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        benefit_id=str(row["benefit_id"]),
        title=str(row["title"]),
        category=str(row["category"]),
        metric=str(row["metric"]),
        value=_number_or_none(row["value"]),
        unit=str(row["unit"]),
        basis=str(row["basis"]),
        scope=str(row["scope"]) if row["scope"] is not None else None,
        period=str(row["period"]),
        cap_value=_number_or_none(row["cap_value"]),
        cap_unit=str(row["cap_unit"]) if row["cap_unit"] is not None else None,
        cap_period=str(row["cap_period"]) if row["cap_period"] is not None else None,
        effective_to=date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
    )


def _expiring_benefit(row: sqlite3.Row) -> ExpiringBenefit:
    return ExpiringBenefit(
        offering_id=str(row["offering_id"]),
        offering_slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        benefit_id=str(row["benefit_id"]),
        title=str(row["title"]),
        category=str(row["category"]),
        effective_to=date.fromisoformat(row["effective_to"]),
    )


def _date_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _number(value: Any, label: str, *, allow_none: bool) -> Number | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogIndexBuildError(f"{label} must be a number or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise CatalogIndexBuildError(f"{label} must be finite")
    if value < 0:
        raise CatalogIndexBuildError(f"{label} must not be negative")
    return value


def _number_or_none(value: Any) -> Number | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogIndexUnavailable("catalog index contains an invalid number")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogIndexBuildError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogIndexBuildError(f"{label} must be non-empty text")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return _text(value, "optional reward text")


__all__ = [
    "BenefitRanking",
    "CatalogIndex",
    "CatalogIndexBuildError",
    "CatalogIndexError",
    "CatalogIndexStaleError",
    "CatalogIndexUnavailable",
    "ExpiringBenefit",
    "INDEX_DIRECTORY",
    "INDEX_FILENAME",
    "INDEX_SCHEMA_VERSION",
    "RankedBenefit",
    "RankedReward",
    "RewardRanking",
    "build_catalog_index",
    "catalog_index_path",
]
