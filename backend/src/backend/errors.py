"""Cross-boundary error types for application and persistence adapters."""


class TransactionConflictError(Exception):
    """A write could not commit because persisted data conflicted."""


class TransactionUnavailableError(Exception):
    """A transaction could not be completed because storage was unavailable."""


class AssessmentWriteConflictError(ValueError):
    """An assessment revision or model binding changed before the write committed."""
