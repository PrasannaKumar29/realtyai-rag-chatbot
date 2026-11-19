# Final matched OpenRouter model comparison — Checkpoint 19D

**Recommended primary:** `baidu/ernie-5.5-flash-preview:free`. **Backup candidate:** `nvidia/nemotron-3-ultra-550b-a55b:free`. No automatic fallback was implemented and no model configuration was changed. This supersedes the provisional recommendation in Checkpoint 19C.

## Scope and common protocol

Eight new generation requests were executed on 19 November 2026: the four non-Spain questions, once per model. All eight succeeded with HTTP 200. The two successful reasoning-enabled Spain responses from Checkpoint 19C were reused, not regenerated. No earlier reasoning-disabled outputs, parameter-error responses or scores enter this matched comparison.

Every compared response used reasoning enabled, temperature 0, maximum completion tokens 4,000, the same system prompt and the exact saved user prompt/evidence for that question. Original source ranking, titles, URLs and S1–S5 identifiers were preserved. Prompt, evidence and common-parameter hashes match across models for each question. Reasoning tokens share the completion budget; 4,000 is not a visible-answer-only limit.

Existing OpenRouter request code was reused with an eight-attempt cap. Only the two approved `:free` model IDs were requested. Actual returned IDs matched. Provider prompt/completion price caps were zero; provider fallback and redirects were disabled. There were no retries, parameter adjustments, new questions, paid routes, new metadata calls, embeddings or retrieval operations. The runner would stop the entire evaluation after any failed request, including a parameter rejection.

## Matched result summary

| Model | New successful requests | Matched successful questions | Mean latency | Median latency | Overall quality / 5 | Reported matched cost |
|---|---:|---:|---:|---:|---:|---:|
| ERNIE | 4/4 | 5/5 | 5.531 s | 3.834 s | 4.88 | USD 0 |
| Nemotron | 4/4 | 5/5 | 8.260 s | 8.121 s | 4.48 | USD 0 |

Both models had zero failures. All ten matched responses reported zero cost. ERNIE was faster on three of five questions; Nemotron was faster on Trump amenities and the English villa list. ERNIE's mean was about 33% lower in this sample.

Latency is non-streamed, end-to-end API response time, not time-to-first-token. The Spain timings were measured earlier in 19C. Provider load, different tokenizers and caching can affect timing: ERNIE reported 512 cached prompt tokens across its matched calls; Nemotron reported zero. This is an observed small comparison, not proof of general latency or free-endpoint reliability. New-only mean latencies were ERNIE 5.955 s and Nemotron 8.295 s.

## Results for all eight new requests

Requested and returned model IDs were exactly the approved IDs in the first section. Each row below is a separate new request. Full returned text, provider name, finish reason and complete usage objects remain in `artifacts/checkpoint_19d/responses/`.

| Question | Model | HTTP | Latency | Input tokens | Completion tokens | Reasoning tokens | Cost |
|---|---|---:|---:|---:|---:|---:|---:|
| Trump Dubai amenities | ERNIE | 200 | 8.987 s | 3,175 | 1,707 | 1,439 | USD 0 |
| Trump Dubai amenities | Nemotron | 200 | 5.832 s | 3,570 | 759 | 475 | USD 0 |
| Wasalt listing FAQ | ERNIE | 200 | 2.108 s | 2,166 | 346 | 244 | USD 0 |
| Wasalt listing FAQ | Nemotron | 200 | 9.559 s | 2,449 | 376 | 226 | USD 0 |
| Riyadh villa rentals | ERNIE | 200 | 9.545 s | 3,055 | 2,079 | 1,820 | USD 0 |
| Riyadh villa rentals | Nemotron | 200 | 5.814 s | 3,492 | 537 | 116 | USD 0 |
| Arabic An-Narjis villa request | ERNIE | 200 | 3.181 s | 3,250 | 597 | 298 | USD 0 |
| Arabic An-Narjis villa request | Nemotron | 200 | 11.976 s | 3,603 | 715 | 298 | USD 0 |

## Full five-question matched comparison

