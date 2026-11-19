# Checkpoint 20A — Safe diagnostics and controlled free fallback

Objective: preserve useful OpenRouter failure diagnostics and add an optional, tightly bounded Nemotron fallback without changing retrieval, source data, citations, historical disclaimers or UI architecture.

Completed with **zero live generation requests and zero query-embedding requests**. Checkpoint 20 validation was not rerun, and its attempt records and saved results were preserved. No dependencies were installed, no environment file was modified, and no Docker, Render or Git mutation occurred.

## Files changed

| File | Change |
|---|---|
| `app/evaluate_openrouter.py` | Shared API adapter now extracts safe diagnostic fields, drops arbitrary failed-response messages/account fields, and removes full-prompt echoes from diagnostic values |
| `app/chatbot.py` | Disabled-by-default free fallback, fixed-message exception carrying diagnostics, and internal per-attempt diagnostics on both success and failure |
| `app/openrouter_diagnostics.py` | New allowlisted extraction, conservative classification and eligibility predicate |
| `tests/test_openrouter_diagnostics.py` | New 21-test mocked/offline regression suite, including listing-card rendering after both models fail |
| `docs/CHECKPOINT_20A_RESULTS.md` | This report |

Created `artifacts/checkpoint_20a/` with initial/final full-suite logs (`offline-tests.txt`, `final-tests.txt`) and initial/final integrity checks (`integrity.json`, `final-integrity.json`). No original Checkpoint 20 artifact was overwritten.

## Available diagnostics

The API adapter returns `diagnostics`; the application retains each attempt under `generation.attempt_diagnostics[]`. Failed generation exceptions also carry that list internally. The UI continues to show fixed, concise error messages, without exposing the diagnostic object. No new automatic disk logging was introduced.

| Field | Retained information |
|---|---|
| `model_requested` | Application-assigned approved model ID, in each application attempt record |
| `http_status` / `error_code` | Integer HTTP status and integer OpenRouter error code, when available |
| `limit_source` | Bounded machine identifier from `error.metadata.limit_source` |
| `provider_name` | Bounded name from error metadata, otherwise the top-level provider field |
| `request_duration_seconds` | Measured request duration, including response processing, rounded to milliseconds |
| `retry_after` | Validated numeric delay or HTTP-date converted to an ISO timestamp |
| `retry_after_seconds` | Numeric header delay, otherwise numeric `metadata.retry_after_seconds`, when supplied |
| `rate_limit_reset` | Allowlisted reset headers and metadata reset timestamps, retaining their origin and units |
| `error_type`, `provider_code`, `provider_error_code`, `reason` | Bounded machine-code identifiers only |
| `rate_limit_category` | Conservative classification described below |

Reset-header support covers `X-RateLimit-Reset`, `RateLimit-Reset`, `X-RateLimit-Reset-Requests` and `X-RateLimit-Reset-Tokens`, including selected values from `error.metadata.headers`. Reset metadata supports `resets_at`, `reset_at` and `reset_time`. Arbitrary strings, malformed types and unrelated headers are discarded. Reset timestamps/durations are preserved without guessing whether they describe a minute or day quota. Retry hints are recorded; this checkpoint adds no automatic waiting or retry loop.

Failed-response raw messages, raw provider bodies, authorization/cookie headers, account IDs, balances and other unallowlisted metadata are not retained. Failed-response usage/provider/response-ID fields that could contain arbitrary echoed data are cleared in favor of the safe diagnostics. Existing API-key redaction still applies, and an echoed complete prompt is omitted even if it appears inside an otherwise allowlisted label. Missing fields remain null or empty rather than being invented.

The public OpenRouter [limits documentation](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/limits.mdx) and [error documentation](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/errors-and-debugging.mdx) were consulted. They distinguish platform from upstream errors and describe error metadata and retry headers. No authenticated key/quota endpoint was queried.

## Classification and fallback policy

The classifier recognizes explicit supported machine codes; it does not parse arbitrary error prose or infer quota scope from provider names, request counts, elapsed time or reset delays.

| Category | Evidence required | Fallback |
|---|---|---|
| `openrouter_free_per_minute` | Explicit `openrouter_free_tier_per_minute` source | Never |
| `daily_or_account_quota` | Recognized daily/account/credit/budget source or explicit quota/credit code | Never |
| `upstream_provider_capacity` | Explicit supported upstream capacity/rate source, without contradictory quota/authentication signals | Only with the flag enabled |
| `unknown_429` | HTTP 429 without sufficient recognized metadata, or conflicting error codes | Never |
| `not_http_429` | Any other HTTP status or transport failure | Never |

