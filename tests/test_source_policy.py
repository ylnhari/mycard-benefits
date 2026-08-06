from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mycard_benefits.sources import (
    AdmissionError,
    AdmissionStatus,
    EvidenceCandidate,
    RetrievalBlocked,
    assess_public_response,
    load_admission,
    prepare_public_request,
)

ROOT = Path(__file__).parents[1]


def _approved(path: Path):  # type: ignore[no-untyped-def]
    candidate = load_admission(path)
    return replace(
        candidate,
        status=AdmissionStatus.APPROVED,
        human_reviewer_id="SYNTHETIC-ONLY-REVIEWER",
    )


def test_candidate_admission_loads_but_cannot_fetch() -> None:
    admission = load_admission(ROOT / "sources/admissions/synthetic-example.json")
    assert not admission.allows_automation
    with pytest.raises(AdmissionError):
        admission.authorize_url("https://example.invalid/synthetic-benefits/card")


def test_approved_scope_is_exact_and_requests_cannot_carry_credentials(tmp_path: Path) -> None:
    path = tmp_path / "admission.json"
    payload = json.loads((ROOT / "sources/admissions/synthetic-example.json").read_text(encoding="utf-8"))
    payload.update({"status": "approved", "human_reviewer_id": "SYNTHETIC-ONLY-REVIEWER"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    admission = _approved(path)

    url, headers = prepare_public_request(
        admission,
        "https://example.invalid/synthetic-benefits/card?q=1#ignored",
        headers={"If-None-Match": '"synthetic"'},
    )
    assert url == "https://example.invalid/synthetic-benefits/card?q=1"
    assert headers["If-None-Match"] == '"synthetic"'
    with pytest.raises(AdmissionError):
        prepare_public_request(admission, "https://example.invalid/other")
    with pytest.raises(AdmissionError):
        prepare_public_request(
            admission,
            "https://example.invalid/synthetic-benefits/card",
            headers={"Authorization": "SYNTHETIC-ONLY-TOKEN"},
        )


@pytest.mark.parametrize("url", [
    "http://example.invalid/synthetic-benefits/",
    "https://user:pass@example.invalid/synthetic-benefits/",
    "https://127.0.0.1/synthetic-benefits/",
    "https://10.0.0.1/synthetic-benefits/",
])
def test_nonpublic_or_authenticated_source_urls_are_rejected(tmp_path: Path, url: str) -> None:
    payload = json.loads((ROOT / "sources/admissions/synthetic-example.json").read_text(encoding="utf-8"))
    payload["url_prefixes"] = [url]
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AdmissionError):
        load_admission(path)


@pytest.mark.parametrize("status", [401, 403, 407, 429])
def test_access_challenges_stop_without_retry(status: int) -> None:
    with pytest.raises(RetrievalBlocked):
        assess_public_response(status_code=status, content_type="text/html")


def test_captcha_and_login_bodies_fail_closed() -> None:
    for preview in (b"Please verify that you are human", b"Log in to continue", b"CAPTCHA"):
        with pytest.raises(RetrievalBlocked):
            assess_public_response(
                status_code=200,
                content_type="text/html; charset=utf-8",
                body_preview=preview,
            )


def test_evidence_candidate_contains_hash_not_content(tmp_path: Path) -> None:
    admission = _approved(ROOT / "sources/admissions/synthetic-example.json")
    body = b"SYNTHETIC-ONLY public fixture"
    assess_public_response(status_code=200, content_type="text/html", body_preview=body)
    candidate = EvidenceCandidate.from_public_response(
        admission,
        url="https://example.invalid/synthetic-benefits/card",
        body=body,
        content_type="text/html; charset=utf-8",
    )
    assert candidate.review_state == "needs_review"
    assert candidate.content_sha256
    assert "body" not in candidate.__dict__
