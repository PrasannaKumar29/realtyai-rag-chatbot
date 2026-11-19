# Project organization — November 18, 2026

The finalized dataset is authoritative. Its complete directory was renamed into place after
the older `data/darglobal/` pilot was archived. Every supplied file's path relative to the dataset,
size and SHA-256 hash was compared before and after the move: **857 of 857 match**.
The file-level inventory is `dataset-integrity.json`; the move log is `organization-log.json`.
No important files or temporary files were deleted.

## Retained as current handover material

| Location | Purpose |
|---|---|
| `data/darglobal/final/markdown/` | Finalized 419 Markdown documents, unchanged |
| `data/darglobal/raw/` | Original supplied raw files and manifest, unchanged |
| `data/darglobal/quarantine/` | Original supplied invalid/duplicate captures, unchanged |
| Other files inside `data/darglobal/` | Original supplied quality/recovery/duplicate reports, unchanged |
| `scripts/darglobal/` | Supplied methodology reference; only local inspection executed in Checkpoint 17B |
| `data/wasalt/` | Complete 261-property and five-informational-document corpus |
| `scripts/wasalt/` | Packaged Wasalt preparation and audit tools |
| `README.md`, `docs/` | Current handover documentation and integrity/move evidence |
| `.git/` | Repository state, untouched |

The DarGlobal methodology source of truth is `scripts/darglobal/darglobal_extraction_reference.py`,
copied unchanged from the user's supplied Downloads file. Its SHA-256 and provenance are
in `reference-provenance.json`. The earlier assistant reconstruction and its supporting files
have been moved to `archive/2026-11-18/assistant-reconstruction/` as superseded history.
Neither reference was executed during the original handover. Checkpoint 17B ran only the primary reference's local `--inspect` command; no acquisition or cleaning was executed.

The dataset's supplied CSV files refer to historical Colab paths such as `darglobal_data/`
and `darglobal_final/markdown/`. Those records were preserved rather than rewritten. Resolve
the finalized documents against `data/darglobal/final/markdown/` and their category/filename.

## Archived without deleting

| Previous location | Archive location | Reason |
|---|---|---|
| `data/darglobal/` | `archive/2026-11-18/data/darglobal/` | Earlier ten-document pipeline/export |
| `data/darglobal_data_collab/` | `archive/2026-11-18/data/darglobal_data_collab/` | Original small Colab sample |
| `data/darglobal_reader_pilot/` | `archive/2026-11-18/data/darglobal_reader_pilot/` | Single-page Reader experiment |
| `data/darglobal_html_pilot/` | `archive/2026-11-18/data/darglobal_html_pilot/` | Blocked direct-HTML experiment |
| `data/corpus/`, `data/synthetic-index/` | Corresponding directories in `archive/2026-11-18/data/` | Earlier collection attempt and synthetic index |
| `01_darglobal_scraping.ipynb` | `archive/2026-11-18/prototype/01_darglobal_scraping.ipynb` | Original experiment retained as evidence |
| `DARGLOBAL_EXTRACTION_HANDOFF.md` | Same filename in `archive/2026-11-18/prototype/` | Earlier handoff superseded by the finalized dataset |
| `src/`, `scripts/`, `tests/`, `config/` | Corresponding directories in `archive/2026-11-18/prototype/` | Useful earlier code retained as reference |
| `app.py`, `Dockerfile` | Same filenames in `archive/2026-11-18/prototype/` | Synthetic app and packaging prototype |
| `pyproject.toml`, `uv.lock`, old requirements locks | Same filenames in `archive/2026-11-18/prototype/` | Earlier dependency/build setup retained |
| Previous README, `.env.example`, `.dockerignore`, `docs/` | Same locations under `archive/2026-11-18/prototype/` | Historical instructions and findings |
| `reports/` | `archive/2026-11-18/prototype/reports/` | Earlier resource and access reports |

Archived extraction entry points include `scripts/collect_website.py`, `audit_sources.py`,
`discover_urls.py`, `extract_pages.py`, `clean_markdown.py` and `audit_corpus.py`. They describe
earlier experiments; do not run them against the finalized dataset. Their old default paths
and cross-file references have not been rewritten. To reuse the old package later, inspect
the archived `src/darglobal_rag/` code and dependency files first.

All moves are reversible. Restoring the old `data/darglobal/` path would require first moving
the completed dataset to another protected location; never merge the two datasets.

## Optional removal candidates — retained pending approval

These paths were identified during inspection but have not been removed:

| Path | Approximate size | Consideration |
|---|---:|---|
| `.uv-cache/` | 486 MB | Re-downloadable dependency cache |
| `.cache/` | 64 MB | Earlier model download cache |
| `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `.DS_Store` files outside the dataset | Small | Tool/OS-generated files |
| `.venv/` | 486 MB | Earlier development environment; archived editable source paths may need rebuilding |
| `.venv-extraction/` | 6.5 MB | Existing lightweight environment retained |
| `models/` | 64 MB | Downloaded model may be useful for later work |
| `.python/` | 77 MB | Project-local Python; virtual environments depend on it |

The environments, interpreter and models are not treated as disposable without approval.
The `.DS_Store` inside the approved dataset is included in the integrity inventory and was
also preserved. Archived data/reports and local caches remain excluded from Git.

## Checkpoint 17B — current layout

The approved move ledger is `migration-17b-ledger.json`. Wasalt data now resides at `data/wasalt/`; its scripts are the `scripts.wasalt` package. The DarGlobal reference is at `scripts/darglobal/darglobal_extraction_reference.py` with identical source bytes. Manual Wasalt exports are preserved in `archive/2026-11-18/manual-wasalt/`. The historical handoff moved unchanged to `docs/WASALT_CONTEXT.md`. Earlier move tables above remain historical records. No original corpus content, acquisition evidence, model, environment or Git history was deleted.
