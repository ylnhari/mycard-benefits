"""Setting up the card-details code, and revealing a partly-filled card.

The owner hit both of these with a real wallet. The code that authorises a
reveal is one credential for the whole vault, but creating it was gated on the
card they happened to click having a number *and* an expiry month *and* year.
Clicking a card with anything missing refused the setup — and since the setup is
what every other card needs, one incomplete card locked the feature for all of
them. The reveal path then withheld a number that was stored, because an expiry
was not.

Values here are synthetic: the PAN is non-numeric and cannot be Luhn-valid.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mycard_benefits.vault.core import VaultAccessError, VaultStore

PASS = "synthetic card details passphrase"
CARD = "hdfc-regalia-gold-credit"
PAN = "SYNTHETIC-ONLY-PAN"
PIN = "135790"


def _session(tmp_path: Path):
    return VaultStore(tmp_path / "private" / "vault.json").create(PASS)


def test_the_code_can_be_created_from_a_card_with_no_expiry(tmp_path: Path) -> None:
    """A vault-wide credential does not depend on one card being complete."""
    session = _session(tmp_path)
    card_id = session.add_card(CARD, {"pan": PAN}, passphrase=PASS)

    token = session.create_detail_credential(card_id, "pin", PIN)

    assert token


def test_the_code_can_be_created_from_a_card_with_no_details_at_all(tmp_path: Path) -> None:
    """Onboarding stores no private values by default, so this is the common case."""
    session = _session(tmp_path)
    card_id = session.add_card(CARD, {}, passphrase=PASS)

    assert session.create_detail_credential(card_id, "pin", PIN)


def test_a_stored_number_is_revealed_even_without_an_expiry(tmp_path: Path) -> None:
    """Withholding a saved number because something else was not saved is wrong."""
    session = _session(tmp_path)
    card_id = session.add_card(CARD, {"pan": PAN}, passphrase=PASS)
    token = session.create_detail_credential(card_id, "pin", PIN)

    values = session.reveal_detail_values(card_id, authorization_token=token)

    assert values["card_number"] == PAN
    # Reported as absent rather than as an empty or invented date.
    assert values["expiry"] is None


def test_a_card_with_no_number_still_reports_nothing_to_reveal(tmp_path: Path) -> None:
    """The permissive change must not turn an empty card into a successful reveal."""
    session = _session(tmp_path)
    complete = session.add_card(CARD, {"pan": PAN}, passphrase=PASS)
    empty = session.add_card(CARD, {}, passphrase=PASS)
    token = session.create_detail_credential(complete, "pin", PIN)

    with pytest.raises(VaultAccessError):
        session.reveal_detail_values(empty, authorization_token=token)


def test_a_complete_card_reveals_its_expiry(tmp_path: Path) -> None:
    """The ordinary case keeps working, formatted as before."""
    session = _session(tmp_path)
    card_id = session.add_card(
        CARD,
        {"pan": PAN, "expiry_month": "04", "expiry_year": "2031", "cvv": "SYNTHETIC"},
        passphrase=PASS,
    )
    token = session.create_detail_credential(card_id, "pin", PIN)

    values = session.reveal_detail_values(card_id, authorization_token=token)

    assert values["card_number"] == PAN
    assert values["expiry"] == "04 / 31"
    assert values["cvv"] == "SYNTHETIC"


def test_an_unauthorized_token_still_reveals_nothing(tmp_path: Path) -> None:
    """The credential remains the only way through, which is the point of it."""
    session = _session(tmp_path)
    card_id = session.add_card(CARD, {"pan": PAN}, passphrase=PASS)
    session.create_detail_credential(card_id, "pin", PIN)

    with pytest.raises(VaultAccessError):
        session.reveal_detail_values(card_id, authorization_token="not-the-token")
