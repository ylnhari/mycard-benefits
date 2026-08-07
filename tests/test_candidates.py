from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mycard_benefits.candidates import (
    CandidateIntegrityError,
    CandidateState,
    CandidateStore,
    CandidateValidationError,
    RecordKind,
    ReviewDecision,
)
from mycard_benefits.candidates.diff import MAX_DIFF_DEPTH, MAX_DIFF_ENTRIES, deterministic_diff

RELEASE = "10000000-0000-4000-8000-000000000000"
OFFERING_ID = "20000000-0000-4000-8000-000000000000"
BENEFIT_ID = "30000000-0000-4000-8000-000000000000"
EVIDENCE_ID = "40000000-0000-4000-8000-000000000000"


def test_proposal_has_canonical_hash_and_deterministic_field_diff(tmp_path: Path) -> None:
    store = _store(tmp_path)
    base = _offering()
    payload = _offering(display_name="SYNTHETIC-ONLY-Changed Offering")

    candidate = store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=base, payload=payload)

    assert len(candidate.content_hash) == 64
    assert candidate.state is CandidateState.NEEDS_REVIEW
    assert [entry.path for entry in store.diff(candidate.id)] == ["/display_name"]


def test_offering_and_benefit_candidate_schemas_are_supported(tmp_path: Path) -> None:
    store = _store(tmp_path)
    offering = store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_offering(), payload=_offering())
    benefit = store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=_benefit(title="SYNTHETIC-ONLY-Changed Benefit"))

    assert (offering.record_kind, benefit.record_kind) == (RecordKind.OFFERING, RecordKind.BENEFIT)


def test_evidence_metadata_is_allowed_but_raw_prose_reviews_and_unknown_fields_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    allowed = _benefit()
    store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=allowed, payload=allowed)
    for forbidden in ("raw_body", "source_prose", "reviews"):
        payload = _benefit()
        payload["evidence"][0][forbidden] = "SYNTHETIC-ONLY-NOT-ALLOWED"
        with pytest.raises(CandidateValidationError, match="missing or unknown"):
            store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)


def test_standard_candidate_requires_one_distinct_human_approval(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    approved = store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)

    assert approved.state is CandidateState.APPROVED
    assert [event.event_type for event in store.events(candidate.id)] == ["proposed", "reviewed", "state_changed"]


def test_enhanced_candidate_requires_two_distinct_human_approvals(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store, review_tier="enhanced")
    first = store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER-ONE", decision=ReviewDecision.APPROVE)
    second = store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER-TWO", decision=ReviewDecision.APPROVE)

    assert first.state is CandidateState.NEEDS_REVIEW
    assert second.state is CandidateState.APPROVED


def test_author_duplicate_and_nonhuman_reviews_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    with pytest.raises(CandidateValidationError, match="author"):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-AUTHOR", decision=ReviewDecision.APPROVE)
    with pytest.raises(CandidateValidationError, match="exactly human"):
        store.review(candidate.id, reviewer_kind="agent", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)
    store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)
    with pytest.raises(CandidateValidationError, match="terminal"):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-OTHER", decision=ReviewDecision.APPROVE)


def test_rejected_and_changes_requested_are_terminal(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rejected = _proposal(store)
    changed = _proposal(store, author="SYNTHETIC-ONLY-SECOND-AUTHOR")
    assert store.review(rejected.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.REJECT).state is CandidateState.REJECTED
    assert store.review(changed.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.CHANGES_REQUESTED).state is CandidateState.CHANGES_REQUESTED
    with pytest.raises(CandidateValidationError, match="terminal"):
        store.review(changed.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-OTHER", decision=ReviewDecision.APPROVE)


def test_duplicate_reviewer_is_rejected_before_terminal_transition(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store, review_tier="high_impact")
    store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)
    with pytest.raises(CandidateValidationError, match="already reviewed"):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)


