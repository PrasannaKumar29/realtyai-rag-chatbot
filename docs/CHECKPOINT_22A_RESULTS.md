# Checkpoint 22A — Conversational context and focused answers

Completed offline on 20 November 2026. **220 tests pass**, including all 209
existing tests and 11 new context regressions. No staging, commits, pushes,
deployment or live OpenAI/OpenRouter requests occurred.

## Diagnosis

Streamlit stores conversation turns in session state and passes prior turns to
`Chatbot.answer`. Previously `interpret(question, ...)` routed only the new text.
Retrieval also received only that text; history reached the generation prompt
later. Thus a generic villa noun could select structured Wasalt filtering before
DarGlobal conversation context was considered. The semantic CLI in `app/search.py`
is independent of this chat path and required no change.

The shared cached Chatbot is intentionally not a session context store. New chat
already clears session conversation and pending state while retaining cached
resources. The fix derives context from the caller's bounded history instead.

## Changes

- `app/property_search.py`: added `conversation_plan`, a small wrapper around the
  existing interpreter. Explicit company scope now also outranks a generic
  property noun; exact listing-ID requests retain priority.
- `app/chatbot.py`: uses the context-aware plan before retrieval; passes the
  compact resolved question to retrieval and generation and saves it as
  `context_question` in the result for subsequent turns.
- `app/answer_prompt.py`: small focused-development guidance addition.
- `tests/test_conversation_context.py`: 11 new offline regressions.
- `docs/CHECKPOINT_22A_RESULTS.md`: this report.

No UI, dependency, Docker, startup, health-check, model/fallback, inventory,
retrieval top-k or environment configuration changes.

## Context resolution

Explicit company names, corpus-recognized development names (including ambiguous
matches), contextual listing identifiers, sale/rental intent and exact-search
form filters take precedence over inherited context. Other questions are eligible
only when marked by a bounded set of elliptical language cues in English or
Arabic, such as “tell me more”, “what about”, “it”, “those” or “فقط”.

At most four recent turns are examined. The latest prior user question and its
assistant result establish the active scope; assistant narrative is never mined
for facts or entities. A previous compact resolved subject supports chained
follow-ups. A named subject must resolve using the existing corpus-derived
catalogue. Multiple projects or a general/cross-source referent produce one short
clarification rather than choosing a project. No prior context also produces a
clarification for these elliptical questions.

For Wasalt filtering, prior verified filters are merged with newly interpreted
constraints. Only categorical context and an existing price period seed the
existing parser; old numbers are not reparsed as new constraints. Fresh values
override matching prior keys. Unsupported conditions, conflicting constraints and
missing rental budget periods retain the interpreter's clarification behavior.
Explicit form filters bypass inherited state. Filtering, missing-value
classification, original URLs, summaries and cards remain deterministic.

Examples covered offline:

| Prior subject | Follow-up | Result |
|---|---|---|
| DarGlobal overview | Tell me more about the villas | DarGlobal retrieval, no Wasalt cards |
| Named AIDA project | What amenities does it have? | Query retains the resolved development |
| Tierra Viva | What are the prices? | Project-scoped query, no unrelated listings |
| Riyadh rental villas | Only those under SAR 100,000 per year | Eight verified matches, zero API calls |
| Arabic Riyadh rental villas | فقط اقل من ١٠٠٠٠٠ سنويا | Same structured constraints and eight matches |
| Named development | Explicit Riyadh rental-villa request | Independent Wasalt search |
| Wasalt search | Explicit named development or DarGlobal villas | Independent DarGlobal retrieval |
| Multiple projects / empty history | Where is it located? | Brief clarification, no external calls |

This is a conservative language-cue mechanism, not general reference resolution.
Unmarked paraphrases, arbitrary new entity names, long-distance references and
complex cross-source follow-ups are not comprehensively supported. For explicit
new subjects, name the company/project or give a complete structured search.
No user profile or mutable cross-session context is introduced. Context is a
routing hint, never factual evidence or authorization to invent project prices.

## Focused-answer instructions

