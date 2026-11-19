# Checkpoint 20E — DarGlobal routing and evidence quality

Objective: resolve named-development questions from existing data and prevent weak category/boilerplate signals from displacing substantive project evidence. Completed with offline validation only; no live OpenAI or OpenRouter request was made.

## AIDA routing: confirmed root cause and correction

The exact question was reproduced before editing:

> What is the AIDA development in Oman, and what are its main features?

It selected `clarify` with empty filters. The router recognized explicit company names plus a small hardcoded group of development/brand names. AIDA was not in that group, and the query had no Wasalt or structured-property intent. The router did not consult the corpus metadata, so the question never reached DarGlobal retrieval despite an existing `AIDA - DarGlobal` development document at `https://darglobal.co.uk/invest-in-aida`.

The hardcoded development-name alternatives were replaced by a small in-memory catalogue derived from existing development/community titles, URL slugs and supporting body text. Current data yields **26 source URLs and 50 aliases**. The catalogue is deliberately conservative, not a complete entity database. A heading alone does not establish an entity, generic marketing titles are rejected, and `/press` cannot create an entity.

Unique multiword names can resolve without a company name. Single-word names require development context, such as `development`, `project` or `amenities`; colliding aliases remain ambiguous. Consequently the exact AIDA question routes to `darglobal`, while `What is AIDA?`, `Who composed AIDA?`, `What is Neptune?` and bare `What is Marea?` request clarification. Full qualified names such as `Marea, Interiors by Missoni`, and other corpus-derived names such as Tierra Viva and Urban Oasis, resolve without requiring the word DarGlobal. Tests also add a temporary synthetic development and a colliding name, proving the mechanism is derived from metadata rather than an AIDA-only rule.

Explicit Wasalt IDs retain priority and skip catalogue lookup. Structured Wasalt filter parsing/classification is otherwise unchanged. Configurable `CHUNKS_PATH` is respected, and the small catalogue cache invalidates on file metadata changes. No derived index is written into source data or Chroma.

## Spain: preserved evidence and selector defect

The useful original record is intact:

- URL: `https://darglobal.co.uk/blog/redefining-real-estate-development-for-the-discerning-buyer`
- Chunk: `chunk_8ab26854bca6eb136a9d74077e44f64ef61760dbae565bf0dba7cd087890b003`
- The substantive Costa del Sol/Spain passage names both Tierra Viva and Marea Interiors by Missoni.

Checkpoint 19B saved this passage at rank five for **“What projects does DarGlobal have in Spain?”**, with cosine distance approximately **0.392291**. The 19D Spain comparison reused the successful 19C pair, which used those saved evidence records; it did not run another Spain retrieval. The user’s newer wording uses “developments,” and its exact query vector/raw manual candidate list was not saved.

The original selector applied:

```text
score = cosine distance - 0.025 × capped keyword overlap
        - 0.15 for any developments-category chunk with overlap
```

This category bonus applied to `Invest-crypto`, which is labelled `developments` in the preserved corpus despite being a payment/investment page. Keyword matching included repeated headings, URLs, image captions and footer navigation. A country name in a footer could therefore pass the old geography check and receive the same project-category bonus as substantive project prose. Greedy selection could spend two slots on the same URL before covering distinct sources. With a six-chunk context, these signals could displace the useful blog.

The saved historical top five **alone** do not reproduce the loss: both old and new selectors retain the blog from that small pool. The defect appears when the application merges its larger source/category pools and reranks them. It is not a missing corpus document, a Wasalt source filter, or the 0.80 cutoff rejecting the known saved blog distance.

### What can and cannot be reproduced exactly

No saved query-embedding artifact was found. The existing retrieval CLI saved result IDs/distances, not its query vector; subsequent chatbot validation also did not save vectors or the relevant manual candidate trace. Under the zero-API restriction, the exact live manual ordering cannot be reconstructed or attributed to one precise displaced slot with certainty.

The offline probe therefore supplies deterministic mocked query embeddings using **existing document vectors**. It opens the real Chroma collection only on the application's temporary copy. AIDA uses its overview document vector; Spain uses the document vector for the first historical Spain result. These are explicitly labelled **surrogates, not recovered query embeddings**. No vector was generated, and no inference service was called.

This controlled diagnostic reproduced the selector failure mode using real corpus/index candidates. It provides direct evidence that the policy can cause the reported behavior, without claiming to replay the unavailable manual vector.

