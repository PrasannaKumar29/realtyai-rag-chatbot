# Checkpoint 20F — RealtyAI architecture, retrieval and UX

Objective: improve general knowledge coverage, representative portfolio evidence, conversational instructions and the Streamlit welcome experience while preserving exact property search and safety. Implemented and validated offline. No live OpenAI/OpenRouter request, Docker work or deployment occurred.

## Files changed

- `app/property_search.py`: ordinary unrecognized knowledge questions now route to bounded general retrieval. Contextual IDs, explicit sources, corpus-derived names and structured filters retain precedence. Greetings and genuinely ambiguous known entities can still request clarification.
- `app/development_evidence.py`: derives a conservative project inventory with original titles, URLs and chunk IDs; recognizes broad portfolio requests, and orders inventory overviews across recorded market groups without implying business importance.
- `app/chatbot.py`: bounded general retrieval searches both companies; broad portfolio context can use original inventory overviews; candidate top-k is 30, focused context six, general/cross-source context eight, broad portfolio context ten. Removes the duplicated long runtime prompt extension and imports the new runtime prompt.
- `app/answer_prompt.py`: new conversational, grounded RealtyAI prompt. Frozen evaluation templates remain unchanged.
- `app/streamlit_app.py`: RealtyAI branding, inline welcome input, four compact prompts, top-right New chat, advanced sidebar filters and preserved conversation/status/card rendering.
- `.streamlit/config.toml`: new neutral dark theme using supported Streamlit settings, with usage telemetry disabled.
- `tests/test_realtyai.py`: seven new meaningful regressions.
- `tests/test_chatbot_ui.py`, `tests/test_chat_loading_and_misses.py`: update assertions for the requested RealtyAI/New chat labels and replacement suggested prompt. Existing behavioral assertions remain.
- `docs/CHECKPOINT_20F_RESULTS.md`: this report.

Created `artifacts/checkpoint_20f/evaluate_offline.py`, `evaluation.json`, `tests.txt` and `integrity.json`. Existing artifacts were preserved.

## Architecture audit and routing simplification

Before: unknown questions often stopped at clarification. Explicit sources or known development aliases reached retrieval. Semantic pools, bounded lexical recovery and category/prose scoring selected six passages; broad questions could have too few useful ranking terms to recover projects. Generic marketing pages could still fill this vacuum. A separate evaluation-style prompt plus repeated runtime instructions produced unnecessarily mechanical guidance.

After:

```text
Ordinary knowledge question
  → explicit source / known entity / bounded general scope
  → one OpenAI query embedding
  → Chroma candidates + existing-vector recovery
  → bounded original evidence → ERNIE → validated citations

Structured property request
  → existing lightweight interpretation → exact JSONL filtering
  → verified counts/cards + historical disclaimer
  → existing generation integration when evidence is available

Broad DarGlobal portfolio question
  → semantic retrieval + corpus-derived inventory overviews
  → diverse original project passages → ERNIE → validated citations
```

General scope searches DarGlobal and Wasalt informational documents, not arbitrary Wasalt listings. It uses the same query vector for both sources. Clarification remains appropriate for ambiguous entity names, unsupported structured conditions, multiple conflicting filter values and simple greetings. There is no new LLM router, framework, agent or hosted reranker.

Exact-ID misses still terminate without Chroma initialization, query embeddings or generation. Unknown attributes remain unknown; exact/unknown/mismatch classifications and price-period boundaries are unchanged. Known development resolution and the 20E prose/citation protections remain.

The structured backend still attempts its existing generation integration for nonempty results; deterministic card summaries override its free-form property prose/counts. This preserves the existing API/error/fallback regressions but remains an opportunity to make optional explanation calls more economical later. No new user-facing explanation setting was introduced.

## Project inventory and portfolio coverage

The catalogue now additionally exposes **19 conservative inventory records**. Eligibility requires a corpus-recognized name supported by the page body and structured project markers such as property/unit type in the original overview. Entries retain the original title, source URL, all associated chunk IDs and the actual overview record. Each URL occurs once; genuinely separate phases/pages are not silently merged without evidence. Generic category names or marketing headlines are not inserted as development names.

