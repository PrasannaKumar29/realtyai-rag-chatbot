"""Select 200 new Wasalt URLs and four balanced 50-URL batches offline."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

from collections import Counter, defaultdict
import csv
import json
import random

from .wasalt_select_50 import DATA, CORE_TYPES, exclusions, hint_for
from .wasalt_select_sample import COLUMNS, valid_record


SEED = 20261118200


def select_expansion(inventory, excluded):
    rng = random.Random(SEED)
    selected = []
    used = set(excluded)
    for purpose in ("sale", "rent"):
        category = sorted([r for r in inventory if r["purpose"] == purpose and valid_record(r)], key=lambda r: (int(r["listing_id"]), r["source_url"]))
        pools = defaultdict(list)
        for index, row in enumerate(category):
            hint = hint_for(row["source_url"])
            if row["listing_id"] not in used and hint:
                pools[hint].append((min(4, index * 5 // len(category)), row))
        coverage = Counter()

        def choose(hint):
            eligible = [(q, r) for q, r in pools[hint] if r["listing_id"] not in used]
            if not eligible:
                return False
            low = min(coverage[q] for q, _ in eligible)
            eligible = sorted([(q, r) for q, r in eligible if coverage[q] == low], key=lambda pair: pair[1]["source_url"])
            quintile, row = rng.choice(eligible)
            coverage[quintile] += 1
            used.add(row["listing_id"])
            selected.append({
                "listing_id": row["listing_id"], "source_url": row["source_url"],
                "purpose": purpose, "property_type_hint": hint,
                "sample_group": f"{purpose}_numeric_id_quintile_{quintile+1}",
                "selection_reason": f"Seed {SEED}; varied URL type hint and numeric ID range; prior IDs excluded; location not inferred",
            })
            return True

        for hint in CORE_TYPES:
            for _ in range(18):
                if not choose(hint):
                    raise ValueError(f"Insufficient {purpose} {hint} inventory")
        extras = sorted(set(pools) - set(CORE_TYPES))
        rng.shuffle(extras)
        remaining = 10
        while remaining:
            progress = False
            for hint in extras:
                if remaining and choose(hint):
                    remaining -= 1
                    progress = True
            if not progress:
                raise ValueError(f"Insufficient other property types for {purpose}")
    return selected


def main():
    paths = [DATA / "expansion_200.csv"] + [DATA / f"expansion_batch_{index:02d}.csv" for index in range(1, 5)]
    if any(path.exists() for path in paths):
        raise FileExistsError("Expansion output already exists; refusing to overwrite")
    with (DATA / "discovered_urls.csv").open(encoding="utf-8", newline="") as handle:
        inventory = list(csv.DictReader(handle))
    excluded = exclusions()
    rows = select_expansion(inventory, excluded)
    assert rows == select_expansion(inventory, excluded)
    assert len(rows) == len({r['listing_id'] for r in rows}) == len({r['source_url'] for r in rows}) == 200
    assert not set(r['listing_id'] for r in rows).intersection(excluded)
    originals = {(r['listing_id'], r['source_url'], r['purpose']) for r in inventory}
    assert all(valid_record(r) and (r['listing_id'], r['source_url'], r['purpose']) in originals for r in rows)
    assert Counter(r['purpose'] for r in rows) == {'sale':100,'rent':100}
    batches = [[] for _ in range(4)]
    for purpose in ('sale','rent'):
        for index,row in enumerate(r for r in rows if r['purpose']==purpose):
            batches[index % 4].append(row)
    for batch in batches:
        assert len(batch)==50 and Counter(r['purpose'] for r in batch)=={'sale':25,'rent':25}
    assert len({r['listing_id'] for b in batches for r in b})==200
    for path, records in zip(paths, [rows, *batches]):
        with path.open('x',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(records)
    print(f'Seed: {SEED}; excluded IDs: {len(excluded)}; selected 200 unique inventory URLs; reproducibility passed')
    for purpose in ('sale','rent'):
        category=[r for r in rows if r['purpose']==purpose]
        print(purpose,'types:',dict(Counter(r['property_type_hint'] for r in category)),'ID range:',min(int(r['listing_id']) for r in category),max(int(r['listing_id']) for r in category))
        print('ID quintiles:',dict(Counter(r['sample_group'] for r in category)))
    print('Four disjoint batches verified: 50 URLs each, 25 sale + 25 rent.')


if __name__ == '__main__':
    main()
