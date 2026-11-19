# RealtyAI — DarGlobal and Wasalt

RealtyAI is a Streamlit chatbot for exploring DarGlobal developments and searching
historical Wasalt property listings. It combines retrieval-augmented answers with
deterministic property filtering and links to the original public sources.

## What it supports

- DarGlobal company and development questions, including recognized project names
  such as AIDA, country-specific questions and representative portfolio overviews.
- Wasalt informational questions and cross-company comparisons.
- Exact Wasalt listing-ID lookup and property filters for location, purpose, type,
  price, price period, area, bedrooms and other supported attributes.
- English and Arabic questions, compact property cards, verified match counts,
  citations, conversation history and visible processing states.

Pure structured property searches use JSONL filtering and presentation, with
**zero OpenAI or OpenRouter calls**. Unknown listing IDs return a dataset-miss
notice without unrelated sources. Missing attributes remain unknown rather than
being treated as confirmed matches or mismatches. Requests for explanations and
knowledge questions retain the evidence-grounded generation path.

## Architecture

```text
Streamlit question or structured form
  ├─ Pure property search → JSONL filters → verified counts, cards and source URLs
  └─ Knowledge / explanation request
       → source routing and corpus-derived development-name resolution
       → OpenAI query embedding + prebuilt Chroma retrieval when needed
       → bounded source evidence → OpenRouter generation → citation validation
```

The prebuilt index contains **1,709 vectors**, generated with
`text-embedding-3-small` at **1,536 dimensions**. A corpus-derived inventory covers
19 development pages; it is a retrieval aid, not a complete corporate catalogue.
Citation IDs are validated by application code against retrieved sources. The
application uses a temporary writable copy of Chroma so the bundled index stays
unchanged. Starting the application does not scrape or rebuild the index.

## Data provenance and limitations

The knowledge bundle derives from **685 public-source documents**: 419 DarGlobal
pages, 261 Wasalt property pages and five Wasalt informational pages. The Wasalt
JSONL contains 261 structured listings. Source URLs point to the original
[darglobal.co.uk](https://darglobal.co.uk/) and [wasalt.sa](https://wasalt.sa/) pages.

Wasalt records were collected on **18 November 2026** and are historical snapshots.
Prices, availability and listing details are not verified current. A missing ID
means it was not found in the collected dataset; it does not establish whether
it exists on the live website. Incomplete coverage and missing or inconsistent
source attributes limit comparisons and search results. Portfolio examples are
representative, and do not establish completeness or business-market rankings.

The complete runtime bundle is included in `runtime_assets/` (45.36 MiB), with
SHA-256 checksums in [its manifest](runtime_assets/manifest.json). It includes
chunk text and provenance, listings, the complete SQLite/HNSW store, the index
manifest and the required tokenizer encoding. Original extraction corpora,
archives, local credentials and machine-specific migration reports remain outside
the published repository. No acquisition is required to run the Docker image.

## Run locally with Docker

From the repository root, build the validated target architecture:

```sh
docker buildx build --platform linux/amd64 --load -t realtyai:local .
```

Start without credentials to explore structured property searches:

```sh
docker run --rm --platform linux/amd64 --name realtyai-local \
  -p 10000:10000 \
  -e OPENAI_API_KEY='' -e OPENROUTER_API_KEY='' realtyai:local
```

Open **http://localhost:10000**. Try `Show listing 5891036` or
`Villas for rent in Riyadh under SAR 100000/year`. Knowledge questions require the
API credentials described below. Stop with Ctrl-C or `docker stop realtyai-local`.

For knowledge answers, securely set `OPENAI_API_KEY` and `OPENROUTER_API_KEY` in
your host environment, then pass them by name instead of putting values in the
command or image:

```sh
docker run --rm --platform linux/amd64 --name realtyai-local \
  -p 10000:10000 \
  --env OPENAI_API_KEY --env OPENROUTER_API_KEY realtyai:local
```

The image runs as an unprivileged user, binds to `0.0.0.0`, and respects `PORT`
(default 10000). It includes a health check at `/_stcore/health`. API credentials
must be supplied at runtime, never as Docker build arguments or committed files.

## Configuration and model dependencies

[`.env.example`](.env.example) documents supported settings with blank credentials.
The Docker image already sets the runtime data paths; ordinary usage needs only
the two keys for knowledge answers. Pure structured searches need neither key.

| Variable | Purpose / default |
|---|---|
| `OPENAI_API_KEY` | Query-embedding credential for semantic questions |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small`; must match the existing index |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536`; must match the existing index |
| `OPENROUTER_API_KEY` | Answer-generation credential |
| `OPENROUTER_MODEL` | `baidu/ernie-5.5-flash-preview:free`; the approved primary is enforced |
| `OPENROUTER_ENABLE_FALLBACK` | `false` by default |
| `CHROMA_COLLECTION` | `real_estate_knowledge` |
| `CHROMA_PATH` | `/opt/realtyai/runtime_assets/chroma` in Docker |
| `CHUNKS_PATH` | `/opt/realtyai/runtime_assets/chunks.jsonl` in Docker |
| `WASALT_LISTINGS_PATH` | `/opt/realtyai/runtime_assets/listings.jsonl` in Docker |
| `TOKENIZER_CACHE` | `/opt/realtyai/runtime_assets/tokenizer` in Docker |
| `PORT` | Streamlit listening port; `10000` |

Semantic query embeddings use the OpenAI API and may incur charges. Generation
requests use the selected free ERNIE endpoint with reasoning enabled and zero-price
routing constraints. Free-provider availability and rate limits can interrupt
answers; account quotas and provider capacity are separate failure modes.

The optional approved Nemotron endpoint,
`nvidia/nemotron-3-ultra-550b-a55b:free`, is attempted at most once only when fallback
is explicitly enabled and the primary HTTP 429 is positively classified as an
upstream-provider capacity/rate-limit error. Account, daily, per-minute,
authentication, credit and unknown errors do not trigger fallback. There is no
paid routing or further model fallback. Deterministic property cards remain
available independently of generation.

## Verification and repository layout

With the container running, verify health and run the guarded offline acceptance:

```sh
curl --fail http://localhost:10000/_stcore/health
docker exec realtyai-local python -B packaging/validate_offline.py
```

The complete development suite has **209 passing tests**. It requires the original
local corpus fixtures and development environment, which are intentionally not
part of the runtime distribution. The container acceptance above uses only the
published runtime bundle and makes no API requests.

| Path | Contents |
|---|---|
| `app/` | Chatbot, retrieval, filtering, citation validation and Streamlit UI |
| `runtime_assets/` | Checksummed, prebuilt knowledge and structured listing bundle |
| `packaging/` | Container startup and offline acceptance scripts |
| `tests/` | Offline development regression tests |
| `scripts/` | Historical corpus preparation/extraction tools; not run at startup |
| `docs/` | Architecture, evaluation and checkpoint reports |
| `Dockerfile`, `requirements-runtime.txt` | Linux runtime packaging and pinned dependencies |

[Checkpoint 21A](docs/CHECKPOINT_21A_RESULTS.md) records AMD64 build verification,
asset sizes, integrity checks and reproduction commands. The observed offline
peak was **375.25 MiB** under Docker Desktop AMD64 emulation; a native service with
an enforced 512 MiB limit still needs validation. Image size is approximately
1.36 GiB. No Render deployment has been performed.
