
"""
SEnSRS website crawler and text extractor.

- Discovers public same-domain pages from seeds, links and sitemaps.
- Uses Playwright when requests returns insufficient page text.
- Preserves form labels, options and instructions without submitting forms.
- Detects rendered 404 pages and records unresolved URLs.
- Excludes PDFs and other static assets from text extraction.
- Generates reports/page_manifest.json and reports/crawl_report.csv.

Run:
    python backend/sensrs_website_crawler.py
    python backend/sensrs_website_crawler.py --max-pages 500
"""

import argparse
import csv
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

DOMAIN = "sensrs.com"
USER_AGENT = "SEnSRS-AI-Bot-WebsiteAudit/1.0"
TIMEOUT = 25
REQUEST_DELAY_SECONDS = 0.5
MIN_USEFUL_CHARS = 180

SEED_URLS = [
    "https://sensrs.com/",
    "https://sensrs.com/about/",
    "https://sensrs.com/about-us/",
    "https://sensrs.com/visionandmission/",
    "https://sensrs.com/people/",
    "https://sensrs.com/project-staff/",
    "https://sensrs.com/policy/",
    "https://sensrs.com/projects/",
    "https://sensrs.com/publications/",
    "https://sensrs.com/internship/",
    "https://sensrs.com/phd-programme/",
    "https://sensrs.com/opportunities/",
    "https://sensrs.com/opportunities/apply/",
    "https://sensrs.com/opportunities/apply-project-staff/",
    "https://sensrs.com/appointment/",
    "https://sensrs.com/consultancy-services/",
    "https://sensrs.com/consultancy-services/drone-services/",
    "https://sensrs.com/consultancy-services/dgps-service/",
    "https://sensrs.com/consultancy-services/bathymetry-survey/",
    "https://sensrs.com/consultancy-services/web-development/",
    "https://sensrs.com/consultancy-services/dashboards-analytics/",
    "https://sensrs.com/consultancy-services/app-development/",
    "https://sensrs.com/consultancy-services/ip-services/",
    "https://sensrs.com/consultancy-services/tls-survey/",
    "https://sensrs.com/consultancy-services/hyperspectral-sensor/",
    "https://sensrs.com/events/",
    "https://sensrs.com/events/current/",
    "https://sensrs.com/events/past/",
    "https://sensrs.com/gallery/",
    "https://sensrs.com/video-gallery/",
    "https://sensrs.com/outreach/",
    "https://sensrs.com/press-and-news/",
    "https://sensrs.com/newsletter/",
    "https://sensrs.com/contact/",
    "https://sensrs.com/consortium/",
    "https://sensrs.com/geoai-summit/",
]

EXCLUDED_PATH_PARTS = (
    "/wp-admin", "/wp-login", "/wp-json", "/xmlrpc.php",
    "/cart", "/checkout", "/my-account", "/login", "/logout",
    "/search", "/feed", "/comments/feed",
)

ASSET_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mov", ".mp3", ".wav", ".zip", ".rar", ".7z",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf",
}

SITEMAP_CANDIDATES = [
    "https://sensrs.com/sitemap.xml",
    "https://sensrs.com/sitemap_index.xml",
    "https://sensrs.com/wp-sitemap.xml",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

MANIFEST_PATH = REPORT_DIR / "page_manifest.json"
CSV_PATH = REPORT_DIR / "crawl_report.csv"


def canonicalize(url):
    """Normalize a URL and restrict it to the SEnSRS domain."""
    if not url:
        return None

    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    if host not in (DOMAIN, "www." + DOMAIN):
        return None

    if parsed.username or parsed.password:
        return None

    path = re.sub(r"/{2,}", "/", parsed.path or "/")

    if path != "/" and not path.endswith("/") and not Path(path).suffix:
        path += "/"

    return urlunparse(("https", DOMAIN, path, "", "", ""))


def is_excluded(url):
    parsed = urlparse(url)
    path = parsed.path.lower()

    if any(part in path for part in EXCLUDED_PATH_PARTS):
        return True

    return Path(path).suffix.lower() in ASSET_EXTENSIONS


def allowed_by_robots(url, robots):
    try:
        return robots.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def fetch(url):
    time.sleep(REQUEST_DELAY_SECONDS)
    return SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)


def discover_sitemaps(robots):
    found = set()
    robots_url = "https://sensrs.com/robots.txt"

    try:
        response = SESSION.get(robots_url, timeout=TIMEOUT)

        if response.ok:
            for line in response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    found.add(line.split(":", 1)[1].strip())

            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            robots = parser

    except Exception as exc:
        print(f"[WARN] Could not read robots.txt: {exc}")

    found.update(SITEMAP_CANDIDATES)
    return found, robots


