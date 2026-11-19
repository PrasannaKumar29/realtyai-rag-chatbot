# AGENTS.md — Dataset Repository Maintenance

## Project scope

This project is part of the DarGlobal Senior AI Engineer technical assignment.

DarGlobal and Wasalt extraction are complete. Current scope: only the explicitly approved repository maintenance checkpoint. Authoritative corpora are `data/darglobal/` and `data/wasalt/`; processing modules live under `scripts/darglobal/` and `scripts/wasalt/`.

Do not work on RAG, embeddings, vector databases, chatbot development, frontend, or deployment.

## Execution rules

1. Work in small, clearly defined phases.
2. Execute ONLY the phase explicitly requested in the latest user message.
3. Never automatically proceed to the next phase.
4. Before editing files or executing commands, explain what you intend to do.
5. For potentially destructive operations, obtain explicit approval.
6. Never delete, rename, or overwrite existing project files without approval.
7. Do not install dependencies unless explicitly authorized.
8. Do not launch bulk scraping unless explicitly authorized.
9. Do not run more than the requested number of property-page tests.
10. Do not use stealth techniques, CAPTCHA solving, proxy rotation, or Cloudflare bypass methods.
11. Preserve original source data and extraction timestamps.
12. Keep Wasalt extraction independent of DarGlobal.

## Mandatory report after each phase

At the end of every phase, provide:

- Objective
- Actions performed
- Files created or modified
- Commands executed
- Actual results
- Errors or blockers
- Recommended next step

Do not execute the recommended next step.

## Stop condition

After completing the currently authorized phase, STOP.

Wait for my next instruction before making additional changes.

## Repository maintenance conventions

Use package entry points from the repository root, for example `.venv-extraction/bin/python -B -m scripts.wasalt.wasalt_finalize_dataset --check`. Use `scripts.wasalt.wasalt_paths` for repository/data/manual-export paths and historical path resolution. Preserve historical CSV/journal values; do not rewrite them to modernize paths. Original manual exports are retained under `archive/2026-11-18/manual-wasalt/`. `docs/WASALT_CONTEXT.md` is historical context. Application development requires a subsequent explicit checkpoint.
