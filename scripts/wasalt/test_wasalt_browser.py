"""Extract one Wasalt property through one visible Chromium navigation."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


PROPERTY_TYPES = {
    "SingleFamilyResidence", "Residence", "Apartment", "House",
    "Accommodation", "ApartmentComplex", "RealEstateListing",
}


def records(value):
    """Visit JSON-LD objects, including lists and @graph containers."""
    if isinstance(value, list):
        for item in value:
            yield from records(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from records(item)


def property_score(record, url, listing_id, page_title):
    types = record.get("@type", [])
    if isinstance(types, str):
        types = [types]
    if not any(t.rsplit("/", 1)[-1] in PROPERTY_TYPES for t in types if isinstance(t, str)):
        return 0
    identities = [record.get(key) for key in ("url", "@id", "identifier")]
    for identity in identities:
        if isinstance(identity, str):
            path = urlsplit(identity).path.rstrip("/")
            if path == urlsplit(url).path or path.rsplit("-", 1)[-1] == listing_id:
                return 2
            if "/property/" in path:
                return 0
    # Wasalt's main property record may have no URL or identifier.
    name = record.get("name")
    if isinstance(name, str) and name.strip():
        name = " ".join(name.split()).casefold()
        title = " ".join(page_title.split()).casefold()
        if title == name or title.startswith(name + " "):
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="One Wasalt sale or long-term rental property URL")
    args = parser.parse_args()
    parsed_url = urlsplit(args.url)
    match = re.fullmatch(r"/en/property/(sale|rent)/[^/]+-(\d+)/?", parsed_url.path)
    if parsed_url.scheme != "https" or parsed_url.netloc != "wasalt.sa" or not match or parsed_url.query or parsed_url.fragment:
        parser.error("Expected one HTTPS Wasalt sale or rental listing URL")
    purpose, listing_id = match.groups()
    output = DATA_ROOT / "raw" / purpose / f"{listing_id}.json"
    if output.exists():
        parser.error(f"Output already exists; refusing to overwrite: {output}")
    result = {
        "status": None, "final_url": None, "title": None,
        "script_count": 0, "property": None,
    }
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            try:
                response = page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
                result["status"] = response.status if response else None
            except Exception as exc:
                errors.append(type(exc).__name__)
            result["final_url"] = page.url
            result["title"] = page.title()
            body = page.locator("body").inner_text(timeout=5000).lower()
            scripts = page.locator('script[type="application/ld+json"]').all_text_contents()
            result["script_count"] = len(scripts)
            blocked = result["status"] in (403, 429) or any(
                marker in result["title"].lower()
                for marker in ("just a moment", "attention required", "security verification")
            ) or any(marker in body for marker in (
                "verify you are human", "performing security verification",
                "enable javascript and cookies to continue", "checking your browser",
            )) or page.locator('#challenge-running, #challenge-form, iframe[src*="challenges.cloudflare.com"]').count() > 0
            if blocked:
                errors.append("Access blocked or challenge detected; no retry attempted")
            elif errors or result["status"] is None or not 200 <= result["status"] < 300:
                errors.append("Navigation did not complete successfully")
            elif urlsplit(result["final_url"]).path.rstrip("/") != parsed_url.path.rstrip("/"):
                errors.append("Redirected away from the requested listing")
            else:
                candidates = []
                for script in scripts:
                    try:
                        parsed = json.loads(script)
                    except (ValueError, TypeError):
                        errors.append("Invalid JSON-LD")
                        continue
                    for record in records(parsed):
                        score = property_score(record, args.url, listing_id, result["title"])
                        if score:
                            candidates.append((score, record))
                if candidates:
                    best_score = max(score for score, _ in candidates)
                    best = []
                    for score, record in candidates:
                        if score == best_score and record not in best:
                            best.append(record)
                    if len(best) == 1:
                        result["property"] = best[0]
                    else:
                        errors.append("Ambiguous main property records")
                else:
                    errors.append("Main property record not found")
        finally:
            browser.close()

    if result["property"] is not None and not errors:
        wrapper = {
            "source": "wasalt",
            "source_url": args.url,
            "listing_id": listing_id,
            "purpose": purpose,
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "json_ld": result["property"],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            json.dump(wrapper, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    prop = result["property"] or {}
    offers = prop.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    offer = next((item for item in offers if isinstance(item, dict)), {})
    address = prop.get("address") or {}
    if not isinstance(address, dict):
        address = {}
    print("HTTP status:", result["status"] if result["status"] is not None else "Unavailable")
    print("Property title:", prop.get("name") or "Unavailable")
    print("Listing ID:", listing_id)
    print("Purpose:", purpose)
    price = offer.get("price")
    print("Price:", f"{price} {offer.get('priceCurrency', '')}".strip() if price is not None else "Unavailable")
    print("City:", address.get("addressLocality") or "Unavailable")
    print("Bedrooms:", prop.get("numberOfBedrooms", "Unavailable"))
    if "numberOfBathroomsTotal" in prop:
        print("Bathrooms:", prop["numberOfBathroomsTotal"])
    print("Output file path:", str(output) if output.exists() else "Not saved")
    if errors:
        print("Errors: " + ", ".join(errors), file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