The positive upstream-source allowlist is `upstream_provider_shared_pool`, `upstream_provider_capacity`, and `upstream_provider_rate_limit`. These are the application's recognized policy values; unknown future source identifiers remain in diagnostics but are ineligible. Explicit quota/credit signals override an upstream label. A conflicting HTTP/body error code also blocks fallback. Provider name plus a generic `rate_limit_exceeded` code does not suffice.

`OPENROUTER_ENABLE_FALLBACK=false` is the default when unset. The flag accepts `true` or `false` (case-insensitive, with surrounding whitespace removed); other values fail configuration validation. No flag was enabled in the actual environment. To change it later, set it before application initialization and restart the cached application runtime.

The only possible request sequence per application generation is:

1. ERNIE: `baidu/ernie-5.5-flash-preview:free`.
2. At most one Nemotron request: `nvidia/nemotron-3-ultra-550b-a55b:free`, only after an actual failed HTTP 429 positively classified as upstream capacity and only when explicitly enabled.

There is no fallback from Nemotron, recursion, primary retry or paid model selection. A primary success or any noneligible failure makes only one request. An injected adapter's existing attempt counter remains authoritative; the application neither resets it nor bypasses it. The default fresh runtime adapter permits one attempt with fallback disabled and at most two when enabled.

Both requests use exactly the same bounded grounded messages, reasoning enabled, temperature zero and a 4,000-token completion budget. Approved `:free` IDs, prompt/completion price caps of zero, required parameter support, disabled provider fallback and disabled redirects are preserved. Returned model identity, truncation and reported-cost checks still apply. No live endpoint availability or fallback performance claim is made from these mocked tests.

Application-controlled citation validation is unchanged and still runs on a fallback answer. Deterministic JSONL listing cards and historical disclaimers remain independent of generation. A mocked double failure rendered listing 5891036 successfully in Streamlit AppTest, retaining its historical disclaimer and both internal diagnostic records.

## Actual verification results

- **144 tests passed, zero failures or skips**, in 6.264 seconds: the prior 123 tests plus 21 new tests. The initial full run passed 143; a final prompt-echo redaction regression brought the final total to 144.
- The new tests cover every category, positive eligibility, disabled/default/invalid flags, one-fallback maximum, quota/authentication precedence, missing/malformed metadata, unknown sources, retry/reset fields, duration, credential/account/prompt exclusion, timeouts/empty/wrong-model/cost rejection, existing counter enforcement, identical evidence/free request configuration, citation rejection, and deterministic card rendering after both models fail.
- SHA-256 verification after the final suite: **all 2,160 protected files unchanged**, including `data/`, chunks, production Chroma, Checkpoints 19C/19D and every Checkpoint 20 artifact.
- Read-only, immutable SQLite inspection confirms **1,709 indexed records**. The completed manifest still matches the chunk checksum and 1,536 dimensions. No Chroma client was opened on the production store.
- Credential-value scanning of changed source/test files and new checkpoint artifacts found no leaks.
- No new generation, embedding, scraping, indexing or deployment was performed. Tests used mocked transports and disabled socket connections.

Commands executed included read-only `cat`, `rg` and `sed` inspection; Python SHA-256/credential scans; immutable SQLite reads; and:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_openrouter_diagnostics.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The full-suite command was run before and after the final redaction regression, saving separate logs. Neither `app.validate_chatbot --execute` nor any earlier evaluator was invoked.

## Original failures, blockers and next step

The existing `q02.json` through `q05.json` retain only a generic rate-limit error, overall pipeline latency and `generation: null`. They do not contain the HTTP response metadata, provider field, retry/reset headers or generation-request duration required to classify the cause. The user-reported dashboard provider, Baidu Qianfan, is useful routing context but does not establish which quota/capacity mechanism rejected a request. **The original four causes remain unknown; none can retrospectively qualify for fallback.** Their overall latencies must not be represented as recovered request-level diagnostic timings.

There are no remaining offline implementation blockers. Live classification and fallback behavior against real responses remain untested because the approved live budget is zero. Historical metadata cannot be recovered from the saved files.

Recommended next step: review this checkpoint and keep fallback disabled until a separately authorized controlled live validation budget is available. No live validation, configuration change or subsequent checkpoint was executed. Stopped after Checkpoint 20A.
