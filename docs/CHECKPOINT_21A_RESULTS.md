# Checkpoint 21A — Docker packaging and GitHub readiness

Completed locally on 19 November 2026. The final Linux AMD64 image builds, serves
Streamlit, loads the existing knowledge assets and passes offline acceptance.
All 209 existing tests pass. No application features changed. No commit, push,
publication, Render deployment or infrastructure provisioning occurred.

## Repository and runtime audit

The repository was already initialized with Git; it has no previous commits.
Only read-only Git inspection was used (`status`, `ls-files`, `check-ignore`).
The initial publication audit found 111 Git-eligible files before this results
document was added; none exceeded 50 MiB and no actual API credentials were found.
Nothing was staged.

The entry point is `app/streamlit_app.py`. Runtime code includes the chatbot,
presentation, deterministic property search, corpus-derived development inventory,
retrieval, citation validation, embedding client and OpenRouter adapter. Some
preparation/index/evaluation modules are imported transitively for existing shared
helpers; their acquisition, indexing and evaluation entry points are not executed.
The Docker allowlist includes only the 16 needed application Python modules.

| Classification | Treatment |
|---|---|
| Runtime code and `.streamlit/config.toml` | Copied through the Docker allowlist |
| Complete existing Chroma store, index manifest, chunk JSONL, listing JSONL, tokenizer data | Byte-identical copies in `runtime_assets/`, eligible for Git and Docker |
| Tests, extraction scripts and checkpoint documentation | Development source; excluded from image |
| Original corpora, research artifacts and archives | Preserved locally; excluded from image |
| `.env`, credentials, local environments, recordings, caches, machine configuration, validation logs | Excluded from Git and image |

Chroma and the corpus-derived inventory need the chunk JSONL, not the original
Markdown corpus or `documents.jsonl`. Citation URLs remain the source metadata.
The existing runtime copies Chroma into a temporary writable directory before
opening it. This works for an unprivileged user and an ephemeral filesystem;
the packaged knowledge bundle remains unchanged. No Mac absolute path is needed.

## Runtime asset manifest and distribution

Selected strategy: ordinary Git distribution of `runtime_assets/`, then image
COPY. Payload is **47,560,766 bytes**, plus the **1,599-byte** checksum manifest:
**47,562,365 bytes total (45.36 MiB)**. Largest file is the SQLite database,
**33,906,688 bytes (32.34 MiB)**. These sizes are below GitHub's 50 MiB warning and
100 MiB blocking limits for individual files. Git LFS, release downloads and
external storage are unnecessary for this frozen bundle. Use Git push rather
than browser upload, which has a smaller per-file limit.
([GitHub file-size documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github))

All paths below are relative to `runtime_assets/`. The complete SHA-256 values
are in [`manifest.json`](../runtime_assets/manifest.json).

| File | Bytes |
|---|---:|
| `chunks.jsonl` | 4,579,165 |
| `listings.jsonl` | 483,148 |
| `chroma/index_manifest.json` | 130,911 |
| `chroma/store/chroma.sqlite3` | 33,906,688 |
| `chroma/store/9e4b1be3-6c95-49a1-9be6-07a297c18f05/data_level0.bin` | 6,598,200 |
| `chroma/store/9e4b1be3-6c95-49a1-9be6-07a297c18f05/length.bin` | 4,200 |
| `chroma/store/9e4b1be3-6c95-49a1-9be6-07a297c18f05/link_lists.bin` | 9,096 |
| `chroma/store/9e4b1be3-6c95-49a1-9be6-07a297c18f05/header.bin` | 100 |
| `chroma/store/9e4b1be3-6c95-49a1-9be6-07a297c18f05/index_metadata.pickle` | 168,132 |
| `tokenizer/9b5ad71b2ce5302211f9c61530b329a4922fc6a4` | 1,681,126 |
| `manifest.json` | 1,599 |

Sources are the existing `artifacts/chunks/chunks.jsonl`,
`data/wasalt/listings.jsonl`, complete `artifacts/chroma/` and the single required
`.cache/tiktoken/` encoding file. The tokenizer cache is explicitly bundled to
prevent an otherwise hidden runtime download; the rest of the cache is excluded.
SQLite, all companion HNSW files, metadata and deterministic IDs are preserved.
No vectors or chunks were regenerated. Existing source files were not moved.

## Files created or modified

Created:

- `Dockerfile`: digest-pinned Python slim image, runtime assets, unprivileged user,
  portable environment paths, health check and startup entry point.
- `.dockerignore`: positive allowlist; no broad repository COPY into the image.
- `requirements-runtime.txt`: complete 103-package Linux AMD64 dependency pins.
- `.env.example`: supported variables, blank credentials and container paths.
- `packaging/start.sh`: direct `exec` of Streamlit with headless mode, `0.0.0.0`
  binding and `${PORT:-10000}`.
- `packaging/validate_offline.py`: container acceptance and memory observations,
  with network/API guards and asset checksums before and after.
