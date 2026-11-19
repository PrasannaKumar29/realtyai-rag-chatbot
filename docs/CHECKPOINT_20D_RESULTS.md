# Checkpoint 20D — Unknown IDs and chat processing status

Objective: make explicit unknown listing IDs terminal dataset lookups, improve visibility during chat processing, and apply the two requested card-caption improvements. Completed locally with offline tests only.

## Root cause of the unknown-ID failure

Before editing, the exact reported question produced `route='wasalt'` and empty filters:

> Show me the details of Wasalt property listing 99999999.

The parser still required exactly seven digits (`[0-9]{7}`), based on the IDs observed in the collected sample. Eight-digit `99999999` was not recognized. The Wasalt keyword then selected informational RAG. This was **ID parsing followed by incorrect routing**, not an unsuccessful JSONL lookup falling back to informational retrieval: the exact lookup was never reached.

The seven-digit known ID 5891036 continued to route correctly. An Arabic eight-digit ID was likewise rejected before the fix.

## Files changed

| File | Change |
|---|---|
| `app/property_search.py` | Replaces the fixed seven-digit limit with contextual numeric identifiers of variable length. Retains quantity/phone guards and excludes bare year-like references unless an explicit ID marker is present. |
| `app/chatbot.py` | Makes exact-ID misses return immediately before semantic retrieval or generation. Defers Chroma initialization until a semantic query actually needs it, with a lock protecting the shared cached runtime. Adds optional status callbacks at real backend stages. |
| `app/streamlit_app.py` | Persists submitted user turns before backend work, tracks one pending request, displays assistant-side native status updates, preserves prior messages, handles interrupted reruns without automatic retries, and retains Clear conversation. Formats capture dates and hides the zero-unknown caption. |
| `app/presentation.py` | Adds human-readable capture-date formatting and the live-site-existence caveat to deterministic English/Arabic dataset-miss notices. |
| `tests/test_chat_loading_and_misses.py` | New 18-test offline regression suite covering misses, initialization, status timing, history, errors, card presentation and zero-API manual mode. |
| `docs/CHECKPOINT_20D_RESULTS.md` | This report. |

Created `artifacts/checkpoint_20d/`: `focused-tests.txt`, `offline-tests.txt`, `final-tests.txt`, `unknown-id-example.json`, `integrity.json`, and `final-integrity.json`. Earlier checkpoints and validation counters remain unchanged. No existing tests were removed or rewritten.

## Deterministic no-match behavior

IDs are now identified by property/listing context rather than by the digit count present in this particular sample. IDs remain strings, including leading zeros. Tests cover one-, five-, seven-, eight-, nine- and twelve-digit unknown values and Arabic-Indic digits. Ordinary prices, areas, phone-labelled numbers and year references do not become IDs. For ambiguous bare year-like references from 1900 through 2100, an explicit ID marker is required to treat the number as an identifier.

The reported question now has `filters={'listing_id': '99999999'}` and checks JSONL directly. An absent identifier returns:

> Listing 99999999 is not in the collected Wasalt dataset. This does not establish whether the listing exists on the live Wasalt website. Verified historical matches: **0**. Displaying **0** listing cards.

An equivalent Arabic notice is generated in code. The historical-data disclaimer remains present. There are no unrelated citations, source links or substitute cards.

The explicit miss guard returns before query embeddings, informational RAG and OpenRouter. It also prevents a mixed-source plan from using informational material to fill an absent property identity. Known records and additional-filter exact/unknown/mismatch classification retain their existing behavior.

The default runtime no longer constructs `Retrieval` in `Chatbot.__init__`. Consequently a pure exact-ID miss does not even initialize Chroma or an embedding client. Semantic retrieval still validates and opens the temporary index copy when first needed, then reuses the cached instance. Model choice, ERNIE reasoning settings, free routing and fallback policy are unchanged.

`unknown-id-example.json` records the exact failing question after the fix, with zero retrieval initializations, zero generation calls, zero HTTP calls and only the actual `Checking Wasalt listings...` stage.

## Loading experience and reruns

Code inspection identified three relevant contributors:

1. The old submission path saved both user and assistant messages only after processing completed. The visible user turn was not yet durable session history while work was running.
2. A cold cached runtime eagerly initialized and validated Chroma before query routing, including for exact-ID misses that needed only JSONL.
3. Processing used a generic spinner, alongside a separate cached-resource spinner, with no backend-stage updates. Streamlit reruns could make stale elements appear dimmed without a useful explanation of the current work.

The revised flow is:

1. Queue the submitted chat/form/example question and persist its user turn.
2. Render prior history and that user turn.
3. Enter `st.chat_message('assistant')` and immediately show a native running `st.status` before calling the cached runtime or backend.
4. Update the label through an optional backend callback at actual operations: `Checking Wasalt listings...`, `Searching the knowledge base...`, or `Generating answer...`.
5. Mark completion/error, render the answer or safe error beneath the user turn, save one assistant turn, clear the pending request, and redraw saved history to re-enable input.

The initial `Preparing your answer...` status covers runtime preparation. It is visible even on a cache miss; Chroma loading for semantic questions then happens under the knowledge-base status. A deterministic ID miss never shows a generation stage. There are no percentages, fake delays, invented stages or streaming-token changes.

