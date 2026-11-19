# Checkpoint 18 — Offline corpus loading and chunking

This stage prepares the finalized Markdown corpus only. It does not generate embeddings, initialize Chroma, call a language model, or implement serving/deployment.

## Inputs verified before choosing rules

| Source | Documents | Body characters: minimum / median / maximum |
|---|---:|---:|
| DarGlobal final Markdown | 419 | 477 / 4,378 / 14,101 |
| Wasalt property Markdown | 261 | 573 / 845 / 2,195 |
| Wasalt informational Markdown | 5 | 505 / 1,580 / 5,182 |

DarGlobal has mixed heading levels and some repeated headings/boilerplate. Its frontmatter supplies `title`, `source_url`, `source_type`, and `scraped_at`. Wasalt properties have a heading-derived title, an overview, an optional Arabic/English description, quality notes, and source links. Their frontmatter includes listing IDs, purpose, numeric attributes and flags, but no `title` field. Informational pages carry categories and multiple source URLs/timestamps; the FAQ contains six complete question-answer sections.

The loader reads only:

- `data/darglobal/final/markdown/**/*.md` — 419 documents.
- The 266 approved document paths in `data/wasalt/corpus_manifest.csv` — 261 properties and five informational documents.

Wasalt raw captures, normalized JSON, JSONL, reports, journals and dataset README are **not** loaded as additional text documents. `data/wasalt/listings.jsonl` remains available for structured filtering in a later checkpoint.

## Running offline

Use the existing `.venv-extraction` interpreter from the repository root:

