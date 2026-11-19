"""Offline document/YAML checks using the actual ten normalized sample records."""

from scripts.wasalt.wasalt_paths import DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import copy
import csv
import json
from pathlib import Path
import re
import tempfile
import unittest

import yaml

from scripts.wasalt.wasalt_export_markdown import DATA, FIELDS, contains_contact, export_sample, render_markdown


class MarkdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        cls.report = export_sample(cls.output)
        with (DATA / "sample_10.csv").open() as handle:
            cls.sample = list(csv.DictReader(handle))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_count_directories_and_report(self):
        self.assertEqual(len(list((self.output / "properties").rglob("*.md"))), 10)
        for purpose in ("sale", "rent"):
            self.assertEqual(len(list((self.output / "properties" / purpose).glob("*.md"))), 5)
        with (self.output / "sample_10_markdown_report.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(r["export_status"] == "success" for r in rows))
        for row in rows:
            record = self.load_record(row)
            self.assertEqual(int(row["quality_warning_count"]), len(record["quality_flags"]))
            self.assertTrue((self.output / row["output_path"]).is_file())

    @staticmethod
    def load_record(row):
        return json.loads((DATA / "normalized" / row["purpose"] / (row["listing_id"] + ".json")).read_text(encoding="utf-8"))

    def check_document(self, path, record):
        document = path.read_bytes().decode("utf-8", errors="strict")
        self.assertTrue(document.startswith("---\n"))
        _, front, body = document.split("---\n", 2)
        metadata = yaml.safe_load(front)
        self.assertIsInstance(metadata, dict)
        for field in FIELDS:
            self.assertEqual(metadata[field], record[field])
        self.assertIsInstance(metadata["listing_id"], str)
        for field in ("bedrooms", "bathrooms"):
            if record[field] is None:
                self.assertNotIn(field, metadata)
                self.assertNotIn(f"- {field.capitalize()}:", body)
            else:
                self.assertEqual(metadata[field], record[field])
        self.assertIn(f"[Original Wasalt listing]({record['source_url']})", body)
        self.assertIn(record["description_clean"], body)
        if re.search(r"[\u0621-\u064a]", record["description_clean"]):
            self.assertRegex(body, r"[\u0621-\u064a]")
            self.assertIn("\n\n", record["description_clean"])
        self.assertFalse(contains_contact(document))
        self.assertNotRegex(body, r"<\s*/?\s*[A-Za-z][^>]*>")
        for flag in record["quality_flags"]:
            self.assertIn("## Quality Notes", body)
            self.assertIn(f"`{flag}`", body)
        if record["purpose"] == "rent":
            self.assertIn(f"SAR {record['price_sar']:,}/year", body)
        self.assertIn(f"{record['area_sqm']:,} sqm", body)

    def test_all_documents_metadata_content_and_utf8(self):
        for row in self.sample:
            with self.subTest(listing=row["listing_id"]):
                record = self.load_record(row)
                path = self.output / "properties" / row["purpose"] / (row["listing_id"] + ".md")
                self.check_document(path, record)

    def test_renderer_preserves_input(self):
        record = self.load_record(self.sample[0])
        before = copy.deepcopy(record)
        render_markdown(record)
        self.assertEqual(record, before)

    def test_safe_yaml_special_characters(self):
        record = self.load_record(self.sample[0])
        record["city"] = 'City: "quoted" # value\nsecond line'
        record["district"] = "null"
        front = render_markdown(record).split("---\n", 2)[1]
        loaded = yaml.safe_load(front)
        self.assertEqual(loaded["city"], record["city"])
        self.assertEqual(loaded["district"], "null")

    def test_missing_values_not_fabricated(self):
        record = self.load_record(self.sample[0])
        for key in ("price_sar", "area_sqm", "city", "region", "district", "bedrooms", "bathrooms"):
            record[key] = None
        body = render_markdown(record).split("---\n", 2)[2]
        for label in ("Price", "Area", "Location", "Bedrooms", "Bathrooms"):
            self.assertNotIn(f"- {label}:", body)

    def test_contact_leaks_refuse_export(self):
        for contact in ("0551234567", "+966 55 123 4567", "٠٥٥١٢٣٤٥٦٧", "agent@example.com", "https://wa.me/966551234567"):
            record = self.load_record(self.sample[0])
            record["description_clean"] += "\n\n" + contact
            with self.subTest(contact=contact), self.assertRaises(ValueError):
                render_markdown(record)

    def test_refuses_existing_outputs(self):
        before = {p: p.read_bytes() for p in self.output.rglob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            export_sample(self.output)
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

    def test_production_documents_when_present(self):
        report = DATA / "sample_10_markdown_report.csv"
        if not report.exists():
            self.skipTest("Production export has not run yet")
        self.assertEqual(len([row for row in self.sample if (DATA / "properties" / row["purpose"] / (row["listing_id"] + ".md")).is_file()]), 10)
        for row in self.sample:
            with self.subTest(listing=row["listing_id"]):
                self.check_document(DATA / "properties" / row["purpose"] / (row["listing_id"] + ".md"), self.load_record(row))

    def test_complete_corpus_when_present(self):
        if not (DATA / "listings.jsonl").exists():
            self.skipTest("Complete corpus has not been exported yet")
        normalized = [json.loads(path.read_text()) for path in sorted((DATA / "normalized").rglob("*.json"))]
        lines = [json.loads(line) for line in (DATA / "listings.jsonl").read_text().splitlines()]
        self.assertEqual(lines, normalized)
        expected_count=261 if (DATA/'final_markdown_report.csv').exists() else 62
        self.assertEqual(len(lines), expected_count)
        self.assertEqual(len({r["listing_id"] for r in lines}), expected_count)
        self.assertEqual(len(list((DATA / "properties").rglob("*.md"))), expected_count)
        with (DATA / "quality_report.csv").open() as handle:
            quality = {row["listing_id"]: row for row in csv.DictReader(handle)}
        self.assertEqual(len(quality), expected_count)
        for record in lines:
            path = DATA / "properties" / record["purpose"] / (record["listing_id"] + ".md")
            document = path.read_bytes().decode("utf-8")
            _, front, body = document.split("---\n", 2)
            metadata = yaml.safe_load(front)
            for key in FIELDS:
                self.assertEqual(metadata[key], record[key])
            self.assertFalse(contains_contact(document))
            self.assertIn(f"[Original Wasalt listing]({record['source_url']})", body)
            if record["description_clean"]:
                self.assertIn(record["description_clean"], body)
            else:
                self.assertNotIn("## Description", body)
            if record["area_sqm"] is None:
                self.assertNotIn("- Area:", body)
            self.assertEqual(quality[record["listing_id"]]["quality_flags"], ";".join(record["quality_flags"]))


if __name__ == "__main__":
    unittest.main()
