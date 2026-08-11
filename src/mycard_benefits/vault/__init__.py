"""Local encrypted card-vault boundary.

This package intentionally has no web or network dependencies. Local audit
storage is injected into protected vault sessions when a caller requires it.
"""

from .core import (
    CardLifecycle,
    ChildRecordKind,
    ChildRecordLifecycle,
    ConsolidationAuthorization,
    ReconciliationCard,
    ReconciliationResult,
    RevealAuthorization,
    VaultAccessError,
    VaultConflictError,
    VaultError,
    VaultPermissionError,
    VaultSession,
    VaultStore,
    secure_private_path,
    validate_offering_id,
    validate_reconciliation_id,
    validate_reconciliation_pan,
    validate_secret_fields,
)
from .personal_state import AttemptOutcome, ManualSpendAggregate, PrivateAttempt
from .protected import (
    AttachmentStore,
    AuditAction,
    AuditLog,
    BackupManager,
    ProtectedError,
    RecoveryManager,
    VerifiedRestoreLease,
)
from .reconciliation import (
    ReconciliationAction,
    ReconciliationOutcome,
    ReconciliationProposal,
    ReconciliationService,
)

__all__ = [
    "CardLifecycle",
    "ChildRecordKind",
    "ChildRecordLifecycle",
    "ConsolidationAuthorization",
    "ReconciliationCard",
    "ReconciliationResult",
    "ReconciliationAction",
    "ReconciliationOutcome",
    "ReconciliationProposal",
    "ReconciliationService",
    "RevealAuthorization",
    "VaultAccessError",
    "VaultConflictError",
    "VaultError",
    "VaultPermissionError",
    "VaultSession",
    "VaultStore",
    "validate_offering_id",
    "validate_reconciliation_id",
    "validate_reconciliation_pan",
    "validate_secret_fields",
    "secure_private_path",
    "AttachmentStore",
    "AuditAction",
    "AuditLog",
    "BackupManager",
    "ProtectedError",
    "RecoveryManager",
    "VerifiedRestoreLease",
    "AttemptOutcome",
    "ManualSpendAggregate",
    "PrivateAttempt",
]
