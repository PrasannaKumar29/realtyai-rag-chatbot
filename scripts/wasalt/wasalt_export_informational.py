"""Prepare five informational documents offline from the approved captures."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import csv
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup
import yaml

from .wasalt_export_markdown import contains_contact
from .wasalt_normalize import clean_description


ROOT = REPO_ROOT
OUT = DATA_ROOT / "informational"


def load_sources():
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in (OUT / "source_data").glob("*.json")}


def paragraphs(article):
    soup = BeautifulSoup(article["parents"][0]["html"], "html.parser")
    result = []
    for node in soup.find_all(["p", "li"]):
        if node.find_parent("li"):
            continue
        value = clean_description(str(node))
        if value and value not in result:
            result.append(value)
    return result


def build_documents(sources):
    docs = []

    def add(path, title, category, source_keys, blocks, notes=None, attributes=None):
        docs.append({"path": path, "title": title, "category": category, "source_keys": source_keys,
                     "blocks": blocks, "notes": notes or [], "attributes": attributes or {}})

    faq_pages = sources["homepage"]["faq_records"]
    faqs = [q for page in faq_pages for q in page["mainEntity"]]
    if len(faqs) != 6:
        raise ValueError("Expected all six homepage FAQs")
    faq_blocks = []
    for item in faqs:
        question = item["name"].strip()
        answer = item["acceptedAnswer"]["text"].strip()
        if not answer or clean_description(answer) != answer:
            raise ValueError("FAQ wording needs manual review; refusing to alter it")
        faq_blocks.append((question, answer))
    add("faq.md", "Wasalt — Frequently Asked Questions", "faq", ["homepage"], faq_blocks)

    corporate = sources["corporate"]["sections"]
    overview = next(s["text"] for s in corporate if "heroBannerContainer" in s["selector"])
    platform = next(s["text"] for s in corporate if "searchHeading" in s["selector"])
    add("corporate.md", "Wasalt — Company and Platform Overview", "corporate", ["corporate"], [
        ("Company overview", overview),
        ("Platform purpose", "\n".join(line for line in platform.splitlines() if line not in {"OUR PRODUCTS", "Wasalt Search"})),
    ])
    service_blocks = []
    for section in corporate:
        lines = section["text"].splitlines()
        if "ContentPart" in section["selector"] and lines[0] in {"Wasalt Search", "Wasalt Auctions", "Projects  & masterplans"}:
            service_blocks.append((lines[0], "\n".join(lines[1:])))
    homepage = sources["homepage"]["section_candidates"]
    daily = next(s for s in homepage if s["heading"] == "List your daily rentals with Wasalt")
    daily_lines = daily["parents"][0]["text"].splitlines()
    daily_text = "\n".join(line for line in daily_lines if line not in {"Register Now", daily["heading"]})
    service_blocks.append(("Daily rentals", daily_text))
    matching = next(s for s in homepage if s["heading"] == "Find the right property for your needs")
    service_blocks.append((matching["heading"], "\n".join(line for line in matching["parents"][0]["text"].splitlines() if line not in {matching["heading"], "Get Matched"})))
    business = next(s for s in homepage if s["heading"] == "Grow your business. Connect with clients easily.")
    app_text = business["parents"][2]["text"]
    app_lines = [line for line in app_text.splitlines() if line and not line.startswith("Scan QR") and not line.startswith("Enhance your experience")]
    service_blocks.append(("Public business and app services", "\n\n".join(app_lines)))
    add("services.md", "Wasalt — Public Services", "services", ["corporate", "homepage"], service_blocks,
        ["The daily-rental source provides a short promotional statement; booking, cancellation, coverage details, and commission amounts were not supplied in the captured explanation.",
         "Business content is limited to publicly described services; no authenticated portal was accessed."])

    projects = sources["project"]["json_ld"]
    if len(projects) != 1:
        raise ValueError("Ambiguous project record")
    project = projects[0]
    about = sources["project"]["about_candidates"][0]
    visible = about["parents"][2]["text"]
    if "Al Rihab, East, Riyadh" not in visible:
        raise ValueError("Expected project location not found in rendered evidence")
    area = re.search(r"\b300 - 13504\.53 sqm\b", visible)
    attributes = {"project_name": project["name"].strip(), "city": project["address"]["addressLocality"],
                  "rendered_location": "Al Rihab, East, Riyadh", "schema_org_type": project["@type"]}
    overview_lines = [f"- Project name: {project['name'].strip()}", "- Location (rendered): Al Rihab, East, Riyadh"]
    if "Under Construction" in visible:
        overview_lines.append("- Status displayed at extraction: Under Construction")
    if area:
        overview_lines.append("- Displayed land area range: " + area.group())
    for label, value in (("Electricity", "No"), ("Water", "No"), ("Residency Type", "Family")):
        if f"{label}\n{value}" in visible:
            overview_lines.append(f"- {label} (source additional information): {value}")
    description = clean_description(project["description"])
    type_quote = "كفلل سكنية ومساحات تجارية"
    amenity_quotes = ["مراكز تسوق حيوية ومطاعم متعددة", "مناطق لعب الأطفال", "كالمدارس والجهات الحكومية والمساجد"]
    if type_quote not in description or not all(q in description for q in amenity_quotes):
        raise ValueError("Project attribute evidence changed; manual review needed")
    add("projects/shams_al_riyadh.md", project["name"].strip(), "project", ["project"], [
        ("Project overview", "\n".join(overview_lines)), ("Original project description", description),
        ("Property types described in the source", type_quote),
        ("Facilities described in the source", "\n".join("- " + q for q in amenity_quotes)),
    ], ["No developer name was found in the captured structured record or rendered overview.",
        "The structured/rendered location says East Riyadh; the Arabic description says north Riyadh. Both source statements are preserved for review.",
        "SingleFamilyResidence is retained as source metadata and is not used to classify this development.",
        "Facilities are described in the source; no readiness or independent verification is inferred."], attributes)

    articles = {a["heading"].split(":", 1)[0]: a for a in sources["auction_terms"]["article_candidates"] if a["parents"]}
    definitions = paragraphs(articles["Article 1"])[0].split("\n\n")
    selected_definitions = [text for text in definitions if text.startswith(('"Auction":', '"Bid Deposit":', '"Bidding Period":', '"Completion Period":', '"Real Estate Unit(s)":'))]
    if len(selected_definitions) != 5:
        raise ValueError("Auction definitions changed; manual review needed")
    terms4, terms5, terms6, terms7 = [paragraphs(articles[f"Article {n}"]) for n in (4, 5, 6, 7)]
    # These are exact selected source paragraphs, not rewritten legal advice.
    process = [terms5[index] for index in (2, 3, 5, 6)]
    completion = "\n\n".join(terms5[7].split("\n\n")[:2])
    completion += "\n\n" + terms5[15].split("\n\n")[0]
    for value in selected_definitions + process + [completion, *terms6, terms7[0]]:
        if re.search(r"moveable|vehicle|truck|machinery", value, re.I):
            raise ValueError("Non-property auction text selected")
    auction_intro = next(answer for question, answer in faq_blocks if question == "What is Wasalt Auctions?")
    add("auctions.md", "Wasalt — Real Estate Auctions and Selected Public Terms", "auctions", ["homepage", "corporate", "auction_terms", "auction_landing"], [
        ("Public auction explanation", auction_intro),
        ("Article 1 — Selected definitions", "\n\n".join(selected_definitions)),
        ("Article 4 — Account requirement", "\n\n".join([terms4[0], terms4[2]])),
        ("Article 5 — Participation and deposits", "\n\n".join(process)),
        ("Article 5 — Winning and completion", completion),
        ("Article 6 — Fee payment", "\n\n".join(terms6)),
        ("Article 7 — Asset inspection", terms7[0]),
    ], ["These are selected public excerpts, not the complete auction terms. Auction-specific conditions remain in the original sources.",
        "The auction landing page was inspected but exposed no substantive public explanation or FAQ; no auction listings or non-property assets were exported."])
    return docs


def render_document(doc, sources):
    primary = sources[doc["source_keys"][0]]
    metadata = {"source": "wasalt", "source_url": primary["source_url"],
                "source_urls": [sources[key]["source_url"] for key in doc["source_keys"]],
                "content_category": doc["category"], "title": doc["title"],
                "extracted_at": primary["extracted_at"],
                "source_extracted_at": {sources[key]["source_url"]: sources[key]["extracted_at"] for key in doc["source_keys"]},
                **doc["attributes"]}
    if doc["category"] == "faq":
        metadata["faq_count"] = len(doc["blocks"])
    front = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip()
    lines = ["---", front, "---", "", "# " + doc["title"]]
    for heading, body in doc["blocks"]:
        lines += ["", "## " + heading, "", body]
    if doc["notes"]:
        lines += ["", "## Extraction Notes", ""] + ["- " + note for note in doc["notes"]]
    lines += ["", "## Sources", ""] + [f"- [Original source]({url})" for url in metadata["source_urls"]]
    rendered = "\n".join(lines) + "\n"
    if contains_contact(rendered):
        raise ValueError("Contact information detected; output refused")
    if re.search(r"just a moment|verify you are human|checking your browser", rendered, re.I):
        raise ValueError("Challenge content detected; output refused")
    if yaml.safe_load(front) != metadata:
        raise ValueError("YAML metadata round-trip failed")
    return rendered


def main():
    sources = load_sources()
    docs = build_documents(sources)
    targets = [OUT / doc["path"] for doc in docs] + [OUT / "extraction_report.csv"]
    for path in targets:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")
    plan = [(doc, render_document(doc, sources)) for doc in docs]
    report = []
    for doc, rendered in plan:
        path = OUT / doc["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
        report.append({"output_path": str(path.relative_to(ROOT)), "category": doc["category"], "source_urls": ";".join(sources[key]["source_url"] for key in doc["source_keys"]), "extraction_status": "success", "faq_count": 6 if doc["category"] == "faq" else 0, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    with (OUT / "extraction_report.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)
    print(f"Prepared {len(docs)} informational documents; six FAQs preserved; no property files modified.")


if __name__ == "__main__":
    main()
