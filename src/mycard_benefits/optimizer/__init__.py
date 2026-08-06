"""Deterministic, local-only contemplated-purchase route optimization."""

from .engine import optimize
from .model import (
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
