# Checkpoint 20B — Property counts and Streamlit presentation

Objective: fix the mismatch between eight exact matches and five model-evidence records, replace default JSON cards, improve citation readability, and show natural-language form queries. Completed locally using mocked/offline validation only.

## Exact changes

| File | Change |
|---|---|
| `app/chatbot.py` | Attaches the property-evidence subset count, supplies separate total/display/evidence/unknown counts to the model, and makes displayed structured-property summaries deterministic regardless of generation outcome. Adjacent trusted citations now have readable labels and separators. |
| `app/streamlit_app.py` | Renders compact labelled cards, keeps JSON inside collapsed technical expanders, preserves source links and warnings, displays natural-language form queries, and recomputes authoritative summaries when rendering older conversation entries. |
| `app/presentation.py` | New pure formatting helpers for verified totals, cards, prices, missing values and natural-language filter descriptions. |
| `tests/test_property_presentation.py` | New 11-test offline regression suite using the actual JSONL and Streamlit AppTest. |
| `docs/CHECKPOINT_20B_RESULTS.md` | This report. |

Created `artifacts/checkpoint_20b/offline-tests.txt`, `presentation-example.json` and `integrity.json`. All existing checkpoint artifacts were preserved. No existing tests were removed or changed.

## Authoritative counts

The deterministic JSONL result remains the source of truth. Exact filtering, unknown-versus-mismatch classification, numeric boundaries, sorting and the ten-card display limit are unchanged.

Structured-property answers now use a code-generated summary instead of free-form model prose. This avoids relying on regexes or prompt instructions to catch every possible numeric or spelled-out false count. Generated text is still validated through the existing citation/grounding checks, and generation errors/diagnostics are retained, but it cannot replace the structured-property summary. The conversation stores the deterministic answer, preventing a wrong generated count from entering subsequent history. Responses without structured-property results retain their validated generated narrative.

Each structured result distinguishes:

- `total_matches`: every verified match in the JSONL search.
- `len(matches)`: the number of displayed cards, capped at ten.
- `evidence_count`: the number of property records prepared for model context, capped at five.
- `unknown_count`: records with an unknown required attribute and no confirmed mismatch, excluded from verified matches.

The model prompt also receives these separate counts and explicitly identifies the evidence as a subset. The UI recomputes its summary from structured values, including for older session entries containing a wrong narrative. Property source links come from the deterministic cards; a discarded generated paragraph cannot cause unrelated sources to appear in the source list.

The requested exact search was reproduced offline with rent, Riyadh, villa, inclusive maximum SAR 100,000 and period year. The mocked model deliberately claimed “Only five listings match.” Actual displayed output was:

> Verified historical matches: **8**. Displaying **8** listing cards. Model evidence covers **5 of 8** verified matches.

The same verified total survives generation failure and invalid citations. A broader rent-only regression distinguishes 130 total matches, ten displayed cards and five evidence records. Zero-match and unknown-attribute cases remain distinct. English and Arabic deterministic summaries are covered.

## Compact cards, citations and form questions

A representative card now displays:

```text
Listing 5872251 · Villa for rent
Ohod · Riyadh
SAR 39,000 / year
Area: 240 sqm · Bedrooms: 4 · Bathrooms: Unknown
```

Cards retain capture timestamps, the original clickable Wasalt URL, a visible source-warning count and readable quality notes. Missing values display `Unknown`; missing rental periods are labelled unknown rather than invented. Numeric zero remains a recorded zero. Raw record JSON is available only inside a collapsed `Technical details` expander. The existing collapsed applied-filter details remain available.

Trusted adjacent markers such as `[S1][S2]` now become separate clickable `Source S1 · Source S2` links. Existing rejection of invented IDs/URLs, unsupported availability claims and HTML remains intact. Only cited sources appear for generated factual answers; card URLs continue to come directly from the verified records.

The exact-search form now displays and stores:

> Find Wasalt villas for rent in Riyadh, up to SAR 100,000/year.

The original machine-readable filter dictionary is passed through unchanged as `explicit_filters`. Display formatting preserves the difference between inclusive “up to” and exclusive “under,” along with rental period, location and minimum/exact attribute constraints. No JSON query instruction appears in the new user message.

## Validation and integrity

**155 tests passed, zero failures or skips**, in 6.127 seconds: all prior 144 tests plus 11 new regressions.

The new tests verify eight matches versus five evidence records, counts on successful/failed/rejected generations, total versus display caps, unknown attributes, Arabic summaries, compact field rendering, original URLs and quality warnings, collapsed raw JSON, old-session count correction, separated validated citations and natural-language form submission with unchanged structured filters. Streamlit interactions used AppTest and mocked services; no browser screenshot inspection or live generation was performed.

After the full suite, SHA-256 comparison confirmed **all 2,164 protected files unchanged**, covering datasets, chunks, production Chroma and the protected earlier checkpoint artifacts. Read-only immutable SQLite inspection confirmed **1,709 indexed records**, 1,536 dimensions, completed index status and the original chunk checksum matching the manifest. The credential-value scan found no leaks in changed code/tests or new artifacts.

No scraping, source changes, rechunking, embedding calls, Chroma changes, dependency installation, Git staging/commits, Docker or Render work occurred. ERNIE selection and the Checkpoint 20A fallback policy are unchanged. There were **zero live OpenRouter requests**; prior validation counters were not touched.

Commands executed included read-only `cat`, `rg` and `sed` inspection; Python SHA-256 and credential checks; immutable SQLite metadata reads; an offline mocked presentation-example script; and:

```bash
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_property_presentation.py' -v
.venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Errors or blockers: none remain in offline validation. An initial UI assertion used an unavailable AppTest `expanded` convenience attribute; the assertion was corrected to inspect its expander proto, and the focused and complete suites then passed.

Recommended next step: repeat the local manual review of card layout and citation readability. The count/card UI can be reviewed from retained conversation results without a new model request; a fresh form submission still uses the configured generation pipeline and therefore needs a separately authorized live budget if performed by the agent. No live request or subsequent checkpoint was executed. Stopped after Checkpoint 20B.