## Before/after evidence comparison

Configuration retained: source-filtered semantic top 35 plus development-category top 35, cosine cutoff 0.80, at most six final chunks for one source or three per company for a cross-source question, and at most two chunks per URL.

Changes are limited to application routing/candidate selection:

1. A ranking-only prose view omits repeated headings, image captions and link-only navigation, including concatenated links. Original text/metadata passed as evidence are unchanged.
2. For portfolio questions, project-name coverage must occur in a substantive sentence containing query terms. Names are derived from the catalogue, with the project's own prose also supporting those terms. This reduces cross-country name contamination from global menus.
3. Relevant actual project pages receive a small 0.03 preference rather than a blanket 0.15 category bonus. Explicitly resolved project pages also receive a bounded direct-entity preference. No special Spain answer, project list or evidence ID is embedded in selection logic.
4. Substantive multi-project evidence is prioritized for portfolio questions; zero-project tangential material does not fill context slots when supported project evidence exists.
5. Distinct URLs are covered before a second chunk from one URL.
6. A bounded lexical recovery pass can identify up to 12 relevant original chunks missed by the two semantic pools. Only missing candidates' **existing stored vectors** are read, their real cosine distances to the current query vector are computed, and the same cutoff/selection rules apply. There is still only one normal query-embedding operation per application retrieval; no document or extra query embeddings are generated by recovery.

The narrow hardcoded Spain/location and Trump/Dubai selector branches were replaced by these general signals and resolved entity names. Generic `/press` exclusion remains unconditional.

Final surrogate Spain diagnostic:

| Stage | Observation |
|---|---|
| Raw pools | 70 candidate entries, including duplicates across the two searches |
| Useful blog | Already present at source-pool rank three, distance approximately 0.2015 |
| Crypto overview | Present in the category pool, distance approximately 0.3012 |
| Old scoring | Crypto received about 0.175 of combined bonuses, versus about 0.025 for the blog, reversing their semantic order |
| Old final six | Two market-entry press chunks, crypto overview, exclusive-plots material, another crypto chunk, and live-all-in material |
| After bounded recovery | 79 candidate entries; no new embeddings |
| New final six | Useful two-project blog first; a substantive Missoni launch article; a Marbella-project blog; Tierra Viva construction evidence; long-term-value blog; Tierra Viva contractor article |

The final selected blog names **both Tierra Viva and Marea Interiors by Missoni**. The crypto page is absent. `/press` hubs remain excluded. The real individual Marea/Tierra Viva pages and their existing records remain in the corpus; relevant FAQ records are eligible for bounded recovery. Selection does not claim that these two developments constitute a complete current catalogue.

For AIDA, before routing was `clarify`, so no evidence reached the model. After routing is `darglobal`; the offline semantic surrogate selects the actual AIDA overview first, containing its Muscat/Oman setting, residential offerings and amenities. The probe's “before evidence” for AIDA is a selector-only counterfactual, explicitly not an actual old routed result.

Full raw candidate IDs, distances, content types, prose scores, project coverage, original full evidence text and final selections are in `artifacts/checkpoint_20e/final-surrogate-diagnostics.json`. `comparison-summary.json` is the short version. The earlier selector and initial diagnostic are retained for provenance.

## Files changed

| File | Change |
|---|---|
| `app/development_evidence.py` | New lightweight metadata catalogue, conservative entity resolution, ranking prose view, query/project relevance signals, bounded lexical recovery and cosine calculation over existing vectors |
| `app/property_search.py` | Replaces fixed development-name routing alternatives with the metadata-derived resolver; accepts the configured chunk path; exact Wasalt filtering code is unchanged |
| `app/chatbot.py` | Updates candidate ranking/diversification, recovers bounded candidates using existing vectors, passes the chunk path to routing, and supports optional internal retrieval diagnostics |
| `tests/test_darglobal_retrieval.py` | New 14-test offline regression suite |
| `docs/CHECKPOINT_20E_RESULTS.md` | This report |

Created `artifacts/checkpoint_20e/selection-before.py`, `surrogate-diagnostics.json`, `final-surrogate-diagnostics.json`, `comparison-summary.json`, `offline_retrieval_probe.py`, `offline-tests.txt` and `integrity.json`.

