"""Offline validation of the five informational documents and source evidence."""

from scripts.wasalt.wasalt_paths import DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import copy
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unittest

import yaml

from scripts.wasalt.wasalt_export_informational import OUT, build_documents, load_sources, render_document
from scripts.wasalt.wasalt_export_markdown import contains_contact
from scripts.wasalt.wasalt_normalize import clean_description


class InformationalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_sources()
        cls.documents = build_documents(cls.sources)

    def test_five_documents_and_source_metadata(self):
        self.assertEqual(len(list(OUT.rglob("*.md"))), 5)
        approved = {source["source_url"] for source in self.sources.values()}
        self.assertEqual(len(approved), 5)
        for doc in self.documents:
            with self.subTest(document=doc["path"]):
                value = (OUT / doc["path"]).read_bytes().decode("utf-8", errors="strict")
                self.assertEqual(value, render_document(doc, self.sources))
                _, front, body = value.split("---\n", 2)
                metadata = yaml.safe_load(front)
                self.assertEqual(metadata["content_category"], doc["category"])
                self.assertIn(metadata["source_url"], approved)
                self.assertTrue(set(metadata["source_urls"]).issubset(approved))
                self.assertIsNotNone(datetime.fromisoformat(metadata["extracted_at"].replace("Z", "+00:00")).tzinfo)
                for url in metadata["source_urls"]:
                    self.assertIn(f"[Original source]({url})", body)
                self.assertGreater(sum(len(text) for _, text in doc["blocks"]), 120)
                self.assertFalse(contains_contact(value))
                self.assertNotRegex(value.lower(), r"just a moment|verify you are human|checking your browser")
                self.assertNotRegex(body, r"<\s*/?\s*[A-Za-z][^>]*>")

    def test_all_six_faqs_verbatim(self):
        expected = [q for record in self.sources["homepage"]["faq_records"] for q in record["mainEntity"]]
        self.assertEqual(len(expected), 6)
        document = (OUT / "faq.md").read_text()
        actual = next(d for d in self.documents if d["category"] == "faq")["blocks"]
        self.assertEqual(actual, [(q["name"].strip(), q["acceptedAnswer"]["text"].strip()) for q in expected])
        for question, answer in actual:
            self.assertIn("## " + question + "\n\n" + answer, document)

    def test_corporate_services_have_source_evidence(self):
        corporate_text = "\n".join(section["text"] for section in self.sources["corporate"]["sections"])
        homepage_text = "\n".join(parent["text"] for section in self.sources["homepage"]["section_candidates"] for parent in section["parents"])
        for doc in self.documents:
            if doc["category"] not in {"corporate", "services"}:
                continue
            for _, block in doc["blocks"]:
                for line in block.splitlines():
                    if line.strip():
                        self.assertIn(line, corporate_text + "\n" + homepage_text)
            output = (OUT / doc["path"]).read_text()
            self.assertNotIn("Register Now", output)
            self.assertNotIn("Scan QR code", output)
            self.assertNotIn("Post Property", output)

    def test_project_description_attributes_and_limitations(self):
        record = self.sources["project"]["json_ld"][0]
        document = (OUT / "projects/shams_al_riyadh.md").read_text()
        self.assertIn(clean_description(record["description"]), document)
        self.assertRegex(document, r"[\u0621-\u064a]")
        self.assertIn("No developer name was found", document)
        self.assertIn("north Riyadh", document)
        self.assertIn("East Riyadh", document)
        rendered = self.sources["project"]["about_candidates"][0]["parents"][2]["text"]
        for field in ("Al Rihab, East, Riyadh", "300 - 13504.53 sqm", "Under Construction"):
            self.assertIn(field, document)
            self.assertIn(field, rendered)

    def test_no_auction_listings_or_nonproperty_material(self):
        document = (OUT / "auctions.md").read_text()
        self.assertNotRegex(document.lower(), r"moveable|vehicle|truck|machinery|auction-group/|view details & bid")
        self.assertNotIn("Article 14", document)
        self.assertIn("selected public excerpts", document)
        self.assertFalse(self.sources["auction_landing"]["has_public_explanations"])
        evidence = "\n".join(parent["text"] for article in self.sources["auction_terms"]["article_candidates"] for parent in article["parents"])
        doc = next(d for d in self.documents if d["category"] == "auctions")
        for heading, text in doc["blocks"]:
            if heading.startswith("Article"):
                for paragraph in text.split("\n\n"):
                    self.assertIn(" ".join(paragraph.split()), " ".join(evidence.split()))

    def test_saved_source_status_and_report_checksums(self):
        for source in self.sources.values():
            self.assertEqual(source["http_status"], 200)
        with (OUT / "extraction_report.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(int(r["faq_count"]) for r in rows), 6)
        for row in rows:
            path = resolve_data_path(row["output_path"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            self.assertEqual(row["extraction_status"], "success")

    def test_output_guard_rejects_contact_and_challenges(self):
        for injected in ("agent@example.com", "0551234567", "Just a moment"):
            doc = copy.deepcopy(self.documents[0])
            doc["blocks"].append(("Unexpected", injected))
            with self.subTest(injected=injected), self.assertRaises(ValueError):
                render_document(doc, self.sources)


if __name__ == "__main__":
    unittest.main()
