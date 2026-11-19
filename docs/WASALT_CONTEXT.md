# Wasalt Property Data Extraction — Codex Handoff

## 1. Project Background

I am completing a technical assignment for the **Senior AI Engineer – Agentic Systems** position at DarGlobal.

The assignment requires extracting publicly available information from:

- DarGlobal: https://darglobal.co.uk/
- Wasalt: https://wasalt.sa/en

The collected information will eventually support an AI chatbot, but **this task is exclusively about Wasalt data acquisition, validation, cleaning, and export.**

Do not develop any RAG pipeline, embeddings, vector database, chatbot, frontend, or deployment infrastructure.

The DarGlobal extraction has already been completed separately. Do not work on DarGlobal.

I have approximately one day to complete the assignment, so prioritize a practical, dependable solution over elaborate infrastructure.

**Authorization:** DarGlobal HR has verbally confirmed that a one-time extraction for this technical assignment is acceptable. Keep all automated collection within that scope. Do not attempt CAPTCHA solving, Cloudflare evasion, stealth plugins, fingerprint manipulation, proxy rotation, or unauthorized API access. If access is blocked, stop and document it.

## 2. Discovery Work Already Completed

We inspected Wasalt's robots.txt and XML sitemaps.

The primary property sitemaps are:

```text
https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz

https://cdn.wasalt.sa/sitemap/rental_pdp_sitemap_en_sa.xml.gz
```

Both are gzip-compressed XML files and were successfully downloaded through Google Colab using Python `requests`.

### Verified sitemap counts

| Category | Unique URLs |
|---|---:|
| Properties for sale | 45,898 |
| Long-term rental properties | 14,102 |
| Daily/short-term rental properties | 2,666 |
| **Total unique URLs** | **62,666** |

The primary product sitemap contained 60,000 URLs, with 60,000 distinct numeric IDs.

The daily-rental sitemap contained 2,676 URL entries, of which 2,666 were unique. One unique daily-rental URL did not match the numeric-ID extraction pattern.

These are discovery counts, not verified active-listing counts.

### Important finding

We do not need to simulate every combination of location, property type, price, bedrooms, or other search filters.

The primary sitemap already provides direct individual listing URLs.

Examples:

**Sale:**
```text
https://wasalt.sa/en/property/sale/apartment-12258-sqm-with-4-bedrooms-5891090
```

**Long-term rent:**
```text
https://wasalt.sa/en/property/rent/villa-250-sqm-facing-south-with-9-bedrooms-5891036
```

**Daily rental:**
```text
https://wasalt.sa/en/dailyrental/apartment-for-booking-5577
```

URL patterns:

- `/property/sale/` → sale
- `/property/rent/` → long-term rental
- `/dailyrental/` → daily/short-term rental

The trailing number is a candidate listing ID for the tested property URLs.

### Other discovered sitemaps

```text
category_sitemap_en_sa.xml.gz
rental_srp_sitemap_en_sa.xml.gz
static_sitemap_en_sa.xml.gz
```

Category and search-result sitemaps are not required for the initial property discovery.

Static pages may be extracted later if time permits.

## 3. Extraction Methods Already Tested

### Method A — Python requests in Google Colab

Tested directly requesting both a sale and a rental listing.

Both returned:

```text
HTTP 403
Title: Just a moment...
Cloudflare security verification
```

Conclusion: direct HTTP access from Colab is blocked.

### Method B — Jina AI Reader

Tested:

```text
https://r.jina.ai/https://wasalt.sa/en/property/sale/...
```

Jina returned HTTP 200 but the body contained a Cloudflare challenge rather than property information.

Conclusion: Jina Reader is not a working extraction method for these pages.

### Method C — Playwright in Google Colab

Installed Playwright and Chromium.

Initially Chromium could not launch because required Linux system libraries were missing:

```text
libatk-1.0.so.0: cannot open shared object file
```

Resolved the browser dependency issue using:

```bash
playwright install-deps chromium
```

Afterward, Chromium launched successfully.

However, when navigating to Wasalt, the result was:

```text
HTTP status: 403
Page title: Just a moment...
JSON-LD scripts: 0
```

Conclusion: Playwright itself works in Colab, but Wasalt blocks automated access from that environment.

### Method D — Regular Chrome browser

**Successful.**

The website loads normally in my desktop Chrome browser.

Using Chrome Developer Tools, we confirmed that individual Wasalt property pages contain structured property information embedded in:

```html
<script type="application/ld+json">
```

These records use Schema.org JSON-LD.

On the test sale listing, Chrome returned 19 JSON-LD records, including a property record and several `Offer` records.

On the test rental listing, Chrome returned 2 JSON-LD records, including one property record.

