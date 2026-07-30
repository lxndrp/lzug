#!/usr/bin/env python3
"""Check that published Wiki pages resolve to rendered HTML pages."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, new_url):
        raise HTTPError(request.full_url, code, msg, headers, None)


def check_page(opener, base_url: str, page_name: str) -> list[str]:
    url = urljoin(base_url.rstrip("/") + "/", quote(page_name))
    request = Request(url, headers={"User-Agent": "lzug-wiki-post-publish-check"})
    try:
        response = opener.open(request, timeout=20)
    except HTTPError as error:
        location = error.headers.get("Location", "")
        if "raw.githubusercontent.com" in location:
            return [f"{page_name}: redirects to raw.githubusercontent.com ({location})"]
        return [f"{page_name}: expected HTTP 200, got {error.code} ({url})"]
    status = getattr(response, "status", response.getcode())
    content_type = response.headers.get_content_type()
    errors = []
    if status != 200:
        errors.append(f"{page_name}: expected HTTP 200, got {status}")
    if content_type != "text/html":
        errors.append(f"{page_name}: expected Content-Type text/html, got {content_type}")
    final_url = response.geturl()
    if "raw.githubusercontent.com" in final_url:
        errors.append(f"{page_name}: rendered page resolved to raw content ({final_url})")
    response.close()
    return errors


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_wiki_http.py WIKI_ROOT WIKI_BASE_URL")
        return 2
    wiki_root = Path(sys.argv[1]).resolve()
    base_url = sys.argv[2]
    if not wiki_root.is_dir():
        print(f"wiki: directory does not exist: {wiki_root}")
        return 1
    pages = sorted(
        path.stem for path in wiki_root.glob("*.md") if path.stem != "_Sidebar"
    )
    if not pages:
        print("wiki: no flat Markdown pages found")
        return 1
    opener = build_opener(RejectRedirects)
    errors = [error for page in pages for error in check_page(opener, base_url, page)]
    if errors:
        print("\n".join(errors))
        return 1
    print(f"wiki HTTP policy: ok ({len(pages)} rendered pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
