from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from mycard_benefits.private_import import (
    Consolidator,
    ImportRejected,
    SourceInput,
    _cards,
    _parse_sources,
    _source_binding,
    parse_sources,
)
from mycard_benefits.vault import VaultAccessError, VaultConflictError, VaultError, VaultStore


def _write(path: Path, value: str | bytes) -> Path:
    path.write_bytes(value.encode() if isinstance(value, str) else value)
    return path


def test_json_csv_and_unknown_document_are_bounded_and_count_only(tmp_path: Path) -> None:
    json_source = _write(tmp_path / "generic.json", json.dumps({"schema_version": 1, "cards": [
        {"source_record_id": "SYNTHETIC-ONLY-A", "issuer": "SYNTHETIC-ONLY-BANK",
         "product": "SYNTHETIC-ONLY-CARD", "owner": "SYNTHETIC-ONLY-PERSON"}
    ]}))
    workbook = _write(tmp_path / "cards.csv",
                      "source_record_id,variant,pan\nSYNTHETIC-ONLY-B,SYNTHETIC-ONLY-V,SYNTHETIC-ONLY-PAN\n")
    docs = tmp_path / "documents"
    docs.mkdir()
    _write(docs / "scan.bin", b"not an admitted document")
    records, counts, source_counts, digest = parse_sources([
        SourceInput("workbook", json_source), SourceInput("workbook", workbook),
        SourceInput("documents", docs),
    ])
    assert len(records) == 2
    assert counts.parsed == 2 and counts.needs_local_review == 1 and counts.rejected == 0
    assert source_counts == {"workbook": 2, "documents": 1}
    assert len(digest) == 64




def test_receipt_is_schema_closed_and_does_not_reflect_private_values(tmp_path: Path) -> None:
    source = _write(tmp_path / "cards.json", json.dumps({"cards": [
        {"source_record_id": "SYNTHETIC-ONLY-SECRET", "owner": "SYNTHETIC-ONLY-NAME",
         "pan": "SYNTHETIC-ONLY-PAN-1A1B1C1D1E1F1G1H1J1K1L1M2"}
    ]}))
    receipt = Consolidator(tmp_path / "data", b"SYNTHETIC-ONLY-KEY").run(
        [SourceInput("workbook", source)]
    ).as_dict()
    allowed = {"schema_version", "run_id", "state", "source_counts", "counts", "input_hash",
               "preview_digest", "artifact_hashes"}
    assert set(receipt) == allowed
    rendered = json.dumps(receipt)
    assert "SYNTHETIC-ONLY-SECRET" not in rendered
    assert "SYNTHETIC-ONLY-NAME" not in rendered
    assert "SYNTHETIC-ONLY-PAN" not in rendered


def test_symlink_and_formula_fail_closed(tmp_path: Path) -> None:
    outside = _write(tmp_path / "outside.json", "{}")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ImportRejected):
        parse_sources([SourceInput("workbook", link)])
    formula = _write(tmp_path / "formula.csv", "source_record_id,notes\nSYNTHETIC-ONLY-X,=NOW()\n")
    with pytest.raises(ImportRejected):
        parse_sources([SourceInput("workbook", formula)])


def test_xlsx_formula_and_path_traversal_fail_closed(tmp_path: Path) -> None:
    workbook = tmp_path / "bad.xlsx"
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "<x:worksheet xmlns:x='x'><x:row><x:c><x:f>NOW()</x:f></x:c></x:row></x:worksheet>")
    with pytest.raises(ImportRejected):
        parse_sources([SourceInput("workbook", workbook)])


def _card_source(path: Path, record_id: str = "SYNTHETIC-ONLY-A") -> Path:
    return _write(path, json.dumps({"schema_version": 1, "cards": [{
        "source_record_id": record_id,
        "owner": "SYNTHETIC-ONLY-OWNER",
        "cardholder": "SYNTHETIC-ONLY-CARDHOLDER",
        "pan": "SYNTHETIC-ONLY-PAN-1A1B1C1D1E1F1G1H1J1K1L1M2",
        "last_four": "1112",
        "expiry": "2030-01",
        "network": "VISA",
        "nickname": "SYNTHETIC-ONLY-NICKNAME",
    }]}))


