from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")


def test_conditional_benefits_use_a_safe_consumer_state_and_detail_action() -> None:
    assert "function benefitIsConditional(benefit)" in SCRIPT
    assert 'label: "Check before use"' in SCRIPT
    assert 'label: "Verified"' in SCRIPT and 'label: "Sources differ"' in SCRIPT
    assert "Check the current qualifying terms before use." in SCRIPT
    assert 'node("button", "Details", "secondary benefit-detail-toggle")' in SCRIPT
    assert "function consumerAllowanceText(benefit)" in SCRIPT
    assert 'unit = "lounge visit"' in SCRIPT
    assert "function openBenefitDetails(benefitId)" in SCRIPT
    assert "visits left" not in SCRIPT.lower()
    assert "visits remaining" not in SCRIPT.lower()
