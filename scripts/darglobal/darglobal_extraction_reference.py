"""DarGlobal extraction reference implementation.

Reconstructed from the Colab workflow. Documentation/reproducibility only:
DO NOT run against the finalized dataset or website without authorization.

Requires: requests, beautifulsoup4, scikit-learn (optional for near-duplicate audit).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://darglobal.co.uk"
SITEMAP = f"{BASE}/sitemap.xml"
ROBOTS = f"{BASE}/robots.txt"
USER_AGENT = "DarGlobalDataReference/1.0"
CATEGORIES = ("blog", "press", "insights", "partners", "project_listings", "communities", "corporate", "developments")
CORPORATE_PATHS = {
    "", "about", "investor", "hospitality", "faq", "why-invest",
    "commercial", "luxury-golf-communities", "tokenization",
}
EXCLUDE_PATHS = {
    "broker-contest-terms-conditions", "privacy-policy", "terms-conditions",
    "contact", "register", "login",
}
ERROR_MARKERS = (
    "a client-side exception has occurred", "application error:",
    "_incapsula_resource", "access denied", "verify you are human",
    "captcha challenge", "this page cannot be found",
)


def discover_urls(session: requests.Session) -> list[str]:
    """Read sitemap URL locations; filtering is handled separately."""
    resp = session.get(SITEMAP, timeout=45)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "xml")
    urls = [tag.get_text(strip=True) for tag in soup.find_all("loc")]
    return list(dict.fromkeys(urls))


def categorize_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    segment = path.split("/", 1)[0].lower()
    if segment in ("blog", "press", "insights", "partners"):
        return segment
    if segment == "projects":
        return "project_listings"
    if segment in ("rayana", "amaya", "one-of-one"):
        return "communities"
    if path.lower() in CORPORATE_PATHS:
        return "corporate"
    return "developments"


def select_urls(urls: list[str]) -> list[str]:
    """Example filtering; compare with the supplied historical manifest."""
    robot = RobotFileParser()
    robot.set_url(ROBOTS)
    robot.read()
    selected = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.netloc.lower() != urlparse(BASE).netloc:
            continue
        path = parsed.path.strip("/").lower()
        if not path or path in EXCLUDE_PATHS or parsed.query:
            continue
        if robot.can_fetch(USER_AGENT, url):
            selected.append(url)
    return sorted(set(selected))


def fetch_markdown(session: requests.Session, url: str) -> dict:
    """Extract using Jina Reader's publicly documented URL interface."""
    resp = session.get(
        "https://r.jina.ai/" + url,
        headers={"Accept": "text/plain"},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.text
    title_match = re.search(r"(?m)^Title:\s*(.+)$", payload)
    title = title_match.group(1).strip() if title_match else urlparse(url).path.rsplit("/", 1)[-1]
    content = payload.split("Markdown Content:", 1)[-1].strip()
    # Remove standard inline image markdown but retain alt text.
    content = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return {"title": title, "url": url, "content": content}


def validate_document(document: dict, min_chars: int = 800) -> tuple[bool, str]:
    content = document["content"].strip()
    title = document["title"].lower()
    beginning = content[:1800].lower()
    if any(marker in title or marker in beginning for marker in ERROR_MARKERS):
        return False, "error or access page"
    if re.search(r"(?im)^#{1,5}\s*404\s*!?\s*$", beginning):
        return False, "404 page"
    if len(content) < min_chars:
        return False, "insufficient content (requires review)"
    return True, "ok"


def output_path(root: Path, url: str) -> Path:
    slug = urlparse(url).path.strip("/").replace("/", "-") or "home"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")[:110]
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    return root / categorize_url(url) / f"{slug}-{digest}.md"


def yaml_string(s: str) -> str:
    """JSON strings are valid YAML scalar strings."""
    return json.dumps(s, ensure_ascii=False)


def save_document(root: Path, document: dict) -> Path:
    path = output_path(root, document["url"])
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "---\n"
        f"title: {yaml_string(document['title'])}\n"
        f"source_url: {yaml_string(document['url'])}\n"
        f"source_type: {yaml_string(categorize_url(document['url']))}\n"
        f"scraped_at: {yaml_string(datetime.now(timezone.utc).isoformat())}\n"
        "---\n\n"
    )
    path.write_text(header + f"# {document['title']}\n\n" + document["content"] + "\n", encoding="utf-8")
    return path


