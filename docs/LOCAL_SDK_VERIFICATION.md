# Checkpoint 19A — Local SDK verification

Verified on 19 November 2026 using the existing `.venv-extraction` Python 3.11.18 environment on macOS arm64. This checkpoint authorized dependency downloads/installation and offline synthetic integration checks only. No live OpenAI requests, production vectors, production Chroma index, corpus changes or deployment were performed.

## Installation

`pyvenv.cfg` records uv 0.13.9 as the environment creator. Neither uv nor pip was available on the inspected executable paths. The established bundled-ensurepip-wheel workflow successfully installed the application requirements without recreating the environment or installing pip itself:

```bash
.venv-extraction/bin/python -I -B - <<'PY'
import ensurepip,pathlib,runpy,sys
wheel=next((pathlib.Path(ensurepip.__file__).parent/'_bundled').glob('pip-*.whl'))
sys.path.insert(0,str(wheel))
sys.argv=['pip','install','--no-cache-dir','--retries','0','-r','app/requirements.txt']
runpy.run_module('pip',run_name='__main__')
PY
```

Installed direct SDK versions are **openai 2.54.0** and **chromadb 1.5.9**, within the existing requirement ranges. Their dependency trees added 80 distributions. All 15 previously installed distributions retained their original versions; the main `.venv` was not modified. The requirements file was not changed. These are verified local versions, not a full cross-platform dependency lock.

Selected installed dependencies:

| Distribution | Version |
|---|---|
| python-dotenv | 1.2.4, already present |
| tiktoken | 0.14.0, already present |
| PyYAML | 6.0.3, already present |
| numpy | 2.4.6 |
| onnxruntime | 1.32.0 |
| httpx | 0.28.1 |
| pydantic | 2.14.3 |
| tokenizers | 0.23.3 |
| grpcio | 1.85.3 |
| kubernetes | 37.0.3 |

Using the bundled pip wheel with `sys.argv=['pip','check']` reported **No broken requirements found**. A non-writable pip cache warning was harmless; the cache was disabled. There were no resolver conflicts or upgrades to pre-existing distributions.

## Verification commands

```bash
.venv-extraction/bin/python -B -m app.verify_local_integrations
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv-extraction/bin/python -B -m app.index_embeddings --dry-run
```

`app.verify_local_integrations` creates an owned `TemporaryDirectory` and runs two isolated child processes. Both processes block Python socket connection/DNS operations, HTTPX sends and requests calls. Telemetry is disabled; Hugging Face is set offline. No embedding model is instantiated or downloaded. The probe recorded **zero network attempts**, not merely blocked errors that were ignored.

The OpenAI client imported and initialized successfully using the explicitly loaded root `.env` with `override=False`. The key was present but never printed. Model and dimensions were `text-embedding-3-small` / 1536, and the SDK's automatic retries remained disabled. Client initialization alone makes no request. A separate regression test uses a fake credential and HTTPX's in-memory MockTransport to verify real SDK request serialization/response parsing without a network connection.

Real Chroma results:

- Created a cosine collection through the existing `ChromaStore`, with `embedding_function=None`.
- Upserted three synthetic 1536-dimensional vectors with documents and scalar metadata.
- Verified exact stored text/metadata, finite vector dimensions and Arabic text.
- Verified expected cosine ordering and source metadata filtering.
- Repeated upsert without increasing the count.
- Confirmed duplicate IDs within one `add` request raise `DuplicateIDError`.
- Confirmed `add` for an already stored ID preserves the existing record.
- Confirmed the adapter rejects a 1535-dimensional vector and Chroma itself rejects invalid insert/query dimensions.
- Explicitly called the public `client.close()`, opened a new client, and verified persisted records and queries.
- Repeated the persistence/query checks in a fresh Python process after the creation process exited.
- Removed only the probe's temporary directory after both processes exited. The temporary database occupied 858,276 bytes in the standalone run.

The existing adapter needed no compatibility changes. Two permanent SDK integration tests were added; the complete suite passed **89 tests, zero failures and zero skips**, preserving all 87 existing tests.

## Updated dry run

| Item | Result |
|---|---|
| Chunks / unique IDs | 1,709 / 1,709 |
| Input tokens | 611,245 |
| Full batches | 23, at most 75 chunks each |
| Model / dimensions | text-embedding-3-small / 1536 |
| Estimated successful-pass cost | USD 0.0122249 |
| Estimate with maximum retry allowance | USD 0.0488996 |
| Cost ceiling | USD 0.25; passed |
| Missing packages | None |
| Root .env / key detected | Yes / yes; no secret displayed |
| Production index | Not built; dry run did not open/create one |

The chunk SHA-256 remains `09f4c8eac0e0d250e8085fc5ed1dfb1f76f1ef60119c622af763d89690d679a1`. Before/after SHA-256 inventories of all 2,094 files under `data/` and `artifacts/chunks/` matched. `artifacts/chroma/` remained absent.

## Resource and deployment limits

Standalone fresh-process peak RSS measurements, in MiB:

| Stage | Create process | Fresh reopen process |
|---|---:|---:|
| Before SDK imports | 28.11 | 28.06 |
| After OpenAI client initialization | 72.25 | 72.19 |
| After Chroma import | 101.06 | 100.98 |
| After synthetic collection operations | 124.59 | 123.02 |

These are per-process high-water marks from `resource.getrusage`, not simultaneous serving-stack measurements. They cover only three vectors, the SDKs and the probe. They exclude the full corpus/index, Streamlit, eventual answer generation, multiple users and a Linux deployment. **This does not establish compliance with Render's 512 MB RAM limit.**

The 80 added distributions account for about 427.64 MiB of installed file bytes on this Mac, including their recorded files. Selected contributions: Kubernetes 117.56 MiB, ONNX Runtime 83.60 MiB, Chroma 55.80 MiB, gRPC 40.25 MiB and NumPy 32.83 MiB. Installed file size is not resident memory and is not a measured Linux image size. Chroma's standard dependency tree is substantial even with automatic embeddings disabled. No dependency pruning was attempted.

This verified arm64 macOS installation does not prove Linux wheel availability, Linux database portability or future combined application RSS. Preserve verified versions and perform those checks in the later packaging/deployment checkpoint. Continue to pass embeddings explicitly and avoid any model download or corpus indexing at application startup.

## Next approval

Local installation and integration verification have no unresolved blocking failures. Checkpoint 19B is ready for **explicit approval** to generate paid embeddings. API authentication/credit acceptance and actual semantic retrieval remain untested because no live request was authorized. Do not execute `app.index_embeddings --execute` until that approval arrives.
