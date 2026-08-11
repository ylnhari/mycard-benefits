"""Synthetic, human-confirmed private card reconciliation workflow.

This module is deliberately a protected service boundary, not a browser write
API.  It previews bounded metadata and applies a change only after fresh vault
reauthentication.  Unknown values stay unknown; no inference is performed.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .core import (
    CardLifecycle,
    ReconciliationAuthorization,
    VaultSession,
)

_ANONYMOUS = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_OFFERING = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SIGNALS = frozenset({"unknown", "expired", "expiring_soon", "active"})
_ACTIONS = frozenset({"confirm", "defer", "reject", "correct"})
_AMBIGUITY_CODES = frozenset({"owner_unknown", "variant_unknown", "lineage_unknown", "status_unknown"})


class ReconciliationAction(StrEnum):
    CONFIRM = "confirm"
    DEFER = "defer"
    REJECT = "reject"
    CORRECT = "correct"


@dataclass(frozen=True)
class ReconciliationProposal:
    card_id: str
    owner_alias: str | None
    owner_role: str | None
    offering_id: str | None
    offering_dimensions: dict[str, str]
    lifecycle: CardLifecycle | None
    expiry_signal: str
    archived_vs_expired: str
    provisional_active: bool
    replacement_card_id: str | None
    ambiguities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.card_id or not isinstance(self.card_id, str):
            raise ValueError("card id is required")
        for value in (self.owner_alias, self.owner_role):
            if value is not None and not _ANONYMOUS.fullmatch(value):
                raise ValueError("owner values must be anonymous aliases")
        if self.offering_id is not None and not _OFFERING.fullmatch(self.offering_id):
            raise ValueError("offering id is invalid")
        if self.lifecycle is not None and not isinstance(self.lifecycle, CardLifecycle):
            raise ValueError("lifecycle is invalid")
        if any(not isinstance(k, str) or not _ANONYMOUS.fullmatch(k) or not _ANONYMOUS.fullmatch(v)
               for k, v in self.offering_dimensions.items()):
            raise ValueError("offering dimensions are invalid")
        if self.expiry_signal not in _SIGNALS:
            raise ValueError("expiry signal is invalid")
        if self.archived_vs_expired not in {"unknown", "archived", "expired", "neither"}:
            raise ValueError("archive status is invalid")
        if any(item not in _AMBIGUITY_CODES for item in self.ambiguities):
            raise ValueError("ambiguity is invalid")

    def canonical(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id, "owner_alias": self.owner_alias,
            "owner_role": self.owner_role, "offering_id": self.offering_id,
            "offering_dimensions": dict(sorted(self.offering_dimensions.items())),
            "lifecycle": self.lifecycle.value if self.lifecycle else None,
            "expiry_signal": self.expiry_signal,
            "archived_vs_expired": self.archived_vs_expired,
            "provisional_active": self.provisional_active,
            "replacement_card_id": self.replacement_card_id,
            "ambiguities": list(self.ambiguities),
        }

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def intent_digest(self, action: ReconciliationAction) -> str:
        payload = {"action": action.value, "proposal": self.canonical()}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ReconciliationOutcome:
    action: ReconciliationAction
    status: str
    proposal_digest: str
    changed: bool
    audit: dict[str, str]


class ReconciliationService:
    """Protected local service.  It accepts synthetic-shaped proposals only."""

    def _resolve(self, session: VaultSession, proposal: ReconciliationProposal) -> ReconciliationProposal:
        try:
            uuid.UUID(proposal.card_id)
        except (ValueError, AttributeError, TypeError):
            raise ValueError("card id is invalid") from None
        cards = {card["card_id"]: card for card in session.list_cards()}
        current = cards.get(proposal.card_id)
        if current is None:
            raise ValueError("card id is invalid")
        replacement = proposal.replacement_card_id
        if replacement is not None:
            try:
                uuid.UUID(replacement)
            except (ValueError, AttributeError, TypeError):
                raise ValueError("replacement id is invalid") from None
            if replacement not in cards or replacement == proposal.card_id:
                raise ValueError("replacement id is invalid")
        return replace(proposal, card_id=current["card_id"],
                       replacement_card_id=cards[replacement]["card_id"] if replacement else None)

    def preview(self, session: VaultSession, proposal: ReconciliationProposal) -> dict[str, Any]:
        resolved = self._resolve(session, proposal)
        return {"status": "pending", "proposal": resolved.canonical(), "proposal_digest": resolved.digest(),
                "allowed_actions": sorted(_ACTIONS), "ui_write_handoff": "protected-local-service",
                "ambiguity_copy": {"owner_unknown": "Owner is not confirmed.",
                                    "variant_unknown": "Card variant is not confirmed.",
                                    "lineage_unknown": "Replacement history is not confirmed.",
                                    "status_unknown": "Card status is not confirmed."}}

    def authorize(self, session: VaultSession, proposal: ReconciliationProposal,
                  action: ReconciliationAction, *, passphrase: str,
                  correction: ReconciliationProposal | None = None) -> ReconciliationAuthorization:
        if not isinstance(action, ReconciliationAction):
            raise ValueError("unsupported reconciliation action")
        chosen = correction if action is ReconciliationAction.CORRECT else proposal
        if action is ReconciliationAction.CORRECT and correction is None:
            raise ValueError("correction is required")
        if chosen is None or chosen.card_id != proposal.card_id:
            raise ValueError("wrong record")
        chosen = self._resolve(session, chosen)
        mutation = self._mutation(session, proposal, chosen, action)
        return session.authorize_reconciliation(
            proposal.card_id, proposal.digest(), action.value, chosen.intent_digest(action), mutation,
            passphrase=passphrase
        )

    def apply(self, session: VaultSession, proposal: ReconciliationProposal, action: ReconciliationAction,
              authorization: ReconciliationAuthorization, *, correction: ReconciliationProposal | None = None) -> ReconciliationOutcome:
        if not isinstance(action, ReconciliationAction):
            raise ValueError("unsupported reconciliation action")
        chosen = correction if action is ReconciliationAction.CORRECT else proposal
        if action is ReconciliationAction.CORRECT and correction is None:
            raise ValueError("correction is required")
        if chosen is None:
            raise ValueError("correction is required")
        if chosen.card_id != proposal.card_id:
            raise ValueError("wrong record")
        chosen = self._resolve(session, chosen)
        session.apply_reconciliation_metadata(authorization, mutation=self._mutation(session, proposal, chosen, action))
        return ReconciliationOutcome(action, "pending_human_confirmation" if action is not ReconciliationAction.CONFIRM else "confirmed_metadata_only",
                                     proposal.digest(), action in {ReconciliationAction.CONFIRM, ReconciliationAction.CORRECT},
                                     {"record": proposal.card_id, "action": action.value})

    def _mutation(self, session: VaultSession, proposal: ReconciliationProposal,
                  chosen: ReconciliationProposal, action: ReconciliationAction) -> dict[str, Any]:
        current = session.reconciliation_card(proposal.card_id)
        expected_old = {key: current[key] for key in ("offering_id", "lifecycle", "replacement_card_id", "updated_at")}
        if "lineage_unknown" in chosen.ambiguities:
            if action is ReconciliationAction.CORRECT:
                raise ValueError("explicit lineage choice is required")
            replacement = current["replacement_card_id"]
        else:
            replacement = chosen.replacement_card_id
        effective = chosen if action in {ReconciliationAction.CONFIRM, ReconciliationAction.CORRECT} else proposal
        metadata = json.dumps({"action": action.value, "proposal": effective.canonical()}, sort_keys=True, separators=(",", ":"))
        return {
            "record": proposal.card_id, "action": action.value,
            "proposal_digest": proposal.digest(), "intent_digest": chosen.intent_digest(action),
            "expected_revision": session.revision_hex,
            "expected_old": expected_old,
            "new": {"offering_id": effective.offering_id or current["offering_id"],
                    "lifecycle": effective.lifecycle.value if effective.lifecycle else current["lifecycle"],
                    "replacement_card_id": replacement},
            "metadata": metadata,
        }
