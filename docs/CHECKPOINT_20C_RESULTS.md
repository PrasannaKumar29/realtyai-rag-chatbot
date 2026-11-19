# Checkpoint 20C — Wasalt listing-ID routing

Objective: route explicit listing-ID questions to the existing exact JSONL property search, avoid false IDs from quantities/contact numbers, and distinguish absent IDs from known listings that fail extra filters. Completed with offline validation only.

## Root cause

The exact reported question was reproduced before editing:

> Show me the details of Wasalt property listing 5891036.

It produced `route='wasalt'` and empty filters. The procedural-intent regex contained unbounded `how.*(?:list|wasalt)`. It matched `how` inside `show`, then matched Wasalt or the `list` substring in `listing`. Procedural intent subsequently overrode the detected numeric ID because `property_intent` required `not procedure`. Informational retrieval then correctly followed the wrong route, restricting evidence to informational documents rather than property records.

A second issue was reproduced: the old detector treated every standalone seven-digit number as a listing ID. It incorrectly added `listing_id='5891036'` to both a SAR 5,891,036 price search and a 5,891,036 sqm area search.

## Files changed

| File | Change |
|---|---|
| `app/property_search.py` | Added contextual listing-ID extraction, bounded English procedural keywords, explicit-ID precedence and clarification for multiple explicit IDs. Exact search now includes lookup-status metadata so absent IDs remain distinct from additional-filter mismatches and unknown attributes. |
| `app/presentation.py` | Adds deterministic English/Arabic notices for IDs absent from the collected dataset, known IDs that mismatch extra filters, and known IDs whose required attributes are unknown. |
| `tests/test_listing_id_routing.py` | New 13-test offline regression suite, including exact source attribution and Streamlit card rendering during a mocked generation failure. |
| `docs/CHECKPOINT_20C_RESULTS.md` | This report. |

Created `artifacts/checkpoint_20c/offline-tests.txt`, `offline-examples.json` and `integrity.json`.

`app/chatbot.py` was inspected but did not require modification. Once the parser returns `properties` with a `listing_id` filter, the existing application already uses JSONL exact filtering, prepares property-only evidence and renders the deterministic card independently of generated prose. No retrieval, citation, UI-layout, ERNIE or fallback-policy code was changed.

## Listing-ID behavior

IDs use the seven-digit format present in the collected dataset. A property/listing noun must introduce the number, optionally followed by a brand, purpose or identifier marker. Supported forms include:

- `Show listing 5891036`
- `Details of Wasalt property 5891036`
- `Tell me about property ID 5891036`
- `Listing #5891036` and `Property no. 5891036`
- `أخبرني عن عقار رقم 5891036`
- `تفاصيل العقار رقم ٥٨٩١٠٣٦`
- Existing contextual villa forms, including `فيلا للايجار ٥٨٩١٠٣٦`

Arabic-Indic digits normalize to the existing string ID; source identifiers are never rewritten. Explicit IDs take precedence over the procedural heuristic. Genuine listing procedures, FAQs, factual and cross-source routes remain available.

Bare numbers or a brand name plus a number do not establish a property ID. The detector rejects quantity suffixes such as SAR, sqm and `/year`, decimal/extended-number forms, and phone-labelled contexts. Numeric spans remain available to the existing price/area parsers, so large numeric constraints no longer acquire an accidental ID filter. Multiple explicit distinct IDs request clarification rather than silently selecting the first.

The ID and any other recognized constraints are applied together through the existing exact classifier. `listing_lookup` records whether that ID exists and, if it does, its exact/unknown/mismatch classification. It does not alter match eligibility:

| Question | Actual offline result |
|---|---|
| Reported failing query | One verified card for 5891036; no semantic retrieval |
| `Show listing 9999999` | “Listing 9999999 is not in the collected Wasalt dataset”; zero cards and no generation/retrieval |
| Arabic request for 5891036 | One verified card and Arabic historical-data disclaimer |
| `Show listing 5891036 in Jeddah` | Known ID, confirmed city mismatch, zero matches; not called absent from the dataset |
| Listing 5872251 requiring six bathrooms | Known ID with unknown bathroom count; not called a confirmed bathroom mismatch |

Listing 5891036 retains the actual JSONL values: villa for rent in An-Narjis, Riyadh; SAR 120,000/year; 250 sqm; nine bedrooms; six bathrooms; original timestamp and quality flags. Its card links to:

[Original Wasalt listing 5891036](https://wasalt.sa/en/property/rent/villa-250-sqm-facing-south-with-9-bedrooms-5891036)

The regression checks that any prepared `[S1]` property evidence points to this same original URL, contains the same ID, and has `content_type='verified_property'`. No FAQ source is substituted. The existing structured-card source link remains authoritative even when OpenRouter fails; no semantic result or model response establishes the identity.

## Tests and integrity

**168 tests passed, zero failures or skips**, in 6.108 seconds: all prior 155 tests plus 13 new regressions.

Coverage includes the exact failure, short/punctuated English forms, Arabic and Arabic-Indic forms, unknown IDs, seven-digit prices and areas, years and phone numbers, combined ID/attribute constraints, known mismatches versus missing attributes, exact JSONL card values and URL selection, genuine procedural/other routes, multi-ID clarification, and card/source/disclaimer rendering during mocked OpenRouter failure. The saved offline examples also assert zero semantic retrieval calls.

After the full suite, SHA-256 checks confirmed **all 2,167 protected files unchanged**, including datasets, chunks, production Chroma and earlier checkpoint artifacts. Immutable read-only SQLite inspection confirms **1,709 records**, 1,536 dimensions, a completed index manifest and the unchanged chunk checksum matching that manifest. Credential-value scanning of changed source/tests and new artifacts found no leaks.

There were **zero live generation requests and zero query-embedding requests**. No scraping, source changes, rechunking, re-embedding, production Chroma opening/modification, dependencies, Docker/deployment, Git staging or commits occurred. Previous validation attempt counters were not touched.

Commands executed included read-only `cat`, `rg` and `sed` inspection, offline before/after routing examples, Python SHA-256 and credential scans, immutable SQLite metadata reads, and:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_listing_id_routing.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Errors or blockers: none remain in offline validation. A focused regression caught `/year` as an additional quantity suffix requiring exclusion; that guard was corrected before the passing focused and complete suites. No live model validation was performed or authorized.

Recommended next step: review the saved offline examples and local card presentation. Agent-driven live requests require a separately authorized budget. No further phase was executed. Stopped after Checkpoint 20C.
