"""Domain errors shared by lifecycle policies and Application orchestration."""


class ExamRoundConflictError(ValueError):
    """Signal a stale, duplicate-different, or parallel lifecycle command."""
