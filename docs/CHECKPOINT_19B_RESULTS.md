# Checkpoint 19B — Indexing and live retrieval results

Completed 19 November 2026. Only the approved embedding/indexing and five retrieval tests were executed. No chatbot, answer generation, structured-property search or deployment was implemented.

## Execution and usage

| Metric | Result |
|---|---|
| Indexed chunks | 1,709 unique records, all 1,536 dimensions |
| Model / collection / distance | text-embedding-3-small / real_estate_knowledge / cosine |
| Indexing wall time | 28.30 seconds |
| Peak indexing process RSS | 275.438 MiB |
| Complete index directory size | 40,817,327 bytes (38.926 MiB), seven files |
| Indexing | 23 requests, zero retries; 611,245 reported input tokens |
| Retrieval | Five requests, zero retries; 76 reported input tokens |
| All requests | 28 HTTP 200 responses; zero transport failures |
| Estimated indexing cost | USD 0.0122249 |
| Estimated total cost including queries | USD 0.01222642 |
| Approved indexing ceiling | USD 0.25 |
| Safe resume | Zero requests/tokens; no duplicate records |
| Full test suite | 89 passed; zero failures or skips |

Costs use the approved USD 0.02/million-token planning rate and returned usage; they are not a billing receipt. Credentials never appear in the reports. Temporary request instrumentation counted attempts/status/usage only; it did not log headers, request bodies, keys or source texts.

## Integrity and persistence

All original 1,709 chunk IDs, texts and metadata matched the persisted collection. Every vector was checked for the configured dimensions and finite nonzero values. Source counts were DarGlobal 1,411, Wasalt properties 289 and Wasalt informational nine. All required metadata was present; source URLs and property listing IDs were preserved. Batch-ID alignment remained consistent with original source order. A fresh process reopened and verified the production collection successfully.

The complete manifest is `artifacts/chroma/index_manifest.json`, with successful validation, 23 completed batch entries and 611,245 reported API input tokens. No pending checkpoint or active lock remains. All 2,094 files under `data/` and `artifacts/chunks/` retained their SHA-256 hashes. Chunk-file SHA-256: `09f4c8eac0e0d250e8085fc5ed1dfb1f76f1ef60119c622af763d89690d679a1`.

## Retrieval results

These are the five actual live questions, with five results each. All queries used the stated source filter; every result passed it. Cosine distance is lower for closer matches and is not a probability or answer-confidence score. Relevance assessments were made offline against full existing chunk text and metadata, without new API requests.

### q01 — What amenities does Trump Dubai offer?

**Source filter:** darglobal. **Assessment:** Strong top-four evidence; the fifth result is a different-country Trump portfolio chunk.