def test_apply_is_one_authorized_atomic_batch_and_preserves_lkg(tmp_path: Path) -> None:
    source = _card_source(tmp_path / "cards.json")
    store = VaultStore(tmp_path / "data" / "private" / "vault.json")
    session = store.create("synthetic passphrase")
    consolidator = Consolidator(tmp_path / "data", b"SYNTHETIC-ONLY-ARTIFACT-KEY")
    preview = consolidator.run([SourceInput("workbook", source)], session=session)
    authorization = session.authorize_consolidation(
        preview.preview_digest, "consolidate_apply", passphrase="synthetic passphrase"
    )
    receipt = consolidator.run(
        [SourceInput("workbook", source)], apply=True, approved_digest=preview.preview_digest,
        session=session, authorization=authorization,
    )
    assert receipt.state == "applied"
    assert receipt.counts.imported == 1 and receipt.counts.conflict == 0
    assert len(session.list_cards()) == 1
    stored = session._decrypt_record(next(iter(session._records.values())))
    assert stored["owner_alias"] == "SYNTHETIC-ONLY-OWNER"
    assert stored["cardholder_name"] == "SYNTHETIC-ONLY-CARDHOLDER"
    artifacts = tmp_path / "data" / "private" / "imports"
    assert list(artifacts.glob("snapshot.lkg.*.bin"))
    assert list(artifacts.glob("vault-import.lkg.*.bin"))
    receipts = list((artifacts / "receipts").glob("*.json"))
    assert len(receipts) == 1
    assert "SYNTHETIC-ONLY" not in receipts[0].read_text(encoding="utf-8")
    with pytest.raises(VaultAccessError):
        session.consume_consolidation(authorization, preview.preview_digest, "consolidate_apply")


def test_bad_second_record_cannot_partially_apply_or_replace_lkg(tmp_path: Path) -> None:
    source = _card_source(tmp_path / "cards.json")
    store = VaultStore(tmp_path / "data" / "private" / "vault.json")
    session = store.create("synthetic passphrase")
    consolidator = Consolidator(tmp_path / "data", b"SYNTHETIC-ONLY-ARTIFACT-KEY")
    preview = consolidator.run([SourceInput("workbook", source)], session=session)
    lkg_before = set((tmp_path / "data" / "private" / "imports").glob("snapshot.lkg.*.bin"))
    source.write_text(json.dumps({"cards": [
        {"source_record_id": "SYNTHETIC-ONLY-A", "pan": "SYNTHETIC-ONLY-PAN-1A1B1C1D1E1F1G1H1J1K1L1M2"},
        {"source_record_id": "SYNTHETIC-ONLY-B", "pan": "SYNTHETIC-ONLY-PAN-2A2B2C2D2E2F2G2H2J2K2L2M3", "unknown": "x"},
    ]}), encoding="utf-8")
    authorization = session.authorize_consolidation(
        preview.preview_digest, "consolidate_apply", passphrase="synthetic passphrase"
    )
    with pytest.raises(ImportRejected):
        consolidator.run(
            [SourceInput("workbook", source)], apply=True, approved_digest=preview.preview_digest,
            session=session, authorization=authorization,
        )
    assert session.list_cards() == ()
    assert set((tmp_path / "data" / "private" / "imports").glob("snapshot.lkg.*.bin")) == lkg_before


def test_pending_recovery_replays_idempotently_after_post_write_interruption(tmp_path: Path) -> None:
    source = _card_source(tmp_path / "cards.json")
    vault_path = tmp_path / "data" / "private" / "vault.json"
    store = VaultStore(vault_path)
    session = store.create("synthetic passphrase")
    consolidator = Consolidator(tmp_path / "data", b"SYNTHETIC-ONLY-ARTIFACT-KEY")
    parsed = _parse_sources([SourceInput("workbook", source)])
    cards = _cards(parsed)
    preview = consolidator.run([SourceInput("workbook", source)], session=session)
    # Model the narrow crash point after the durable pending state and vault
    # write but before the committed receipt is sealed.
    consolidator._write_plan_artifacts(tmp_path / "data" / "private" / "imports", parsed, cards, preview.preview_digest, state="pending")
    session.reconcile_cards(cards)
    session.lock()
    recovered = store.open("synthetic passphrase")
    authorization = recovered.authorize_consolidation(
        preview.preview_digest, "consolidate_recover", passphrase="synthetic passphrase"
    )
    receipt = consolidator.run(
        [SourceInput("workbook", source)], apply=True, approved_digest=preview.preview_digest,
        session=recovered, authorization=authorization,
    )
    assert receipt.state == "applied" and receipt.counts.existing == 1
    assert consolidator.pending_digest() is None


