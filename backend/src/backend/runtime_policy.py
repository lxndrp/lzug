"""Runtime-specific HTTP policy extension points.

The product image ships only the neutral default policy from this module.
Alternative assemblies can provide routes and additional restrictions without
placing their implementation or configuration in the product image.
"""

from __future__ import annotations

from pathlib import Path
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

    def database_for_request(self, base_db_path: Path, session_token: str | None) -> Path:
        """Resolve the persistence boundary for one request."""

    def external_notifications_enabled(self) -> bool:
        """Return whether technical notification channels may be used."""

    def session_view(self, handler: RequestContext, context: AuthContext) -> dict[str, Any]:
        """Return assembly-specific, non-secret fields for ``GET /api/session``."""

    def discard_session(self, handler: RequestContext, session_token: str | None) -> None:
        """Discard assembly-owned state after an explicit logout."""

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

    def database_for_request(self, base_db_path: Path, session_token: str | None) -> Path:
        del session_token
        return base_db_path

    def external_notifications_enabled(self) -> bool:
        return True

    def session_view(self, handler: RequestContext, context: AuthContext) -> dict[str, Any]:
        del handler, context
        return {}

    def discard_session(self, handler: RequestContext, session_token: str | None) -> None:
        del handler, session_token

    def authorize_mutation(
        self,
        handler: RequestContext,
        method: str,
        path_parts: list[str],
        context: AuthContext,
    ) -> None:
        return None