Quality is the mean of the five scored dimensions for that answer. Spain is explicitly reused from `artifacts/checkpoint_19c/adjustment_responses/`. No Spain request was sent in 19D.

| Question | ERNIE quality | ERNIE latency | Nemotron quality | Nemotron latency |
|---|---:|---:|---:|---:|
| Trump Dubai amenities | 5.0 | 8.987 s | 4.4 | 5.832 s |
| Spain projects — REUSED 19C | 5.0 | 3.834 s | 5.0 | 8.121 s |
| Wasalt listing FAQ | 5.0 | 2.108 s | 4.4 | 9.559 s |
| Riyadh villa rentals | 5.0 | 9.545 s | 4.4 | 5.814 s |
| Arabic An-Narjis villa request | 4.4 | 3.181 s | 4.2 | 11.976 s |

All ten unedited answers, including the two clearly labeled reused Spain answers, are available in [the matched answer transcript](../artifacts/checkpoint_19d/answers.md). Its per-question source maps allow every S1–S5 citation to be checked against the original evidence. The complete matched results and provenance checksums are also in `matched_results.json`.

## Quality dimensions

Scores are subjective assistant judgments against the full supplied evidence, not an independent blinded human study or a separate LLM-judge API call. Scale: 1 poor, 2 substantial issues, 3 mixed, 4 minor issues, 5 strong. A score of five means strong performance on this question, not guaranteed correctness on all future questions. Equal numbers of matched questions are used for both models.

| Dimension | ERNIE | Nemotron |
|---|---:|---:|
| Factual grounding | 4.8 | 4.2 |
| Instruction following | 4.8 | 4.2 |
| Citation accuracy | 4.8 | 4.4 |
| Answer completeness | 5.0 | 4.8 |
| English/Arabic quality | 5.0 | 4.8 |

Per-response scores, source-specific reasons and issue categories are kept separately from raw model output in `scores.csv` and `quality_review.json`. Valid citation IDs are only a syntax check; a citation can exist yet fail to support the attached qualifier.

### Trump amenities

Both models correctly distinguish resident amenities from club facilities requiring membership. ERNIE additionally exposes the source wording difference: S2 says resident-only for the highest outdoor pool, while S3 mentions residents and guests. It also covers hotel-guest offerings. Nemotron generally follows S1/S2 exclusivity but does not expose the S3 difference. Its closing statement that no other facilities are listed overstates completeness: S3 also describes hotel private lounges and personalized service, a category it omits.

### Spain — reused matched pair

Both answers correctly identify Tierra Viva and Marea from substantive S5 text and use S1 for market-entry background. Neither relies on the misleading generic press-hub title. Both receive strong scores. These are exactly the successful reasoning-enabled responses from 19C, with their original timings and usage, not the earlier reasoning-disabled Nemotron answer.

### Wasalt FAQ

ERNIE gives the supported account/details/photos/price workflow and the explicitly captured login/OTP steps. Nemotron also gives the correct core workflow, without repeating its earlier app-audience-role invention. However, it says the apps can manage listings, citing S2. S2 advertises app downloads, selling/buying/renting and connecting with clients, but does not explicitly establish a listing-management feature. This may be plausible outside the evidence; it is not credited as grounded here.

### English property list

Both models preserve all five city/type/purpose matches, areas, bedrooms and annual prices and explicitly state that availability/prices are historical snapshots. Neither is penalized for lacking a structured-filter engine. ERNIE stays concise. Nemotron supplies more source-backed details, including recorded building years and the one supplied bathroom count, but adds split ACs for S1. That source says air conditioners are installed without specifying their type; the spot-light/gypsum wording does not establish split ACs. The numeric property facts remain correct.

### Arabic comparison and missing information

Both models correctly identify rental listing 5891036 in An-Narjis, Riyadh: approximately 250 sqm, six bathrooms, nine bedrooms, SAR 120,000/year, with a historical-snapshot caveat. Both use valid S1 citations.

