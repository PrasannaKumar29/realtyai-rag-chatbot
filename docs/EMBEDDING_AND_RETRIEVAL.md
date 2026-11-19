# Checkpoint 19 — Embedding and persistent semantic retrieval

This stage implements direct OpenAI SDK embeddings and Chroma persistence. The initial approved execution is **offline tests and dry run only**. No API request or real index creation has been executed. There is no chatbot, OpenRouter call, Streamlit UI, structured property search, Docker build or deployment.

## Inputs and configuration

Read the existing `artifacts/chunks/chunks.jsonl` without regenerating or modifying it. It contains 1,709 unique chunks, 611,245 exact input tokens and SHA-256 `09f4c8eac0e0d250e8085fc5ed1dfb1f76f1ef60119c622af763d89690d679a1`. Do not separately embed Wasalt JSONL: those properties already occur in these chunks.

`app/config.py` remains the single configuration module. `IndexConfig` contains the existing `CorpusConfig` and adds index settings. It explicitly loads `REPO_ROOT / '.env'` with `override=False`; an existing process environment wins. Render can omit `.env` entirely. Credentials are read only by the embedding client and are never stored in manifests or printed. Neither the actual `.env` nor its values were inspected or rewritten.

| Environment variable | Default |
|---|---|
| `OPENAI_API_KEY` | Required for paid calls; presence only is reported |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536` |
| `CHROMA_PATH` | `<project>/artifacts/chroma` |
| `CHROMA_COLLECTION` | `real_estate_knowledge` |
| `EMBEDDING_BATCH_SIZE` | `75`, at most 100 |
| `EMBEDDING_USD_PER_MILLION_TOKENS` | `0.02`, supplied planning rate |
| `EMBEDDING_COST_CEILING_USD` | `0.25` |

The older corpus-preparation CLI retains its original `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` convention to preserve reproducibility. The new index/query entry points use the approved `OPENAI_*` names and do not invoke corpus preparation. Changing the model/dimensions/source checksum of an existing index is rejected. Use a separate storage path for a deliberately different build; existing indexes are never deleted automatically. If choosing another model, explicitly set an appropriate planning rate too.

The verified local `cl100k_base` tokenizer cache from Checkpoint 18 is required. No tokenizer or embedding model is downloaded at runtime. Missing cache fails explicitly. Token counts are recalculated from actual complete chunk text and checked against the saved counts. No empty input, duplicate ID, missing attribution, non-scalar metadata or oversized input is accepted.

## Dependencies and authorization

Available in `.venv-extraction` at inspection: Python 3.11.18, `python-dotenv==1.2.4`, `tiktoken==0.14.0`, `PyYAML==6.0.3`.

Missing from both local environments: **`openai` and `chromadb`**. No dependency was installed or upgraded. `app/requirements.txt` adds only these direct integrations and the already available dotenv package to the corpus requirements. Proposed ranges are `openai>=1.30,<3` and `chromadb>=1.0,<2`; actual compatible versions and transitives must be pinned after an approved installation and real-package local smoke test. No orchestration framework is needed.

The extraction environment has no pip executable. Reuse the already established bundled-ensurepip-wheel installation approach if installation is approved; do not assume `python -m pip` works. Installing packages is a separate approval from generating paid embeddings. Transitive Chroma dependencies may be substantial even though its default embedding model is disabled.

## Commands

From the repository root, initial authorized commands:

```bash
.venv-extraction/bin/python -B -m app.index_embeddings --dry-run
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_embeddings.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Omitting both mode flags also selects dry run. It checks package discovery, key presence, validated inputs, batching, planning cost, scalar collection metadata and an existing manifest's compatibility. It **does not import the OpenAI/Chroma SDKs, open a Chroma client, create index directories or make network calls**. Existing collection contents cannot be fully audited without opening the database; the dry-run report labels this limitation explicitly.

After dependency setup and **separate explicit approval of paid execution**, the indexing command will be:

```bash
.venv-extraction/bin/python -B -m app.index_embeddings --execute
```

This command has not been run against OpenAI. There will be 23 batches: 22 × 75 and one × 59. Current single-success-pass estimate is **USD 0.0122249**, using 611,245 tokens at USD 0.02/million. The safety estimate including four attempts per batch is **USD 0.0488996**. The cost gate conservatively uses that retry allowance against USD 0.25. `--allow-cost-override` must be explicit and combined with `--execute`; it should only be used following approval of the higher estimate. Estimates do not guarantee billing when interrupted/timed-out requests have unknown outcomes or many separate resumptions occur.

After a complete validated index exists, an approved retrieval test can use:

```bash
.venv-extraction/bin/python -B -m app.search --query 'What amenities does Marea offer?' --top-k 5
.venv-extraction/bin/python -B -m app.search --query 'Villas in Riyadh' --top-k 5 --source wasalt
```

Retrieval makes a paid query embedding call. It has **not** been run live. It first checks manifest readiness/configuration, database IDs/count, stored vectors, documents and metadata, then queries with an explicit vector. Output includes rank, chunk ID, title, source, a 700-character excerpt, original source URL and cosine distance (lower is closer). `--source` accepts `darglobal` or `wasalt`. It generates no answers. Full validation on each CLI invocation prioritizes correctness; a future serving checkpoint may cache validated readiness rather than repeating it per request.

## SDK calls and retry policy

`app/embeddings.py` lazily constructs official `OpenAI` with SDK retries disabled, a 60-second timeout, and only the configured credential. The direct embeddings endpoint receives explicit model, dimensions, text inputs and float output encoding. Response indices must be an exact permutation of input indices; sorting them restores input order. Count, model, vector dimensions, nonzero finite values and reported usage are validated before storing anything.