While processing, chat input and submit actions are disabled; prior messages remain rendered and Clear conversation remains available. A request token prevents an old completion from appending an answer after the conversation was cleared. If another rerun interrupts a started request, the UI records a clear interruption message and re-enables input instead of automatically submitting another API request. History remains capped at 20 turns, without duplicating the current user question in the prompt/history.

Validation instrumented the native status container while backend work was executing, confirming its state was `running` and the user/history were already present before both initialization and processing. Form and example submissions were checked to invoke the backend once, including after the completion redraw. Native Streamlit rerun repaint/dimming may still occur briefly; no CSS hides it. This checkpoint provides real progress visibility rather than a guarantee about every browser repaint. Desktop/mobile screenshot inspection was not performed; the layout continues to use Streamlit-native responsive components.

## Small presentation changes

- Cards now show `Captured: 18 Nov 2026` for the recorded capture date. The precise original timestamp remains unchanged in the collapsed technical JSON. Missing or invalid timestamps display `Unknown`; no timestamp is invented.
- The “0 other records have unknown required attributes” caption is omitted. Positive unknown counts remain visible. Missing attributes, source-quality notes, original listing URLs and historical disclaimers are preserved.

## Validation and integrity

Final full suite: **186 tests passed, zero failures or skips**, in 7.018 seconds: all prior 168 tests plus 18 new regressions. See `artifacts/checkpoint_20d/final-tests.txt`.

New coverage includes known 5891036, unknown 99999999 and other lengths, Arabic unknowns, absence of unrelated sources, no retrieval construction/embedding/generation/HTTP on an exact miss, ordinary numeric constraints, lazy initialization reuse, user/history ordering, a running native status before initialization/backend work, real-stage labels, completion/error rendering, safe initialization errors, interrupted-rerun handling, Clear behavior, history bounds, single execution of chat/form/example requests, timestamp formatting, nonzero unknown captions and known-card preservation under a mocked generation failure.

The first full run exposed a test-fixture isolation issue: a cached mock from a new UI test survived into an existing test. Adding cache cleanup on test teardown resolved it. The failed initial log is retained as `offline-tests.txt`; the subsequent complete suite passed. No product fallback or model policy was changed to address this test issue.

Final SHA-256 audit: **all 2,170 protected files unchanged**, covering datasets, chunks, production Chroma and protected prior checkpoint artifacts. Immutable read-only SQLite inspection confirms **1,709 records**, 1,536 dimensions, a complete manifest and the original chunk checksum matching the manifest. Credential-value scanning of changed code/tests and new artifacts found no leaks.

There were **zero live OpenRouter requests and zero OpenAI calls**. No scraping, rechunking, re-embedding, source/index modification, dependency installation, Git staging/commits, Docker or Render work occurred. The production Chroma store was not opened by an SDK client during this checkpoint.

Commands executed included read-only file/regex inspection, offline routing examples, SHA-256 and credential scans, immutable SQLite metadata reads and:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_chatbot*.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_listing_id_routing.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_property_presentation.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_chat_loading_and_misses.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Errors or blockers: none remain in offline validation. Live service response timing and browser rendering were not exercised. No server restart or live request was performed by the agent.

## Exact restart and zero-API manual review

1. Stop the existing Streamlit process with **Ctrl+C** in its hosting terminal, or the running-command Stop control. This ensures the old cached Chatbot instance is discarded. If port 8501 is still occupied, stop that original instance before starting another on the same port.
2. From a terminal, run the following. The empty API-key overrides apply only to this process; they do not modify `.env`. Process values take precedence over dotenv, including empty values.

```bash
# Run from the repository root.
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

3. Open or refresh `http://127.0.0.1:8501` and select **Clear conversation**.
4. Submit `Show me the details of Wasalt property listing 99999999.` Verify a deterministic dataset-miss notice, the live-existence caveat, zero cards and no informational citations. The only backend stage is checking listings; a fast miss may finish too quickly to observe the indicator for long.
5. Submit `أخبرني عن عقار رقم ٩٩٩٩٩٩٩٩` and verify the equivalent Arabic notice.
6. Submit `Show listing 5891036`. In this zero-API profile, generation reports that its key is not configured, while the verified card still displays SAR 120,000/year, 250 sqm, nine bedrooms, six bathrooms, An-Narjis/Riyadh and the original Wasalt source link. Confirm `Captured: 18 Nov 2026`, a collapsed precise timestamp, the historical disclaimer and absence of the zero-unknown caption. The empty-key behavior was verified offline with an HTTP-call guard.
7. Confirm question-before-answer ordering, retained prior messages, re-enabled input and Clear conversation. Real status behavior during backend work is also covered by the offline tests; do not add artificial waiting to make a fast lookup look slow.

Normal credential-enabled startup uses the same command without the two empty-key assignments. Restoring live model/embedding access is outside this checkpoint's zero-call validation. Keep the empty overrides for this manual review unless a separate live budget is authorized.

Recommended next step: perform the zero-API manual review above. No subsequent phase was executed. Stopped after Checkpoint 20D.