def parse_sitemap(url, seen=None, depth=0):
    if seen is None:
        seen = set()

    if url in seen or depth > 4:
        return set()

    seen.add(url)
    urls = set()

    try:
        response = SESSION.get(url, timeout=TIMEOUT)

        if not response.ok:
            return urls

        root = ET.fromstring(response.content)

        for element in root.iter():
            if element.tag.split("}")[-1].lower() != "loc":
                continue

            if not element.text:
                continue

            loc = element.text.strip()
            loc_path = urlparse(loc).path.lower()

            if "sitemap" in loc_path or loc.lower().endswith(".xml"):
                urls.update(parse_sitemap(loc, seen, depth + 1))
            else:
                normalized = canonicalize(loc)

                if normalized and not is_excluded(normalized):
                    urls.add(normalized)

    except Exception as exc:
        print(f"[WARN] Sitemap failed {url}: {exc}")

    return urls


def extract_text(soup):
    """Extract the most complete useful content without deleting forms."""
    for element in soup([
        "script", "style", "noscript", "svg",
        "iframe", "template"
    ]):
        element.decompose()

    for element in soup.find_all(["nav", "header", "footer", "aside"]):
        element.decompose()

    # Keep form elements so public application labels/options are retained.
    # Never read input values or submit forms.
    for element in soup.find_all(["input", "textarea"]):
        element.replace_with(" ")

    for element in soup.find_all("select"):
        options = [
            option.get_text(" ", strip=True)
            for option in element.find_all("option")
        ]
        element.replace_with(" " + " ".join(options) + " ")

    candidates = []

    selectors = [
        ("main", {}),
        ("article", {}),
        ("div", {"id": re.compile(r"content|main", re.I)}),
        ("div", {"class": re.compile(
            r"elementor|site-content|entry-content|post-content|"
            r"page-content|content-area|wp-block-post-content", re.I
        )}),
        ("section", {}),
        ("body", {}),
    ]

    for tag, attrs in selectors:
        for element in soup.find_all(tag, attrs=attrs):
            text = element.get_text("\n", strip=True)
            if text:
                candidates.append(text)

    raw = max(candidates, key=len) if candidates else soup.get_text("\n", strip=True)

    lines = []
    previous_blank = False

    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            if lines and not previous_blank:
                lines.append("")
            previous_blank = True
            continue

        lines.append(line)
        previous_blank = False

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def page_text_and_links(html, current_url):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    links = set()
    for anchor in soup.find_all("a", href=True):
        absolute = canonicalize(urljoin(current_url, anchor["href"]))
        if absolute and not is_excluded(absolute):
            links.add(absolute)

    text = extract_text(soup)
    return title, text, links


def is_rendered_404(title, text):
    """Detect common 404 pages even when the HTTP status is 200."""
    title_text = (title or "").strip().lower()
    body = (text or "").strip().lower()
    compact = re.sub(r"\s+", " ", body)

    if title_text in {"404", "404: this page could not be found"}:
        return True

    if compact.startswith("404 this page could not be found"):
        return True

    if len(compact) < 250 and (
        "page not found" in compact or "404 not found" in compact
    ):
        return True

    return False


def safe_filename(url):
    path = urlparse(url).path.strip("/")
    slug = path.replace("/", "__") or "home"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", slug).strip("_").lower()
    slug = (slug or "page")[:100]
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{digest}.txt"


def render_with_playwright(url, browser):
    """Render JavaScript pages and return title, text, links, final URL."""
    page = browser.new_page(
        user_agent=USER_AGENT,
        viewport={"width": 1365, "height": 900},
    )

    try:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000,
        )

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(1200)

        final_url = canonicalize(page.url) or page.url
        title = page.title()
        html = page.content()
        title_from_html, text, links = page_text_and_links(html, final_url)

        if not title:
            title = title_from_html

        status = response.status if response else "NO_RESPONSE"

        return {
            "title": title,
            "text": text,
            "links": links,
            "final_url": final_url,
            "status": status,
        }

    finally:
        page.close()


