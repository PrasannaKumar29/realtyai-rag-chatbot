"""Deterministic offline selection of 25 new sale and 25 new rent URLs."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random
from urllib.parse import urlsplit

from .wasalt_select_sample import COLUMNS, type_hint, valid_record


ROOT = REPO_ROOT
DATA = DATA_ROOT
SEED = 20261118050
CORE_TYPES = ("apartment", "villa", "land", "floor", "building")


def hint_for(url):
    hint = type_hint(url)
    if hint:
        return hint
    slug = urlsplit(url).path.rsplit("/", 1)[-1]
    for prefix, hint in (("rest-house-", "rest_house"), ("room-", "room"), ("duplex-", "duplex"), ("chalet-", "chalet")):
        if slug.startswith(prefix):
            return hint
    return None


def exclusions():
    excluded = {"5891090", "5891036"}
    excluded.update(path.stem for path in (DATA / "raw").rglob("*.json"))
    for path in MANUAL_EXPORTS.glob("wasalt_*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("listing_id") is not None:
            excluded.add(str(record["listing_id"]))
    for path in DATA.glob("*_manifest.csv"):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("extraction_status") == "success":
                    excluded.add(row["listing_id"])
    return excluded


def select(inventory, excluded):
    rng = random.Random(SEED)
    selected = []
    used = set(excluded)
    for purpose in ("sale", "rent"):
        category = [row for row in inventory if row["purpose"] == purpose]
        pools = defaultdict(list)
        for index, row in enumerate(category):
            if row["listing_id"] not in used and valid_record(row):
                hint = hint_for(row["source_url"])
                if hint:
                    pools[hint].append((min(4, index * 5 // len(category)), row))
        coverage = Counter()

        def choose(hint):
            eligible = [(q, row) for q, row in pools[hint] if row["listing_id"] not in used]
            if not eligible:
                return False
            min_coverage = min(coverage[q] for q, _ in eligible)
            eligible = [(q, row) for q, row in eligible if coverage[q] == min_coverage]
            eligible.sort(key=lambda pair: pair[1]["source_url"])
            quintile, row = rng.choice(eligible)
            used.add(row["listing_id"])
            coverage[quintile] += 1
            selected.append({
                "listing_id": row["listing_id"], "source_url": row["source_url"], "purpose": purpose,
                "property_type_hint": hint, "sample_group": f"{purpose}_inventory_quintile_{quintile + 1}",
                "selection_reason": f"Seed {SEED}; varied URL type hint; inventory quintile {quintile + 1}/5; excludes previously extracted IDs; source verification required",
            })
            return True

        for hint in CORE_TYPES:
            for _ in range(4):
                if not choose(hint):
                    raise ValueError(f"Insufficient new {purpose} {hint} URLs")
        extras = sorted(set(pools) - set(CORE_TYPES))
        rng.shuffle(extras)
        remaining = 5
        while remaining:
            progress = False
            for hint in extras:
                if remaining and choose(hint):
                    remaining -= 1
                    progress = True
            if not progress:
                raise ValueError(f"Insufficient other types for {purpose}")
    return selected


def main():
    output = DATA / "sample_50.csv"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    with (DATA / "discovered_urls.csv").open(encoding="utf-8", newline="") as handle:
        inventory = list(csv.DictReader(handle))
    excluded = exclusions()
    rows = select(inventory, excluded)
    assert rows == select(inventory, excluded)
    assert len(rows) == len({r["listing_id"] for r in rows}) == len({r["source_url"] for r in rows}) == 50
    assert not ({r["listing_id"] for r in rows} & excluded)
    originals = {(r["listing_id"], r["source_url"], r["purpose"]) for r in inventory}
    assert all(valid_record(r) and (r["listing_id"], r["source_url"], r["purpose"]) in originals for r in rows)
    assert Counter(r["purpose"] for r in rows) == {"sale": 25, "rent": 25}
    with output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Seed: {SEED}; excluded IDs: {len(excluded)}; selected: {len(rows)}; reproducibility verified")
    for purpose in ("sale", "rent"):
        print(purpose, dict(Counter(r["property_type_hint"] for r in rows if r["purpose"] == purpose)))
        print('Inventory coverage:',dict(Counter(r['sample_group'] for r in rows if r['purpose']==purpose)))


if __name__ == "__main__":
    main()
