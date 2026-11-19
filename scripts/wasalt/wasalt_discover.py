"""Download only two Wasalt detail sitemaps and inventory every loc entry."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import requests


ENDPOINTS = (
    "https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz",
    "https://cdn.wasalt.sa/sitemap/rental_pdp_sitemap_en_sa.xml.gz",
)
ROOT = DATA_ROOT
COLUMNS = ("source", "listing_id", "source_url", "purpose", "sitemap_source", "discovered_at")
EARLIER = {"sale": 45898, "rent": 14102, "daily_rental": 2666, "total_unique": 62666}


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class NoDTD(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError("DTD declarations are not allowed")


def parse_sitemap(payload):
    layers = 0
    while payload.startswith(b"\x1f\x8b"):
        if layers == 3:
            raise ValueError("Unexpected nested compression")
        payload = gzip.decompress(payload)
        layers += 1
    root = ET.fromstring(payload, parser=ET.XMLParser(target=NoDTD()))
    local = lambda tag: tag.rsplit("}", 1)[-1]
    if local(root.tag) != "urlset":
        raise ValueError("Expected urlset; will not follow sitemap indexes")
    urls = [(node.text or "").strip() for node in root.iter() if local(node.tag) == "loc"]
    issues = []
    for index, node in enumerate(root, 1):
        if local(node.tag) != "url":
            issues.append({"entry": index, "reason": "unexpected_root_child", "tag": node.tag})
        else:
            count = sum(local(child.tag) == "loc" for child in node)
            if count != 1:
                issues.append({"entry": index, "reason": "unexpected_loc_count", "count": count})
    if not urls:
        raise ValueError("Sitemap has no loc elements")
    return urls, layers, issues


def classify_url(raw):
    issues = []
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return raw, "other", "", ["malformed_url"]
    if not raw or re.search(r"\s", raw) or parts.scheme not in ("http", "https") or not parts.hostname:
        return raw, "other", "", ["malformed_url"]
    host = parts.hostname.lower()
    authority = host if port in (None, 443 if parts.scheme == "https" else 80) else f"{host}:{port}"
    if parts.username is not None or parts.password is not None:
        issues.append("unexpected_url_credentials")
        authority = parts.netloc
    path = parts.path.rstrip("/") or "/"
    canonical = urlunsplit((parts.scheme.lower(), authority, path, urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True))), ""))
    if host != "wasalt.sa" or parts.scheme != "https" or port not in (None, 443):
        issues.append("unexpected_host_scheme_or_port")
    if parts.query:
        issues.append("unexpected_query")
    if parts.fragment:
        issues.append("unexpected_fragment")
    match = re.fullmatch(r"/en/property/(sale|rent)/([^/]+)", path)
    daily = re.fullmatch(r"/en/dailyrental/([^/]+)", path)
    if match:
        purpose, slug = match.groups()
    elif daily:
        purpose, slug = "daily_rental", daily.group(1)
    else:
        purpose, slug = "other", path.rsplit("/", 1)[-1]
        issues.append("unexpected_path")
    identifier = re.search(r"(?:^|-)(\d+)$", slug)
    listing_id = identifier.group(1) if identifier else ""
    if not listing_id:
        issues.append("missing_listing_id")
    return canonical, purpose, listing_id, issues


def build_inventory(downloads):
    inventory = {}
    sitemap_reports = []
    anomalies = []
    for download in downloads:
        locations, layers, xml_issues = parse_sitemap(download["payload"])
        canonical_in_sitemap = []
        category_counts = Counter()
        for position, location in enumerate(locations, 1):
            canonical, purpose, listing_id, issues = classify_url(location)
            canonical_in_sitemap.append(canonical)
            category_counts[purpose] += 1
            if issues:
                anomalies.append({"sitemap_source": download["url"], "position": position, "source_url": location, "issues": issues})
            if canonical not in inventory:
                inventory[canonical] = {
                    "source": "wasalt", "listing_id": listing_id, "source_url": canonical,
                    "purpose": purpose, "sitemap_source": [download["url"]],
                    "discovered_at": download["downloaded_at"],
                }
            elif download["url"] not in inventory[canonical]["sitemap_source"]:
                inventory[canonical]["sitemap_source"].append(download["url"])
        sitemap_reports.append({
            **{k: v for k, v in download.items() if k != "payload"},
            "gzip_layers": layers, "loc_entries": len(locations),
            "unique_canonical_urls": len(set(canonical_in_sitemap)),
            "duplicate_url_entries": len(locations) - len(set(canonical_in_sitemap)),
            "entry_category_counts": dict(category_counts), "xml_issues": xml_issues,
        })
    counts = Counter(record["purpose"] for record in inventory.values())
    id_groups = defaultdict(list)
    missing = []
    for record in inventory.values():
        if record["listing_id"]:
            id_groups[(record["purpose"], record["listing_id"])].append(record["source_url"])
        else:
            missing.append(record["source_url"])
    collisions = [{"purpose": key[0], "listing_id": key[1], "urls": urls} for key, urls in sorted(id_groups.items()) if len(urls) > 1]
    # A city/district name is not inferred from property type, measurements, or
    # numeric IDs. Retain all slug shapes for an auditable location assessment.
    shapes = Counter()
    location_candidates = []
    for record in inventory.values():
        slug = urlsplit(record["source_url"]).path.rsplit("/", 1)[-1]
        shape = re.sub(r"\d+(?:\.\d+)?", "{number}", slug)
        shapes[shape] += 1
        if re.search(r"(?:^|-)(?:in|city|district|riyadh|jeddah|makkah|dammam|khobar)(?:-|$)", slug, re.I):
            location_candidates.append(record["source_url"])
    report = {
        "generated_at": timestamp(), "sitemaps": sitemap_reports,
        "total_loc_entries": sum(s["loc_entries"] for s in sitemap_reports),
        "total_unique_urls": len(inventory),
        "duplicate_url_entries": sum(s["loc_entries"] for s in sitemap_reports) - len(inventory),
        "category_counts": {key: counts[key] for key in ("sale", "rent", "daily_rental", "other")},
        "missing_listing_ids": {"count": len(missing), "urls": missing},
        "duplicate_id_collisions": collisions,
        "duplicate_id_collision_groups": len(collisions),
        "duplicate_id_excess_urls": sum(len(c["urls"]) - 1 for c in collisions),
        "malformed_or_unexpected_entries": anomalies,
        "earlier_observations": EARLIER,
        "differences_from_earlier": {**{key: counts[key] - EARLIER[key] for key in ("sale", "rent", "daily_rental")}, "total_unique": len(inventory) - EARLIER["total_unique"]},
        "location_assessment": {
            "url_slug_shapes": dict(sorted(shapes.items())),
            "potential_location_url_count": len(location_candidates),
            "potential_location_urls": location_candidates,
            "note": "No city/district classifications assigned. Candidate markers and complete slug shapes are provided for inspection; matching a marker is not a verified location.",
        },
    }
    return list(inventory.values()), report


def main():
    inventory_path = ROOT / "discovered_urls.csv"
    report_path = ROOT / "discovery_report.json"
    targets = [ROOT / "sitemaps" / url.rsplit("/", 1)[-1] for url in ENDPOINTS]
    for path in [inventory_path, report_path, *targets]:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    downloads = []
    with requests.Session() as session:
        session.headers.update({"Accept-Encoding": "identity"})
        for url, target in zip(ENDPOINTS, targets):
            with session.get(url, timeout=(15, 90), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Sitemap HTTP {response.status_code}: {url}; no retries")
                payload = response.raw.read(decode_content=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(payload)
                downloads.append({
                    "url": url, "downloaded_at": timestamp(), "local_path": str(target.relative_to(REPO_ROOT)),
                    "http_status": response.status_code, "content_type": response.headers.get("Content-Type"),
                    "content_encoding": response.headers.get("Content-Encoding"),
                    "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "payload": payload,
                })
    rows, report = build_inventory(downloads)
    ROOT.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for record in rows:
            writer.writerow({**record, "sitemap_source": ";".join(record["sitemap_source"])})
    with report_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: report[key] for key in ("total_loc_entries", "total_unique_urls", "duplicate_url_entries", "category_counts", "duplicate_id_collision_groups", "differences_from_earlier")}, indent=2))
    print(f"Missing IDs: {report['missing_listing_ids']['count']}")
    print(f"Anomalous entries: {len(report['malformed_or_unexpected_entries'])}")
    print(f"Inventory: {inventory_path}\nReport: {report_path}")


if __name__ == "__main__":
    main()
