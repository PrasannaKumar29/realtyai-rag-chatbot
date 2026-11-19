"""Export existing normalized Wasalt properties, entirely offline."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re

import yaml
from .wasalt_dataset_io import write_text_atomic


ROOT = REPO_ROOT
DATA = DATA_ROOT
FIELDS = (
    "source", "listing_id", "source_url", "purpose", "property_type", "city",
    "district", "price_sar", "price_period", "area_sqm", "scraped_at", "quality_flags",
)
REPORT_FIELDS = ("listing_id", "purpose", "property_type", "output_path", "export_status", "quality_warning_count")
NOTES = {
    "property_type_inferred_from_title": "Property type is inferred from the listing title.",
    "schema_type_property_type_mismatch": "The source Schema.org type is SingleFamilyResidence and does not match the title-based property type.",
    "missing_bathrooms": "No structured bathroom count is available; none is assumed.",
    "area_description_mismatch": "The area in the title differs from the description; the title value is retained for review.",
}
CONTACT = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:mailto|tel):|"
    r"(?:wa\.me|whatsapp\.com|t\.me|instagram\.com|snapchat\.com|facebook\.com)/|"
    r"(?<!\w)(?:\+|00)\d(?:[ ()\-]*\d){7,14}(?!\w)|"
    r"(?<!\w)(?:0[15](?:[ ()\-]*\d){8}|966[15](?:[ ()\-]*\d){8})(?!\w)|"
    r"(?:instagram|snapchat|telegram|انستقرام|سناب|تلجرام)\s*[:：]?\s*@[\w.]+",
    re.I,
)


def escape_inline(value):
    """Keep title/location punctuation from changing Markdown structure."""
    value = " ".join(str(value).split())
    return re.sub(r"([\\`*_{}\[\]<>|])", r"\\\1", value)


def contains_contact(value):
    # Scan Arabic/Persian digits in ASCII form without changing exported text.
    scan = "".join(str(int(c)) if c.isdecimal() else c for c in value)
    return bool(CONTACT.search(scan))


def format_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric normalized attribute")
    return f"{value:,}"


def render_markdown(record):
    """Render normalized values without changing the supplied record."""
    metadata = {key: record.get(key) for key in FIELDS}
    for key in ("bedrooms", "bathrooms"):
        if record.get(key) is not None:
            metadata[key] = record[key]
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
    lines = ["---", frontmatter, "---", "", "# " + escape_inline(record["title"]), "", "## Property Overview", ""]
    purpose = {"sale": "For sale", "rent": "Long-term rent"}.get(record["purpose"])
    if purpose:
        lines.append(f"- Purpose: {purpose}")
    if record.get("property_type"):
        lines.append("- Property type: " + escape_inline(record["property_type"].replace("_", " ").capitalize()))
    location = list(dict.fromkeys(record[key] for key in ("district", "region", "city") if record.get(key)))
    if location:
        lines.append("- Location: " + escape_inline(", ".join(location)))
    if record.get("price_sar") is not None:
        price = "SAR " + format_number(record["price_sar"])
        if record.get("price_period"):
            price += "/" + escape_inline(record["price_period"])
        elif record.get("purpose") == "rent":
            price += " (payment period unspecified)"
        lines.append("- Price: " + price)
    if record.get("area_sqm") is not None:
        area = format_number(record["area_sqm"]) + " sqm"
        if record.get("area_source") == "title":
            area += " (from listing title)"
        lines.append("- Area: " + area)
    for key in ("bedrooms", "bathrooms"):
        if record.get(key) is not None:
            lines.append(f"- {key.capitalize()}: {format_number(record[key])}")
    if record.get("description_clean"):
        lines.extend(["", "## Description", "", record["description_clean"]])
    if record.get("quality_flags"):
        lines.extend(["", "## Quality Notes", ""])
        for flag in record["quality_flags"]:
            note = NOTES.get(flag, flag.replace("_", " ").capitalize() + ".")
            lines.append(f"- {note} (`{flag}`)")
    lines.extend(["", "## Source", "", f"[Original Wasalt listing]({record['source_url']})", ""])
    rendered = "\n".join(lines)
    if contains_contact(rendered):
        raise ValueError(f"Contact information detected for {record['listing_id']}; export refused")
    if re.search(r"<\s*/?\s*[A-Za-z][^>]*>", record.get("description_clean") or ""):
        raise ValueError("Clean description unexpectedly contains HTML; export refused")
    if yaml.safe_load(frontmatter) != metadata:
        raise ValueError("YAML round-trip failed")
    return rendered


def export_sample(output_root=DATA, all_normalized=False, final_corpus=False):
    if all_normalized:
        sample = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((DATA / "normalized").rglob("*.json"))]
    else:
        with (DATA / "sample_10.csv").open(encoding="utf-8", newline="") as handle:
            sample = list(csv.DictReader(handle))
    size = 261 if final_corpus else (62 if all_normalized else 10)
    purpose_counts = {"sale":131,"rent":130} if final_corpus else {"sale":size//2,"rent":size//2}
    if (len(sample) != size or len({r["listing_id"] for r in sample}) != size
            or len({r["source_url"] for r in sample}) != size
            or Counter(r["purpose"] for r in sample) != purpose_counts
            or any(not row["listing_id"].isdigit() for row in sample)):
        raise ValueError(f"Expected exactly {size} distinct sale/rent records")
    output_root = Path(output_root)
    report_path = output_root / ("final_markdown_report.csv" if final_corpus else ("corpus_markdown_report.csv" if all_normalized else "sample_10_markdown_report.csv"))
    report_exists=report_path.exists()
    if report_exists and not final_corpus:
        raise FileExistsError(f"Refusing to overwrite {report_path}")
    plan = []
    for item in sample:
        output = output_root / "properties" / item["purpose"] / f"{item['listing_id']}.md"
        if output.exists() and not all_normalized:
            raise FileExistsError(f"Refusing to overwrite {output}")
        path = DATA / "normalized" / item["purpose"] / f"{item['listing_id']}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if any(record.get(key) != item[key] for key in ("listing_id", "source_url", "purpose")):
            raise ValueError(f"Normalized/sample identity mismatch: {item['listing_id']}")
        rendered = render_markdown(record)
        if output.exists():
            existing = output.read_text(encoding="utf-8")
            metadata = yaml.safe_load(existing.split("---\n", 2)[1])
            if any(metadata.get(k) != record.get(k) for k in FIELDS):
                raise ValueError(f"Existing Markdown metadata mismatch: {output}")
            if contains_contact(existing):
                raise ValueError(f"Existing Markdown contains contact details: {output}")
        plan.append((record, output, rendered))
    # Validate every document before creating any production output.
    protected = list((DATA / "raw").rglob("*.json")) + list((DATA / "normalized").rglob("*.json"))
    protected += [DATA / "sample_10.csv", MANUAL_EXPORTS / "wasalt_5891090.json", MANUAL_EXPORTS / "wasalt_5891036.json"]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    report_rows = []
    for record, output, markdown in plan:
        status = "existing_preserved" if output.exists() else "success"
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(markdown)
            assert output.read_text(encoding="utf-8") == markdown
        report_rows.append({
            "listing_id": record["listing_id"], "purpose": record["purpose"],
            "property_type": record["property_type"],
            "output_path": str(output.relative_to(output_root)), "export_status": status,
            "quality_warning_count": len(record.get("quality_flags") or []),
        })
    if report_exists:
        with report_path.open(encoding='utf-8',newline='') as handle:
            historical=list(csv.DictReader(handle))
        assert len(historical)==len(report_rows)
        assert {r['listing_id'] for r in historical}=={r['listing_id'] for r in report_rows}
    else:
        with report_path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            writer.writerows(report_rows)
    for path, before in hashes.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before, f"Protected data changed: {path}"
    return report_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complete-corpus", action="store_true", help="Complete Markdown, JSONL and quality CSV for the existing 62 records")
    parser.add_argument("--final-corpus", action="store_true", help="Finalize exactly 261 existing normalized properties, preserving Markdown")
    parser.add_argument("--rebuild-derived", action="store_true", help="Authorize atomic replacement of only listings.jsonl and quality_report.csv")
    args = parser.parse_args()
    if args.complete_corpus or args.final_corpus:
        from .wasalt_normalize_sample import validation_status
        jsonl = DATA / "listings.jsonl"
        quality = DATA / "quality_report.csv"
        for path in (jsonl, quality):
            if path.exists() and not args.rebuild_derived:
                raise FileExistsError(f"Refusing to overwrite {path}")
        report = export_sample(all_normalized=True,final_corpus=args.final_corpus)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "normalized").rglob("*.json"))]
        jsonl_text="".join(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n' for record in records)
        columns = ("listing_id", "purpose", "property_type", "city", "district", "price_sar", "area_sqm", "bedrooms", "bathrooms", "description_present", "quality_flags", "validation_status")
        buffer=io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({**{key: record.get(key) for key in columns if key not in {"description_present", "quality_flags", "validation_status"}}, "description_present": bool(record.get("description_clean")), "quality_flags": ";".join(record["quality_flags"]), "validation_status": validation_status(record)})
        write_text_atomic(jsonl,jsonl_text,replace=args.rebuild_derived)
        write_text_atomic(quality,buffer.getvalue(),replace=args.rebuild_derived)
        print("Corpus export statuses:", dict(Counter(r["export_status"] for r in report)))
        print(f"JSONL records: {len(records)}; quality rows: {len(records)}")
    else:
        report = export_sample()
        print(f"Exported {len(report)} UTF-8 Markdown documents (5 sale, 5 rent).")
    print("Raw and normalized inputs: unchanged; all frontmatter round-trips passed.")


if __name__ == "__main__":
    main()