Each input is limited to 8,191 tokens; each request is capped at 75 inputs by default and 250,000 aggregate tokens, below the configured absolute cap of 300,000. Batch order remains source-file order. Connection/timeouts, 408/409, rate-limit 429 and 5xx errors have at most three retries, with bounded 1/2/4-second exponential delays (maximum delay 16 seconds). Authentication, permission, invalid input and billing/quota errors fail without retries. Exception bodies and full source inputs are never logged. API usage records reflect returned successful responses; unknown usage from timed-out attempts is not invented.

## Persistence, compatibility and recovery

Planned output:

```text
artifacts/chroma/
├── store/                  # Complete Chroma persistent client directory
├── index_manifest.json     # Identity, progress, successful batch ledger, usage, audit
├── pending_batch.json      # Temporary durable vector checkpoint, absent when complete
└── .index.lock             # Exclusive writer lock, absent when idle
```

`ChromaStore` explicitly passes `embedding_function=None` on both collection creation and lookup. Every upsert supplies documents, scalar metadata and 1,536-dimensional embeddings; every query supplies its embedding. The collection is `real_estate_knowledge`, cosine distance. Text and chunk ID have separate Chroma fields; all other existing non-null scalar metadata, including source, document ID, title, category, URL, chunk index and available listing IDs, are retained. JSON-encoded list metadata remains a string.

The manifest identity covers schema version, source SHA-256, model, dimensions, collection, expected chunk count and distance metric. It also records the portable source path, build/update timestamps, indexed count, status, per-batch IDs and usage, Chroma package version, fingerprint and validation results.

1. Validate all inputs, manifest identity and cost before creating a client or requesting vectors. Reject orphaned/unproven storage rather than adopting or deleting it.
2. Acquire an exclusive local writer lock. Atomic JSON writes use a same-directory temporary file, file fsync, replace and parent-directory fsync.
3. Read existing IDs and verify their text, metadata and vector dimensions. IDs must reconcile with completed batch entries and any pending checkpoint.
4. When vectors return, save them with IDs, usage, model/source fingerprint and payload checksum in `pending_batch.json` **before** upserting to Chroma.
5. Upsert and read back the batch, then atomically update the manifest ledger. Remove the pending file only after progress is durable.
6. On resume, replay a compatible pending vector checkpoint locally. Idempotent upsert handles a crash during/after a database write. A batch already present in the ledger is not charged twice in the usage totals.
7. Embed only remaining IDs. Recheck source checksum between batches. Mark `complete` only after the exact full ID set/count, vectors, text, metadata and unchanged source checksum pass validation. Partial or failed indexes cannot serve retrieval.

If the process dies after OpenAI responds but **before** vectors are durably saved, that request may need to be repeated; the API and local filesystem cannot form one atomic transaction. Already checkpointed vectors do not require another call. A hard process kill may leave `.index.lock`; verify the writer is no longer running before manually removing a stale lock. The program never removes another process's lock automatically. Interrupted collection initialization can safely reopen/create the matching empty collection under its existing compatible manifest.

Chroma/SQLite supplies its own transactional persistence; the filesystem JSON checkpoint is not a substitute for a valid database. Corrupt or missing previously committed database records cause a stop for review rather than automatic re-embedding. Unsupported or mismatched state is preserved for inspection.

## Validation and limitations

Offline tests cover environment precedence, no secret exposure, input/response alignment, dimensions and finite values, bounded retries and hard failures, batching, Chroma argument contracts, metadata, duplicate prevention, configuration/checksum mismatch, orphaned/locked state, API failure resumption, crash after database commit, replay after manifest commit, corrupt checkpoint refusal, cost gating, default dry run, real-corpus dry run and retrieval with fakes.

The 26 new Checkpoint 19 tests prohibit network calls. The complete suite passed **87 tests**, including all 61 existing tests, with zero failures. A before/after SHA-256 inventory confirmed all **2,094 files** across `data/` and `artifacts/chunks/` were unchanged. The actual SDKs are absent, so adapters have been tested against fakes, **not** against an installed Chroma database or live OpenAI. Package API/version compatibility, actual DB reopen behavior, measured indexing/search memory and real semantic results remain verification tasks after approved dependency setup. No vector index exists yet. The 1,709 × 1,536 float32 vectors alone are about 10 MiB; this does not establish the complete stack's RSS. Validate Chroma, Python and eventual Streamlit memory together against Render's 512 MB limit later.

## Later index transfer to Docker/Render

Generated artifacts are excluded by `artifacts/.gitignore`; therefore a remote Render Git build will **not** receive them automatically. A later deployment checkpoint must explicitly transfer a completed validated `artifacts/chroma/` bundle, the unchanged `artifacts/chunks/chunks.jsonl` needed for compatibility checks, and the verified tokenizer cache into the controlled Docker build context or an approved artifact store/build step. Never include `.env` or API credentials.

Stop the indexing process before bundling the entire persistent database directory, including its manifest and all Chroma/SQLite files; do not copy only `chroma.sqlite3` or only HNSW files. Require manifest `complete`, successful validation and no pending checkpoint/active writer. Preserve matching application code, package lock/Chroma version, SHA-256 inventory and model/dimension configuration. Validate reopening the transferred index in the target Linux environment before shipping it. No transfer, Dockerfile, download-at-startup mechanism or deployment is implemented here. The future application must use the prebuilt index and environment secrets, never regenerate embeddings or download a default model at startup.
