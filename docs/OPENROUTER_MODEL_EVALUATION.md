# Checkpoint 19C — OpenRouter free-model evaluation

Completed 19 November 2026. **Provisional primary: NVIDIA Nemotron 3 Ultra (free). Provisional fallback: Baidu ERNIE-5.5-Flash-Preview (free), with reasoning enabled.** This is not a statistically comprehensive comparison or proof that Nemotron is intrinsically better. Four ERNIE questions, including Arabic, have no successful response within this checkpoint's request budget. No chatbot or automatic fallback was implemented, and `.env` was not changed.

## Availability and API constraints

Only official OpenRouter API endpoints were visited. The model catalog, authentication endpoint and both provider-endpoint lookups returned HTTP 200. The exact requested and returned IDs for successful generations match. Both models list text input/output, temperature, max_tokens and reasoning support. Prompt and completion pricing are zero.

| Exact model ID | Catalog available/free | Context tokens | Advertised maximum completion tokens | Observed constraint |
|---|---|---:|---:|---|
| `baidu/ernie-5.5-flash-preview:free` | Yes / yes | 1024000 | 921600 | Reasoning is mandatory; disabling it returns HTTP 400. |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Yes / yes | 1000000 | 65536 | Accepts reasoning disabled and enabled. |

Availability metadata: [official model catalog](https://openrouter.ai/api/v1/models), [ERNIE endpoints](https://openrouter.ai/api/v1/models/baidu/ernie-5.5-flash-preview:free/endpoints), [Nemotron endpoints](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b:free/endpoints). Exact captured values and timestamps are in `artifacts/checkpoint_19c/availability.json`. Availability and free-tier quotas can change.

Authentication was verified through `GET /api/v1/key`; no key, key label or account balance was saved. The key reported free-tier status. The returned legacy rate-limit field was explicitly deprecated, so its negative request count was not interpreted as unlimited quota. No useful numeric daily quota was supplied, no per-request limit was advertised, and no rate limiting occurred in this run.

## Evidence and fairness

The five Checkpoint 19B questions and their exact top-five rankings were reconstructed from saved result IDs plus full `chunks.jsonl` text. No truncated CLI excerpts were used as evidence. Original titles, URLs, source attributes, dates and chunk IDs were retained. Stable IDs S1–S5 are scoped to each question. Each model received identical evidence and identical system/user messages for that question; SHA-256 comparisons verified this, including the adjusted pair. No retrieval, embedding or reranking API call was made.

The system prompt requires supplied-evidence-only answers, valid source IDs, Arabic for Arabic questions, historical Wasalt snapshots, explicit uncertainty, and no reliance on generic press-hub titles as article evidence. The original order and misleading press-hub content were deliberately preserved to test grounding. Prompts and full evidence are separate artifacts. Model order alternated by question to reduce a fixed order effect; provider load and tokenizer differences remain confounders.

## Protocol failure and bounded adjustment

Initial common settings: temperature 0, reasoning disabled, output cap 2,000 tokens, no streaming. Nemotron answered all five questions. ERNIE rejected all five with: **Reasoning is mandatory for this endpoint and cannot be disabled.** The catalog advertised reasoning controls but did not specify that disabling reasoning was prohibited.

Continuing ERNIE after the first rejection was an evaluator implementation mistake. Those repeated failures consumed five generation attempts without producing text. They are configuration failures, not evidence of provider outage, poor language quality or model hallucination.

The user explicitly allowed parameter adjustments and a hard maximum of 12 generation attempts. The two remaining attempts were used for the **Spain question only**, with identical temperature 0, reasoning enabled and a 4,000-token total completion cap for both models. Both succeeded. The higher cap accommodates mandatory reasoning; reported completion usage includes reasoning tokens, not just visible answer text. Initial outputs remain preserved and are not overwritten or treated as equivalent to the adjusted protocol.

Automatic approval review initially interpreted the budget as ten and rejected the adjustment before starting a process. The original user instruction allowing 12 attempts and the persisted count of ten were verified; review then approved the two requests. The rejected action generated no API request.

The reusable evaluator now defaults to the verified common reasoning-enabled/4,000-token settings and stops further requests for a model after a parameter rejection. It performs no automatic retries or model/provider fallback. Both model IDs are allowlisted, catalog pricing must be zero, provider maximum prices are zero, and paid or alternate model IDs are rejected. Existing evaluation output cannot be silently overwritten or rerun. A fresh run would need new explicit authorization and a separately prepared output directory.

## Request counts, latency and usage

| Model | Attempts | Answers | HTTP 400 | Successful-response mean latency | Input tokens | Completion tokens |
|---|---:|---:|---:|---:|---:|---:|
| `baidu/ernie-5.5-flash-preview:free` | 6 | 1 | 5 | 3.834 s | 3,392 | 553 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 6 | 6 | 0 | 5.225 s | 20,706 | 1,770 |

**Total: 12 generation attempts, seven successful answers and five HTTP 400 parameter rejections.** Separately, four metadata/authentication GETs succeeded: 16 OpenRouter HTTP requests in total. There were no automatic retries, silent model fallbacks, authentication errors, 429s, 5xx responses or transport errors. The two explicit adjusted generations count toward the 12-attempt ceiling.

All seven successful responses reported `usage.cost=0`: **USD 0 reported cost**. Aggregate reported usage was **24,098 prompt tokens + 2,323 completion tokens = 26,421 tokens**. Completion tokens include **803 reasoning tokens**. Failed requests returned no usage, so no unreported usage was invented. Provider tokenizers differ, so identical prompts need not yield identical token counts.

The latency column pools different successful protocols and is not a fair head-to-head speed comparison. Nemotron's original five-question reasoning-disabled mean was **4.645 seconds**. The matched Spain pair was **ERNIE 3.834 seconds versus Nemotron 8.121 seconds**: ERNIE was faster on that single common-setting sample. These are non-streamed end-to-end response times, not time-to-first-token.

| Question | ERNIE initial | Nemotron initial | Matched adjustment |
|---|---|---|---|
| Trump Dubai amenities | No answer: HTTP 400 | Answered, 7.651 s | Not run; request budget exhausted. |
| Spain projects | No answer: HTTP 400 | Answered, 2.813 s | Both answered; reasoning enabled, 4,000 tokens. |
| Wasalt property listing FAQ | No answer: HTTP 400 | Answered, 3.098 s | Not run; request budget exhausted. |
| Riyadh villa rentals | No answer: HTTP 400 | Answered, 4.093 s | Not run; request budget exhausted. |
| Arabic An-Narjis villa request | No answer: HTTP 400 | Answered, 5.572 s | Not run; request budget exhausted. |

All original responses, all five ERNIE error placeholders, both adjusted answers and each question's source-ID mapping are reproduced without editing in [the complete answer transcript](../artifacts/checkpoint_19c/answers.md). Raw JSON responses are stored separately from scores and reviews.

## Quality scores

Scores are subjective assistant assessments against the actual supplied evidence, not blinded human review or another live LLM-judge call. Scale: 1 poor, 2 substantial issues, 3 mixed, 4 minor issues, 5 strong. Failed requests receive N/A, not an invented language-quality score of one. Scores across unequal sample sizes/protocols must not be used as a leaderboard.

| Model / protocol | Answer sample | Grounding | Instructions | Citations | Completeness | Language | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Nemotron, initial reasoning disabled | Five questions | 4.6 | 4.2 | 4.6 | 5.0 | 4.8 | 4.64 |
| ERNIE, initial reasoning disabled | No answers | N/A | N/A | N/A | N/A | N/A | N/A |
| ERNIE, adjusted reasoning enabled | Spain only | 5 | 5 | 5 | 5 | 5 | 5.0 |
| Nemotron, adjusted reasoning enabled | Spain only | 5 | 5 | 5 | 5 | 5 | 5.0 |

Per-response scores and reasons are in `artifacts/checkpoint_19c/scores.csv` and `quality_review.json`. The original Nemotron answers scored: Trump 5.0, Spain 4.4, FAQ 4.4, English property 4.6 and Arabic property 4.8.

### Grounding and citation findings

- **Trump:** Nemotron accurately separated exclusive resident amenities from club access requiring membership. It did not import amenities from the off-topic AIDA/Jeddah result. Citations supported the statements.
- **Spain, initial:** Nemotron named Tierra Viva and Marea from S5 and acknowledged limited coverage. Some specificity, including the luxury-villa characterization and first-project launch location phrasing, was not established by the cited S1/S5 bodies. S1 does not name Tierra Viva; the substantive named-project support is S5. No new development name was fabricated.
- **Spain, adjusted pair:** Both models used S5 for the two names and locations, S1 for market-entry context, and avoided treating the generic press-hub title as article proof. Both were concise and fully grounded on this question.
- **FAQ:** Nemotron correctly described account creation, property details, photos and pricing. It added unsupported audience roles for the Wasalt App versus Wasalt Business App. Those plausible roles are absent from the supplied evidence and should not be asserted or credited to S1.
- **English properties:** All five areas, prices, bedroom counts, districts and available bathroom values agreed with supplied records. The opening said properties were **currently offered**, contradicting the explicit snapshot instruction despite the later historical-data disclaimer. This is an instruction-following failure, not a wrong numeric attribute.
- **Arabic property:** Nemotron selected listing 5891036, correctly preserved the supplied area, bathrooms, price, location and other listed features, cited S1, used the exact source URL, and acknowledged the historical extraction date. Minor Arabic grammatical agreement did not obscure meaning.
- All emitted source IDs were valid S1–S5. **Valid ID syntax does not establish factual citation support**; the issues above were found by reading the actual evidence. No fabricated development name or incorrect supplied numeric property detail was found. No fabricated external URL was found. FAQ extras were unnecessary but not severely verbose.

Property-query scores do not penalize the absence of a structured-filter engine. They assess how accurately each answer describes the provided records and their limitations. No structured filtering was implemented.

## Recommendation and Checkpoint 20 limitations

**Choose Nemotron provisionally as primary** because there is actual successful coverage of all five questions, including Arabic, with useful citations, correct numerical property data and generally concise responses. Its initial mean latency was responsive in this window. This recommendation is based on observed coverage, not model popularity or size. Snapshot wording and unsupported embellishment need strict checking in the next approved phase.

**Recommend ERNIE provisionally as fallback with reasoning enabled**, without implementing fallback. It produced a high-quality, faster answer in the one matched Spain pair. It was not successfully evaluated on the other four questions or Arabic, so its broader suitability remains unverified. Do not interpret the initial parameter-error count as intrinsic free-endpoint unreliability.

There is no current authentication, free-pricing, dependency or index blocker. However, this checkpoint did not complete a five-question successful matched comparison. A definitive head-to-head selection needs separate approval for the four remaining common-setting pairs (eight additional requests) or explicit acceptance of the provisional recommendation. **No further requests are authorized within this checkpoint.** Even a larger small test cannot guarantee free-endpoint availability or all future answers.

## Files, commands and verification

Created `app/evaluate_openrouter.py`, `tests/test_openrouter_evaluation.py`, this report and `artifacts/checkpoint_19c/`. The existing configuration, requirements and `.env` were not modified. No dependencies were installed. Raw model outputs, prompts/evidence, request-status logs, usage, scores and the answer transcript are separate artifacts.

Commands executed:
```bash
.venv-extraction/bin/python -B -m app.evaluate_openrouter
.venv-extraction/bin/python -B -m app.evaluate_openrouter --execute
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_openrouter_evaluation.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Additional bounded Python commands performed official metadata/authentication GETs, the two explicit adjusted `OpenRouterAPI.generate` calls, read-only SQLite verification and report generation. The adjusted call settings and statuses are recorded in `adjustment_manifest.json`; the original ten-attempt manifest remains unchanged.

Final tests: **99 passed, zero failures or skips**, including all existing 89. The added tests mock the API and cover free-model allowlisting, free-price validation, token/temperature/provider settings, error handling, no automatic retries/fallback, secret redaction, request ceilings, identical prompts, stop-on-parameter-rejection, and read-only evidence reconstruction.

All **2,101 files** across `data/`, `artifacts/chunks/` and `artifacts/chroma/` retained their original SHA-256 hashes. The Chroma collection still contains **1,709 records**, confirmed with SQLite read-only/immutable mode and exact ID-set comparison. No Chroma client was opened against the production index during this evaluation. No document or query embeddings were generated. Report validation checks the two model allowlists, twelve-attempt count, matching prompt/evidence hashes, zero reported cost and absence of API keys in saved evaluation artifacts.

Existing `.gitignore` rules exclude secrets and artifacts. No Git staging, commits, app interface, answer-serving pipeline, automatic fallback, Docker work or deployment occurred. **Stopped pending model-selection approval.**