def test_strict_records_documents_and_csv_headers_fail_closed(tmp_path: Path) -> None:
    non_object = _write(tmp_path / "non-object.json", json.dumps({"cards": ["bad"]}))
    with pytest.raises(ImportRejected):
        parse_sources([SourceInput("workbook", non_object)])
    duplicate_headers = _write(tmp_path / "duplicate.csv", "source_record_id,source_record_id\nSYNTHETIC-ONLY-A,SYNTHETIC-ONLY-A\n")
    with pytest.raises(ImportRejected):
        parse_sources([SourceInput("workbook", duplicate_headers)])
    documents = tmp_path / "documents"
    documents.mkdir()
    _card_source(documents / "admitted.json")
    records, counts, source_counts, _ = parse_sources([SourceInput("documents", documents)])
    assert len(records) == 1 and counts.needs_local_review == 0 and source_counts == {"documents": 1}


def test_compatible_cross_source_observations_merge_and_policy_limits_bind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _card_source(tmp_path / "first.json", "SYNTHETIC-ONLY-FIRST")
    second = _card_source(tmp_path / "second.json", "SYNTHETIC-ONLY-SECOND")
    parsed = _parse_sources([SourceInput("workbook", first), SourceInput("workbook", second)])
    cards = _cards(parsed)
    assert len(cards) == 1
    assert parsed.counts.conflict == 0
    original = _source_binding(parsed, cards)
    monkeypatch.setattr("mycard_benefits.private_import.MAX_XLSX_RATIO", 201)
    assert _source_binding(parsed, cards) != original


def test_contradictory_observations_are_explicit_review_conflicts(tmp_path: Path) -> None:
    first = _card_source(tmp_path / "first.json", "SYNTHETIC-ONLY-FIRST")
    contradictory = json.loads(first.read_text(encoding="utf-8"))
    contradictory["cards"][0]["nickname"] = "SYNTHETIC-ONLY-CONTRADICTION"
    second = _write(tmp_path / "second.json", json.dumps(contradictory))
    parsed = _parse_sources([SourceInput("workbook", first), SourceInput("workbook", second)])
    with pytest.raises(ImportRejected, match="compatible card observations"):
        _cards(parsed)
    assert parsed.counts.conflict == 1
    assert parsed.counts.needs_local_review == 1


def test_apply_authorization_rejects_same_session_target_revision_change(tmp_path: Path) -> None:
    source = _card_source(tmp_path / "cards.json")
    session = VaultStore(tmp_path / "data" / "private" / "vault.json").create("synthetic passphrase")
    consolidator = Consolidator(tmp_path / "data", b"SYNTHETIC-ONLY-ARTIFACT-KEY")
    preview = consolidator.run([SourceInput("workbook", source)], session=session)
    authorization = session.authorize_consolidation(
        preview.preview_digest, "consolidate_apply", passphrase="synthetic passphrase"
    )
    session.add_card("synthetic-example-in-visa", {"pan": "SYNTHETIC-ONLY-PAN-2A2B2C2D2E2F2G2H2J2K2L2M3"}, passphrase="synthetic passphrase")
    with pytest.raises((VaultConflictError, ImportRejected)):
        consolidator.run(
            [SourceInput("workbook", source)], apply=True,
            approved_digest=preview.preview_digest, session=session, authorization=authorization,
        )


def test_failed_prewrite_apply_allows_corrected_source_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _card_source(tmp_path / "cards.json")
    session = VaultStore(tmp_path / "data" / "private" / "vault.json").create("synthetic passphrase")
    consolidator = Consolidator(tmp_path / "data", b"SYNTHETIC-ONLY-ARTIFACT-KEY")
    preview = consolidator.run([SourceInput("workbook", source)], session=session)
    authorization = session.authorize_consolidation(
        preview.preview_digest, "consolidate_apply", passphrase="synthetic passphrase"
    )
    monkeypatch.setattr(session, "reconcile_cards", lambda cards: (_ for _ in ()).throw(VaultError("synthetic write failure")))
    with pytest.raises(VaultError):
        consolidator.run(
            [SourceInput("workbook", source)], apply=True,
            approved_digest=preview.preview_digest, session=session, authorization=authorization,
        )
    corrected = json.loads(source.read_text(encoding="utf-8"))
    corrected["cards"][0]["source_record_id"] = "SYNTHETIC-ONLY-CORRECTED"
    source.write_text(json.dumps(corrected), encoding="utf-8")
    monkeypatch.undo()
    retry_preview = consolidator.run([SourceInput("workbook", source)], session=session)
    retry_auth = session.authorize_consolidation(
        retry_preview.preview_digest, "consolidate_apply", passphrase="synthetic passphrase"
    )
    receipt = consolidator.run(
        [SourceInput("workbook", source)], apply=True,
        approved_digest=retry_preview.preview_digest, session=session, authorization=retry_auth,
    )
    assert receipt.state == "applied"