ERNIE is more concise and linguistically smoother. It usefully labels another villa as partial, but its heading says the bathroom count does not match while the following bullet correctly says the count is missing. **Unknown is not a proven mismatch.** It should say the six-bathroom constraint cannot be verified for that alternative. This lowers its grounding, instruction and citation scores despite the correct main match.

Nemotron's longer description maps living areas labeled `الدور الأول` in the source to `الدور الأرضي` in its answer. The source itself has ambiguous level descriptions; silently resolving that ambiguity is not supported. It should preserve the labels or acknowledge uncertainty. Minor agreement in `يوجد فيلا` and an unverified Arabic rendering of the English brand name make its Arabic less polished. Its requested core numerical values are still correct.

No fabricated development names, invalid source IDs, invented external URLs or incorrect core numeric listing values were found. Remaining problems concern unsupported qualifiers, missing-versus-mismatched classification, source ambiguity and excessive certainty.

## Token usage and cost

Completion tokens include reasoning tokens; reasoning must not be added again when calculating totals. Input counts differ between provider tokenizers even though prompt hashes match. Figures below include the reused Spain pair exactly once.

| Model | Matched input | Matched completion | Included reasoning | Matched total | Reported cost |
|---|---:|---:|---:|---:|---:|
| ERNIE | 15,038 | 5,282 | 4,248 | 20,320 | USD 0 |
| Nemotron | 16,910 | 2,870 | 1,471 | 19,780 | USD 0 |

The eight **new** requests reported 24,760 input and 7,116 completion tokens (4,916 included reasoning tokens): **31,876 new tokens and USD 0 reported cost**. The full matched set totals 40,100 tokens, including the two reused responses. Those reused tokens were not newly incurred in 19D.

## Recommendation

**Primary: ERNIE**, with reasoning enabled. It gave more conservative, source-specific answers on the FAQ and English property cases, surfaced the amenities-source disagreement, delivered clearer Arabic, and was faster overall in this sample. The Arabic unknown-bathroom classification needs a guardrail; this recommendation is not a claim that its outputs need no validation.

**Backup candidate: Nemotron**, with reasoning enabled. It answered every matched question, preserves the key property values, and can be faster on individual questions. It tends to add more detail, which created extra unsupported qualifiers and an ambiguous floor assignment in this test. No automatic fallback was implemented.

This is one answer per model for five questions, not a statistically comprehensive benchmark or guarantee of free-endpoint reliability. Reused Spain timings, provider load, caching and non-blinded scoring limit generalization. Preserve source IDs/URLs, reject invented qualifiers, keep unknown fields unknown, and avoid resolving contradictory source text silently in the next approved phase. No prompt, retrieval, structured filtering or production chatbot change was made to fix these issues here.

## Files, commands and verification

Created: `app/evaluate_openrouter_matched.py`, `tests/test_openrouter_matched.py`, `artifacts/checkpoint_19d/`, and this report. All Checkpoint 19C artifacts remain unchanged. Existing evaluation code, `.env` and dependency files were not modified. No packages were installed.

Commands executed:
```bash
.venv-extraction/bin/python -B -m app.evaluate_openrouter_matched
.venv-extraction/bin/python -B -m app.evaluate_openrouter_matched --execute
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_openrouter_matched.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_openrouter*.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Additional offline commands reviewed answers against saved full evidence, produced scores/provenance/usage tables and verified file hashes. Evaluator tests: **14 passed**. Full suite: **103 passed, zero failures or skips**, including all prior 99. The four new mocked tests cover exact saved question selection and Spain provenance, eight-call settings/hash identity, global stop on parameter rejection, and refusal to overwrite/repeat an existing run.

Final verification confirms all **2,126 protected files** across original datasets, chunks, the production index and Checkpoint 19C artifacts retain their SHA-256 hashes. The production collection still has **1,709 records**, checked with read-only/immutable SQLite metadata access, not Chroma retrieval. No embeddings or index rebuild occurred. Saved results contain only approved free model IDs, zero reported cost, matching prompt/evidence hashes, and no API credentials. All new text artifacts are UTF-8.

**Stopped after comparison. Await approval of the primary/backup selection before Checkpoint 20.**