- `runtime_assets/`: the ten copied payload files and checksum manifest above.
- `docs/CHECKPOINT_21A_RESULTS.md`: this report.

Modified:

- `.gitignore`: excludes logs, recordings, private keys, machine directories,
  historical archive and `packaging-output/`; preserves original data ignores.
- `README.md`: current RealtyAI packaging introduction and link to this report;
  historical dataset handoff remains below it.

Local build logs and audit outputs are under ignored `packaging-output/`.
There are no changes to `app/`, tests, retrieval settings, project inventory,
prompts, model selection, fallback policy or Streamlit UI.

## Docker and dependency decisions

Base: `python:3.11.18-slim-bookworm`, pinned to multiarchitecture manifest digest
`sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`.
The Dockerfile remains architecture-portable; validation explicitly selected
`linux/amd64`. No additional apt packages, reverse proxy or services were added.

Direct package versions match the existing accepted chatbot requirements:
`openai==2.54.0`, `chromadb==1.5.9`, `python-dotenv==1.2.4`,
`tiktoken==0.14.0`, `PyYAML==6.0.3`, `requests==2.34.2`,
`streamlit==1.67.0`. The full effective dependency list is
[`requirements-runtime.txt`](../requirements-runtime.txt); it was resolved in
Linux AMD64, frozen and rebuilt successfully with `pip check`.
Chroma requires sizeable native/transitive packages including ONNX Runtime,
NumPy and tokenizers; Streamlit includes pandas and PyArrow. No Torch,
TensorFlow, browser automation, notebook or extraction dependency stack was added.
The local virtual environment was not modified.

Runtime UID/GID is `10001:10001`. Assets are root-owned and readable; Chroma's
existing temporary-copy behavior supplies its writable store. The shell uses
`exec` so Streamlit receives container shutdown signals. Default port is 10000;
an independent HTTP check also passed with `PORT=10001`.

## AMD64 build and container results

Buildx `v0.38.1` and Docker Desktop's Linux backend were available. Final build:

```sh
docker buildx build --platform linux/amd64 --load -t realtyai:21a .
```

Succeeded. Image architecture: **linux/amd64**. Final image ID:
`sha256:06eadac0d3580e0e21818fa39bfb3a5fbacf67641d449e0aab6d455b12152944`.
Uncompressed image size: **1,460,813,108 bytes (1,393.14 MiB; 1.36 GiB)**.
This disk size includes required transitive wheels; it is distinct from RAM.

The container started without API credentials, import failures or missing paths.
Streamlit bound to `0.0.0.0:10000`; the health endpoint returned HTTP 200 and
`ok`. The published application root also returned HTTP 200 in the port-override
check. Streamlit AppTest inside the AMD64 image rendered RealtyAI and a known
listing card without exceptions. Native SDK import smoke confirmed `x86_64`,
OpenAI 2.54.0, Chroma 1.5.9 and Streamlit 1.67.0 with networking disabled.

Offline acceptance confirmed:

- Collection `real_estate_knowledge`: exactly **1,709** existing records, IDs,
  text, metadata and embedding configuration validated by the runtime.
- A real HNSW query using one existing vector returned three stored results
  with preserved source URLs. Run with `--network none`; no new embedding.
- **261** Wasalt structured listings load successfully.
- Listing **5891036** returns the stored SAR 120,000/year, 250 square metres,
  nine bedrooms and six bathrooms, plus its original Wasalt property URL.
- Listing **99999999** returns the deterministic dataset miss and live-site
  caveat, with no unrelated sources.
- Riyadh rental villas under SAR 100,000/year return **eight** verified matches.
- Structured queries and card rendering make **zero generation and zero query
  embedding requests**, enforced by mocks and network guards.
- Packaged asset checksums match before and after validation.

Packaging issues encountered and resolved: the initial AppTest harness used a
relative script path resolved from its own directory; it now uses an absolute
path derived from the package root. A transient Docker `--rm` name-removal race
was resolved by waiting for removal before restarting. Neither required an
application change. The expected bare-mode Streamlit test-context warning was
non-fatal. Original read permissions on the copied index manifest required
image-only read permission normalization. No remaining build/runtime failure.

## Measured memory and limitations

Host: Apple Silicon ARM64; Docker Desktop AMD64 emulation, approximately
7.75 GiB available. No 512 MiB cgroup limit was imposed.

| Observation | MiB | Measurement |
|---|---:|---|
| Streamlit startup, before application initialization | 70.57 | Docker stats working set |
| Chroma loaded and verified | 315.22 | cgroup memory.current |
| Deterministic Wasalt queries completed | 320.86 | cgroup memory.current |
| UI card rendered; checksums reverified | 344.66 | cgroup memory.current |
| Peak during this acceptance run | **375.25** | cgroup memory.peak |