We successfully exported one sale and one rental JSON file directly from Chrome using a JavaScript console script.

This confirms that structured extraction is feasible once the page is accessible.

## 4. Actual Extracted Data — Confirmed Schema

### Example A — Sale listing

Listing ID: `5891090`

Source URL:

```text
https://wasalt.sa/en/property/sale/apartment-12258-sqm-with-4-bedrooms-5891090
```

Observed property information:

```json
{
  "@context": "https://schema.org",
  "@type": "SingleFamilyResidence",
  "name": "Apartment 122.58 SQM with 4 Bedrooms",
  "numberOfRooms": "4",
  "numberOfBedrooms": "4",
  "address": {
    "@type": "PostalAddress",
    "addressCountry": "Saudi Arabia",
    "addressLocality": "Makkah Al Mukarramah",
    "streetAddress": "Almouhamdeah"
  },
  "offers": [
    {
      "@type": "Offer",
      "price": 435000,
      "priceCurrency": "SAR"
    }
  ]
}
```

Additional fields in the original JSON-LD:

- `image`
- `description` containing Arabic HTML
- `leaseLength`

Important data-quality observations:

1. `@type` is `SingleFamilyResidence`, despite the listing being an apartment.
2. Area `122.58 sqm` is present in the title but not in a dedicated area field in this JSON-LD.
3. The structured data says four bedrooms, but the Arabic description mentions three rooms.
4. The description mentions three bathrooms, but the main JSON-LD record has no dedicated bathroom field.
5. The description includes seller telephone information.

Preserve the original values and flag inconsistencies. Do not invent missing fields.

### Example B — Rental listing

Listing ID: `5891036`

Source URL:

```text
https://wasalt.sa/en/property/rent/villa-250-sqm-facing-south-with-9-bedrooms-5891036
```

Observed JSON-LD:

```json
{
  "@context": "https://schema.org",
  "@type": "SingleFamilyResidence",
  "name": "Villa 250 SQM Facing South with 9 Bedrooms",
  "numberOfRooms": "9",
  "numberOfBedrooms": "9",
  "numberOfBathroomsTotal": "6",
  "address": {
    "@type": "PostalAddress",
    "addressCountry": "Saudi Arabia",
    "addressLocality": "Riyadh",
    "addressRegion": "North Riyadh",
    "streetAddress": "An-Narjis"
  },
  "offers": [
    {
      "@type": "Offer",
      "price": 120000,
      "priceCurrency": "SAR /Year"
    }
  ]
}
```

Additional fields include:

- Image URL
- Arabic HTML description
- Property orientation
- Approximate property age
- Room and floor descriptions
- Amenities such as air conditioning, kitchens, rooftop and courtyard

The original Arabic description specifies two rental payment arrangements:

- SAR 120,000 in one payment
- SAR 125,000 in two payments

The main structured offer lists SAR 120,000/year.

Preserve the official structured offer and the alternative payment details separately. Do not treat them as contradictory prices without considering payment arrangements.

## 5. Existing Local Files

I have manually downloaded these two files from Chrome:

```text
wasalt_5891090.json
wasalt_5891036.json
```

They should be available in my local Downloads folder unless I have moved them.

Each file follows this wrapper structure:

```json
{
  "source": "wasalt",
  "source_url": "...",
  "listing_id": "...",
  "purpose": "sale",
  "extracted_at": "...",
  "json_ld": {}
}
```

The `json_ld` field contains the original property record.

**Codex must first inspect the workspace and locate or ask me to provide these files if they are not available. Do not assume they are already inside the project directory.**

I also ran Python code in Colab that produced a dictionary named `all_property_urls`, containing the discovered listing URLs.

A `discovered_urls.csv` export was proposed, but its successful creation or transfer to my local machine has not been confirmed. Check whether this CSV already exists locally. Otherwise, reconstruct the discovery inventory directly from the two sitemap files.

Do not fabricate missing input files.

## 6. Immediate Objective — Test Local Playwright

We have not yet tested Playwright running locally on my Mac.

This is the first task to execute.

### Setup

