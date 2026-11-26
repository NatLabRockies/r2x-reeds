"""Check built navigation, fragment targets and responsive API menu structure."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "_build"


class Page(HTMLParser):
    """Collect actual link targets and IDs from a built page."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.sidebar_button = False
        self.feed(path.read_text())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if identifier := attributes.get("id"):
            self.ids.add(identifier)
        if tag == "a" and (href := attributes.get("href")):
            self.links.append(href)
        if tag == "button" and attributes.get("popovertarget") == "starlight__sidebar":
            self.sidebar_button = True


def validate() -> None:
    """Require all local page/member links to resolve after the production build."""
    pages = {path: Page(path) for path in BUILD.rglob("*.html")}
    assert pages, "Build the site before checking links"
    checked = 0
    fragments = json.loads((ROOT / "public/api-fragments.json").read_text())
    links = [(path, target) for path, page in pages.items() for target in page.links]
    links.extend((ROOT / "public/api-fragments.json", target) for target in fragments.values())
    for origin, target in links:
        url = urlsplit(target)
        if url.scheme or url.netloc:
            continue
        if not url.path and url.fragment and origin in pages:
            destination = origin
        elif url.path.startswith("/r2x-reeds/"):
            destination = BUILD / url.path.removeprefix("/r2x-reeds/")
        else:
            continue
        if destination.is_dir():
            destination /= "index.html"
        assert destination.is_file(), (origin, target)
        if url.fragment and destination in pages:
            assert unquote(url.fragment) in pages[destination].ids, (origin, target)
        checked += 1
    api = pages[BUILD / "reference/api/reedsconfig/index.html"]
    assert api.sidebar_button and "starlight__sidebar" in api.ids
    assert "solve_year" in api.ids
    edit_prefix = "https://github.com/NatLabRockies/r2x-reeds/edit/"
    generated_pages = {
        path: page
        for path, page in pages.items()
        if path.relative_to(BUILD).parts[:2] == ("reference", "api")
    }
    assert generated_pages
    for path, page in generated_pages.items():
        assert not any(link.startswith(edit_prefix) for link in page.links), path
    authored_api = pages[BUILD / "reference/python-api/index.html"]
    assert any(link.startswith(edit_prefix) for link in authored_api.links)
    assert "/r2x-reeds/changelog/" in (BUILD / "versions/index.html").read_text()
    for legacy in (ROOT / "public").rglob("*.html"):
        if "Page moved" in legacy.read_text():
            assert "legacy-redirect.js" in legacy.read_text(), legacy
            assert "<noscript>" in legacy.read_text(), legacy
    print(
        f"Checked {len(pages)} HTML pages, {checked} internal links/anchors, API bookmarks and mobile sidebar access"
    )


if __name__ == "__main__":
    validate()
