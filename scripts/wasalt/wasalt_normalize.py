"""Offline normalization of a single Wasalt JSON-LD wrapper; no acquisition."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


TYPES = {
    "apartment": "apartment", "villa": "villa", "land": "land",
    "house": "house", "studio": "studio", "office": "office",
    "building": "building", "floor": "floor", "شقة": "apartment", "فيلا": "villa",
    "أرض": "land", "rest house": "rest_house", "room": "room",
    "chalet": "chalet", "duplex": "duplex",
}
PERIODS = {
    "year": "year", "yearly": "year", "annual": "year", "annually": "year",
    "month": "month", "monthly": "month", "week": "week", "weekly": "week",
    "day": "day", "daily": "day", "night": "night", "nightly": "night",
    "سنة": "year",
}
PHONE = re.compile(
    r"(?<!\w)(?:\+|00)?\d(?:[\d ()\-\u200e\u200f]*\d)?(?!\w)"
)


def numeric(value):
    """Accept finite numeric values and clearly formatted numeric strings only."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", value):
            return None
        value = value.replace(",", "")
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number) if number.is_integer() else number


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def clean_description(description):
    if not isinstance(description, str):
        return None
    soup = BeautifulSoup(description, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all("a", href=True):
        if re.search(r"^(?:tel:|mailto:)|(?:wa\.me|whatsapp\.com|t\.me|instagram\.com|snapchat\.com|facebook\.com)/", tag["href"], re.I):
            tag.replace_with("[contact removed]")
    for tag in soup.find_all("br"):
        tag.replace_with("\n")
    for tag in soup.find_all(["p", "div", "li", "section", "article", "h1", "h2", "h3"]):
        tag.insert_before("\n\n")
        tag.insert_after("\n\n")
    result = soup.get_text()
    # Separate Saudi contacts first: the general numeric matcher can otherwise
    # consume two phone numbers separated by a hyphen as one long number.
    scan = "".join(str(int(c)) if c.isdecimal() else c for c in result)
    saudi_pattern = r"(?<!\w)(?:(?:\+|00)?966[ ()-]*[15]|0[ ()-]*[15])(?:[ ()-]*\d){8}(?!\w)"
    for match in reversed(list(re.finditer(saudi_pattern, scan))):
        result = result[:match.start()] + "[phone removed]" + result[match.end():]

    def redact(match):
        candidate = match.group()
        digits = "".join(str(int(c)) for c in candidate if c.isdecimal())
        # Do not mistake long prices for phone numbers. Generic numbers need
        # an explicit contact label; international and Saudi formats stand alone.
        international = candidate.startswith(("+", "00")) and 8 <= len(digits) <= 15
        saudi = (len(digits) == 10 and digits.startswith("0")) or (
            len(digits) == 12 and digits.startswith("966")
        )
        prefix = result[max(0, result.rfind("\n", 0, match.start())):match.start()]
        labelled = bool(re.search(r"(?:phone|mobile|call|contact|whatsapp|هاتف|جوال|اتصل|واتس|للتواصل)[^\d\n]{0,35}$", prefix, re.I))
        generic = labelled and 8 <= len(digits) <= 15
        return "[phone removed]" if international or saudi or generic else candidate

    result = PHONE.sub(redact, result)
    result = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[contact removed]", result)
    result = re.sub(r"(?:https?://|www\.)?(?:wa\.me|(?:api\.|web\.)?whatsapp\.com|t\.me|(?:www\.)?(?:instagram|snapchat|facebook)\.com)/[^\s<>]+", "[contact removed]", result, flags=re.I)
    result = re.sub(r"((?:instagram|snapchat|telegram|انستقرام|سناب|تلجرام)\s*[:：]?\s*)@[\w.]+", r"\1[contact removed]", result, flags=re.I)
    result = re.sub(r"(?m)^[ \t]*(?:📞|☎️?)[^\n]*$", "[contact removed]", result)
    result = re.sub(r"[^\S\n]+", " ", result)
    result = "\n".join(line.strip() for line in result.splitlines())
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def normalize_property(raw_record: dict) -> dict:
    """Return a new record, preserving source values without mutating input."""
    flags = []
    raw = raw_record if isinstance(raw_record, dict) else {}
    prop = raw.get("json_ld")
    if not isinstance(prop, dict):
        prop = {}
        flags.append("missing_property_record")
    url = text(raw.get("source_url"))
    try:
        parts = urlsplit(url or "")
    except ValueError:
        parts = urlsplit("")
    match = re.fullmatch(r"/en/property/(sale|rent)/[^/]+-(\d+)/?", parts.path)
    valid_url = parts.scheme == "https" and parts.netloc == "wasalt.sa" and match and not parts.query and not parts.fragment
    purpose, url_id = match.groups() if valid_url else (None, None)
    if not valid_url:
        flags.append("invalid_source_url")
    listing_id = str(raw["listing_id"]) if raw.get("listing_id") is not None else url_id
    if listing_id and url_id and listing_id != url_id:
        flags.append("listing_id_url_mismatch")
    if raw.get("purpose") and purpose and raw["purpose"] != purpose:
        flags.append("purpose_url_mismatch")
    title = text(prop.get("name"))
    explicit = prop.get("propertyType") or prop.get("accommodationCategory") or prop.get("additionalType")
    if isinstance(explicit, dict):
        explicit = explicit.get("name") or explicit.get("@id")
    explicit = text(explicit)
    property_type = None
    if explicit:
        label = re.sub(r"[\s_-]+", " ", explicit.rstrip("/").rsplit("/", 1)[-1]).casefold()
        property_type = TYPES.get(label)
        if property_type is None:
            flags.append("ambiguous_property_type")
    else:
        matches = []
        for key, value in TYPES.items():
            pattern = re.escape(key).replace(r"\ ", r"[\s_-]+")
            for match_type in re.finditer(r"(?<!\w)" + pattern + r"(?!\w)", title or "", re.I):
                matches.append((match_type.start(), match_type.end(), value))
        # A multiword type takes precedence over contained words, e.g. the
        # word "house" inside "rest house" is not a second property type.
        found = {kind for start, end, kind in matches if not any(
            other_start <= start and end <= other_end and other_end - other_start > end - start
            for other_start, other_end, _ in matches
        )}
        if len(found) == 1:
            property_type = found.pop()
            flags.append("property_type_inferred_from_title")
        elif len(found) > 1:
            flags.append("ambiguous_property_type")
    schema_type = prop.get("@type")
    schema_types = schema_type if isinstance(schema_type, list) else [schema_type]
    if property_type in {"apartment", "land", "building", "floor", "room", "rest_house", "chalet"} and "SingleFamilyResidence" in schema_types:
        flags.append("schema_type_property_type_mismatch")
    address = prop.get("address")
    address = address if isinstance(address, dict) else {}
    offers = prop.get("offers")
    offers = [offers] if isinstance(offers, dict) else offers
    offers = [o for o in offers if isinstance(o, dict)] if isinstance(offers, list) else []
    if len(offers) > 1:
        flags.append("multiple_offers")
    offer = offers[0] if len(offers) == 1 else {}
    price = numeric(offer.get("price"))
    currency_raw = text(offer.get("priceCurrency"))
    currency = None
    period = None
    if currency_raw:
        currency_match = re.match(r"^([A-Za-z]{3})(?:\s|/|$)", currency_raw)
        currency = currency_match.group(1).upper() if currency_match else None
        period_match = re.search(r"/\s*([^\W\d_]+)\s*$", currency_raw, re.I)
        if period_match:
            period = PERIODS.get(period_match.group(1).lower())
    explicit_period = text(offer.get("billingPeriod"))
    if explicit_period:
        mapped = PERIODS.get(explicit_period.casefold())
        if period and mapped and period != mapped:
            flags.append("price_period_mismatch")
            period = None
        elif not period:
            period = mapped
    if currency != "SAR":
        flags.append("missing_currency" if currency is None else "non_sar_currency")
    price_sar = price if currency == "SAR" else None
    if purpose == "rent" and period is None:
        flags.append("unclear_price_frequency")
    area = None
    area_source = None
    floor_size = prop.get("floorSize")
    if isinstance(floor_size, dict):
        unit = text(floor_size.get("unitCode")) or text(floor_size.get("unitText"))
        if unit and unit.casefold() in {"mtk", "sqm", "sq m", "m2", "m²", "square meter", "square meters", "square metre", "square metres"}:
            area = numeric(floor_size.get("value"))
            if area is not None:
                area_source = "structured"
        else:
            flags.append("unclear_area_unit")
    if area is None:
        title_area = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:SQM|m²|m2|sq\.?\s*m)\b", title or "", re.I)
        if title_area:
            area = numeric(title_area.group(1))
            area_source = "title"
    if area == 0:
        area = area_source = None
        flags.append("invalid_area")

    def count(key):
        value = prop.get(key)
        if isinstance(value, dict):
            value = value.get("value")
        number = numeric(value)
        if number is not None and number == int(number):
            return int(number)
        if value is not None:
            flags.append("invalid_" + key)
        return None

    original = prop.get("description")
    clean = clean_description(original)
    result = {
        "source": raw.get("source"), "listing_id": listing_id, "source_url": url,
        "purpose": purpose, "property_type": property_type, "schema_org_type": schema_type,
        "title": title, "city": text(address.get("addressLocality")),
        "region": text(address.get("addressRegion")), "district": text(address.get("streetAddress")),
        "price_sar": price_sar, "price_currency": currency, "price_period": period,
        "area_sqm": area, "area_source": area_source,
        "bedrooms": count("numberOfBedrooms"), "bathrooms": count("numberOfBathroomsTotal"),
        "rooms": count("numberOfRooms"), "description_original": original,
        "description_clean": clean, "image_url": None,
        "scraped_at": raw.get("extracted_at"), "quality_flags": flags,
    }
    image = prop.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    result["image_url"] = text(image.get("url") or image.get("contentUrl")) if isinstance(image, dict) else text(image)
    for key in ("source", "listing_id", "purpose", "title", "property_type", "city", "district", "price_sar", "area_sqm", "bedrooms", "bathrooms", "description_clean", "scraped_at"):
        if property_type in {"land", "building", "room"} and key in {"bedrooms", "bathrooms"}:
            continue
        if result[key] is None or result[key] == "":
            flags.append("missing_" + key)
    if result["source"] not in (None, "wasalt"):
        flags.append("unexpected_source")
    if result["scraped_at"]:
        try:
            stamp = datetime.fromisoformat(result["scraped_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                flags.append("timestamp_missing_timezone")
        except (ValueError, TypeError, AttributeError):
            flags.append("invalid_timestamp")
    # Only explicit standalone room totals are compared. Floor-level counts
    # and general Arabic interpretation are intentionally outside this check.
    word_counts = {"ثلاث": 3, "ثلاثة": 3, "أربع": 4, "أربعة": 4}
    for line in (clean or "").splitlines():
        area_match = re.search(r"(?:Land Area|Built up Area|مساحة|المساحة)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:SQM|م²|م2|متر مربع)\b", line, re.I)
        if area_match and area is not None and numeric(area_match.group(1)) != area:
            flags.append("area_description_mismatch")
        room_match = re.fullmatch(r"[\W_]*(\d+|ثلاث|ثلاثة|أربع|أربعة)\s+غرف[\W_]*", line)
        if room_match:
            token = room_match.group(1)
            described = word_counts.get(token) if token in word_counts else numeric(token)
            if result["rooms"] is not None and described != result["rooms"]:
                flags.append("rooms_description_mismatch")
    if clean and "دفعتين" in clean and "دفعة" in clean:
        flags.append("payment_options_in_description")
    result["quality_flags"] = list(dict.fromkeys(flags))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; refusing to overwrite")
    normalized = normalize_property(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"Saved {args.output}; flags: {', '.join(normalized['quality_flags']) or 'none'}")


if __name__ == "__main__":
    main()