def test_tampered_hash_is_persisted_as_stale_with_an_event(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        connection.execute("UPDATE candidates SET payload_json = ? WHERE id = ?", (json.dumps(_offering(display_name="SYNTHETIC-ONLY-TAMPER")), candidate.id))
    with pytest.raises(CandidateIntegrityError, match="hash mismatch"):
        store.get_candidate(candidate.id)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        state = connection.execute("SELECT state FROM candidates WHERE id = ?", (candidate.id,)).fetchone()[0]
        events = connection.execute("SELECT event_type FROM events WHERE candidate_id = ? ORDER BY id", (candidate.id,)).fetchall()
    assert state == CandidateState.STALE.value
    assert events[-1][0] == "staled"


def test_already_stale_candidate_does_not_append_duplicate_stale_events_or_reviews(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        connection.execute("UPDATE candidates SET payload_json = ? WHERE id = ?", (json.dumps(_offering(display_name="SYNTHETIC-ONLY-TAMPER")), candidate.id))
    for _ in range(2):
        with pytest.raises(CandidateIntegrityError):
            store.get_candidate(candidate.id)
    with pytest.raises(CandidateIntegrityError):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        stale_events = connection.execute("SELECT COUNT(*) FROM events WHERE candidate_id = ? AND event_type = 'staled'", (candidate.id,)).fetchone()[0]
        review_count = connection.execute("SELECT COUNT(*) FROM reviews WHERE candidate_id = ?", (candidate.id,)).fetchone()[0]
    assert (stale_events, review_count) == (1, 0)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("record_kind", "invalid-kind", "record_kind"),
        ("state", "invalid-state", "state"),
        ("created_at", "not-a-timestamp", "created_at"),
    ],
)
def test_tampered_candidate_columns_stale_once_and_raise_integrity_error(tmp_path: Path, column: str, value: str, message: str) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        connection.execute(f"UPDATE candidates SET {column} = ? WHERE id = ?", (value, candidate.id))  # noqa: S608
    with pytest.raises(CandidateIntegrityError, match=message):
        store.get_candidate(candidate.id)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        state = connection.execute("SELECT state FROM candidates WHERE id = ?", (candidate.id,)).fetchone()[0]
        stale_events = connection.execute("SELECT COUNT(*) FROM events WHERE candidate_id = ? AND event_type = 'staled'", (candidate.id,)).fetchone()[0]
    assert (state, stale_events) == (CandidateState.STALE.value, 1)


@pytest.mark.parametrize(
    ("table", "column", "message"),
    [
        ("reviews", "decision", "review decision"),
        ("reviews", "created_at", "review created_at"),
        ("events", "created_at", "event created_at"),
    ],
)
def test_tampered_subordinate_rows_raise_integrity_error_without_staling_candidate(tmp_path: Path, table: str, column: str, message: str) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision=ReviewDecision.APPROVE)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        connection.execute(f"UPDATE {table} SET {column} = ? WHERE candidate_id = ?", ("invalid", candidate.id))  # noqa: S608
    read = store.reviews if table == "reviews" else store.events
    with pytest.raises(CandidateIntegrityError, match=message):
        read(candidate.id)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        state = connection.execute("SELECT state FROM candidates WHERE id = ?", (candidate.id,)).fetchone()[0]
        stale_events = connection.execute("SELECT COUNT(*) FROM events WHERE candidate_id = ? AND event_type = 'staled'", (candidate.id,)).fetchone()[0]
    assert (state, stale_events) == (CandidateState.APPROVED.value, 0)


def test_release_binding_reopen_and_candidate_drift_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store)
    with pytest.raises(CandidateIntegrityError, match="different base_release"):
        CandidateStore(tmp_path / "candidates.sqlite3", "50000000-0000-4000-8000-000000000000")
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        connection.execute("UPDATE candidates SET base_release_id = ? WHERE id = ?", ("60000000-0000-4000-8000-000000000000", candidate.id))
    with pytest.raises(CandidateIntegrityError, match="release_id drift"):
        store.get_candidate(candidate.id)
    with sqlite3.connect(tmp_path / "candidates.sqlite3") as connection:
        state = connection.execute("SELECT state FROM candidates WHERE id = ?", (candidate.id,)).fetchone()[0]
    assert state == CandidateState.STALE.value


def test_reviews_are_append_only_and_keep_candidate_needing_review_until_threshold(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = _proposal(store, review_tier="ambiguous")
    store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER-ONE", decision=ReviewDecision.APPROVE, note="SYNTHETIC-ONLY-NOTE")
    reviews = store.reviews(candidate.id)

    assert store.get_candidate(candidate.id).state is CandidateState.NEEDS_REVIEW
    assert [(review.id, review.reviewer_id, review.decision) for review in reviews] == [(1, "SYNTHETIC-ONLY-REVIEWER-ONE", ReviewDecision.APPROVE)]
    with pytest.raises(FrozenInstanceError):
        reviews[0].decision = ReviewDecision.REJECT


def test_invalid_store_owned_kinds_and_decisions_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(CandidateValidationError, match="record_kind"):
        store.propose(record_kind="offering", target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_offering(), payload=_offering())  # type: ignore[arg-type]
    candidate = _proposal(store)
    with pytest.raises(CandidateValidationError, match="review decision"):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-REVIEWER", decision="approve")  # type: ignore[arg-type]


def test_bounds_unknown_fields_and_target_identity_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _offering()
    payload["unknown"] = "SYNTHETIC-ONLY"
    with pytest.raises(CandidateValidationError, match="missing or unknown"):
        store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_offering(), payload=payload)
    with pytest.raises(CandidateValidationError, match="match target"):
        store.propose(record_kind=RecordKind.OFFERING, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_offering(), payload=_offering())
    with pytest.raises(CandidateValidationError, match="maximum length"):
        store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_offering(), payload=_offering(display_name="x" * 513))


