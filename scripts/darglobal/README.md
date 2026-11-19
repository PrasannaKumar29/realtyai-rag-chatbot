# Extraction source of truth

**`darglobal_extraction_reference.py` is the source of truth for the extraction methodology.**
It is your supplied file, preserved unchanged. Future documentation and refactoring should
follow this file rather than the earlier assistant reconstruction, which is now archived.
Its original SHA-256 is recorded in `../../docs/reference-provenance.json`.

The completed dataset remains `../../data/darglobal/final/markdown/`: **419 documents, unchanged**.
No scraping, cleaning, imports of the reference module or execution of its functions was performed.

## Behavior documented by the source

- Discover URLs from `sitemap.xml`; filter them using `robots.txt`, site/path rules and query checks.
- Categorize them into blogs, press, insights, partners, project listings, communities, corporate
  and developments. The reference excludes the homepage during URL selection.
- Fetch Markdown through Jina Reader and retain image alt text when removing inline images.
- Validate error/access markers, 404 headings and an 800-character minimum.
- Use stable path-based filenames with an eight-character URL hash.
- Save YAML title, source URL, source type and scraping timestamp, plus the Markdown body.
- Append CSV attempt records; skip already saved files. Use a two-second batch delay and stop
  after three consecutive failures or detected access/rate restrictions.
- Apply conservative cleaning and detect exact duplicates from normalized document-body hashes.

These descriptions follow the supplied implementation. Its cleaner is explicitly illustrative,
not a byte-for-byte recreation of the final Colab cleaner. TF-IDF near-duplicate analysis and
the full recovery/quarantine workflow are described in the supplied dataset reports, but are
not implemented as complete stages in this reference. Do not invent those implementations or
substitute the archived assistant defaults when explaining this file.

## Dependencies and preservation

`requirements.txt` lists the reference's direct dependencies, including the `lxml` XML parser
backend required by `BeautifulSoup(..., "xml")`. No dependencies were installed or resolved.
The file's CLI exposes local inspection only; it was not invoked. Only static syntax checks
were performed. Do not run extraction or cleaning against the completed dataset.

The previous assistant source and its README, dependency list and environment template are
preserved in `../../archive/2026-11-18/assistant-reconstruction/`. They are historical material,
not another active source of truth.

## Current entry point

From the repository root, local inspection is `.venv-extraction/bin/python -B scripts/darglobal/darglobal_extraction_reference.py --inspect --root data/darglobal/final/markdown`. The source itself is preserved byte-for-byte; the legacy default `darglobal_data` remains in the reference and must be overridden explicitly. No acquisition or cleaning is authorized by an inspection command.
