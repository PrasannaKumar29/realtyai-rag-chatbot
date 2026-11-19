# Checkpoint 20 — Local DarGlobal + Wasalt chatbot

Objective: implement and validate the local Streamlit chatbot using the existing corpus, prebuilt Chroma index and approved ERNIE endpoint. Local implementation is complete. Live generation validation is partially blocked by OpenRouter rate limits. No deployment, Docker work, Git staging or commits occurred.

The explicit Checkpoint 20 approval supersedes the older maintenance-only scope in AGENTS.md for this checkpoint. Streamlit installation was separately approved in this session. Source datasets, original chunks, embeddings and earlier evaluation artifacts were preserved.

## Files created and actions performed

No pre-existing repository source or documentation files were overwritten.

| New file | Purpose |
|---|---|
| `app/property_search.py` | Bounded English/Arabic interpretation and exact JSONL filtering |
| `app/chatbot.py` | Retrieval tools, source selection, ERNIE adapter, citation guardrails and bounded conversation |
| `app/streamlit_app.py` | Chat, example questions, history, exact-search form, listing cards and error handling |
| `app/requirements-chatbot.txt` | Runtime dependency pins matching the installed direct packages |
| `app/validate_chatbot.py` | One-run-only validation runner with a five-request cap and resource sampling |
| `tests/test_chatbot.py` | 18 offline application regressions |
| `tests/test_chatbot_ui.py` | Two Streamlit application interaction/rendering tests |
| `docs/CHECKPOINT_20_RESULTS.md` | This report |

Created `artifacts/checkpoint_20/`: five `qNN_started.json` attempt markers, five `qNN.json` results, `started.json`, `resources.json`, `ui_resources.json`, `offline-tests.txt`, and `integrity.json`. These local artifacts remain subject to the existing Git-ignore policy.

Installed Streamlit 1.67.0 and its required dependencies into `.venv-extraction`, using the bundled pip wheel because that environment has no installed pip executable. Existing OpenAI/Chroma versions were reused. The new runtime requirements file pins the observed installed direct dependencies; it is not a complete platform-specific transitive lock.

## Architecture and routing

`Streamlit → bounded interpretation → explicit retrieval/filter tool → trusted evidence IDs → ERNIE → citation validation`.

- DarGlobal factual questions use source-filtered semantic retrieval, plus a development-category candidate search using the same query vector.
- Wasalt informational questions query only the five informational categories. Property documents cannot enter this retrieval tool.
- Property requests filter JSONL before any generation. Pure structured searches require no query embedding or Chroma query. Their cards come directly from JSONL, independently of model output.
- Cross-source questions retrieve up to three chunks per source. Cross-source property questions additionally apply the structured property filter first; property eligibility never comes from similarity. Optional property semantic ranking was not needed and is not implemented.
- Ambiguous routes and unsupported constraints ask for clarification without a generation call. The exact-search form supports source city/district labels directly. Arabic aliases cover common locations and property terms; this small parser is not a general natural-language query engine. Unrecognized numeric constraints are rejected instead of silently discarded. Follow-up questions without a clear topic may need the user to restate it.

Retrieval reuses `EmbeddingClient`, `ChromaStore`, the existing chunk loader and manifest validation. Startup verifies index identity, all IDs, stored text/metadata and vector dimensions once. Chroma opens a temporary copy of the entire index so even housekeeping writes cannot affect the production index. The copy costs approximately 39 MiB of temporary disk per process. No model or tokenizer download occurs.

Candidate selection excludes the generic `/press` hub regardless of inherited title. It favors relevant development documents, limits each source URL to two chunks, and filters unrelated Trump/Dubai and Spain candidates narrowly. The distance cutoff is a heuristic, not a calibrated confidence score. Original metadata and IDs remain unchanged.

History is limited to 20 stored messages and four prompt history messages of at most 1,000 characters each. Questions are limited to 1,500 characters. Evidence is capped at six semantic chunks, plus at most five property records for a mixed query. History is not treated as evidence.

## Structured filtering

Actual JSONL inspection confirmed 261 records, separate `price_sar`/`price_period` fields, null missing attributes, source-quality flags and original source URLs. The search supports purpose, city, district, property type, listing ID, maximum/minimum price, rental period, minimum/exact bedrooms, minimum/exact area and exact bathroom counts when interpreted. The form exposes the core required filters.

Text “under” is strictly less than; “up to” and the form's maximum price are inclusive. Rental budgets require a period. Monthly and daily requests are not silently converted to annual prices. Specified categorical values match exactly after case/Arabic normalization; explicit aliases map to preserved source labels.