Create a lightweight Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install playwright beautifulsoup4 pandas lxml
python -m playwright install chromium
```

Do not introduce Selenium, Scrapy, databases, Docker, or cloud infrastructure unless genuinely necessary.

### Test

Use Playwright to launch visible Chromium:

```python
browser = await p.chromium.launch(headless=False)
```

Navigate to one known sale listing.

Capture:

- HTTP response status
- Final URL
- Page title
- Number of JSON-LD script elements
- Whether a valid main property record exists
- Main property name, price, and address

Avoid saving or logging personal contact information.

Run only this one-page feasibility test initially.

### Decision logic

**If local Playwright succeeds:**

Proceed to a small extraction test of approximately 5 sale and 5 rental properties.

**If local Playwright returns a Cloudflare challenge:**

Do not try stealth browser libraries, CAPTCHA solving, browser fingerprint manipulation, proxy rotation, session-token copying, or similar evasion.

Stop automation and report the result.

An authorized export or explicitly permitted access method will then be necessary for large-scale collection.

Do not build a bulk crawler before resolving this access requirement.

## 7. Extraction Architecture — If Access Succeeds

Implement a straightforward modular Python pipeline.

### Phase A — URL discovery

Download and parse the English property sitemaps.

Produce a deduplicated inventory containing:

```json
{
  "source": "wasalt",
  "listing_id": "5891090",
  "source_url": "...",
  "purpose": "sale",
  "sitemap_source": "...",
  "discovered_at": "..."
}
```

Store listing IDs as strings.

Separate sale, long-term rent, and daily rentals.

Avoid extracting thousands of category/search landing pages.

### Phase B — Property acquisition

For each selected listing:

1. Visit the property URL using the approved extraction method.
2. Check the response and page title.
3. Detect Cloudflare challenges and incomplete pages.
4. Retrieve the HTML.
5. Save the raw HTML or original JSON-LD.
6. Parse all JSON-LD records.
7. Identify the record corresponding to the requested listing.
8. Preserve the original source URL and collection timestamp.

Do not assume the first JSON-LD record is the property. Some pages contain breadcrumbs, offers, and related listing data.

Prefer matching against the requested listing ID, URL, or relevant property identity.

Keep raw acquisition separate from cleaning.

### Phase C — Structured normalization

The target schema should include:

```json
{
  "source": "wasalt",
  "listing_id": null,
  "source_url": null,
  "purpose": null,
  "property_type": null,
  "schema_org_type": null,
  "title": null,
  "city": null,
  "region": null,
  "district": null,
  "price_sar": null,
  "price_period": null,
  "alternative_prices": [],
  "area_sqm": null,
  "area_source": null,
  "bedrooms": null,
  "bathrooms": null,
  "rooms": null,
  "amenities": [],
  "description_original": null,
  "description_clean": null,
  "image_url": null,
  "listing_status": null,
  "scraped_at": null,
  "quality_flags": []
}
```

Populate fields only when supported by source evidence.

Specific normalization rules:

- Extract purpose from the verified URL structure.
- Prefer an explicit property-type field when available.
- Otherwise infer property type from the title, but retain the source schema type.
- Convert valid numeric prices to numbers.
- Preserve rental payment frequency separately.
- Do not assume a rental price is monthly or yearly unless supported.
- Use a dedicated area field when available.
- If area comes from the title, record `area_source = "title"`.
- Do not infer area from the URL slug alone.
- Normalize bedroom/bathroom counts only when explicit.
- Preserve meaningful Arabic descriptions.
- Convert description HTML to readable text.
- Remove seller phone numbers and personal contact information from cleaned output.
- Preserve original raw source data separately with appropriate access controls.
- Record contradictions between structured values and descriptions.

Do not blindly treat `SingleFamilyResidence` as the actual property type.

### Phase D — Markdown generation

Generate one Markdown file per verified property.

Example:

```markdown
---
source: wasalt
listing_id: "5891036"
source_url: "https://wasalt.sa/en/property/rent/..."
purpose: rent
property_type: villa
city: Riyadh
district: An-Narjis
price_sar: 120000
price_period: year
area_sqm: 250
bedrooms: 9
bathrooms: 6
scraped_at: "..."
---

# Villa 250 SQM Facing South with 9 Bedrooms

## Property Overview

- Purpose: Long-term rent
- Location: An-Narjis, Riyadh
- Price: SAR 120,000/year
- Area: 250 sqm
- Bedrooms: 9
- Bathrooms: 6

## Description

[Cleaned original description, preserving Arabic text]

## Additional Details

[Only attributes supported by the source]

## Source

