"""Offline integrity gates and reconciliation for the existing expansion."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from .test_wasalt_browser import property_score
from .wasalt_extract_batch import failure_gate, write_json_exclusive
from .wasalt_select_sample import valid_record


ROOT = REPO_ROOT
DATA = DATA_ROOT


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def inventory_checks():
    expansion = read_csv(DATA / "expansion_200.csv")
    inventory = {(r["listing_id"], r["purpose"], r["source_url"]) for r in read_csv(DATA / "discovered_urls.csv")}
    batches = [read_csv(DATA / f"expansion_batch_{index:02d}.csv") for index in range(1, 5)]
    assert len(expansion) == len({r["listing_id"] for r in expansion}) == len({r["source_url"] for r in expansion}) == 200
    assert Counter(r["purpose"] for r in expansion) == {"sale": 100, "rent": 100}
    identities = {(r["listing_id"], r["purpose"], r["source_url"]) for r in expansion}
    assert identities.issubset(inventory)
    assert all(valid_record(r) for r in expansion)
    combined = []
    for batch in batches:
        assert len(batch) == 50 and Counter(r["purpose"] for r in batch) == {"sale": 25, "rent": 25}
        combined.extend(batch)
    assert len({r["listing_id"] for r in combined}) == 200
    assert {(r["listing_id"], r["purpose"], r["source_url"]) for r in combined} == identities
    return expansion, batches


def raw_records():
    records = {}
    for path in list((DATA / "raw").rglob("*.json")) + [MANUAL_EXPORTS / "wasalt_5891090.json", MANUAL_EXPORTS / "wasalt_5891036.json"]:
        value = json.loads(path.read_text(encoding="utf-8"))
        key = (value["purpose"], value["listing_id"])
        # Root manual exports intentionally duplicate the original rental capture.
        if key in records:
            assert value["source_url"] == records[key]["source_url"]
            assert value["json_ld"] == records[key]["json_ld"]
        else:
            records[key] = value
    ids = [value["listing_id"] for value in records.values()]
    assert len(ids) == len(set(ids)), "Unexpected listing ID reused across sale/rent"
    return records


def validate_batch(index, write_report=True):
    _, batches = inventory_checks()
    selected = batches[index - 1]
    expected = {r["listing_id"]: r for r in selected}
    path = DATA / f"expansion_batch_{index:02d}_manifest.csv"
    manifest = read_csv(path)
    journal = path.with_suffix(".csv.journal")
    assert len(manifest) == 50 and {m["listing_id"] for m in manifest} == set(expected)
    assert len({m["source_url"] for m in manifest}) == 50
    metadata = json.loads((journal / "batch.json").read_text())
    assert metadata["listings"] == [{k: item[k] for k in ("listing_id", "purpose", "source_url")} for item in selected]
    results = list(journal.glob("*.result.json"))
    started = list(journal.glob("*.started.json"))
    assert len(results) == 50
    started_ids = {json.loads(p.read_text())["listing_id"] for p in started}
    assert started_ids.issubset(expected)
    issues = []
    missing = defaultdict(list)
    shapes = defaultdict(list)
    verified = 0
    for attempt in manifest:
        item = expected[attempt["listing_id"]]
        assert all(attempt[k] == item[k] for k in ("listing_id", "purpose", "source_url"))
        result = json.loads((journal / f"{item['listing_id']}.result.json").read_text())
        assert all(str(result[k]) == attempt[k] for k in attempt)
        if attempt["extraction_status"] != "skipped":
            assert item["listing_id"] in started_ids
        if attempt["extraction_status"] != "success":
            issues.append(attempt)
            continue
        raw_path = DATA / "raw" / item["purpose"] / f"{item['listing_id']}.json"
        assert resolve_data_path(attempt["output_file_path"]) == raw_path
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        assert set(raw) == {"source", "listing_id", "purpose", "source_url", "extracted_at", "json_ld"}
        assert raw["source"] == "wasalt"
        assert all(raw[k] == item[k] for k in ("listing_id", "purpose", "source_url"))
        assert raw["extracted_at"] == attempt["extraction_timestamp"]
        assert datetime.fromisoformat(raw["extracted_at"].replace("Z", "+00:00")).tzinfo is not None
        intent = json.loads((journal / f"{item['listing_id']}.started.json").read_text())
        assert all(intent[k] == item[k] for k in ("listing_id", "purpose", "source_url"))
        prop = raw["json_ld"]
        assert isinstance(prop, dict) and prop
        assert property_score(prop, item["source_url"], item["listing_id"], attempt["page_title"]) > 0
        assert attempt["main_property_found"] == "Yes"
        address = prop.get("address") or {}
        offers = prop.get("offers") or []
        offers = [offers] if isinstance(offers, dict) else offers
        fields = {"title": prop.get("name"), "city": address.get("addressLocality"), "district": address.get("streetAddress"),
                  "price": [o["price"] for o in offers if isinstance(o, dict) and o.get("price") is not None],
                  "description": prop.get("description"), "bedrooms": prop.get("numberOfBedrooms"),
                  "bathrooms": prop.get("numberOfBathroomsTotal"), "dedicated_area": prop.get("floorSize")}
        for key, value in fields.items():
            if value is None or value == "" or value == []:
                missing[key].append(item["listing_id"])
        shapes[tuple(sorted(prop))].append(item["listing_id"])
        verified += 1
    assert not list((DATA / "raw").rglob("*.tmp"))
    assert not list(journal.glob("*.tmp"))
    counts = Counter(row["extraction_status"] for row in manifest)
    streak = 0
    stop_reasons = []
    for attempt in manifest:
        streak, reason = failure_gate(attempt, streak)
        if reason:
            stop_reasons.append(reason)
    report = {
        "batch": index, "selected": 50, "attempted": len(started),
        "status_counts": {s: counts[s] for s in ("success", "failed", "invalid", "blocked", "skipped")},
        "http_status_counts": dict(Counter(row["http_status"] for row in manifest)),
        "verified_raw_records": verified, "manifest_journal_consistent": True,
        "no_partial_json_files": True, "current_unique_raw_properties": len(raw_records()),
        "missing_fields": {key: {"count": len(ids), "listing_ids": ids} for key, ids in missing.items()},
        "schema_variants": [{"keys": list(keys), "listing_ids": ids} for keys, ids in shapes.items()],
        "non_success_results": issues,
        "safe_to_proceed": not stop_reasons and counts["blocked"] == 0 and counts["skipped"] == 0,
        "stop_reasons": stop_reasons,
    }
    if write_report:
        write_json_exclusive(DATA / f"expansion_batch_{index:02d}_validation.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"missing_fields", "schema_variants", "non_success_results"}}, indent=2))
    print("Missing fields:", {key: len(ids) for key, ids in missing.items()})
    return report["safe_to_proceed"]


def consolidate(replace=False):
    expansion, _ = inventory_checks()
    expected = {r["listing_id"]: r for r in expansion}
    all_results = []
    per_batch = []
    not_executed = []
    for index in range(1, 5):
        manifest = DATA / f"expansion_batch_{index:02d}_manifest.csv"
        if not manifest.exists():
            not_executed.append(index)
            continue
        results = read_csv(manifest)
        # Audit every original CSV/journal/raw association without changing reports.
        validate_batch(index, write_report=False)
        all_results.extend(results)
        per_batch.append({"batch": index, "statuses": dict(Counter(r["extraction_status"] for r in results))})
    assert len({r["listing_id"] for r in all_results}) == len(all_results)
    for result in all_results:
        item = expected[result["listing_id"]]
        assert all(result[k] == item[k] for k in ("listing_id", "purpose", "source_url"))
    acquired = raw_records()
    success_ids = {r["listing_id"] for r in all_results if r["extraction_status"] == "success"}
    assert all((expected[i]["purpose"], i) in acquired for i in success_ids)
    counts = Counter(r["extraction_status"] for r in all_results)
    first_batch_ids = {r["listing_id"] for r in read_csv(DATA / "expansion_batch_01.csv")}
    baseline_shapes = {tuple(sorted(raw["json_ld"])) for raw in acquired.values()
                       if raw["listing_id"] not in expected or raw["listing_id"] in first_batch_ids}
    schema_shapes = defaultdict(list)
    missing = defaultdict(list)
    schema_types = Counter()
    for raw in acquired.values():
        if raw["listing_id"] not in success_ids:
            continue
        prop = raw["json_ld"]
        schema_shapes[tuple(sorted(prop))].append(raw["listing_id"])
        schema_types[str(prop.get("@type"))] += 1
        address = prop.get("address") or {}
        offers = prop.get("offers") or []
        offers = [offers] if isinstance(offers, dict) else offers
        fields = {"title": prop.get("name"), "city": address.get("addressLocality"),
                  "price": [o["price"] for o in offers if isinstance(o, dict) and o.get("price") is not None],
                  "description": prop.get("description"), "bedrooms": prop.get("numberOfBedrooms"),
                  "bathrooms": prop.get("numberOfBathroomsTotal"), "dedicated_area": prop.get("floorSize")}
        for key, value in fields.items():
            if value is None or value == "" or value == []:
                missing[key].append(raw["listing_id"])
    report = {
        "total_selected": 200, "total_attempted": sum(r["extraction_status"] != "skipped" for r in all_results),
        "total_successful": counts["success"], "failed": counts["failed"], "invalid": counts["invalid"],
        "blocked": counts["blocked"], "skipped": counts["skipped"],
        "not_yet_executed": 200 - len(all_results), "not_executed_batches": not_executed,
        "pending": sum((expected[i]["purpose"], i) not in acquired for i in set(expected) - {r["listing_id"] for r in all_results if r["extraction_status"] != "skipped"}),
        "http_status_distribution": dict(Counter(r["http_status"] for r in all_results if r["http_status"])),
        "reconciled_result_rows": len(all_results), "current_unique_raw_property_count": len(acquired),
        "unique_raw_by_purpose": dict(Counter(purpose for purpose, _ in acquired)),
        "duplicate_listing_ids_within_purpose": 0, "batches": per_batch,
        "expansion_missing_fields": {key: {"count": len(ids), "listing_ids": ids} for key, ids in missing.items()},
        "expansion_schema_types": dict(schema_types),
        "expansion_schema_variations": [{"keys": list(keys), "count": len(ids), "listing_ids": ids, "new_since_batch_01": keys not in baseline_shapes} for keys, ids in schema_shapes.items()],
    }
    destination = DATA / "expansion_acquisition_report.json"
    if replace:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA, prefix=".acquisition-report-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    else:
        write_json_exclusive(destination, report)
    print(json.dumps({k:v for k,v in report.items() if k not in {"expansion_missing_fields", "expansion_schema_variations"}}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, choices=(2, 3, 4))
    parser.add_argument("--consolidate", action="store_true")
    parser.add_argument("--replace-consolidated-report", action="store_true", help="Explicitly authorize atomic replacement of only the consolidated report")
    args = parser.parse_args()
    if args.consolidate:
        consolidate(replace=args.replace_consolidated_report)
    elif args.batch:
        if not validate_batch(args.batch):
            raise SystemExit(2)
    else:
        parser.error("Specify --batch or --consolidate")


if __name__ == "__main__":
    main()
