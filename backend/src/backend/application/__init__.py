"""Framework-neutral application capabilities and shared domain failures."""


class AuthenticationRequiredError(Exception):
    """Signal that no authenticated application identity is available."""


class ForbiddenRequestError(Exception):
    """Signal that the authenticated identity lacks the required capability."""
