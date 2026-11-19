"""Offline acquisition checks for the single 50-property batch; no normalization."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import re


DATA = DATA_ROOT
REPORT = DATA / "sample_50_acquisition_report.json"


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def title_type(title):
    for label, pattern in (
        ("rest_house", r"rest house"), ("apartment", r"(?:semi furnished |furnished )?apartment"),
        ("villa", r"(?:furnished )?villa"), ("land", r"land"), ("floor", r"floor"),
        ("building", r"building"), ("room", r"room"), ("duplex", r"duplex"), ("chalet", r"chalet"),
    ):
        if re.match(pattern + r"\b", title, re.I):
            return label
    return "unknown"


def main():
    if REPORT.exists():
        raise FileExistsError(f"Refusing to overwrite {REPORT}")
    sample = read_csv(DATA / "sample_50.csv")
    manifest = read_csv(DATA / "sample_50_manifest.csv")
    expected = {r["listing_id"]: r for r in sample}
    assert len(sample) == len(manifest) == len(expected) == 50
    assert len({m['listing_id'] for m in manifest}) == 50
    prior_ids = {"5891090", "5891036"} | {r["listing_id"] for r in read_csv(DATA / "sample_10.csv")}
    assert not set(expected).intersection(prior_ids)
    previous_shapes = set()
    for item in read_csv(DATA / "sample_10.csv"):
        prop = json.loads((DATA / "raw" / item["purpose"] / (item["listing_id"] + ".json")).read_text())["json_ld"]
        previous_shapes.add(tuple(sorted(prop)))
    shapes = defaultdict(list)
    missing = defaultdict(list)
    mismatches = []
    details = []
    for attempt in manifest:
        item = expected[attempt["listing_id"]]
        assert all(attempt[k] == item[k] for k in ("listing_id", "source_url", "purpose"))
        if attempt["extraction_status"] != "success":
            continue
        path = DATA / "raw" / item["purpose"] / (item["listing_id"] + ".json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert set(raw) == {"source", "listing_id", "purpose", "source_url", "extracted_at", "json_ld"}
        assert all(raw[k] == item[k] for k in ("listing_id", "source_url", "purpose"))
        assert raw["source"] == "wasalt" and raw["extracted_at"] == attempt["extraction_timestamp"]
        assert datetime.fromisoformat(raw["extracted_at"].replace("Z", "+00:00")).tzinfo is not None
        prop = raw["json_ld"]
        assert isinstance(prop, dict) and prop
        address = prop.get("address")
        address = address if isinstance(address, dict) else {}
        offers = prop.get("offers")
        offers = [offers] if isinstance(offers, dict) else offers
        offers = [o for o in offers if isinstance(o, dict)] if isinstance(offers, list) else []
        attributes = {
            "title": prop.get("name"), "price": [o["price"] for o in offers if o.get("price") is not None],
            "city": address.get("addressLocality"), "district": address.get("streetAddress"),
            "region": address.get("addressRegion"), "bedrooms": prop.get("numberOfBedrooms"),
            "bathrooms": prop.get("numberOfBathroomsTotal"), "rooms": prop.get("numberOfRooms"),
            "dedicated_area": prop.get("floorSize"), "description": prop.get("description"),
        }
        absent = [key for key, value in attributes.items() if value is None or value == "" or value == []]
        for key in absent:
            missing[key].append(item["listing_id"])
        hint = title_type(prop.get("name") or "")
        if hint != item["property_type_hint"]:
            mismatches.append({"listing_id": item["listing_id"], "url_hint": item["property_type_hint"], "title_hint": hint})
        shapes[tuple(sorted(prop))].append(item["listing_id"])
        details.append({
            "listing_id": item["listing_id"], "purpose": item["purpose"], "title": prop.get("name"),
            "url_type_hint": item["property_type_hint"], "title_type_hint": hint,
            "schema_org_type": prop.get("@type"), "city": address.get("addressLocality"),
            "offers": [{key: o.get(key) for key in ("price", "priceCurrency")} for o in offers],
            "missing_attributes": absent,
            "field_types": {key: type(value).__name__ for key, value in prop.items()},
        })
    counts = Counter(m["extraction_status"] for m in manifest)
    report = {
        "selected": 50, "attempted": sum(m["extraction_status"] != "skipped" for m in manifest),
        "status_counts": {s: counts[s] for s in ("success", "failed", "invalid", "blocked", "skipped")},
        "http_status_counts": dict(Counter(m["http_status"] for m in manifest)),
        "successful_purposes": dict(Counter(d["purpose"] for d in details)),
        "successful_title_type_hints": dict(Counter(d["title_type_hint"] for d in details)),
        "selected_type_hints_by_purpose": {p: dict(Counter(r["property_type_hint"] for r in sample if r["purpose"] == p)) for p in ("sale", "rent")},
        "type_hint_mismatches": mismatches,
        "missing_attributes": {key: {"count": len(ids), "listing_ids": ids} for key, ids in missing.items()},
        "schema_variants": [{"keys": list(keys), "listing_ids": ids, "new_vs_sample_10": keys not in previous_shapes} for keys, ids in shapes.items()],
        "failures": [m for m in manifest if m["extraction_status"] != "success"],
        "properties": details,
    }
    with REPORT.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"properties", "schema_variants", "missing_attributes"}}, indent=2))
    print('Missing attributes:',{key: len(ids) for key, ids in missing.items()})
    for variant in report['schema_variants']:
        print('Schema variant:',variant['keys'],'count:',len(variant['listing_ids']),'new:',variant['new_vs_sample_10'])
    print('Report:',REPORT)


if __name__ == "__main__":
    main()