Focused project answers should prioritize project identity, location, distinctive
features and amenities. Country economics, taxation, infrastructure announcements
and tourism statistics are omitted unless requested or essential to a project
fact. Detailed requests and “tell me more” still allow relevant subject detail.
Missing project pricing must not be filled with market estimates. There are no
fixed word counts, extra generation pass, project templates or model changes.
Existing citations, uncertainty, historical-status and grounding instructions
remain. Mocked outputs verify query/prompt assembly and validation behavior;
they do not establish live prose conciseness, pricing coverage or answer quality.

## Scrolling investigation

The welcome input is inline; subsequent chat input is already in the main body,
which Streamlit documents as bottom-pinned. Prior turns render before the pending
assistant status, followed by a completion rerun. Session-state ordering, loading
states and New chat remain unchanged.

The documented `st.container(autoscroll=...)` behavior applies to fixed-height
scrolling containers. It does not provide a one-shot full-page scroll-to-turn
operation. Rehousing the accepted full-page conversation in a fixed-height scroll
surface would change mobile interaction and does not establish reliable
submission-only scrolling. Therefore **no scrolling change was made**, as allowed
by the checkpoint. No DOM selectors, iframe scripts or forced-scroll loops were
added. The production scroll-position limitation remains; no browser scroll
behavior is claimed to have been fixed or verified.

References: [Streamlit chat input](https://docs.streamlit.io/develop/api-reference/chat/st.chat_input)
and [container scrolling](https://docs.streamlit.io/develop/api-reference/layout/st.container).

## Validation and integrity

The final complete suite passed **220 tests in 7.868 seconds**, zero failures.
Existing tests continue to cover loading order, history, New chat, citation
rejection, property cards, historical disclaimers and exact/unknown IDs.
New tests cover scoped follow-ups, both explicit switch directions, Arabic
narrowing, sequential constraints, form overrides, ambiguous references, bounded
history, chained subjects, original URL validation and zero calls for pure search.
Network/HTTP/API guards and mocked generation/retrieval keep these tests offline.

All 11 new tests also passed in **0.182 seconds** inside the existing
`realtyai:21a` Linux AMD64 image. Changed `app/` and the test file were mounted
read-only; only the required listing fixture was additionally mounted read-only.
The container ran with `--network none` and empty API keys. No image rebuild,
dependency installation or deployment was needed for this compatibility check.
Existing Docker COPY rules already include every modified runtime module.

SHA-256 comparison verified **2,112 protected files unchanged**, covering original
source datasets, prepared chunks, original Chroma and the packaged runtime bundle.
Every runtime manifest checksum still matches. Immutable SQLite verification
confirmed **1,709 embedding records**; Wasalt JSONL still has **261 records**.
No real credential values were found in changed code/tests. `git diff --check`
passed. No scraping, re-chunking, re-embedding or index writes occurred.

The helper uses the existing development catalogue/cache and small per-turn data;
no framework, model, service or additional embedding call was added. Production
512 MiB/0.1 CPU memory and latency were not remeasured here. The AMD64 offline
runtime tests establish compatibility, not production concurrency or live-provider
availability. All existing runtime assets, pins and startup/health settings remain.

## Local commands and recommended next step

From the repository root with the existing development environment and fixtures:

```sh
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_conversation_context.py' -v
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

For a zero-API UI review, restart the local cached Streamlit process:

```sh
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Ask for Riyadh rental villas, then the price-ceiling follow-up. Verify counts,
filters, cards and historical notices. Use New chat, then an elliptical reference,
and confirm clarification instead of inheriting the previous search. Knowledge
queries with empty credentials cannot validate generated answer quality; use the
offline mocked tests to inspect scoped queries. Any live generation/embedding
review needs a separately authorized budget.

After explicit approval, review the five-file diff, stage those five files and
commit with a message such as `Preserve bounded conversational context and focus project answers`.
Rebuild/test the AMD64 image, then push only when redeployment is authorized:
`main` has automatic Render deployment enabled. Monitor deployment health at
`/_stcore/health`, native memory and mobile/desktop behavior, and use an approved
API budget for the named-development/overview follow-ups. No such publication,
rebuild or deployment was performed in this checkpoint.

Stopped after offline implementation and verification. Remaining limitations are
full-page scrolling, bounded language/reference support and unmeasured live
answer quality/runtime performance; no offline test blocker remains.