def test_persistence_listing_stats_and_event_order_are_deterministic(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _proposal(store, author="SYNTHETIC-ONLY-A")
    second = _proposal(store, author="SYNTHETIC-ONLY-B")
    reopened = CandidateStore(tmp_path / "candidates.sqlite3", RELEASE)

    expected = sorted((first, second), key=lambda candidate: (candidate.created_at, candidate.id))
    assert [candidate.id for candidate in reopened.list_candidates()] == [candidate.id for candidate in expected]
    assert reopened.stats()[CandidateState.NEEDS_REVIEW] == 2
    assert [event.id for event in reopened.events(first.id)] == [1]


def test_schema_hygiene_requires_anonymous_https_and_bounded_diff(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = _benefit()
    payload["evidence"][0]["url"] = "http://example.invalid/not-allowed"
    with pytest.raises(CandidateValidationError, match="anonymous HTTPS"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)
    deeply_nested = _benefit()
    deeply_nested["allowance"] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}
    with pytest.raises(CandidateValidationError, match="nesting depth"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=deeply_nested)


def test_canonical_hash_key_order_diff_types_paths_and_bounds_are_typed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _offering()
    reordered = dict(reversed(list(first.items())))
    one = store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=first, payload=first)
    two = store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=reordered, payload=reordered)
    assert one.content_hash == two.content_hash
    diff = deterministic_diff('{"a/b":1,"a~b":"x"}', '{"a/b":"1","a~b":"y"}')
    assert [(entry.path, entry.before_json, entry.after_json) for entry in diff] == [("/a~1b", "1", "\"1\""), ("/a~0b", "\"x\"", "\"y\"")]
    with pytest.raises(CandidateValidationError, match="maximum entries"):
        deterministic_diff(json.dumps({str(index): index for index in range(MAX_DIFF_ENTRIES + 1)}), "{}")
    nested_before: object = 0
    nested_after: object = 1
    for _ in range(MAX_DIFF_DEPTH + 1):
        nested_before = [nested_before]
        nested_after = [nested_after]
    with pytest.raises(CandidateValidationError, match="maximum depth"):
        deterministic_diff(json.dumps(nested_before), json.dumps(nested_after))
    with pytest.raises(CandidateValidationError, match="canonical JSON"):
        deterministic_diff("{", "{}")


def test_maximum_schema_valid_evidence_edit_is_proposable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    base = _benefit()
    payload = _benefit()
    base["evidence"] = _evidence_set(0)
    payload["evidence"] = _evidence_set(1)
    candidate = store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=base, payload=payload)
    assert len(store.diff(candidate.id)) == 400


def test_schema_rejects_floats_dates_timestamps_credentials_conflicts_and_empty_evidence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for value in (float("nan"), float("inf")):
        payload = _offering()
        payload["aliases"] = [value]
        with pytest.raises(CandidateValidationError, match="floats"):
            store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_offering(), payload=payload)
    payload = _benefit()
    payload["effective_from"] = "2026-8-7"
    with pytest.raises(CandidateValidationError, match="YYYY-MM-DD"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)
    payload = _benefit()
    payload["evidence"][0]["retrieved_at"] = "2026-08-07T00:00:00"
    with pytest.raises(CandidateValidationError, match="RFC3339"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)
    payload = _benefit()
    payload["evidence"][0]["url"] = "https://user:secret@example.invalid/path"
    with pytest.raises(CandidateValidationError, match="anonymous HTTPS"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)
    payload = _benefit()
    payload["conflicts_with"] = ["3000000a-0000-4000-8000-000000000000".upper()]
    with pytest.raises(CandidateValidationError, match="canonical lowercase UUID"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)
    payload = _benefit()
    payload["evidence"] = []
    with pytest.raises(CandidateValidationError, match="non-empty"):
        store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload)
    payload = _benefit()
    payload["evidence"][0]["url"] = "https://example.invalid/source?revision=1#terms"
    assert store.propose(record_kind=RecordKind.BENEFIT, target_record_id=BENEFIT_ID, author_id="SYNTHETIC-ONLY-AUTHOR", review_tier="standard", base_record=_benefit(), payload=payload).id