Cgroup usage includes the running Streamlit server, concurrent offline validator,
AppTest and accounted file cache; Docker stats excludes some reclaimable cache,
so its startup value is not directly comparable. Observed peak was 136.75 MiB
below a nominal 512 MiB allocation. These measurements support a 512 MiB trial,
but do not establish reliable operation under an enforced limit or predict native
Render memory, multiple sessions, cold-start peaks or live semantic/LLM workload.
If native measurements approach the limit, choose an adequately sized instance
before considering any separately approved memory optimization. No aggressive
memory or architecture changes were made.

## Security, reproducibility and integrity

The Docker context allows only explicit runtime files, excludes `.env` and key
files, and never includes local environments, `.git`, recordings or full corpora.
No secret was supplied as a build argument or image ENV. Tests used blank API
keys; the local `.env` was neither copied nor mounted. Git-eligible source,
Docker metadata/history and runtime image checks found no actual API-key values.
The image has no project `.env`, `.git` or local virtual environment.

An isolated export at `/tmp/realtyai-21a-export` contained only Docker-required,
Git-eligible files, without the original data/artifact paths or credentials.
The final AMD64 build from that export succeeded as `realtyai:21a-export`.
All runtime payloads in the export were checksum-identical. Thus the Docker
build does not depend on ignored Mac workspace files. The originals remain
ignored; the copied `runtime_assets/` bundle is eligible for the first commit.
This is a fresh-checkout-equivalent build, not an actual clone of a published
repository. Package downloads still require ordinary build-time internet access.

The full test command was:

```sh
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

**209 tests passed in 8.258 seconds**, with no failures. This complete historical
suite runs in the original development workspace, where ignored original corpus
fixtures exist; the report does not claim all research tests run from a fresh
checkout. Container acceptance requires only the distributable runtime bundle.

SHA-256 comparison against the pre-checkpoint snapshot verified **2,101 protected
files unchanged**, covering original DarGlobal/Wasalt data, chunks and Chroma
files. The existing embeddings, deterministic IDs and source URLs are preserved.
No scraping, chunking, indexing, live OpenAI/OpenRouter request or model evaluation
occurred. All test containers were stopped and removed.

## Clean local reproduction

Run from the repository root (or a future clone containing `runtime_assets/`):

```sh
docker buildx version
docker buildx build --platform linux/amd64 --load -t realtyai:21a .
docker run --rm --platform linux/amd64 --name realtyai-21a \
  -p 10000:10000 -e PORT=10000 \
  -e OPENAI_API_KEY='' -e OPENROUTER_API_KEY='' realtyai:21a
```

Keep that terminal open. In another terminal, after startup:

```sh
curl --fail http://localhost:10000/_stcore/health
docker exec realtyai-21a python -B packaging/validate_offline.py
docker stats --no-stream realtyai-21a
```

Open `http://localhost:10000`. For zero-API interaction, use a structured query
such as `Show listing 5891036`. Do not supply or mount `.env`. Stop with Ctrl-C
in the first terminal or `docker stop realtyai-21a`; allow automatic removal
before reusing the name. Repeated checks may show different memory values.

## Next authorized phase needed — not executed

There is no local packaging blocker. Remaining checks are publication and a
native deployed trial, including actual cold-start/memory behavior and HTTPS.
The final image is comparatively large, so build/pull time remains a deployment
consideration. No Render readiness claim includes an actual Render deployment.

After explicit approval for the first commit and publication:

1. Review `git status --short` and `git add --dry-run .`; confirm the runtime
   manifest and all companion Chroma files are included, and secrets/local
   outputs are excluded. Recheck eligible files for secrets.
2. Stage the reviewed source, documentation, packaging and runtime bundle with
   `git add .`, then review `git diff --cached --stat` and
   `git diff --cached --name-only` before
   `git commit -m "Package RealtyAI for Linux AMD64 Docker"`.
3. Create the approved GitHub repository, add its actual URL with
   `git remote add origin <approved-github-repository-url>`, and push the current
   branch with `git push -u origin HEAD`. Do not initialize another repository.
4. Clone that repository into a clean directory and repeat the AMD64 build and
   zero-API container acceptance commands above.

After separate explicit deployment approval, create a Render **Web Service**
from that repository/branch, choose **Docker**, use repository root as context
and `./Dockerfile`, and leave the Docker command override empty. Configure the
health path `/_stcore/health`; the image binds `0.0.0.0` and honors `PORT`
(default 10000). These settings follow the
[Render Docker documentation](https://render.com/docs/docker) and
[web-service documentation](https://render.com/docs/web-services).
Set API credentials through Render's secret environment settings, never Git or
build arguments. Keep `OPENROUTER_ENABLE_FALLBACK=false`, the selected free model
and existing embedding settings from `.env.example`. No persistent disk is
required for the immutable bundled knowledge and temporary Chroma copy.

Choose the explicitly approved compute allocation, deploy, record the HTTPS URL,
verify health and structured searches, and measure native memory at cold start
and under the intended workload before accepting 512 MiB suitability. Any live
semantic or generation checks require an explicitly approved API budget; the
zero-API acceptance remains available without keys. Do not provision paid
resources without approval.

**Stop:** Checkpoint 21A is complete. No publication or deployment action follows
automatically.
