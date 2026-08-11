"""Deterministic, local-only contemplated-purchase route optimization."""

from .engine import optimize
from .model import (
    ActionLinkReviewState,
    ComponentValueClass,
    EvidenceTier,
    Freshness,
    LinkClass,
    OptimizationResult,
    PurchaseScenario,
    RouteCandidate,
    RouteComponent,
    UserFee,
)

__all__ = [
    "ComponentValueClass",
    "ActionLinkReviewState",
    "EvidenceTier",
    "Freshness",
    "LinkClass",
    "OptimizationResult",
    "PurchaseScenario",
    "RouteCandidate",
    "RouteComponent",
    "UserFee",
    "optimize",
]