def save_page(url, title, text, status, notes=""):
    filename = safe_filename(url)
    file_path = DATA_DIR / filename

    file_path.write_text(
        f"PAGE_TITLE: {title}\nPAGE_URL: {url}\n\n{text}\n",
        encoding="utf-8",
    )

    manifest_entry = {
        "file": filename,
        "title": title or urlparse(url).path.strip("/") or "SEnSRS Home",
        "url": url,
        "status": status,
        "characters": len(text),
        "notes": notes,
    }

    return manifest_entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-pages", type=int, default=500,
        help="Maximum URLs to visit (default: 500)",
    )
    parser.add_argument(
        "--no-robots", action="store_true",
        help="Ignore robots.txt restrictions (not recommended)",
    )
    args = parser.parse_args()

    robots = RobotFileParser()
    robots.set_url("https://sensrs.com/robots.txt")
    sitemap_urls, robots = discover_sitemaps(robots)

    sitemap_pages = set()
    for sitemap in sorted(sitemap_urls):
        sitemap_pages.update(parse_sitemap(sitemap))

    queue = deque()
    queued = set()

    for url in [*SEED_URLS, *sorted(sitemap_pages)]:
        normalized = canonicalize(url)
        if normalized and not is_excluded(normalized) and normalized not in queued:
            queue.append(normalized)
            queued.add(normalized)

    visited = set()
    discovered = set(queued)
    manifest = []
    rows = []

    print(f"Seeds: {len(SEED_URLS)}")
    print(f"Sitemap URLs discovered: {len(sitemap_pages)}")
    print(f"Starting crawl; maximum URLs: {args.max_pages}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        try:
            while queue and len(visited) < args.max_pages:
                url = queue.popleft()

                if url in visited:
                    continue

                visited.add(url)

                if not args.no_robots and not allowed_by_robots(url, robots):
                    rows.append({
                        "url": url, "final_url": "", "status": "BLOCKED_BY_ROBOTS",
                        "title": "", "characters": 0, "file": "",
                        "notes": "Skipped per robots.txt",
                    })
                    print(f"[ROBOTS] {url}")
                    continue

                try:
                    response = fetch(url)
                    final_url = canonicalize(response.url) or response.url
                    content_type = response.headers.get("Content-Type", "").lower()
                    status_code = response.status_code

                    if status_code >= 400:
                        rows.append({
                            "url": url, "final_url": final_url, "status": status_code,
                            "title": "", "characters": 0, "file": "",
                            "notes": "HTTP error; not saved",
                        })
                        print(f"[HTTP {status_code}] {url}")
                        continue

                    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                        rows.append({
                            "url": url, "final_url": final_url, "status": status_code,
                            "title": "", "characters": 0, "file": "",
                            "notes": f"Non-HTML content excluded: {content_type}",
                        })
                        continue

                    title, text, links = page_text_and_links(response.text, final_url)
                    render_status = status_code

                    # Retry low-text pages using a real browser.
                    if len(text) < MIN_USEFUL_CHARS:
                        print(f"[BROWSER RETRY] {url}")
                        try:
                            rendered = render_with_playwright(url, browser)
                            title = rendered["title"] or title
                            text = rendered["text"] or text
                            links.update(rendered["links"])
                            final_url = rendered["final_url"] or final_url
                            render_status = rendered["status"]
                        except Exception as exc:
                            print(f"[BROWSER ERROR] {url}: {exc}")

                    discovered.update(links)

                    for link in sorted(links):
                        if link not in queued and link not in visited:
                            queue.append(link)
                            queued.add(link)

                    if is_rendered_404(title, text):
                        rows.append({
                            "url": url, "final_url": final_url,
                            "status": "RENDERED_404", "title": title,
                            "characters": len(text), "file": "",
                            "notes": "Rendered page appears to be a 404; not saved",
                        })
                        print(f"[404 PAGE] {url}")
                        continue

                    notes = ""
                    if len(text) < MIN_USEFUL_CHARS:
                        notes = "LOW_TEXT: inspect manually; may be empty or blocked"
                    if final_url != url:
                        notes = (notes + "; " if notes else "") + "redirected"

                    entry = save_page(final_url, title, text, render_status, notes)
                    manifest.append(entry)

                    rows.append({
                        "url": url,
                        "final_url": final_url,
                        "status": render_status,
                        "title": title,
                        "characters": len(text),
                        "file": entry["file"],
                        "notes": notes,
                    })

                    print(
                        f"[{render_status}] {len(text):>6} chars | "
                        f"{title[:45]} | {final_url}"
                    )

                except requests.RequestException as exc:
                    rows.append({
                        "url": url, "final_url": "", "status": "REQUEST_ERROR",
                        "title": "", "characters": 0, "file": "",
                        "notes": str(exc)[:250],
                    })
                    print(f"[REQUEST ERROR] {url}: {exc}")

                except Exception as exc:
                    rows.append({
                        "url": url, "final_url": "", "status": "CRAWL_ERROR",
                        "title": "", "characters": 0, "file": "",
                        "notes": str(exc)[:250],
                    })
                    print(f"[CRAWL ERROR] {url}: {exc}")

        finally:
            browser.close()

    # Record queued/discovered pages that the limit prevented us from visiting.
    recorded_urls = {row["url"] for row in rows}
    for url in sorted(discovered - visited):
        if url not in recorded_urls:
            rows.append({
                "url": url, "final_url": "", "status": "NOT_VISITED",
                "title": "", "characters": 0, "file": "",
                "notes": "Discovered but not crawled; increase --max-pages if appropriate",
            })

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "url", "final_url", "status", "title",
                "characters", "file", "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts = {}
    for row in rows:
        key = str(row["status"])
        counts[key] = counts.get(key, 0) + 1

    print("\n========== CRAWL SUMMARY ==========")
    print(f"Visited URLs: {len(visited)}")
    print(f"Pages saved in manifest: {len(manifest)}")
    print(f"Discovered URLs: {len(discovered)}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"CSV report: {CSV_PATH}")
    print("Status counts:")

    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")

    print("\nReview LOW_TEXT, RENDERED_404, errors, blocked pages,")
    print("non-HTML documents and NOT_VISITED rows before ingestion.")


if __name__ == "__main__":
    main()
