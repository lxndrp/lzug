"""Pure route contract for the canonical Wiki and its public projection."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class WikiRoute:
    """All names derived from one extensionless flat Wiki page name."""

    page: str
    title: str
    publication_file: str
    publication_route: str


def wiki_route(page: str) -> WikiRoute:
    """Derive the public projection for an extensionless flat Wiki page name."""
    if not page or "/" in page or page.startswith("."):
        raise ValueError(f"Wiki page must be an extensionless flat page: {page}")

    is_home = page == "Home"
    slug = "index" if is_home else page.lower()
    return WikiRoute(
        page=page,
        title="Handbuch" if is_home else page,
        publication_file="_index.md" if is_home else f"{slug}.md",
        publication_route="/handbuch/" if is_home else f"/handbuch/{slug}/",
    )


def wiki_source_url(page: str, wiki_base_url: str) -> str:
    """Return the public canonical Wiki URL for a page."""
    route = wiki_route(page)
    base_url = wiki_base_url.rstrip("/")
    return base_url if route.page == "Home" else f"{base_url}/{quote(route.page)}"