Recorded market labels are derived from existing country-listing URL metadata and literal occurrences in the project overview/title. Unmatched markets remain unspecified. This is intentionally incomplete and is not a corporate market analysis. Some pages mention a city rather than the country label, so a missing label does not mean the project lacks a location. The model receives original text and must preserve the location actually supported there.

For broad portfolio questions, round-robin coverage of these recorded groups supplies distinct original project overviews, preventing a context consisting mainly of crypto/payment pages or generic categories. These inventory-aided entries carry **no fabricated cosine distance**; diagnostics record null for that field. They are a provenance-based retrieval aid, not a separate factual source. Focused named-development and country questions continue to use 20E semantic/prose selection and the same cosine cutoff.

Generic pages are not categorically banned. They remain eligible for relevant financial, company and investment questions. Generic `/press` hub contamination remains excluded. Existing original texts, vectors, metadata and deterministic IDs are unchanged.

## Bounded offline configuration comparison

Compared candidate k **10, 20, 30** and final context limits **6, 8, 10, 12** using actual Chroma on a temporary index copy and existing document vectors as mocked queries. Missing real query vectors prevent treating this as a production recall benchmark.

For the broad-question comparison at k=20:

| Context cap | Inventory-aided distinct original project URLs | Source tokens |
|---|---:|---:|
| 6 | 6 | 2,348 |
| 8 | 8 | 3,224 |
| 10 | 10 | 3,922 |
| 12 | 12 | 4,684 |

All four covered five explicitly recorded market labels in this surrogate comparison. More passages increased named examples but did not establish broader business importance. Inventory availability made broad coverage less sensitive to k; the semantic-pool-only comparison still uses the current selector on the URLs already available, rather than representing the old unmodified algorithm.

Selected policy: k=30 for DarGlobal candidate searches to retain a bounded recall margin, six final passages for focused questions, four per company for general/cross-source questions, and ten original overview passages for broad portfolio questions. Ten provides more representative examples than six without sending 30 chunks to the model. This is a conservative design choice, not a proven optimal live-query setting.

Each original chunk is at most 500 tokens, so ten project overviews bound source text at 5,000 tokens; the measured broad context was 3,922. Prompt, source metadata and bounded history add overhead. Existing question/history limits remain. Focused lexical recovery remains capped at 12 candidates and reads only their existing vectors.

## Updated generation instructions

The runtime prompt now identifies RealtyAI and asks for direct, professional answers in the user's language, including Arabic. It discourages evaluation-style openings and discussion of supplied context, chunks or RAG. Focused answers should be concise; broad and multipart answers should give proportionate coverage without forcing a fixed project count.

Grounding remains mandatory: only supplied facts, original source IDs, no invented URLs/names/specifications/amenities/features, preserved ambiguity and access conditions, unknown values remaining unknown, no live availability claims and historical Wasalt records. Citation IDs still map to trusted URLs in application code; unused retrieved sources are not appended automatically.

Portfolio answers must be representative rather than claim completeness. Major/largest-market answers require an explicit business metric such as revenue, sales or pipeline; otherwise the assistant must say that it cannot verify the ranking. Page counts, country frequency, our inventory distribution and similarity scores are explicitly prohibited as substitutes. No fresh model answer was generated to verify compliance with these instructions.

## RealtyAI experience

The welcome screen uses the title **RealtyAI** and subtitle:

> Your AI-powered guide to DarGlobal developments and Wasalt properties.

The primary input is inline in a native container under the welcome heading. Four suggestions appear beneath it in two compact columns: Explore DarGlobal developments; What is the AIDA project?; Find villas for rent in Riyadh; How does Wasalt work?

After submission, the conversation remains in the main column and the input uses Streamlit's bottom-docked main-area behavior. Submitted questions are persisted before backend work. The real assistant-side status stages, bounded history, safe errors, citations and compact property cards remain.

**New chat** is in the top-right main-content column. It clears conversation/pending state, returns to the welcome screen, and does not clear the cached runtime/index or make a request. The sidebar retains only snapshot information and collapsed **Advanced property search**. Theme settings use native configuration; there are no external logos, positional CSS hacks, artificial delays, percentages or token-streaming changes.

## Offline evaluation and tests

