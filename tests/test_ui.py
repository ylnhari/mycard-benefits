from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings

ROOT = Path(__file__).parents[1]


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=ROOT / "catalog", port=8777)
    return TestClient(create_app(settings))


def test_dashboard_has_all_public_navigation_and_honest_vault_gate(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")

    assert page.status_code == 200
    for item in ("Overview", "My Cards", "Benefits", "Ask", "Compare", "Expiring Soon", "Updates", "Sources", "Research Queue", "Settings"):
        assert item in page.text
    assert 'href="#ask"' in page.text
    assert "Rover sign-in required" not in page.text
    assert "Secret card fields are never returned" in page.text
    assert "PAN, CVV, PIN" in page.text
    assert "disabled" in page.text


def test_catalog_dashboard_assets_use_read_only_endpoints_and_safe_dom_updates() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    assert 'getCatalog("offerings")' in script
    assert 'getCatalog("benefits")' in script
    assert 'fetch("/api/v1/private/cards"' in script
    assert 'credentials: "same-origin"' in script
    assert 'cache: "no-store"' in script
    assert "Rover" not in script
    assert "Companion Dashboard" in script
    assert "function renderPrivateCards" in script
    assert "textContent" in script
    assert "innerHTML" not in script
    assert "insertAdjacentHTML" not in script
    assert 'rel = "noopener noreferrer"' in script
    assert "@media (max-width:850px)" in style
    assert "prefers-reduced-motion" in style


def test_dashboard_accessibility_follow_up_has_target_sizes_and_focus_fallback() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    assert "min-height:44px" in style
    assert "summary { display:flex; align-items:center; min-height:44px" in style
    assert ".evidence-list a,.source-card a { display:inline-flex; align-items:center; min-height:44px" in style
    assert "function viewFromHash()" in script
    assert 'return views.has(requested) ? requested : "overview"' in script
    assert 'heading.focus({ preventScroll: true })' in script
    assert "showView(initialView);" in script
    assert "showView(view, { focus: true });" in script
    assert "innerHTML" not in script


def test_qa_ui_is_accessible_bounded_and_uses_post_only(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    for fragment in ('id="qaForm"', 'id="qaQuery"', 'maxlength="500"', 'id="qaStatus"', 'role="status"', 'aria-live="polite"', 'id="qaResults"'):
        assert fragment in page.text
    assert 'fetch("/api/v1/qa", { method: "POST"' in script
    assert "method: \"GET\"" not in script
    assert "value.length > 500" in script
    assert 'event.key === "Enter"' in script and "event.isComposing" in script
    assert 'event.key === "Escape"' in script
    assert 'submit.disabled = true' in script and 'form.setAttribute("aria-busy", "true")' in script
    assert 'heading.focus({ preventScroll: true })' in script
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script
    assert ".qa-controls input" in style and "min-height:44px" in style
    assert ".qa-controls { display:grid; grid-template-columns:1fr; }" in style


def test_qa_renderer_covers_safe_results_examples_and_fallbacks() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    for fragment in ("function renderQaResult", "result.message", "result.benefits", "result.offerings", "result.choices", "result.suggestions", "result.intent === \"no_result\"", "function qaFactCard", "function qaLink", "safeHref(url)"):
        assert fragment in script
    assert 'link.target = "_blank"' in script and 'link.rel = "noopener noreferrer"' in script
    assert "Public catalog unavailable — no private fallback is used." in script
    assert "Unable to answer that question. Try a supported public catalog question." in script
    assert "data-qa-example" in script and "function supportedSuggestion" in script and "function qaButton" in script
    assert "localStorage" not in script[script.index("function setQaStatus"):]
