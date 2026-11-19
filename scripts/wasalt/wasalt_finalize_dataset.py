"""Finalize/audit the existing 261-property Wasalt dataset without network access."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re

import yaml

from .wasalt_dataset_io import write_text_atomic
from .wasalt_export_markdown import FIELDS, contains_contact
from .wasalt_normalize import PERIODS
from .wasalt_normalize_sample import validation_status


ROOT=REPO_ROOT
DATA=DATA_ROOT
CHALLENGE=re.compile(r'just a moment|verify you are human|checking your browser|404 not found|internal server error|bad gateway',re.I)


def csv_rows(path):
    with path.open(encoding='utf-8',newline='') as handle:
        return list(csv.DictReader(handle))


def csv_text(rows,columns):
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=columns)
    writer.writeheader();writer.writerows(rows)
    return buffer.getvalue()


def audit_dataset():
    normalized_paths=sorted((DATA/'normalized').rglob('*.json'))
    records=[json.loads(p.read_text(encoding='utf-8')) for p in normalized_paths]
    assert len(records)==len({r['listing_id'] for r in records})==len({r['source_url'] for r in records})==261
    assert Counter(r['purpose'] for r in records)=={'sale':131,'rent':130}
    assert len(list((DATA/'raw').rglob('*.json')))==261
    assert len(list((DATA/'properties').rglob('*.md')))==261
    infos=sorted((DATA/'informational').rglob('*.md'));assert len(infos)==5
    jsonl=[json.loads(line) for line in (DATA/'listings.jsonl').read_text(encoding='utf-8').splitlines()]
    assert jsonl==records
    quality={r['listing_id']:r for r in csv_rows(DATA/'quality_report.csv')};assert len(quality)==261
    corpus=[]; fingerprints=defaultdict(list); counts=Counter(); warnings=[]
    acquisition=[]
    for i in range(1,5): acquisition.extend(csv_rows(DATA/f'expansion_batch_{i:02d}_manifest.csv'))
    selected={r['listing_id']:r for r in csv_rows(DATA/'expansion_200.csv')}
    assert len(acquisition)==200
    successes={r['listing_id']:r for r in acquisition if r['extraction_status']=='success'}
    assert len(successes)==199
    failed=[r for r in acquisition if r['extraction_status']!='success']
    assert len(failed)==1 and failed[0]['listing_id']=='5842008' and failed[0]['http_status']=='404'
    assert '5842008' not in {r['listing_id'] for r in records}
    assert not (DATA/'raw/rent/5842008.json').exists()
    for path,n in zip(normalized_paths,records):
        identity=n['listing_id']; purpose=n['purpose']
        assert path==DATA/'normalized'/purpose/f'{identity}.json'
        raw_path=DATA/'raw'/purpose/f'{identity}.json'
        raw=json.loads(raw_path.read_text(encoding='utf-8'))
        p=raw['json_ld']
        for key in ('source','listing_id','source_url','purpose'):assert n[key]==raw[key]
        assert n['scraped_at']==raw['extracted_at']
        assert datetime.fromisoformat(n['scraped_at'].replace('Z','+00:00')).tzinfo is not None
        assert n['schema_org_type']==p.get('@type')
        assert n['description_original']==p.get('description')
        if identity in successes:
            a=successes[identity]
            assert all(n[k]==a[k]==selected[identity][k] for k in ('listing_id','purpose','source_url'))
            assert n['scraped_at']==a['extraction_timestamp']
        offers=p.get('offers') or [];offers=[offers] if isinstance(offers,dict) else offers
        assert len(offers)==1
        offer=offers[0]
        assert Decimal(str(n['price_sar']))==Decimal(str(offer['price']).replace(',',''))
        assert n['price_currency']=='SAR' and offer['priceCurrency'].split('/')[0].strip()=='SAR'
        expected_period=PERIODS.get(offer['priceCurrency'].split('/',1)[1].strip().lower()) if '/' in offer['priceCurrency'] else None
        assert n['price_period']==expected_period
        title_area=re.search(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(?:SQM|m²|m2|sq\.?\s*m)\b',p.get('name',''),re.I)
        if n['area_source']=='title':
            assert title_area and Decimal(str(n['area_sqm']))==Decimal(title_area.group(1))
        if not p.get('floorSize') and not title_area:
            assert n['area_sqm'] is None and n['area_source'] is None
        for source,target in (('numberOfBedrooms','bedrooms'),('numberOfBathroomsTotal','bathrooms'),('numberOfRooms','rooms')):
            if p.get(source) is None:assert n[target] is None
            elif str(p[source]).isdigit():assert n[target]==int(p[source])
        if p.get('description') is None:
            assert n['description_original'] is None and n['description_clean'] is None
        if n['description_clean']:
            assert not contains_contact(n['description_clean']) and not CHALLENGE.search(n['description_clean'])
            if re.search(r'[\u0621-\u064a]',p.get('description') or ''):assert re.search(r'[\u0621-\u064a]',n['description_clean'])
        markdown_path=DATA/'properties'/purpose/f'{identity}.md'
        markdown=markdown_path.read_bytes().decode('utf-8',errors='strict')
        _,front,body=markdown.split('---\n',2);metadata=yaml.safe_load(front)
        assert all(metadata[k]==n[k] for k in FIELDS)
        for key in ('bedrooms','bathrooms'):
            if n[key] is None:assert key not in metadata and f'- {key.capitalize()}:' not in body
            else:assert metadata[key]==n[key]
        if n['area_sqm'] is None:assert '- Area:' not in body
        if n['description_clean']:assert n['description_clean'] in body
        assert f'[Original Wasalt listing]({n["source_url"]})' in body
        assert not contains_contact(markdown) and not CHALLENGE.search(markdown)
        status=validation_status(n)
        q=quality[identity]
        assert q['validation_status']==status and q['quality_flags']==';'.join(n['quality_flags'])
        assert q['description_present']==str(bool(n['description_clean']))
        for key in ('purpose','property_type','city','district','price_sar','area_sqm','bedrooms','bathrooms'):
            assert q[key]==('' if n[key] is None else str(n[key]))
        fingerprint=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        fingerprints[fingerprint].append(identity)
        corpus.append({'document_id':identity,'content_category':'property_'+purpose,'source_url':n['source_url'],'local_output_path':str(markdown_path.relative_to(DATA)),'extracted_at':n['scraped_at'],'validation_status':status})
        counts.update(n['quality_flags'])
    assert not [ids for ids in fingerprints.values() if len(ids)>1], 'Duplicate complete source JSON-LD records'
    for path in infos:
        document=path.read_bytes().decode('utf-8',errors='strict')
        _,front,body=document.split('---\n',2);metadata=yaml.safe_load(front)
        assert not contains_contact(document) and not CHALLENGE.search(document)
        assert metadata['source_url'] in metadata['source_urls']
        corpus.append({'document_id':'informational:'+str(path.relative_to(DATA/'informational')).removesuffix('.md'),
                       'content_category':'informational_'+metadata['content_category'],'source_url':metadata['source_url'],
                       'local_output_path':str(path.relative_to(DATA)),'extracted_at':metadata['extracted_at'],'validation_status':'valid_with_warnings' if '## Extraction Notes' in body else 'valid'})
    assert len(corpus)==len({r['document_id'] for r in corpus})==266
    for flag in ('area_description_mismatch','rooms_description_mismatch','payment_options_in_description'):
        ids=[r['listing_id'] for r in records if flag in r['quality_flags']]
        if ids:warnings.append({'issue':flag,'listing_ids':ids})
    for k in ('description_clean','area_sqm','bedrooms','bathrooms'):
        amount=sum(n[k] is None for n in records)
        if amount:warnings.append({'issue':'missing_'+k,'count':amount})
    report={
        'generated_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'raw_property_files':261,'unique_raw_properties':261,'normalized_records':261,'property_markdown_documents':261,
        'informational_markdown_documents':5,'total_corpus_documents':266,'jsonl_records':len(jsonl),'quality_rows':len(quality),
        'sale_rent_distribution':dict(Counter(r['purpose'] for r in records)),
        'property_type_distribution':dict(sorted(Counter(r['property_type'] for r in records).items())),
        'city_distribution':dict(sorted(Counter(r['city'] for r in records).items())),
        'property_quality_status_distribution':dict(Counter(validation_status(r) for r in records)),
        'corpus_quality_status_distribution':dict(Counter(r['validation_status'] for r in corpus)),
        'missing_fields':{key:sum(r[key] is None for r in records) for key in ('description_clean','area_sqm','bedrooms','bathrooms','rooms','region')},
        'quality_flag_counts':dict(sorted(counts.items())), 'unresolved_source_concerns':warnings,
        'schema_org_types':dict(Counter(str(r['schema_org_type']) for r in records)),
        'collection_range_utc':{'first':min(r['scraped_at'] for r in records),'last':max(r['scraped_at'] for r in records)},
        'excluded_unavailable_listing':{'listing_id':'5842008','http_status':404,'retained_in_acquisition_logs':True},
        'duplicate_ids':0,'duplicate_urls':0,'duplicate_complete_source_records':0,
        'checks':{'raw_metadata_and_description_preserved':True,'prices_and_periods_match_source':True,'decimal_areas_match_source':True,
                  'nulls_not_fabricated':True,'source_urls_preserved':True,'arabic_preserved':True,'contact_scan_clean':True,
                  'no_challenge_content':True,'utf8_valid':True,'portable_relative_paths':True},
        'integration_ready':True,
    }
    return records,corpus,report


def readme_text(report):
    return f'''# Wasalt dataset

Public source: https://wasalt.sa/en. Collected on 18 November 2026 using visible local Playwright Chromium and original embedded JSON-LD. Informational pages use JSON-LD plus selected public rendered content. Acquisition was sequential, bounded, without retries or access-control evasion.

## Coverage

261 unique properties: 131 sale and 130 long-term rent; nine title-derived property types across {len(report['city_distribution'])} source city labels. Five informational documents cover six FAQs, company overview, services (including a short daily-rental introduction), one project and selected real-estate auction terms. There are 266 Markdown documents in total. No daily-rental listings are included.

The sample deliberately favors property-type and listing-ID diversity. It is not a representative market census. Prices, availability, descriptions and project attributes are historical snapshots, not live marketplace data. Listing 5842008 returned HTTP 404, remains in acquisition logs and is excluded from the corpus.

## Files

- `raw/sale/`, `raw/rent/`: 261 original JSON-LD wrappers, with source URL and timestamp. The original manual sale capture is copied byte-for-byte into `raw/sale/5891090.json`; the original remains unchanged in `archive/2026-11-18/manual-wasalt/`.
- `normalized/sale/`, `normalized/rent/`: 261 normalized property JSON files.
- `properties/sale/`, `properties/rent/`: 261 property Markdown documents.
- `informational/`: five informational Markdown documents and their source evidence.
- `listings.jsonl`: exactly the normalized property records, one JSON object per UTF-8 line.
- `quality_report.csv`: property quality flags and statuses; missing numerical values use empty CSV cells and JSON nulls.
- `corpus_manifest.csv`: 266 document entries using paths relative to this folder. Categories `property_sale` and `property_rent` are distinct from `informational_*`. Informational documents retain all contributing URLs in their YAML frontmatter.
- `final_audit_report.json`, `file_integrity.json`: quality counts, distributions, source discrepancies and SHA-256 checksums.
- Acquisition manifests, durable journals, discovery inventory and earlier reports are retained as provenance. Earlier sample reports are historical snapshots, not current corpus totals.

## JSONL schema and Markdown

Each JSONL record includes `source`, string `listing_id`, `source_url`, `purpose`, `property_type`, `schema_org_type`, `title`, `city`, `region`, `district`, `price_sar`, `price_currency`, `price_period`, `area_sqm`, `area_source`, `bedrooms`, `bathrooms`, `rooms`, `description_original`, `description_clean`, `image_url`, `scraped_at`, and `quality_flags`. Missing attributes stay null. SAR rental periods are separate from price, including the source label `SAR /سنة` mapped to `year`.

Markdown uses YAML metadata, a property heading and overview, the cleaned source-language description when present, quality notes and a source link. Descriptions are not automatically translated. Raw captures and `description_original` retain source content and may contain seller contact information; use `description_clean` and prepared Markdown for presentation.

## Known limitations

All 261 properties carry warnings, including title-inferred types and the broad source Schema.org type `SingleFamilyResidence`. Areas generally come from titles; no area is inferred from URL slugs. There are {report['missing_fields']['description_clean']} missing descriptions, {report['missing_fields']['area_sqm']} missing areas, {report['missing_fields']['bedrooms']} missing bedroom counts and {report['missing_fields']['bathrooms']} missing bathroom counts. Missing counts may be inapplicable for land/building/room records. Source city spelling is preserved. Description/structured room and area disagreements are flagged, not silently resolved. No independent availability verification or comprehensive Arabic semantic analysis was performed.

The project source has conflicting east/north location statements and no developer in the captured overview. Daily-rental guidance is brief, and the auction document contains selected excerpts rather than the complete terms. The original 62 normalized records and documents remain unchanged.

## Offline reproduction

Use Python 3.11 and the already installed BeautifulSoup4 and PyYAML packages. No browser or network is required for normalization/export/audit. The reusable scripts are in `scripts/wasalt/`; run package commands from the repository root with the existing `.venv-extraction` interpreter.

On a fresh output copy retaining the original 62 normalized/Markdown records, raw captures and manifests, run:

```bash
.venv-extraction/bin/python -B -m scripts.wasalt.wasalt_normalize_sample --expansion-successes --output-report data/wasalt/expansion_quality.csv
.venv-extraction/bin/python -B -m scripts.wasalt.wasalt_export_markdown --final-corpus --rebuild-derived
.venv-extraction/bin/python -B -m scripts.wasalt.wasalt_finalize_dataset --prepare
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_wasalt_*.py' -v
```

The first command uses only the 199 successful expansion acquisitions. Existing normalized/Markdown files are never overwritten. New report/README/manifest names must be absent in a fresh output copy; existing historical reports can be retained outside that working output copy. `--rebuild-derived` explicitly replaces only `listings.jsonl` and `quality_report.csv`. Do not delete or alter this completed dataset to rerun commands. Audit the completed output without writing:

```bash
.venv-extraction/bin/python -B -m scripts.wasalt.wasalt_finalize_dataset --check
```

The folder is self-contained for data use; keep `scripts/wasalt/` and the archived manual exports with the repository for reproducibility. No RAG, embedding, chatbot or deployment artifacts are included.
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true')
    mode.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.prepare:
        for name in ('corpus_manifest.csv','README.md','final_audit_report.json','file_integrity.json'):
            if (DATA/name).exists():raise FileExistsError(f'Refusing to overwrite {name}')
        manual=DATA/'raw/sale/5891090.json'
        if not manual.exists():
            with manual.open('xb') as handle:handle.write((MANUAL_EXPORTS/'wasalt_5891090.json').read_bytes())
        assert manual.read_bytes()==(MANUAL_EXPORTS/'wasalt_5891090.json').read_bytes()
    records,corpus,report=audit_dataset()
    if args.check:
        assert csv_rows(DATA/'corpus_manifest.csv')==[{k:str(v) for k,v in row.items()} for row in corpus]
        integrity=json.loads((DATA/'file_integrity.json').read_text())
        for path,digest in integrity['sha256'].items():assert hashlib.sha256((DATA/path).read_bytes()).hexdigest()==digest,path
        print('Read-only final audit passed: 261 raw/normalized/property Markdown; 5 informational; 266 manifest entries.')
        return
    write_text_atomic(DATA/'corpus_manifest.csv',csv_text(corpus,corpus[0].keys()))
    write_text_atomic(DATA/'README.md',readme_text(report))
    checksums={str(path.relative_to(DATA)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(DATA.rglob('*')) if path.is_file()}
    report['file_integrity']={'raw_source_files':261,'all_raw_files_sha256_recorded':True,'checked_files':len(checksums),
                              'inventory':'file_integrity.json','audit_and_integrity_files_excluded_from_checksum_inventory':True}
    write_text_atomic(DATA/'file_integrity.json',json.dumps({'algorithm':'SHA-256','sha256':checksums},ensure_ascii=False,indent=2)+'\n')
    write_text_atomic(DATA/'final_audit_report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'city_distribution','unresolved_source_concerns'}},indent=2))


if __name__=='__main__':
    main()