Each record is classified as exact, unknown, or confirmed mismatch. A record with an unknown required attribute and no known mismatch is counted separately, never presented as an exact match. Unknown values are not zero. A record can retain both missing-field and mismatch details internally.

Cards display the original listing ID, attributes, capture timestamp, quality flags and clickable original URL. Results are ordered by recorded price, then ID, with at most ten displayed. Match totals make truncation explicit. The historical-snapshot disclaimer is added by application code in English or Arabic. Cards remain usable when generation fails.

## ERNIE and citations

Only `baidu/ernie-5.5-flash-preview:free` is enabled. `OPENROUTER_MODEL`, if supplied, must equal that ID. Nemotron remains a candidate only; no fallback was implemented.

The runtime reuses the proven OpenRouter request adapter: reasoning enabled, temperature 0, 4,000 completion tokens, non-streaming, provider fallback disabled, required parameter support, prompt/completion price caps of zero, redirects disabled and no retries. It rejects wrong returned models, empty/malformed or truncated answers, nonzero reported cost and failed requests. Credentials come from process environment or root `.env`, with process values taking precedence. Query embeddings also have retries disabled in this runtime.

Application-assigned source IDs map to actual evidence URLs. Model URLs, HTML, unknown source IDs and missing citations cause response rejection. Only cited sources appear in the UI source list. Explicit current-availability claims are blocked, and property disclaimers do not depend on the model. The prompt additionally prohibits unsupported features, guessed attributes and silent resolution of source ambiguity.

Citation syntax checks do not establish that every claim is entailed. Availability detection is phrase-based, not a complete semantic safety guarantee. Human review is still needed for generated claims; the property cards themselves use verified values.

## Tests and five end-to-end results

Final full suite: **123 tests passed, zero failures or skips** in 5.757 seconds: all 103 prior tests plus 20 chatbot/UI tests. The final log is `artifacts/checkpoint_20/offline-tests.txt`.

Coverage includes four routes and ambiguity, actual JSONL constraints, strict price boundaries, rental periods, nulls versus mismatches, Arabic filtering, both-source tool scopes, informational-only retrieval, press-hub exclusion, source diversification, rejected citations/links/current availability, insufficient evidence, bounded history, service failures, ERNIE reasoning settings and UI conversation/cards. UI interaction tests use mocked services; a separate resource run loaded real Chroma/JSONL and rendered listing 5891036 with mocked generation, without an API request.

Exactly five fresh ERNIE requests were attempted through the complete chatbot pipeline. There were three fresh OpenAI query-embedding calls for the semantic questions; structured requests used JSONL directly. No document embeddings were regenerated. No retries, paid OpenRouter models, fallback or replay of frozen 19D evidence occurred.

| Question | Actual result | End-to-end seconds |
|---|---|---:|
| Trump Dubai amenities | Generated answer; valid citations to development and specific press articles | 9.723 |
| DarGlobal developments in Spain | OpenRouter HTTP 429; graceful error, no generated answer | 1.362 |
| Wasalt property-listing procedure | OpenRouter HTTP 429; graceful error, no generated answer | 0.559 |
| Riyadh rental villas under SAR 100,000/year | Eight exact matches and deterministic cards; OpenRouter HTTP 429 prevented narrative | 0.213 |
| Arabic request for listing 5891036, An-Narjis/Riyadh, 250 sqm, six bathrooms | One exact match and deterministic card; OpenRouter HTTP 429 prevented Arabic narrative | 0.217 |

The eight rental IDs/prices are: `5872251` SAR 39,000; `5907001` SAR 50,000; `5911445` SAR 60,000; `5923347` SAR 60,000; `5890394` SAR 65,000; `5870346` SAR 80,000; `5896807` SAR 80,000; `5918803` SAR 80,000. Every returned record is a Riyadh villa, for rent, with `price_period=year` and price strictly below SAR 100,000.

Listing `5891036` has recorded price SAR 120,000/year, area 250 sqm, nine bedrooms and six bathrooms. It correctly does not enter the under-SAR-100,000 search. All displayed records passed independent rechecking against the applied filters. Missing bathroom attributes in alternatives were not called confirmed bathroom mismatches.

