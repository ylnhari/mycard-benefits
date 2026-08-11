"""The public shape of a user-tracked spend-condition state.

This module defines the three-value state shape only: `met`, `not_met`, or
`unknown`. The actual per-card value a user records is private data that
belongs in the encrypted local vault (`src/mycard_benefits/vault/`), which
this change does not touch — the vault, real card records, and any private
per-card storage are out of scope here. What is safe and useful to define in
the public catalog layer is the closed, transaction-free shape every such
state must take, so a future private tracking feature (and any public UI
describing it) cannot silently grow a fourth state or start requiring a
transaction record to answer the condition.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum


class SpendConditionState(StrEnum):
    """A user-set answer to a spend-triggered eligibility condition.

    There is no transaction-derived state and no partial-progress state:
    absent a user's own answer, the state is always `UNKNOWN`, never guessed
    from a spend total this app does not and must not ingest.
    """

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


DEFAULT_SPEND_CONDITION_STATE = SpendConditionState.UNKNOWN


@dataclass(frozen=True)
class SpendConditionAnswer:
    """One user-set answer to one condition, carrying no transaction data.

    `condition_id` names the catalog eligibility condition this answers, not
    a purchase, merchant, amount, or date — see the module docstring.
    """

    condition_id: str
    state: SpendConditionState = DEFAULT_SPEND_CONDITION_STATE

    def __post_init__(self) -> None:
        if not self.condition_id or not isinstance(self.condition_id, str):
            raise ValueError("condition_id must be a non-empty string")
        if not isinstance(self.state, SpendConditionState):
            raise ValueError("state must be a SpendConditionState")


TRANSACTION_SHAPED_FIELD_NAMES = frozenset(
    {"amount", "merchant", "date", "currency", "transaction_id", "mcc", "channel"}
)


def assert_no_transaction_shaped_fields() -> None:
    """A structural guard, run by tests, that the answer shape never grows a transaction field.

    Raises if a future edit adds a field to `SpendConditionAnswer` that looks
    like transaction data, so that drift is caught at review time rather than
    discovered later as a private-data leak.
    """
    field_names = {field.name for field in fields(SpendConditionAnswer)}
    overlap = field_names & TRANSACTION_SHAPED_FIELD_NAMES
    if overlap:
        raise AssertionError(f"SpendConditionAnswer must not carry transaction-shaped fields: {sorted(overlap)}")
