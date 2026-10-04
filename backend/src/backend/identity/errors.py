"""Transport- and persistence-independent Identity operation errors."""


class AdminOperationError(ValueError):
    """A safe, stable operator operation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
