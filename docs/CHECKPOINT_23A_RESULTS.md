# Checkpoint 23A — RealtyAI visual polish

Completed offline on 20 November 2026. **224 automated tests passed**, including
all 220 existing tests and four new UI regressions. No staging, commit, push,
Render action, dependency installation or live OpenAI/OpenRouter request occurred.

## Audit and scope

The accepted interface already had an inline welcome input, four starter prompts,
two-column suggestions, native role-specific chat messages, bottom-docked input
after the first turn, immediate user-message rendering, assistant status stages,
New chat in the main header, collapsed advanced filters and deterministic cards.
Sources were collapsed by default. Cards emphasized title and price equally.
The theme was charcoal/teal with mostly default borders and typography.

Those interaction paths remain. The rendering functions in `app/presentation.py`
were inspected and left unchanged. No routing, prompt, filtering, citations,
conversation context or backend code was modified. No auto-scroll fix attempted.

## Files changed

- `.streamlit/config.toml`: supported dark-theme palette, font/heading scale,
  borders, radii and sidebar surface settings. Telemetry remains disabled.
- `app/streamlit_app.py`: welcome/header styling and grouping, visible sources,
  property price/title hierarchy and quieter sidebar introduction.
- `tests/test_premium_ui.py`: four offline UI/accessibility regressions.
- `docs/CHECKPOINT_23A_RESULTS.md`: this report.

## Visual design

| Role | Value |
|---|---|
| Main background | Charcoal navy `#10171d` |
| Card/input surface | Slate `#19242b` |
| Primary accent | Muted sand `#cbb58b` |
| Main text | Warm white `#f1efe9` |
| Links | Pale teal `#b7d8d1`, underlined |
| Borders | Slate `#3d4d54` |
| Sidebar | `#131d24` with `#1c2931` controls |

The existing sans-serif system remains: no custom fonts, logos, photographs,
images or external downloads. Supported theme settings use a smaller heading
scale, soft 0.75rem base corners and 0.5rem button corners. RealtyAI remains the
wordmark, with the exact accepted subtitle. New chat remains adjacent to it.

The welcome input and four original questions now share one restrained framed
panel with a sand top rule, deliberate padding and a small exploration label.
The native two-column controls remain functional. A narrow-screen media rule
reduces panel padding and title size without fixed heights or minimum page widths.
A welcome-only supporting caption identifies the public-information grounding and
independent demonstration status; there is no official endorsement claim.

CSS is limited to documented application-owned `st.container(key=...)` classes
(`st-key-realty_header` and `st-key-realty_welcome`) and their descendants. It does
not select internal Streamlit DOM classes, intercept controls, modify developer
UI, run JavaScript or use an iframe. `st.html` receives a constant style string;
no response or source content is interpolated into HTML.

## Conversation, sources and cards

Native chat-message layout, user/assistant distinction, centered content width,
loading stages, answer text, history, callbacks, pending-request handling and
bottom-docked conversation input remain unchanged. Theme typography and borders
provide the common visual language without restructuring the conversation.

Cited-source controls now appear directly below the answer with a divider and
`Sources · Original public pages` caption. Full-width native links retain the
original source IDs, titles, URLs and order. They no longer require opening an
expander. Inline citations and their validation remain unchanged. Long titles
use native button layout; actual browser wrapping still needs visual review.

Property cards retain their native bordered container, verified listing ID/type,
location and attributes. When available, the existing original listing title is
shown as secondary metadata. Price has a distinct heading size and the original
Wasalt link uses the available card width. Capture dates, historical disclaimers,
unknown values, quality-warning counts and notes remain. Technical details stay
collapsed. No source field, verified count, card limit, URL or value is changed.

The sidebar retains its heading and snapshot notice, adds a short exact-filter
introduction and divider, and uses a subdued coordinated surface. Advanced search
remains collapsed; every filter, option, validation and submission behavior is
unchanged.

## Accessibility and validation

Native keyboard navigation, labels, focus behavior and browser text layout are
preserved. No fixed text heights or forced left-to-right direction were added.
Arabic titles and unknown attributes render through existing native components;
all original Arabic/source text remains available. Main foreground contrast is
at least 4.5:1 against both configured main and sidebar surfaces, verified by the
standard relative-luminance calculation. This is not a complete accessibility
audit: browser zoom, captions, all interactive states, RTL geometry and narrow
viewport appearance require manual review.

The full existing suite plus new tests passed:

```text
Ran 224 tests in 8.527s
OK
```

New tests exercise each of the four original starter buttons through submission
and New chat; directly visible source links with original ordering/labels/URLs;
Arabic cards with unknown price/attributes, source warnings, historical notice,
original URL and collapsed technical/advanced panels; and theme text contrast.
Existing tests retain coverage for loading order/status, form filters, verified
counts/cards, citations, errors, conversational follow-ups and zero-API searches.
Mocks, socket guards and empty process keys keep verification offline.

All four new tests also passed inside the existing Linux AMD64 `realtyai:21a`
image in **0.949 seconds**, using read-only mounts of the changed UI/theme and
new test file, `--network none` and empty API keys. No image rebuild or deployment
was performed. Bare-mode Streamlit test-context warnings were non-fatal.
`git diff --check` passed. No actual credential values were found in changed code.

## Integrity and deployment compatibility

SHA-256 comparison verified **2,120 protected files unchanged**: original source
datasets, chunks, original Chroma, the runtime bundle, backend/presentation modules
and packaging files included in the checkpoint snapshot. All runtime manifest
checksums match. Immutable SQLite verification confirms **1,709 embeddings**;
packaged Wasalt JSONL still contains **261 records**. The 19-project inventory,
models, fallback policy, dependencies, environment variables, Dockerfile, startup
command and health check at `/_stcore/health` remain unchanged.

Both changed runtime files already appear in the Docker allowlist and existing
COPY instructions. There are no new runtime files/assets or dependencies to
package. The native theme and small static CSS introduce no heavy memory resource;
production memory was not remeasured. No Render configuration or paid-plan change.

## Visual review limitations and exact restart

Browser discovery found **no connected browser**. No screenshots were captured or
reviewed. AppTest establishes component/interaction behavior, not rendered visual
quality. Welcome, populated DarGlobal conversation, Wasalt cards, expanded sidebar,
mobile/narrow layout, RTL and long source labels still need your local visual
review. The known full-page scroll-position limitation is unchanged. This design
is intended for the configured dark theme; user-selected theme overrides were not
visually assessed.

Stop the prior local Streamlit process with Ctrl-C, then run from the repository
root. Empty keys deliberately disable generation/embedding; do not remove these
overrides during a zero-API review:

```sh
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Open `http://127.0.0.1:8501`. Review the welcome panel and four starter controls.
Submit `Show listing 5891036`, then `Villas for rent in Riyadh under SAR 100000/year`
and the Arabic ID query `أخبرني عن عقار رقم 5891036`. Check original links, cards,
prices, unknowns, dates, warnings and historical notices. Expand Advanced property
search and test the unchanged controls. Select New chat to return to welcome.
Check both desktop and a narrow mobile viewport. An empty-key knowledge query
will show safe service errors; use the offline source fixture test to validate
source presentation without a live generation call.

Repeat automated validation with:

```sh
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_premium_ui.py' -v
OPENAI_API_KEY='' OPENROUTER_API_KEY='' .venv-extraction/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

Recommended next step: local desktop/mobile visual review before approving a
separate publication checkpoint. No offline test blocker remains. **Stopped;
no commit, push or redeployment follows automatically.**