Manual review of the successful amenities answer found support for resident amenities, paid club access and hotel facilities. It explicitly preserved the conflict between resident-only pool access and press wording mentioning residents and guests. All five cited IDs exist and resolve to original URLs; two IDs point to separate chunks of the development page and two to separate chunks of the launch article. No generic press-hub evidence was cited. The sky-pool statement is supported by the launch article; the accompanying construction article separately supports the two-penthouse detail.

Only **one of five generations succeeded**. The four rate-limited narratives have not been validated live. Request budget is exhausted for this checkpoint. Their saved results preserve the actual failures; a later offline improvement makes the property fallback text affirm the verified cards rather than show a generic generation-failure sentence. No live request was repeated for that change.

## Resources and local startup

Measured in a fresh macOS process importing Streamlit and the real application, with RSS sampled during the live queries:

| Stage | Memory |
|---|---:|
| Python startup | 19.02 MiB RSS |
| After Streamlit/application imports | 56.55 MiB RSS |
| After complete Chroma validation | 245.45 MiB RSS |
| Highest sampled RSS during queries | 267.86 MiB RSS |
| Peak RSS after all five queries | 267.88 MiB |
| Separate full Streamlit AppTest harness, real Chroma plus rendered listing card, mocked generation | 310.23 MiB peak RSS |

Runtime initialization took 0.990 seconds. The successful generation service call took 7.971 seconds, within the 9.723-second complete query. Rate-limit response timings are failure latencies, not successful-answer performance.

The server started successfully, and `http://127.0.0.1:8501/_stcore/health` returned HTTP 200 `ok`. The browser integration could not obtain a browser connection. No desktop/mobile screenshot inspection was possible; UI validation used Streamlit AppTest instead. The first card-rendering test exceeded AppTest's three-second default timeout during cold imports; the explicit 30-second test timeout passed, followed by the final full suite.

Exact local startup command, from the repository root:

```bash
.venv-extraction/bin/python -B -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

The local server was left running at `http://127.0.0.1:8501` for review. Do not start a second instance on that occupied port.

Runtime path settings: `CHROMA_PATH`, `CHROMA_COLLECTION`, `CHUNKS_PATH`, `TOKENIZER_CACHE` and `WASALT_LISTINGS_PATH`. Defaults resolve from repository location; no user-machine absolute paths are embedded in the runtime. OpenAI configuration reuses the existing `OPENAI_EMBEDDING_MODEL`/`OPENAI_EMBEDDING_DIMENSIONS` contract and must match the index manifest.

## Integrity, commands, blockers and recommended next step

SHA-256 comparison: **2,145 protected files unchanged**, covering `data/`, existing chunks, production Chroma and Checkpoints 19C/19D. The saved integrity report found no credential values in the new source/test/results files. No scraping, source modification, rechunking, indexing, earlier model evaluation or original timestamp rewriting occurred.

Commands executed included the following, plus read-only `cat`, `rg`, schema/hash inspection and Streamlit AppTest Python snippets:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_chatbot.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_chatbot*.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv-extraction/bin/python -B -m app.validate_chatbot
.venv-extraction/bin/python -B -m app.validate_chatbot --execute
```

The execute command refuses to run again because its output directory already exists. Do not delete results to bypass this guard. Dependency installation used the existing `ensurepip/_bundled/pip-26.3-py3-none-any.whl` through `runpy`, invoking `pip install --retries 0 streamlit` after approval. The initial sandbox could not resolve PyPI or bind a server socket; the authorized installation, validation and localhost server succeeded with expanded execution permissions. An initial ad-hoc JSONL inspection used `splitlines()`, which splits Unicode line separators inside valid text; it was corrected to iterate actual file lines. No input file was changed.

Remaining blockers for deployment:

1. OpenRouter rate limiting prevented four successful live generation checks. Another explicitly approved request budget is required to revalidate those cases; none remains here.
2. macOS memory below 512 MiB is encouraging, but Linux container RSS, concurrency and actual browser/mobile rendering still require verification.
3. Git-ignored artifacts require an approved transfer/bundling mechanism: the complete stopped prebuilt Chroma directory and manifest, unchanged chunks JSONL, verified tokenizer cache, and Wasalt listings JSONL. A Render Git checkout alone will not contain them. The application never rebuilds them.
4. Later Docker/Render work must verify compatible Linux dependency installation/index reopening, provision secrets through environment variables, and configure hosting, port binding and public HTTPS. No Dockerfile, Docker build, upload or deployment was implemented.

Recommended next step: review the local application and approve a separate validation/deployment checkpoint, including any additional free-model requests and artifact transfer plan. This recommendation has not been executed. Stopped after Checkpoint 20.