```bash
.venv-extraction/bin/python -B -m app.prepare_corpus
.venv-extraction/bin/python -B -m app.prepare_corpus --verify-existing
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The first command refuses to overwrite existing artifacts. A fresh `--output-dir` can be used for experiments. `--replace-generated` explicitly replaces only the three generated artifact files; source data is never an output destination. `--verify-existing` is read-only and compares regenerated artifacts byte-for-byte.

The user approved installing `tiktoken==0.14.0` and its required `regex` dependency in `.venv-extraction`, and a one-time tokenizer-data download. No other stack dependencies were installed. `app/requirements.txt` records the minimal direct dependencies; this stage uses standard-library `unittest`, not a new test framework.

The approved download cached `cl100k_base` under `.cache/tiktoken/`. The runtime tokenizer verifies the cached file's SHA-256 and constructs `tiktoken.Encoding` from local bytes with the same pattern and special tokens as the official tokenizer. It has **no download fallback**. Tests compare English/Arabic token IDs with the installed official constructor while disabling its download reader. A missing or invalid cache raises an explicit error. Keep/copy this tokenizer cache for offline reproduction; do not copy an API key or install Chroma/OpenAI to run this stage.

## Central configuration

`app/config.py` defines:

| Setting | Default |
|---|---|
| Embedding model name, for the next stage | `text-embedding-3-small` |
| Embedding dimensions, for the next stage | 1536 |
| Tokenizer | `cl100k_base`, verified against the model mapping |
| Target chunk tokens | 450 |
| Maximum chunk tokens, including context | 500 |
| Approximate long-section overlap | Up to 50 tokens, on whole-word boundaries |

`EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` environment variables override the future embedding configuration. Chunk sizes are centralized in `CorpusConfig`. The current offline implementation supports the verified `cl100k_base` encoding only; changing to an incompatible model fails explicitly instead of silently downloading another tokenizer. Dimensions do not change the tokenizer. This stage stores configuration and performs no embedding call.

## Splitting rules

1. Parse YAML frontmatter separately. Retain its values as metadata; it is not chunk prose.
2. Keep a document intact when its text/context fits within 500 tokens.
3. Respect Markdown heading hierarchy, ignoring heading-like lines inside fenced code blocks.
4. Group neighboring short sections toward 450 tokens. Further split only oversized sections, preferring sentence/paragraph endings near the target.
5. Split at whitespace boundaries, never token-byte boundaries or within individual words. Markdown links with spaced titles are atomic too. English/Arabic slices come directly from the original Unicode strings.
6. Carry the document title and useful section headings into continued chunks. Long-section windows overlap by approximately 50 tokens, shortened to whole words. Short/topic-section transitions do not receive artificial overlap.
7. Repeat the original property heading and overview when splitting a long property description. Keep identification in metadata, and location/purpose/price/attributes in the text. Continued description headings follow the repeated overview.
8. Keep each informational FAQ pair atomic. The actual six-pair FAQ fits in one chunk. If a future pair alone exceeds the limit, fail for review rather than silently separating question from answer.
9. Merge or rebalance tiny tails when they can share substantive context without exceeding 500 tokens. Do not delete source form/link text as an unapproved cleaning step.

A single unbroken word/link or essential property context that cannot fit raises an explicit exception. No such exception occurred for the current corpus. Short complete documents and meaningful standalone topics can remain below 350 tokens; the target is not a mandatory minimum. The audit records smaller chunks for review.

## Outputs and current results

All artifacts are outside source datasets:

```text
artifacts/chunks/
├── chunks.jsonl       # Input for Checkpoint 19
├── documents.jsonl    # 685 document identities, source hashes and chunk counts
└── summary.json       # Counts, token distributions, warnings and validation results
```

Generated artifacts are Git-ignored by `artifacts/.gitignore` and can be rebuilt from unchanged sources and the cached tokenizer.

The current corpus produces **1,709 chunks**:

| Source | Documents | Chunks |
|---|---:|---:|
| DarGlobal | 419 | 1,411 |
| Wasalt properties | 261 | 289 |
| Wasalt informational | 5 | 9 |
| **Total** | **685** | **1,709** |

Token counts: **minimum 89; median 396; average 357.662; maximum 500**. There are 417 documents requiring more than one chunk: 397 DarGlobal documents, 18 properties, and two informational documents. The other 243 properties remain one chunk each. Category-level counts are in `summary.json`.

All required metadata is present. There are no duplicate document IDs, repeated source paths, duplicate chunk IDs, or identical document-body groups. Two pairs of distinct informational documents share a primary source URL: auctions/FAQ use the homepage; corporate/services use the corporate page. Their content categories and IDs remain distinct, and all contributing URLs/timestamps are preserved. A URL is not treated as a universal document ID for aggregated informational content.

There are 58 chunks below 150 tokens. These retain short complete documents or useful topics; the shortest is a project overview. Existing source boilerplate and quality flags remain visible. Chunking does not independently verify marketing claims, correct contradictory attributes, or make historical prices live.

## Chunk record contract for Checkpoint 19

`app.prepare_corpus.iter_chunks(path)` streams one JSON object per line. Each flat record contains at least:

- `chunk_id`: `chunk_` plus a deterministic SHA-256 digest.
- `document_id`: source-qualified identity; e.g. `wasalt:property:5891036`.
- `source`, `content_type`, `title`, `text`, `source_url`.
- `chunk_index`: zero-based position within that document.
- `token_count`: exact count of the complete `text`, including repeated context.
- `source_path`, `source_sha256`, `extracted_at`, and `title_source`.
- `section_path`, `source_spans_json`, and `chunker_version`.
- Existing attributes when available: string `listing_id`, `purpose`, city/district, price, period, area, bedroom/bathroom counts, and source timestamps.

Document IDs use the DarGlobal category/filename, Wasalt property listing ID, or Wasalt informational manifest ID, all source-qualified. Chunk IDs incorporate document ID, position, text, and centrally configured policy. There are no random IDs or generation timestamps in chunk artifacts, so unchanged inputs/configuration produce identical bytes.

Metadata is scalar-only: strings, integers, floats, and booleans. Null optional values are omitted rather than replaced by zero. Arrays/maps use reversible JSON strings such as `quality_flags_json`, `source_urls_json`, and `source_extracted_at_json`. This is a practical Chroma-compatible schema without importing or creating a Chroma collection.

For Checkpoint 19, read each existing `text` as the embedding input and preserve `chunk_id` as its identity. Keep all other fields as attribution/filter metadata (exclude `text` from the metadata dictionary if the store has a separate document field). Read model name/dimensions from `CorpusConfig.from_env()` and validate the artifact configuration against that setting. Do not redo chunking implicitly or reinterpret listing IDs as integers. API calls, batching embeddings, and index initialization are intentionally absent here.

## Validation and representative inspection

The preparation validates all 685 documents, exact token counts, unique IDs, contiguous chunk indexes, source URLs, 261 property identities, scalar metadata and unchanged Markdown hashes. Every source-span slice must occur verbatim in a chunk, and merged spans must cover every non-whitespace source character. This catches omissions independently of the number of chunks. A second full load/chunk pass must produce equal records; `--verify-existing` additionally compares saved bytes.

Tests cover parser behavior, official tokenizer agreement, missing-cache failure without network, deterministic IDs, fenced headings, English Markdown links, Arabic word boundaries, overlap limits, property context ordering, FAQ atomicity, tail rebalancing, and complete artifact reproduction. The existing Wasalt extraction tests remain separate and must still pass.

Actual inspected examples:

- DarGlobal Trump Dubai development: two chunks, retaining title, project specifications, amenities and source FAQ text. Existing map attribution remains source content rather than being silently removed.
- Wasalt villa `5891036`: two chunks, both retaining its heading, Riyadh/An-Narjis location, rent purpose, SAR 120,000/year and available counts; Arabic description continues across the chunks.
- Wasalt FAQ: one chunk with all six complete pairs and all source metadata.
- Shams Al Riyadh: topic-based overview, original Arabic description and source-quality notes; no developer or conflicting location is invented.

Inspect the actual `chunks.jsonl` records for exact wording. The summary's corpus fingerprint and output SHA-256 identify the precise source/configuration run. Source datasets, their integrity inventories, and acquisition logs are unchanged.

Final verification: all **61 tests passed** (13 corpus tests plus 48 existing Wasalt tests), and the saved artifacts matched read-only deterministic regeneration. All **2,090 files** across the two source dataset directories retained their original SHA-256 hashes. A separate fresh-process measurement of complete offline preparation, including both reproducibility passes, peaked at **132.08 MiB RSS on this Mac**. This measures corpus preparation; the eventual combined serving stack will need its own memory check.