[Original property URL]
```

This is an illustrative output format. Do not hardcode sample information into other records.

### Phase E — Quality validation

Validate each property before accepting it.

Minimum checks:

- Valid source URL
- Listing ID detected
- Main property record found
- Nonempty property title
- At least some substantive listing information
- No Cloudflare challenge text
- No HTML error page
- Successful JSON parsing
- Duplicate detection

Quality warnings:

- Missing price
- Missing city
- Missing area
- Ambiguous property type
- Mismatch between description and structured attributes
- Unclear price frequency
- Unavailable or stale listing

Missing optional fields should not automatically invalidate otherwise useful records.

Track accepted, flagged, failed, and skipped records separately.

### Phase F — Small-batch test

Before scaling:

- Select 5 sale listings.
- Select 5 long-term rental listings.
- Include varied property types when possible.
- Validate the raw JSON, normalized JSON, and Markdown.
- Inspect the resulting records for missing and misleading fields.

Only scale after confirming quality.

### Phase G — Controlled extraction

If the small test works and the authorized access method supports collection, target:

- Minimum: 100–200 verified listings
- Preferred: 300–500 verified listings

Prioritize:

- Riyadh sale
- Riyadh rent
- Jeddah sale
- Jeddah rent

Include apartments, villas, land, and other supported types.

The sitemap does not provide reliable city classifications, so do not pretend URLs are already categorized by city. Determine location from extracted property details.

Use a reasonable request rate, low concurrency, resumable progress tracking, and bounded retries for transient network errors.

Stop if Cloudflare blocks automated access. Do not repeatedly retry challenges.

Do not scrape all 62,666 URLs.

## 8. Target Directory Structure

Create a clean standalone Wasalt extraction directory:

```text
wasalt_scraper/
├── README.md
├── requirements.txt
├── .gitignore
├── config.py
├── scripts/
│   ├── discover_urls.py
│   ├── test_browser.py
│   ├── extract_properties.py
│   ├── normalize_properties.py
│   ├── validate_properties.py
│   └── export_corpus.py
├── wasalt_data/
│   ├── discovered_urls.csv
│   ├── raw/
│   │   ├── sale/
│   │   └── rent/
│   ├── properties/
│   │   ├── sale/
│   │   └── rent/
│   ├── listings.jsonl
│   ├── manifest.csv
│   └── quality_report.csv
└── tests/
    └── test_normalization.py
```

The exact module structure may be simplified if appropriate. Prioritize readable code and reproducibility.

`manifest.csv` should record each attempted extraction:

- Listing ID
- Source URL
- Purpose
- Status
- Attempt timestamp
- Extraction method
- Error reason, if any
- Output file location

Suggested statuses:

- `success`
- `failed`
- `blocked`
- `invalid`
- `skipped`
- `needs_review`

## 9. Existing Code and Workspace Hygiene

Before writing new code:

1. Inspect the current VS Code workspace.
2. Identify existing relevant scripts and datasets.
3. Do not delete unrelated project files.
4. Do not overwrite the DarGlobal dataset.
5. Check whether the two manual Wasalt JSON exports are accessible.
6. If the existing project already has a suitable structure, integrate the Wasalt extractor without unnecessary restructuring.

Keep data acquisition independently reproducible.

Preserve source traceability.

Avoid committing large raw datasets or sensitive contact information to a public repository.

## 10. Execution Instructions for Codex

**Work incrementally, but execute the code rather than only proposing an architecture.**

### First milestone

Immediately:

1. Inspect my local environment and workspace.
2. Set up Playwright if necessary.
3. Create the minimal one-page extraction test.
4. Run it locally on listing `5891090`.
5. Print the HTTP status, title, JSON-LD count, and whether the main property record was found.

If successful, test listing `5891036`.

Then proceed to small-batch extraction and normalization.

If blocked, do not attempt anti-bot evasion. Instead, create the normalization and export pipeline using the two manually collected sample files, and report precisely what additional authorized access is required.

### Second milestone

Produce a functioning pipeline that can:

- Read discovered property URLs.
- Acquire source data through a permitted method.
- Parse JSON-LD.
- Normalize structured fields.
- Clean Arabic descriptions.
- Remove contact information from prepared outputs.
- Write per-listing Markdown.
- Produce `listings.jsonl`.
- Generate a manifest and quality report.

### Final milestone

Produce an exportable dataset folder that can be copied into my main technical assignment project.

The output must include:

- Actual extracted source data
- Clean structured property records
- Markdown documents
- Extraction manifest
- Quality report
- Reproducible extraction code
- Clear README instructions

## 11. Critical Reminders

- Do not work on DarGlobal.
- Do not develop RAG or chatbot components.
- Do not introduce embeddings or vector databases.
- Do not invent property attributes.
- Do not discard Arabic descriptions.
- Do not treat sitemap entries as verified active properties.
- Do not confuse daily rentals with long-term rentals.
- Do not blindly trust the Schema.org `@type`.
- Do not scrape search pages unnecessarily.
- Do not attempt to bypass Cloudflare or CAPTCHA.
- Preserve original URLs and timestamps.
- Separate acquisition, normalization, validation, and export.
- Prefer working code and verified data over elaborate design.

**Start now with the local Playwright feasibility test. If it succeeds, continue toward a validated 300–500-property dataset. If it fails, complete the normalization/export implementation using existing samples and document the access limitation.**