The representative set covers 11 intents: AIDA; Spain; iconic portfolio; projects plus major market; both-company comparison; Wasalt listing procedure; constrained Riyadh villas; known ID; unknown ID; Arabic property ID; and an unsupported future revenue forecast.

- Deterministic routing/filter checks: eight eligible Riyadh villa rentals, one known/Arabic ID match, zero unknown-ID matches. Existing null/boundary tests pass.
- Mocked retrieval/ranking tests: retained focused source selection, bounded broad coverage and trusted-source behavior.
- Actual Chroma with saved **document** vectors as surrogate queries: AIDA selected six passages (2,633 source tokens), Spain six (2,289), portfolio ten (3,922), comparison eight (2,394), FAQ six (1,412). Spain still retained the original blog naming both Tierra Viva and Marea.
- End-to-end live validation: **none**. No real query embeddings were available. Directness, completeness, major-market refusal and natural output style were not rated from mocked answers. The unsupported forecast case produces context in the surrogate run; that does not mean the context supports a forecast or that model refusal was demonstrated. Prompt instructions and existing insufficient-evidence/citation guards remain necessary.

**207 tests passed, zero failures or skips**, in 7.655 seconds: prior 200 tests plus seven new regressions. Existing tests were retained, with requested branding/action expectations updated. New coverage includes general routing, provenance/market/context bounds, information-only general Wasalt scope, prompt safeguards, welcome components and New chat preserving resources without requests.

Browser skill discovery returned no connected browser. Functional UI validation used Streamlit AppTest; no desktop/mobile screenshot review was possible. Native dark-theme appearance and perceived welcome placement require local manual acceptance.

## Integrity, commands and restrictions

SHA-256 verification confirms **all 2,206 protected files unchanged**, including original datasets, chunks, production Chroma and prior checkpoint artifacts. Read-only immutable SQLite confirms **1,709 records**. Unchanged binary/store file hashes preserve the existing embeddings byte-for-byte. No credential values were found in changed code/tests and new artifacts.

Commands included read-only source/documentation inspection, Python integrity/credential checks, immutable SQLite reads and:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_realtyai.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
.venv-extraction/bin/python -B artifacts/checkpoint_20f/evaluate_offline.py
```

The evaluation script preserves its saved output and refuses to overwrite it. A matrix field was renamed after generation to clarify that the semantic-pool comparison uses the current selector; recorded rankings/counts were not changed.

Zero live API calls, dependencies, scraping, corpus edits, chunk regeneration, document embeddings, index rebuilds, model/fallback changes, Docker/Render work or Git mutation occurred. No offline test blocker remains.

## Restart and manual acceptance

Stop the previous Streamlit process with Ctrl+C or its running-command Stop control. Restart from the repository root so the new theme and cached runtime are loaded. For **zero-API review**, use empty process-level key overrides (the root `.env` is untouched):

```bash
# Run from the repository root.
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Refresh `http://127.0.0.1:8501`. Confirm RealtyAI/subtitle, prominent welcome input, four compact suggestions, neutral dark theme, advanced filters and top-right New chat. Submit `Show listing 99999999` to verify the deterministic miss/caveat without citations. Submit `Show listing 5891036` to inspect the retained card/date/source link; in this empty-key profile, its existing generation integration reports a missing-key error while the card remains available. Confirm immediate user turn, prior history, processing/error presentation and New chat returning to welcome. Very fast misses may complete before a long animation is visible; no fake delays are added.

Knowledge answers cannot be acceptance-tested with empty embedding/generation credentials. After a **separately authorized live budget**, restart the same command without the two empty-key assignments and try focused amenities, AIDA, Spain, both broad portfolio questions, major markets, company comparison and FAQ questions. Check natural language, distinct supported examples, source-specific citations, no completeness claims and no guessed major-market ranking. No such live review was performed here.

Remaining risks before Docker: actual live ranking and free-provider reliability remain unproven by surrogate vectors; prompt behavior requires manual acceptance; inventory and market labels are conservative/partial; structured searches retain a generation attempt whose prose is suppressed in favor of deterministic cards; Linux memory/concurrency and artifact-transfer/dependency packaging remain unvalidated. None authorizes deployment now.

Recommended next step: local manual acceptance using the approved budget/profile, then wait for explicit packaging/deployment approval. **Stopped after Checkpoint 20F.**
