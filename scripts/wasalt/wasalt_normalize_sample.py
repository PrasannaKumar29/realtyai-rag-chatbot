"""Normalize only selected, already acquired sample records, entirely offline."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from .wasalt_normalize import normalize_property


ROOT = REPO_ROOT
DATA = DATA_ROOT
REPORT = DATA / "sample_10_quality.csv"
COLUMNS = (
    "listing_id", "purpose", "property_type", "price_sar", "area_sqm", "city",
    "district", "bedrooms", "bathrooms", "quality_flags", "validation_status",
)


def validation_status(record):
    required = ("source", "listing_id", "source_url", "purpose", "title", "scraped_at")
    fatal_flags = {
        "missing_property_record", "invalid_source_url", "listing_id_url_mismatch",
        "purpose_url_mismatch", "unexpected_source", "invalid_timestamp",
        "sample_identity_mismatch", "raw_input_invalid",
    }
    if any(not record.get(key) for key in required) or fatal_flags.intersection(record["quality_flags"]):
        return "invalid"
    if record.get("source") != "wasalt" or record.get("purpose") not in {"sale", "rent"}:
        return "invalid"
    if not any(record.get(key) is not None for key in ("price_sar", "city", "area_sqm", "description_clean")):
        return "invalid"
    return "valid_with_warnings" if record["quality_flags"] else "valid"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, default=DATA / "sample_10.csv")
    parser.add_argument("--acquisition-manifest", type=Path, default=DATA / "sample_10_manifest.csv")
    parser.add_argument("--output-report", type=Path, default=REPORT)
    parser.add_argument("--expansion-successes", action="store_true", help="Normalize only successful acquisitions from all four existing expansion manifests")
    args = parser.parse_args()
    if args.output_report.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output_report}")
    input_manifest = DATA / "expansion_200.csv" if args.expansion_successes else args.input_manifest
    with input_manifest.open(encoding="utf-8", newline="") as handle:
        sample = list(csv.DictReader(handle))
    size = len(sample)
    if (size not in ((200,) if args.expansion_successes else (10, 50)) or len({r["listing_id"] for r in sample}) != size
            or len({r["source_url"] for r in sample}) != size
            or Counter(r["purpose"] for r in sample) != {"sale": size // 2, "rent": size // 2}
            or any(not r["listing_id"].isdigit() for r in sample)):
        raise ValueError("Expected exactly 10 or 50 distinct sale/rent sample IDs")
    acquisition_paths = [DATA / f"expansion_batch_{i:02d}_manifest.csv" for i in range(1,5)] if args.expansion_successes else [args.acquisition_manifest]
    acquisition_rows = []
    for path in acquisition_paths:
        with path.open(encoding="utf-8", newline="") as handle:
            acquisition_rows.extend(csv.DictReader(handle))
    manifest = {row["listing_id"]: row for row in acquisition_rows}
    if args.expansion_successes:
        if len(manifest) != 200 or len(acquisition_rows) != 200 or {r["listing_id"] for r in sample} != set(manifest):
            raise ValueError("Expansion manifests must reconcile exactly 200 selections")
        sample = [row for row in sample if manifest[row["listing_id"]]["extraction_status"] == "success"]
        if len(sample) != 199 or any(row["listing_id"] == "5842008" for row in sample):
            raise ValueError("Expected exactly 199 successful expansion records, excluding 5842008")
    columns = list(COLUMNS)
    if size in (50,200):
        columns.insert(columns.index("quality_flags"), "description_present")
    # Protect all existing raw/normalized JSON, including the earlier checkpoints.
    protected = list((DATA / "raw").rglob("*.json")) + list((DATA / "normalized").rglob("*.json"))
    protected += [MANUAL_EXPORTS / "wasalt_5891090.json", MANUAL_EXPORTS / "wasalt_5891036.json", input_manifest, *acquisition_paths]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    quality_rows = []
    created = skipped = 0
    for item in sample:
        raw_path = DATA / "raw" / item["purpose"] / f"{item['listing_id']}.json"
        output = DATA / "normalized" / item["purpose"] / f"{item['listing_id']}.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        acquisition = manifest[item["listing_id"]]
        if acquisition["extraction_status"] != "success" or any(raw.get(key) != item[key] or acquisition[key] != item[key] for key in ("listing_id", "purpose", "source_url")):
            raise ValueError(f"Raw/acquisition identity mismatch: {item['listing_id']}")
        if output.exists():
            record = json.loads(output.read_text(encoding="utf-8"))
            skipped += 1
            print(f"Skipped existing normalized output: {output.relative_to(ROOT)}")
        else:
            record = normalize_property(raw)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
            assert json.loads(output.read_text(encoding="utf-8")) == record
            created += 1
        flags = list(record["quality_flags"])
        if any(record.get(key) != item[key] for key in ("listing_id", "purpose", "source_url")):
            flags.append("sample_identity_mismatch")
        checked = {**record, "quality_flags": flags}
        status = validation_status(checked)
        quality = {**{key: record.get(key) for key in columns if key not in {"description_present", "quality_flags", "validation_status"}}, "quality_flags": ";".join(flags), "validation_status": status}
        if "description_present" in columns:
            quality["description_present"] = bool(record.get("description_clean"))
        quality_rows.append(quality)
        print(item["listing_id"], record["property_type"], status, ";".join(flags))
    with args.output_report.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(quality_rows)
    for path, before in hashes.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before, f"Protected input changed: {path}"
    print(f"Created: {created}; skipped existing: {skipped}; quality rows: {len(quality_rows)}")
    print("Quality statuses:", dict(Counter(r["validation_status"] for r in quality_rows)))
    print("Protected raw, earlier normalized outputs, and manifest checksums: unchanged")


if __name__ == "__main__":
    main()