`app/search.py`, `app/vector_store.py`, configuration, source datasets, prepared chunks, stored metadata, deterministic IDs, model/fallback policy and Streamlit layout/loading code are unchanged. The old semantic-only `app.search` CLI still returns raw semantic results; use the chatbot or the offline probe to inspect the application’s final selection.

## Tests and integrity

**200 tests passed, zero failures or skips**, in 7.536 seconds: all previous 186 tests plus 14 new regressions.

New coverage includes the exact AIDA route reaching a grounded prompt, other known names without company names, ambiguous/colliding names, a synthetic metadata-derived entity, preservation of the actual saved Spain passage, category-bonus displacement, navigation contamination, lexical recovery without new embeddings, threshold/URL limits, generic press hubs, cross-source retrieval, Wasalt route/search preservation, final prompt evidence containing both Spanish names, and invalid citation/URL rejection. Generated answers in these regressions are mocked, not new ERNIE evaluations.

The complete existing suite also preserves known/unknown Wasalt IDs, eight Riyadh rental-villa matches, historical disclaimers, zero external calls on exact misses, citation control, fallback safeguards, loading-state ordering and session history.

Final SHA-256 audit: **all 2,176 protected files unchanged**, including both datasets, prepared chunks, production Chroma and protected prior checkpoint artifacts. Immutable read-only SQLite inspection confirms **1,709 indexed records**, 1,536 dimensions, completed manifest status and the unchanged chunk checksum matching the manifest. SDK queries used only temporary index copies. Credential-value scanning of changed code/tests and new diagnostic artifacts found no leaks.

There were **zero live OpenAI and zero live OpenRouter requests**. No scraping, source edits, document rechunking/re-embedding, Chroma rebuild, dependency installation, model/fallback change, Docker/Render work or Git staging/commits/pushes occurred.

Commands executed included read-only `cat`/`rg` inspection, corpus/artifact schema and text inspection, saved-vector offline diagnostics, SHA-256/credential checks, immutable SQLite metadata reads and:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_chatbot.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_darglobal_retrieval.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv-extraction/bin/python -B artifacts/checkpoint_20e/offline_retrieval_probe.py --output artifacts/checkpoint_20e/final-surrogate-diagnostics.json
```

Errors or blockers: no offline failures remain. A focused existing test caught a duplicate-ID test fixture where a rejected hub initially masked a valid candidate; exclusions were moved ahead of deduplication. Navigation-only concatenated links were also checked and excluded from ranking prose. Exact live-query rankings and fresh ERNIE answer quality remain unverified because their query vectors were not saved and this checkpoint permits no new API calls.

## Exact retest instructions

For a repeatable **zero-API routing/evidence retest**, from the repository root:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_darglobal_retrieval.py' -v
.venv-extraction/bin/python -B artifacts/checkpoint_20e/offline_retrieval_probe.py
```

The probe prints before/after selections for both exact questions using the explicitly mocked vectors and the real temporary Chroma copy. It makes no inference calls. To save another full report, add `--output /tmp/checkpoint20e-retest.json` with a new filename; the probe refuses to overwrite an existing file.

For a **local UI routing-only check without external calls**, stop the existing Streamlit process with Ctrl+C (or its running-command Stop control) so the old cached runtime is discarded. Then run:

```bash
# Run from the repository root.
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Refresh `http://127.0.0.1:8501`, clear the conversation and enter the two exact questions:

1. `What is the AIDA development in Oman, and what are its main features?`
2. `What developments does DarGlobal have in Spain?`

With deliberately empty keys, AIDA should reach the knowledge-base stage rather than the ambiguous-route response. Both semantic requests will end with the safe service-unavailable response because embedding credentials are disabled; this does **not** validate their answer content. Use the offline probe/tests above to review actual selected evidence without API calls.

For a future **credential-enabled end-to-end manual check**, separately authorize a live budget, stop the zero-API server, and start the same Streamlit command without the two empty-key assignments. Ask those two questions again. Check that AIDA cites relevant original project evidence and that Spain names both Tierra Viva and Marea with substantive citations, without relying on the crypto page or claiming catalogue completeness. That future check would make query-embedding and generation requests and was not performed here. No API counters were bypassed, and no prior validation runner was rerun.

Recommended next step: review the offline evidence comparison, then decide whether to authorize the live manual checks. Stopped after Checkpoint 20E; no deployment phase was started.
