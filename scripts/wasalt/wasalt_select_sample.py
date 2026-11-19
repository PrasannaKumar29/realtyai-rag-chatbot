"""Select ten Wasalt URLs offline; never access property pages."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

from collections import Counter
import csv
import hashlib
from itertools import permutations
from pathlib import Path
import random
import re
from urllib.parse import urlsplit


ROOT = REPO_ROOT
INVENTORY = DATA_ROOT / "discovered_urls.csv"
OUTPUT = DATA_ROOT / "sample_10.csv"
SEED = 20261118
MIN_ID_GAP = 100
TYPES = ("apartment", "villa", "land", "floor", "building")
COLUMNS = ("listing_id", "source_url", "purpose", "property_type_hint", "sample_group", "selection_reason")


def type_hint(url):
    slug = urlsplit(url).path.rsplit("/", 1)[-1]
    match = re.match(r"(?:(?:semi-)?furnished-)?(apartment|villa|land|floor|building)(?:-|$)", slug)
    if not match:
        match = re.match(r"\d+-bedrooms?-(apartment|villa|land|floor|building)-", slug)
    return match.group(1) if match else None


def valid_record(row):
    parts = urlsplit(row["source_url"])
    match = re.fullmatch(r"/en/property/(sale|rent)/[a-z0-9.,-]+-(\d+)", parts.path)
    return bool(
        parts.scheme == "https" and parts.netloc == "wasalt.sa"
        and not parts.query and not parts.fragment and match
        and match.group(1) == row["purpose"] and match.group(2) == row["listing_id"]
    )


def select_sample(inventory):
    rng = random.Random(SEED)
    sample = []
    for purpose in ("sale", "rent"):
        # Keep source inventory order so quintiles reflect sitemap coverage.
        category = [r for r in inventory if r["purpose"] == purpose]
        pools = {}
        for index, row in enumerate(category):
            if not valid_record(row):
                continue
            hint = type_hint(row["source_url"])
            if hint in TYPES:
                quintile = min(4, index * 5 // len(category))
                pools.setdefault((quintile, hint), []).append(row)
        orders = list(permutations(TYPES))
        rng.shuffle(orders)
        selected = None
        for order in orders:
            trial = []
            for quintile, hint in enumerate(order):
                used = [int(r["listing_id"]) for r in sample + trial]
                candidates = [r for r in pools.get((quintile, hint), []) if all(abs(int(r["listing_id"]) - other) >= MIN_ID_GAP for other in used)]
                # Stable ordering makes the seeded choice independent of dict order.
                candidates.sort(key=lambda r: r["source_url"])
                if not candidates:
                    break
                row = rng.choice(candidates)
                trial.append({
                    "listing_id": row["listing_id"], "source_url": row["source_url"],
                    "purpose": purpose, "property_type_hint": hint,
                    "sample_group": f"{purpose}_inventory_quintile_{quintile + 1}",
                    "selection_reason": (
                        f"Seed {SEED}; one {hint} URL hint for {purpose}; "
                        f"inventory quintile {quintile + 1}/5; ID gap >= {MIN_ID_GAP}; "
                        "property type requires source verification"
                    ),
                })
            if len(trial) == 5:
                selected = trial
                break
        if selected is None:
            raise ValueError(f"Cannot meet diversity/spread constraints for {purpose}; no output written")
        sample.extend(selected)
    return sample


def validate_sample(sample, inventory):
    assert len(sample) == 10
    assert len({r["source_url"] for r in sample}) == 10
    assert len({r["listing_id"] for r in sample}) == 10
    assert Counter(r["purpose"] for r in sample) == {"sale": 5, "rent": 5}
    originals = {(r["source_url"], r["listing_id"], r["purpose"]) for r in inventory}
    for row in sample:
        assert (row["source_url"], row["listing_id"], row["purpose"]) in originals
        assert valid_record(row)
        assert row["property_type_hint"] == type_hint(row["source_url"])
    for purpose in ("sale", "rent"):
        group = [r for r in sample if r["purpose"] == purpose]
        assert Counter(r["property_type_hint"] for r in group) == {t: 1 for t in TYPES}
        assert {r["sample_group"] for r in group} == {f"{purpose}_inventory_quintile_{i}" for i in range(1, 6)}
    ids = sorted(int(r["listing_id"]) for r in sample)
    assert all(b - a >= MIN_ID_GAP for a, b in zip(ids, ids[1:]))
    assert sample == select_sample(inventory), "Seeded selection is not reproducible"


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    original_bytes = INVENTORY.read_bytes()
    with INVENTORY.open(encoding="utf-8", newline="") as handle:
        inventory = list(csv.DictReader(handle))
    sample = select_sample(inventory)
    validate_sample(sample, inventory)
    with OUTPUT.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sample)
    with OUTPUT.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == sample
    assert INVENTORY.read_bytes() == original_bytes
    print(f"Seed: {SEED}; inventory SHA-256: {hashlib.sha256(original_bytes).hexdigest()}")
    for row in sample:
        print(row["listing_id"], row["purpose"], row["property_type_hint"], row["sample_group"])
    print("All validation checks passed; reproducibility and saved CSV verified.")
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
