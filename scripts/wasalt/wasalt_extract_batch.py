"""One sequential, bounded extraction from a validated sample manifest."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from .test_wasalt_browser import property_score, records
from .wasalt_select_sample import valid_record


ROOT = REPO_ROOT
SAMPLE = DATA_ROOT / "sample_10.csv"
MANIFEST = DATA_ROOT / "sample_10_manifest.csv"
DELAY_SECONDS = 3
COLUMNS = (
    "listing_id", "purpose", "source_url", "http_status", "extraction_status",
    "json_ld_record_count", "main_property_found", "output_file_path",
    "error_reason", "extraction_timestamp", "json_ld_script_count", "page_title", "failure_category",
)


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def failure_gate(row, consecutive_failures=0):
    """Stop on access restrictions, fatal local errors, or two transient failures."""
    if row["extraction_status"] == "blocked" or row["http_status"] in (401,403,429,"401","403","429"):
        return 0, "Access restriction detected; no further requests"
    if row["http_status"] in (404, 410, "404", "410") or row["extraction_status"] != "failed":
        return 0, None
    error = row.get("error_reason", "")
    if any(marker in error for marker in ("PermissionError", "OSError", "FileNotFoundError", "TargetClosedError")):
        return consecutive_failures + 1, "Systemic browser/storage failure; no further requests"
    consecutive_failures += 1
    if consecutive_failures >= 2:
        return consecutive_failures, "Repeated server/network/extraction failures; no further requests"
    return consecutive_failures, None


def write_json_exclusive(path, value):
    """Publish a complete JSON file atomically, without replacing any file."""
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".wasalt-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # link() fails if the destination exists; readers only see complete data.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def previous_attempts(manifest_path, sample):
    """Read durable attempt records; resumption never retries an earlier attempt."""
    journal = manifest_path.with_suffix(manifest_path.suffix + ".journal")
    if not manifest_path.exists() or not journal.is_dir():
        raise ValueError("Resume requires an existing manifest and its durable journal")
    metadata = json.loads((journal / "batch.json").read_text(encoding="utf-8"))
    identities = [{k: item[k] for k in ("listing_id", "purpose", "source_url")} for item in sample]
    if metadata["listings"] != identities:
        raise ValueError("Resume source belongs to a different sample")
    attempted = set()
    for path in journal.glob("*.started.json"):
        entry = json.loads(path.read_text(encoding="utf-8"))
        attempted.add(entry["listing_id"])
    for path in journal.glob("*.result.json"):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry["extraction_status"] == "blocked":
            raise ValueError("Previous batch hit an access restriction; resumption refused")
        if entry["extraction_status"] != "skipped":
            attempted.add(entry["listing_id"])
    return attempted


def top_records(value):
    """Count top-level JSON-LD records, expanding arrays and @graph containers."""
    if isinstance(value, list):
        for item in value:
            yield from top_records(item)
    elif isinstance(value, dict):
        if "@graph" in value:
            yield from top_records(value["@graph"])
        else:
            yield value


def challenge_detected(page, status, title):
    if status in (401, 403, 429):
        return True
    if any(marker in title.lower() for marker in (
        "just a moment", "attention required", "security verification", "access denied",
    )):
        return True
    if page.locator('#challenge-running, #challenge-form, iframe[src*="challenges.cloudflare.com"]').count():
        return True
    body = page.locator("body").inner_text(timeout=5000).lower()
    return any(marker in body for marker in (
        "verify you are human", "performing security verification",
        "enable javascript and cookies to continue", "checking your browser",
        "sorry, you have been blocked",
    ))


def extract_one(context, item):
    row = {key: "" for key in COLUMNS}
    row.update({key: item[key] for key in ("listing_id", "purpose", "source_url")})
    row.update(extraction_status="failed", main_property_found="No", json_ld_record_count=0,
               json_ld_script_count=0, extraction_timestamp=timestamp())
    output = DATA_ROOT / "raw" / item["purpose"] / f"{item['listing_id']}.json"
    if output.exists():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
            if (not isinstance(existing.get("json_ld"), dict) or not existing["json_ld"]
                    or any(existing.get(k) != item[k] for k in ("listing_id", "purpose", "source_url"))):
                raise ValueError("Existing record identity/content mismatch")
            row.update(extraction_status="skipped", main_property_found="Yes", output_file_path=str(output.relative_to(ROOT)), error_reason="Valid raw output already exists; no request made")
        except (ValueError, TypeError, KeyError):
            row.update(extraction_status="invalid", error_reason="Existing raw output is invalid; preserved without request")
        return row
    page = context.new_page()
    # Permit exactly one top-level document request for this requested listing.
    # Redirects/reloads and document requests for other pages are not followed.
    document_requests = 0

    def guard(route):
        nonlocal document_requests
        request = route.request
        if request.is_navigation_request():
            if request.frame != page.main_frame or request.url != item["source_url"] or document_requests >= 1:
                route.abort()
                return
            document_requests += 1
        route.continue_()

    page.route("**/*", guard)
    try:
        navigation_error = None
        try:
            response = page.goto(item["source_url"], wait_until="domcontentloaded", timeout=45000)
            row["http_status"] = response.status if response else ""
        except Exception as exc:
            navigation_error = type(exc).__name__
        row["page_title"] = page.title()
        if challenge_detected(page, row["http_status"], row["page_title"]):
            row.update(extraction_status="blocked", failure_category="access_restriction", error_reason="Access restriction/challenge detected; stopped without retry")
            return row
        if row["http_status"] in (404, 410):
            row.update(failure_category="unavailable", error_reason=f"Unavailable: HTTP {row['http_status']}; no retry")
            return row
        if navigation_error:
            row["failure_category"] = "network_error"
            row["error_reason"] = "Navigation failed: " + navigation_error
            return row
        if not isinstance(row["http_status"], int) or not 200 <= row["http_status"] < 300:
            row["failure_category"] = "server_error" if isinstance(row["http_status"], int) and row["http_status"] >= 500 else "http_error"
            row["error_reason"] = "Unsuccessful HTTP response"
            return row
        if urlsplit(page.url).path.rstrip("/") != urlsplit(item["source_url"]).path.rstrip("/"):
            row.update(extraction_status="invalid", error_reason="Final URL does not match requested listing")
            return row
        scripts = page.locator('script[type="application/ld+json"]').all_text_contents()
        row["json_ld_script_count"] = len(scripts)
        parsed = []
        errors = []
        for index, script in enumerate(scripts, 1):
            try:
                parsed.append(json.loads(script))
            except (ValueError, TypeError):
                errors.append(f"Invalid JSON-LD script {index}")
        row["json_ld_record_count"] = sum(1 for value in parsed for _ in top_records(value))
        candidates = []
        for value in parsed:
            for record in records(value):
                try:
                    score = property_score(record, item["source_url"], item["listing_id"], row["page_title"])
                except (TypeError, ValueError, AttributeError):
                    errors.append("Invalid property JSON-LD structure")
                    continue
                if score:
                    candidates.append((score, record))
        best = []
        if candidates:
            score = max(score for score, _ in candidates)
            for rank, record in candidates:
                if rank == score and record not in best:
                    best.append(record)
        if len(best) != 1:
            row.update(extraction_status="invalid", failure_category="invalid_json_ld", error_reason="Main property record missing or ambiguous" + ("; " + "; ".join(errors) if errors else ""))
            return row
        row["main_property_found"] = "Yes"
        if errors:
            row.update(extraction_status="invalid", failure_category="invalid_json_ld", error_reason="; ".join(errors))
            return row
        row["extraction_timestamp"] = timestamp()
        wrapper = {
            "source": "wasalt", "source_url": item["source_url"],
            "listing_id": item["listing_id"], "purpose": item["purpose"],
            "extracted_at": row["extraction_timestamp"], "json_ld": best[0],
        }
        write_json_exclusive(output, wrapper)
        row.update(extraction_status="success", output_file_path=str(output.relative_to(ROOT)))
    except Exception as exc:
        if row["http_status"] in (401,403,429):
            row.update(extraction_status="blocked", failure_category="access_restriction", error_reason="Access restriction; inspection stopped: " + type(exc).__name__)
        elif row["http_status"] in (404,410):
            row.update(failure_category="unavailable", error_reason=f"Unavailable: HTTP {row['http_status']}; no retry")
        else:
            row["failure_category"] = "extraction_error"
            row["error_reason"] = "Extraction error: " + type(exc).__name__
    finally:
        page.close()
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, default=SAMPLE)
    parser.add_argument("--output-manifest", type=Path, default=MANIFEST)
    parser.add_argument("--resume-from", type=Path, help="Explicitly resume untouched listings from an earlier journal, using a new output manifest; never retries attempted listings")
    args = parser.parse_args()
    if args.output_manifest.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output_manifest}")
    with args.input_manifest.open(encoding="utf-8", newline="") as handle:
        sample = list(csv.DictReader(handle))
    size = len(sample)
    if (size not in (10, 50) or len({r["source_url"] for r in sample}) != size
            or len({r["listing_id"] for r in sample}) != size
            or Counter(r["purpose"] for r in sample) != {"sale": size // 2, "rent": size // 2}
            or not all(valid_record(r) for r in sample)):
        raise ValueError("Expected exactly 10 or 50 valid unique listings, equally split sale/rent")
    attempted_before = previous_attempts(args.resume_from, sample) if args.resume_from else set()
    journal = args.output_manifest.with_suffix(args.output_manifest.suffix + ".journal")
    if journal.exists():
        raise FileExistsError(f"Refusing to overwrite journal {journal}")
    journal.mkdir()
    write_json_exclusive(journal / "batch.json", {"created_at": timestamp(), "listings": [{k: item[k] for k in ("listing_id", "purpose", "source_url")} for item in sample]})
    # Carry attempt history forward so a second explicit resume cannot retry it.
    for listing_id in attempted_before:
        write_json_exclusive(journal / f"{listing_id}.started.json", {"listing_id": listing_id, "carried_from": str(args.resume_from)})
    outcomes = []
    with args.output_manifest.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        handle.flush()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(service_workers="block")
            try:
                stopped = None
                consecutive_failures = 0
                for index, item in enumerate(sample):
                    if stopped or item["listing_id"] in attempted_before:
                        row = {key: "" for key in COLUMNS}
                        row.update({key: item[key] for key in ("listing_id", "purpose", "source_url")})
                        reason = "Not attempted: " + stopped if stopped else "Previously attempted; no automatic retry (prior raw/result preserved)"
                        row.update(extraction_status="skipped", error_reason=reason, main_property_found="No", extraction_timestamp=timestamp())
                    else:
                        if index:
                            time.sleep(DELAY_SECONDS)
                        output = DATA_ROOT / "raw" / item["purpose"] / f"{item['listing_id']}.json"
                        if not output.exists():
                            write_json_exclusive(journal / f"{item['listing_id']}.started.json", {"listing_id": item["listing_id"], "purpose": item["purpose"], "source_url": item["source_url"], "started_at": timestamp()})
                        try:
                            row = extract_one(context, item)
                        except Exception as exc:
                            row = {key: "" for key in COLUMNS}
                            row.update({key: item[key] for key in ("listing_id", "purpose", "source_url")})
                            row.update(extraction_status="failed", main_property_found="No", failure_category="browser_error", error_reason="Browser/page error: " + type(exc).__name__, extraction_timestamp=timestamp())
                        consecutive_failures, stopped = failure_gate(row, consecutive_failures)
                    write_json_exclusive(journal / f"{item['listing_id']}.result.json", row)
                    writer.writerow(row)
                    handle.flush()
                    os.fsync(handle.fileno())
                    outcomes.append(row)
                    print(item["listing_id"], item["purpose"], row["http_status"], row["extraction_status"], row["error_reason"], flush=True)
            finally:
                context.close()
                browser.close()
    print("Results:", dict(Counter(r["extraction_status"] for r in outcomes)))


if __name__ == "__main__":
    main()