| Rank | Full chunk ID | Document title | Source URL | Distance | Relevance |
|---|---|---|---|---:|---|
| 1 | `chunk_371a74a9e0b7dced89ceb117ecbd634833ba53f6579c1e6fb257c2d32500cf40` | Trump International Hotel & Tower Dubai \| DarGlobal | [Source](https://darglobal.co.uk/trump-international-hotel-and-tower-dubai) | 0.257476 | Directly relevant: resident rooftop pool, gym, owners lounge and children's play area. |
| 2 | `chunk_6c5e07344bdd5c4b9fb5e92eb5334536dd9c05b3a78d17e908d2736702f4b4f8` | Trump International Hotel & Tower Dubai \| DarGlobal | [Source](https://darglobal.co.uk/trump-international-hotel-and-tower-dubai) | 0.262884 | Relevant: project FAQ and private-club amenities; distinguish membership access. |
| 3 | `chunk_05d347de338a42b66e99d2d354c3a53eabcede9491ac420486498ade30f9492e` | DarGlobal and The Trump Organization Launch Dubai's New Icon, Trump International Hotel & Tower | [Source](https://darglobal.co.uk/press/dar-global-trump-organization-launch-trump-hotel-tower-dubai) | 0.296300 | Relevant: project launch describes pools, lounges and club. |
| 4 | `chunk_70080948ef60922c86d88c6bd08e6bdaa4210c8cdc9e8c0ce0a268a020d0c544` | DarGlobal and The Trump Organization Launch Dubai's New Icon, Trump International Hotel & Tower | [Source](https://darglobal.co.uk/press/dar-global-trump-organization-launch-trump-hotel-tower-dubai) | 0.301836 | Relevant but overlapping press coverage of the same project. |
| 5 | `chunk_5f7cd1aa9903c1c24dd952fa21086bfe0d4aa7f5db4073cf689af63a73abad2f` | Trump Branded Residences Gulf \| DarGlobal Portfolio | [Source](https://darglobal.co.uk/partners/the-trump-organization) | 0.326900 | Off-topic for Dubai amenities: this chunk describes AIDA in Oman and Jeddah. |

### q02 — What projects does DarGlobal have in Spain?

**Source filter:** darglobal. **Assessment:** Mixed retrieval: useful named-project evidence at rank five, with broad background and press-hub false positives above it.

| Rank | Full chunk ID | Document title | Source URL | Distance | Relevance |
|---|---|---|---|---:|---|
| 1 | `chunk_59028523a5f102a137b4fe309d2fec455ee6898b4807117cc2df2cb3fb20238d` | DarGlobal's Agents Event Debuts in Spanish Real Estate | [Source](https://darglobal.co.uk/press/dar-globals-agents-event-paves-the-way-for-a-spectacular-debut-in-spanish-real-estate) | 0.341504 | Partial: Spanish market entry and Costa del Sol plans, without named Spanish projects in this chunk. |
| 2 | `chunk_97ba7d25ae083e0efbf4c4e85c954f2b718df07b563412485754d074a7f793f0` | DarGlobal Appoints Ene Construccion Amaz SL as Main Contractor for Tierra Viva – A Luxury Villa Development with Design Inspired by Automobili Lamborghini | [Source](https://darglobal.co.uk/press) | 0.371512 | Poor evidence: Tierra Viva title, but chunk body is a generic press listing with unrelated items. |
| 3 | `chunk_4eae997234200ac57dc2fcda97a37500ee7b778cf0873391c9e40350f403bb1f` | DarGlobal \| International Luxury Real Estate Developer | [Source](https://darglobal.co.uk/) | 0.371868 | Partial background: corporate presence in Spain; no specific project list. |
| 4 | `chunk_96c8f5ead208a165f2d6f71fe13a981d0afa14a0a2fb0faee7a0fa8fa5854bed` | DarGlobal Appoints Ene Construccion Amaz SL as Main Contractor for Tierra Viva – A Luxury Villa Development with Design Inspired by Automobili Lamborghini | [Source](https://darglobal.co.uk/press) | 0.387392 | Poor evidence: same inherited Tierra Viva title; body contains unrelated press-list items. |
| 5 | `chunk_8ab26854bca6eb136a9d74077e44f64ef61760dbae565bf0dba7cd087890b003` | Redefining Real Estate Development for the Discerning Buyer | [Source](https://darglobal.co.uk/blog/redefining-real-estate-development-for-the-discerning-buyer) | 0.392291 | Relevant: explicitly names Tierra Viva in Benahavis and Marea on the Costa del Sol. |

### q03 — How can I list my property on Wasalt?

**Source filter:** wasalt. **Assessment:** Direct FAQ answer ranked first. Lower results become broad or unrelated.

| Rank | Full chunk ID | Document title | Source URL | Distance | Relevance |
|---|---|---|---|---:|---|
| 1 | `chunk_d1f621eb5227b9e6ae07c6962cc90a6ed9c078cbf2d0c61f0568e7480efd4587` | Wasalt — Frequently Asked Questions | [Source](https://wasalt.sa/en) | 0.315784 | Direct answer: FAQ explains account creation, details/photos and pricing. |
| 2 | `chunk_754318ef57c1850329a4b9e35fe16c08c2a636086e09615226656eb4fde373f5` | Wasalt — Public Services | [Source](https://wasalt.sa/en/corporate) | 0.392512 | Related services background, not the complete listing procedure. |
| 3 | `chunk_c899280f019758c760f746d382fce5daca0cd9f834a18bf0a8ea953fc9e57012` | Wasalt — Company and Platform Overview | [Source](https://wasalt.sa/en/corporate) | 0.417294 | Related platform background, not a step-by-step listing answer. |
| 4 | `chunk_a29e0e04d131cc75493ea14edef886597b82cac8fdb5cdaa7c412b7de6daffb3` | Wasalt — Real Estate Auctions and Selected Public Terms | [Source](https://wasalt.sa/en) | 0.522657 | Different workflow: auction terms, not general property listing. |
| 5 | `chunk_a75a59db46a57ebdce6417294ae8876a2789b082567cbf25f45858a154a9c96b` | Land 500 SQM Facing West | [Source](https://wasalt.sa/en/property/rent/land-500-sqm-facing-west-5887210) | 0.526277 | Not relevant: an individual rental land listing. |

### q04 — Villas for rent in Riyadh.

**Source filter:** wasalt. **Assessment:** All five results match villa/rent/Riyadh in existing metadata. This is not a guarantee of arbitrary structured constraints.

| Rank | Full chunk ID | Document title | Source URL | Distance | Relevance |
|---|---|---|---|---:|---|
| 1 | `chunk_75d768a1f45752202d82fa006bf750df5b65be842ce685e9b999c801b9db1928` | Villa 250 SQM Facing West with 5 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-250-sqm-facing-west-with-5-bedrooms-5890394) | 0.385460 | Relevant: villa, rent, Riyadh; listing 5890394. |
| 2 | `chunk_66bf9f2f51fb670115bd38149adcee7519bbcab5a54feaababb79bbb63d52d67` | Villa 240 SQM Facing East with 4 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-240-sqm-facing-east-with-4-bedrooms-5872251) | 0.390154 | Relevant: villa, rent, Riyadh; listing 5872251. |
| 3 | `chunk_ec8d93b4c4e84c6177c020b3ff5aa876b2093af0b07e2cb4beaaa95878ac71e6` | Villa 650 SQM Facing South with 6 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-650-sqm-facing-south-with-6-bedrooms-5896807) | 0.390464 | Relevant: villa, rent, Riyadh; listing 5896807. |
| 4 | `chunk_3cd9bda573da174e5e4280d20f59398a0498ead3120dcf2c15c87e0b9328261b` | Villa 200 SQM Facing North with 6 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-200-sqm-facing-north-with-6-bedrooms-5870346) | 0.391370 | Relevant: villa, rent, Riyadh; listing 5870346. |
| 5 | `chunk_9507296ebcdd3a7604e36fe8b7de7c6ac7d67b8256c7225c082a38b2afc91d4d` | Villa 195 SQM Facing East with 5 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-195-sqm-facing-east-with-5-bedrooms-5907001) | 0.391506 | Relevant: villa, rent, Riyadh; listing 5907001. |

### q05 — فيلا للإيجار في حي النرجس بالرياض بمساحة 250 متر و6 دورات مياه

**Source filter:** wasalt. **Assessment:** The exact existing Arabic rental match ranked first. Lower results fail several requested attributes.

| Rank | Full chunk ID | Document title | Source URL | Distance | Relevance |
|---|---|---|---|---:|---|
| 1 | `chunk_ce20e3bb25748b7c41d788698a7b37a35c7e5fa2e8476f3ccaec58c1f6f5a789` | Villa 250 SQM Facing South with 9 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-250-sqm-facing-south-with-9-bedrooms-5891036) | 0.364372 | Exact structured match: listing 5891036, villa rental in An-Narjis, Riyadh; 250 sqm and six bathrooms. |
| 2 | `chunk_f9d65e495fc5045dd3494a97b4489bf6fcd7e4077e3c50d292551f1a117ee031` | Floor 165 SQM with 6 Bedrooms | [Source](https://wasalt.sa/en/property/rent/floor-165-sqm-with-6-bedrooms-5862272) | 0.395749 | Weak: rental floor in Bader, Riyadh; wrong type, district and area. |
| 3 | `chunk_8abc6437b782c2f7bf7de634c32ebb3aff641d253216680916c65e2b18d95fa6` | Floor 234.46 SQM with 3 Bedrooms | [Source](https://wasalt.sa/en/property/rent/floor-23446-sqm-with-3-bedrooms-5902941) | 0.412966 | Weak: rental floor in Al-Janadriyah, Riyadh; wrong type, district and area. |
| 4 | `chunk_6e2c64b0fb33dc91d1068db25eb15ce0d53d5c511835f13f72629cc48ce203e1` | Building 158 SQM Facing North | [Source](https://wasalt.sa/en/property/rent/building-158-sqm-facing-north-5833997) | 0.427602 | Not a match: rental building in Makkah, not the requested Riyadh villa. |
| 5 | `chunk_75d768a1f45752202d82fa006bf750df5b65be842ce685e9b999c801b9db1928` | Villa 250 SQM Facing West with 5 Bedrooms | [Source](https://wasalt.sa/en/property/rent/villa-250-sqm-facing-west-with-5-bedrooms-5890394) | 0.430132 | Partial: Riyadh villa rental, 250 sqm, but different district and no bathroom count. |

## Retrieval weaknesses and recommendations

The Spain query retrieved a press record whose title names Tierra Viva but whose preserved body is the generic `/press` listing, not that article. Two such chunks ranked second and fourth. This inherited source/title mismatch can cause false-positive evidence. Actual Tierra Viva and Marea development documents are present in the corpus but did not reach this query's top five; the useful named-project answer appeared in a blog chunk at rank five. Report this as a source-quality and ranking limitation; no source text, chunk policy or embeddings were changed.

The Trump question found relevant amenities in its first four results, but the fifth result described other countries. The FAQ question found the exact answer first, with off-topic lower results. The English property query matched five verified Riyadh villa rentals. The Arabic query correctly ranked listing 5891036 first, while lower results included wrong types/districts and one wrong city.

Future approved work should evaluate category routing, source-quality exclusions/flags, document diversification or reranking, and separate structured property constraints. These are recommendations only. Do not treat semantic similarity as proof of city, area, price or availability; listing snapshots remain historical.

## Commands executed

Preflight: `.venv-extraction/bin/python -B -m app.index_embeddings --dry-run`.

Production indexing and safe resume used the existing command:
```bash
.venv-extraction/bin/python -B -m app.index_embeddings --execute
```

The production execution was wrapped with `/usr/bin/time -l` for resource measurements and temporary HTTPX instrumentation for request counts. Each retrieval executed the existing CLI, with one OpenAI query embedding call:
```bash
.venv-extraction/bin/python -B -m app.search --query 'What amenities does Trump Dubai offer?' --top-k 5 --source darglobal
.venv-extraction/bin/python -B -m app.search --query 'What projects does DarGlobal have in Spain?' --top-k 5 --source darglobal
.venv-extraction/bin/python -B -m app.search --query 'How can I list my property on Wasalt?' --top-k 5 --source wasalt
.venv-extraction/bin/python -B -m app.search --query 'Villas for rent in Riyadh.' --top-k 5 --source wasalt
.venv-extraction/bin/python -B -m app.search --query 'فيلا للإيجار في حي النرجس بالرياض بمساحة 250 متر و6 دورات مياه' --top-k 5 --source wasalt
```

Tests: `.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v`. Additional offline audit commands checked persisted content, source hashes, file sizes and request logs.

A restricted macOS timing wrapper reported `sysctl kern.clockrate: Operation not permitted` after the first successful zero-call resume. The resume output and HTTP metrics confirmed completion; a subsequent plain resume exited zero with zero API calls. Production indexing measurements came from the successful initial timed execution. No embedding request was repeated because of the timing warning.

## Output files and readiness

- `artifacts/chroma/`: production database and completed manifest, seven files.
- `artifacts/checkpoint_19b/`: indexing/query request counters, timing logs, all 25 retrieved results with excerpts, offline relevance assessments, index audit, safe-resume results, test output and consolidated `final_report.json`.
- `docs/CHECKPOINT_19B_RESULTS.md`: this report. Existing application code and source data were not modified.

The index is technically ready for chatbot integration. The five-question check is not a comprehensive relevance benchmark; the documented source/ranking weaknesses need handling in later approved work. Peak indexing RSS on this Mac does not establish the eventual combined application's fit within Render's 512 MB instance. No full reindex is required or recommended for this checkpoint. Await approval before starting the next phase.
