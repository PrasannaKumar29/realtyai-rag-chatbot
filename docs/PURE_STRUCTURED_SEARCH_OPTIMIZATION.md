# Pure Wasalt structured-search optimization

Objective: return complete deterministic property results without unnecessary inference. Completed; no UI, retrieval configuration, model/fallback policy or deployment changes.

`Chatbot.answer` now returns immediately after JSONL filtering for pure `properties` requests. Both successful results and zero-match/unknown-attribute results bypass generation and semantic retrieval. Listing cards, counts, original URLs, Arabic summaries, historical disclaimers and missing-value classification are unchanged. `generation` remains null and `evidence_count` is zero, so the interface no longer reports a model-evidence subset for these requests.

Requests explicitly asking for explanation (English explain/why/compare/amenities/description and corresponding Arabic cues) retain the existing generation integration. Callers may also request it with `explain_properties=True`. Exact-search form filters remain deterministic unless a caller explicitly opts in. Missing IDs remain terminal even when explanation is requested. Factual, informational and mixed-source retrieval/generation paths remain. This optimization does not broaden or change the existing explanation content/presentation behavior.

Files modified:

- `app/chatbot.py`: deterministic early-return condition and optional explanation flag/cues.
- `tests/test_chatbot.py`, `tests/test_openrouter_diagnostics.py`, `tests/test_listing_id_routing.py`, `tests/test_property_presentation.py`: fixtures that specifically test generated evidence, history bounds, false counts or model failures now explicitly opt into explanations. Their safety/fallback assertions remain.
- `tests/test_chat_loading_and_misses.py`: pure-search expectations now require no generation stage/error; the model-error scenario explicitly requests an explanation. Pure example/form searches expect zero generation calls.

Created `tests/test_pure_structured_search.py`, this report, and `artifacts/structured_search_optimization/{tests.txt,integrity.json}`.

The new focused regressions guard HTTP transport, OpenRouter generation, query embeddings and retrieval construction. They exercise known/unknown IDs, eight Riyadh annual-rental villa matches, Arabic, unknown bathrooms, conflicting city filters and explicit price/area/bedroom filters. A separate test confirms that explanations and informational questions still invoke their existing mocked generation paths.

Final complete suite: **209 tests passed, zero failures or skips**, in 7.620 seconds. Initial verification exposed old assumptions that all nonempty property results generated an answer; explanation fixtures and pure-search expectations were adjusted to the newly authorized behavior, followed by the passing full run. No tests were removed.

Commands: `.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py'`, plus read-only source inspection, SHA-256/credential checks and immutable SQLite metadata inspection.

Integrity: **all 2,210 protected files unchanged**, including source datasets, chunks, production Chroma and prior checkpoint artifacts. Chroma retains **1,709 records**; unchanged binary hashes preserve its existing vectors. No credential values were found in changed code/tests. There were **zero live API calls**, no dependencies, Docker/deployment work or Git operations.

No offline blockers remain. Recommended next step: review the local pure structured-search behavior after restarting the cached Streamlit runtime. No further action or packaging was executed. Stopped after this optimization.