def append_manifest(manifest: Path, record: dict) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    fields = ["url", "status", "file_path", "characters", "error", "attempted_at"]
    exists = manifest.exists() and manifest.stat().st_size > 0
    with manifest.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({key: record.get(key, "") for key in fields})


def scrape_batch(urls: list[str], root: Path, delay: float = 2.0) -> None:
    """Only run intentionally, respecting website and service permissions."""
    session = requests.Session()
    manifest = root / "manifest.csv"
    consecutive_failures = 0
    for url in urls:
        path = output_path(root, url)
        status, error, n_chars = "failed", "", 0
        if path.exists():
            status = "existing"
        else:
            try:
                document = fetch_markdown(session, url)
                n_chars = len(document["content"])
                valid, reason = validate_document(document)
                if valid:
                    save_document(root, document)
                    status = "success"
                else:
                    error = reason
            except requests.RequestException as exc:
                error = str(exc)
        append_manifest(manifest, {
            "url": url, "status": status, "file_path": str(path) if status != "failed" else "",
            "characters": n_chars, "error": error,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
        })
        print(status, url, error)
        if status == "failed":
            consecutive_failures += 1
            if any(x in error.lower() for x in ("403", "429", "access denied", "captcha")):
                print("Access restriction; stopping.")
                break
            if consecutive_failures >= 3:
                print("Three consecutive failures; stopping.")
                break
        else:
            consecutive_failures = 0
        time.sleep(delay)


def split_frontmatter(text: str) -> tuple[str, str]:
    match = re.match(r"\A(---\s*\n.*?\n---\s*\n)(.*)", text, re.DOTALL)
    return (match.group(1), match.group(2)) if match else ("", text)


def conservative_clean(text: str) -> str:
    """Preserve main information; do not truncate at forms that may precede project cards."""
    header, body = split_frontmatter(text)
    # Remove standalone image placeholders and generic navigation lines.
    body = re.sub(r"(?im)^\s*Image\s+\d+(?::[^\n]*)?\s*$", "", body)
    body = re.sub(r"(?im)^\s*English\s*\|\s*العربية\s*$", "", body)
    body = re.sub(r"(?im)^\s*\[Register Interest\]\([^\n]*\)\s*$", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return header + body.strip() + "\n"


def clean_corpus(raw_root: Path, final_root: Path) -> None:
    """Illustrative conservative cleaner, not a byte-for-byte recreation of Colab v2."""
    for source in raw_root.rglob("*.md"):
        destination = final_root / source.relative_to(raw_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(conservative_clean(source.read_text(encoding="utf-8")), encoding="utf-8")


def duplicate_audit(root: Path) -> dict:
    """Exact-body duplicates; optional TF-IDF near-duplicate analysis in Colab notes."""
    groups = defaultdict(list)
    for path in root.rglob("*.md"):
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
        canonical = re.sub(r"\s+", " ", body).lower().strip()
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        groups[digest].append(str(path))
    return {digest: paths for digest, paths in groups.items() if len(paths) > 1}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="Print local dataset counts only (no network)")
    parser.add_argument("--root", default="darglobal_data", help="Raw dataset directory")
    args = parser.parse_args()
    if not args.inspect:
        parser.error("This is a reference implementation. Use --inspect for local-only verification.")
    root = Path(args.root)
    print("Markdown files:", len(list(root.rglob("*.md"))))
    print("Exact duplicate groups:", len(duplicate_audit(root)))


if __name__ == "__main__":
    main()
