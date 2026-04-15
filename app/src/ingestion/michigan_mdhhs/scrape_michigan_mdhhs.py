# /// script
# dependencies = [
#   "install-playwright",
#   "playwright",
# ]
# ///
# (This comment enables `uv run` to automatically create a virtual environment)

"""
Playwright-based pre-scraper for michigan.gov/mdhhs.

michigan.gov uses a WAF that blocks non-browser HTTP clients (returns 403).
This script uses a real Chromium browser to crawl assistance-programs pages,
saving rendered HTML locally for the Scrapy spider to process.

Usage:
    uv run --no-project scrape_michigan_mdhhs.py
    # or: pip install install-playwright playwright && python scrape_michigan_mdhhs.py
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from install_playwright import install
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.michigan.gov"
SEED_URLS = [
    "/mdhhs/assistance-programs",
    "/mdhhs/assistance-programs/cash",
    "/mdhhs/assistance-programs/food",
    "/mdhhs/assistance-programs/medicaid",
    "/mdhhs/assistance-programs/wic",
    "/mdhhs/assistance-programs/child-care-assistance",
    "/mdhhs/assistance-programs/healthcare",
    "/mdhhs/assistance-programs/emergency-relief",
    "/mdhhs/assistance-programs/housing-and-homeless-services",
    "/mdhhs/assistance-programs/cshcs",
    "/mdhhs/assistance-programs/other-help",
    "/mdhhs/assistance-programs/migrant-services",
    "/mdhhs/assistance-programs/refugee",
    "/mdhhs/assistance-programs/universal-caseload-action-plan",
    "/mdhhs/assistance-programs/benefit-updates",
    "/mdhhs/doing-business/ebt",
]

ALLOW_PATTERNS = [
    re.compile(r"/mdhhs/assistance-programs/"),
    re.compile(r"/mdhhs/doing-business/ebt"),
]

DENY_PATTERNS = [
    re.compile(r"/news"),
    re.compile(r"press-release"),
    re.compile(r"-/media/"),
    re.compile(r"/faq/"),
    re.compile(r"/inside-mdhhs/"),
    re.compile(r"/keeping-michigan-healthy/"),
    re.compile(r"/safety-injury-prev/"),
    re.compile(r"/adult-child-serv/"),
    # Administrative/archival content not useful for caseworkers
    re.compile(r"/lhd-links/"),       # Local health dept admin links (CSHCS)
    re.compile(r"/lhd-info-emails/"), # Archived info emails (CSHCS)
    re.compile(r"/past-alerts/"),     # Historical alert email archives
    re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip)$", re.IGNORECASE),
]

MAX_DEPTH = 4
DELAY_SECONDS = 0.5

OUTPUT_DIR = Path(__file__).parent / "pages"
MAPPING_FILE = Path(__file__).parent / "url_mapping.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def url_to_filename(url: str) -> str:
    """Convert a URL path to a safe filename."""
    parsed = urlparse(url)
    slug = parsed.path.strip("/").replace("/", "__") or "index"
    return f"{slug}.html"


def should_crawl(url: str) -> bool:
    """Check if a URL matches allow patterns and doesn't match deny patterns."""
    parsed = urlparse(url)
    path = parsed.path

    if parsed.netloc and parsed.netloc != "www.michigan.gov":
        return False

    if any(pattern.search(path) for pattern in DENY_PATTERNS):
        return False

    return any(pattern.search(path) for pattern in ALLOW_PATTERNS)


def normalize_url(url: str) -> str:
    """Strip fragments and trailing slashes for dedup."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def extract_links(page) -> list[str]:
    """Extract all internal links from the current page."""
    links = page.eval_on_selector_all(
        "a[href]",
        "elements => elements.map(el => el.href)"
    )
    results = []
    for href in links:
        if not href:
            continue
        absolute = urljoin(BASE_URL, href)
        normalized = normalize_url(absolute)
        if should_crawl(normalized):
            results.append(normalized)
    return results


# ---------------------------------------------------------------------------
# Main crawl
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    p = sync_playwright().start()
    install([p.chromium])
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    # BFS queue: (url, depth)
    queue: list[tuple[str, int]] = [
        (normalize_url(f"{BASE_URL}{path}"), 0) for path in SEED_URLS
    ]
    visited: set[str] = set()
    url_mapping: dict[str, str] = {}  # filename -> original URL

    print(f"Starting crawl with {len(queue)} seed URLs")

    while queue:
        url, depth = queue.pop(0)

        if url in visited:
            continue
        visited.add(url)

        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if not response or response.status >= 400:
                print(f"  SKIP {url} (status {response.status if response else 'no response'})")
                continue

            # Wait a moment for any dynamic content to render
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as exc:
            print(f"  ERROR {url}: {exc}")
            continue

        # Save rendered HTML
        filename = url_to_filename(url)
        html_content = page.content()
        (OUTPUT_DIR / filename).write_text(html_content, encoding="utf-8")
        url_mapping[filename] = url

        print(f"  [{len(url_mapping):3d}] depth={depth} {url} -> {filename}")

        # Discover links if we haven't hit max depth
        if depth < MAX_DEPTH:
            for link in extract_links(page):
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(DELAY_SECONDS)

    # Write URL mapping
    MAPPING_FILE.write_text(json.dumps(url_mapping, indent=2), encoding="utf-8")

    browser.close()
    p.stop()

    print(f"\nDone. Saved {len(url_mapping)} pages to {OUTPUT_DIR}")
    print(f"URL mapping: {MAPPING_FILE}")


if __name__ == "__main__":
    main()
