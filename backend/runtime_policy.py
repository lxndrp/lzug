"""Runtime-specific HTTP policy extension points.

The product image ships only the neutral default policy from this module.
Alternative assemblies can provide routes and additional restrictions without
placing their implementation or configuration in the product image.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .auth import AuthContext
    from .transport import RequestContext


class RuntimePolicy(Protocol):
    """Assembly-owned routes, session metadata, and mutation restrictions."""

    def handle_public_get(self, handler: RequestContext, path_parts: list[str]) -> bool:
        """Handle one unauthenticated GET request when owned by the assembly."""

    def handle_public_post(self, handler: RequestContext, path_parts: list[str]) -> bool:
        """Handle one unauthenticated POST request when owned by the assembly."""

    def allow_product_auth(self) -> bool:
        """Return whether the normal local authentication routes remain available."""

    def session_view(self, context: AuthContext) -> dict[str, Any]:
        """Return assembly-specific, non-secret fields for ``GET /api/session``."""

    def authorize_mutation(
        self,
        handler: RequestContext,
        method: str,
        path_parts: list[str],
        context: AuthContext,
    ) -> None:
        """Raise the handler's forbidden error when a mutation is not allowed."""


class ProductRuntimePolicy:
    """Unchanged self-hosting behavior for the canonical product assembly."""

    def handle_public_get(self, handler: RequestContext, path_parts: list[str]) -> bool:
        return False

    def handle_public_post(self, handler: RequestContext, path_parts: list[str]) -> bool:
        return False

    def allow_product_auth(self) -> bool:
        return True

    def session_view(self, context: AuthContext) -> dict[str, Any]:
        return {}

    def authorize_mutation(
        self,
        handler: RequestContext,
        method: str,
        path_parts: list[str],
        context: AuthContext,
    ) -> None:
        return None