def test_bounds_fk_initialization_and_two_store_concurrent_review(tmp_path: Path) -> None:
    path = tmp_path / "candidates.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('base_release_id', ?)", ("50000000-0000-4000-8000-000000000000",))
    with pytest.raises(CandidateIntegrityError):
        CandidateStore(path, RELEASE)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'candidates'").fetchone() is None

    store = _store(tmp_path / "second")
    candidate = _proposal(store, review_tier="high_impact")
    second_store = CandidateStore(tmp_path / "second" / "candidates.sqlite3", RELEASE)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(instance.review, candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-SAME-REVIEWER", decision=ReviewDecision.APPROVE) for instance in (store, second_store)]
        outcomes = [future.exception() for future in futures]
    assert sum(outcome is None for outcome in outcomes) == 1
    assert any(isinstance(outcome, CandidateValidationError) for outcome in outcomes if outcome is not None)
    assert len(store.reviews(candidate.id)) == 1
    with sqlite3.connect(tmp_path / "second" / "candidates.sqlite3") as connection:
        foreign_keys = connection.execute("PRAGMA foreign_key_list(reviews)").fetchall()
    assert any(foreign_key[2] == "candidates" and foreign_key[6] == "RESTRICT" for foreign_key in foreign_keys)
    with pytest.raises(CandidateValidationError, match="bounded"):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="x" * 129, decision=ReviewDecision.APPROVE)
    with pytest.raises(CandidateValidationError, match="maximum"):
        store.review(candidate.id, reviewer_kind="human", reviewer_id="SYNTHETIC-ONLY-SECOND", decision=ReviewDecision.APPROVE, note="x" * 1001)


def _store(tmp_path: Path) -> CandidateStore:
    return CandidateStore(tmp_path / "candidates.sqlite3", RELEASE)


def _proposal(store: CandidateStore, *, review_tier: str = "standard", author: str = "SYNTHETIC-ONLY-AUTHOR"):
    return store.propose(record_kind=RecordKind.OFFERING, target_record_id=OFFERING_ID, author_id=author, review_tier=review_tier, base_record=_offering(), payload=_offering(display_name="SYNTHETIC-ONLY-PROPOSED"))


def _offering(*, display_name: str = "SYNTHETIC-ONLY-Offering") -> dict[str, object]:
    return {"id": OFFERING_ID, "slug": "synthetic-only-offering", "display_name": display_name, "issuer_id": "synthetic-only-issuer", "product_variant_id": "synthetic-only-variant", "network_id": "synthetic-only-network", "market": "IN", "aliases": ["SYNTHETIC-ONLY Alias"], "effective_from": "2026-01-01"}


def _benefit(*, title: str = "SYNTHETIC-ONLY Benefit") -> dict[str, object]:
    return {"id": BENEFIT_ID, "offering_id": OFFERING_ID, "benefit_type": "cashback", "title": title, "status": "needs_review", "review_tier": "standard", "eligibility": [{"field": "transaction.channel", "operator": "equals", "value": "online"}], "evidence": [{"id": EVIDENCE_ID, "source_policy_class": "issuer_document", "url": "https://example.invalid/synthetic-terms", "content_sha256": "a" * 64, "retrieved_at": "2026-08-07T00:00:00Z", "confidence": "high"}], "conflicts_with": []}


def _evidence_set(seed: int) -> list[dict[str, str]]:
    return [
        {
            "id": f"40000000-0000-4000-8000-{index + seed:012d}",
            "source_policy_class": "issuer_document" if seed == 0 else "merchant_terms",
            "url": f"https://example.invalid/synthetic-{seed}-{index}",
            "content_sha256": f"{index + seed:064x}",
            "retrieved_at": f"2026-08-07T00:00:{index + seed:02d}Z",
            "confidence": "high" if seed == 0 else "low",
            "effective_from": "2026-01-01" if seed == 0 else "2026-02-01",
            "effective_to": "2026-03-01" if seed == 0 else "2026-04-01",
        }
        for index in range(50)
    ]
