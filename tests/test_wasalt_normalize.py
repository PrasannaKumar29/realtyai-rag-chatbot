"""Offline checks against the two original Wasalt test inputs."""

from scripts.wasalt.wasalt_paths import DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import copy
import csv
from decimal import Decimal
import json
from pathlib import Path
import re
import unittest

from scripts.wasalt.wasalt_normalize import clean_description, normalize_property
from scripts.wasalt.wasalt_normalize_sample import validation_status


ROOT = Path(__file__).resolve().parents[1]


class NormalizeTests(unittest.TestCase):
    def test_adjacent_phone_contacts_and_arabic_year(self):
        from scripts.wasalt.wasalt_export_markdown import contains_contact
        cleaned=clean_description('<p>للتواصل</p><p>0551234567 - 0541234567</p><p>📞 اسم الشخص</p><p>المساحة 449.535 متر</p>')
        self.assertFalse(contains_contact(cleaned))
        self.assertNotIn('اسم الشخص',cleaned)
        self.assertIn('449.535',cleaned)
        raw=copy.deepcopy(self.rent_raw)
        raw['json_ld']['offers'][0]['priceCurrency']='SAR /سنة'
        normalized=normalize_property(raw)
        self.assertEqual(normalized['price_period'],'year')
        self.assertNotIn('unclear_price_frequency',normalized['quality_flags'])
        smart_home='📱 منزل ذكي بتفاصيل فاخرة'
        self.assertEqual(clean_description('<p>'+smart_home+'</p>'),smart_home)

    @classmethod
    def setUpClass(cls):
        cls.sale_raw = json.loads((MANUAL_EXPORTS / "wasalt_5891090.json").read_text())
        cls.rent_raw = json.loads((DATA_ROOT / "raw/rent/5891036.json").read_text())

    def test_sale(self):
        p = normalize_property(self.sale_raw)
        expected = {
            "listing_id": "5891090", "purpose": "sale", "price_sar": 435000,
            "price_currency": "SAR", "price_period": None, "area_sqm": 122.58,
            "area_source": "title", "bedrooms": 4, "bathrooms": None, "rooms": 4,
            "city": "Makkah Al Mukarramah", "district": "Almouhamdeah",
            "property_type": "apartment", "schema_org_type": "SingleFamilyResidence",
        }
        for key, value in expected.items():
            with self.subTest(field=key):
                self.assertEqual(p[key], value)
        self.assertIn("rooms_description_mismatch", p["quality_flags"])
        self.assertIn("missing_bathrooms", p["quality_flags"])
        self.assertIn("schema_type_property_type_mismatch", p["quality_flags"])

    def test_rental(self):
        p = normalize_property(self.rent_raw)
        expected = {
            "listing_id": "5891036", "purpose": "rent", "price_sar": 120000,
            "price_currency": "SAR", "price_period": "year", "area_sqm": 250,
            "area_source": "title", "bedrooms": 9, "bathrooms": 6,
            "city": "Riyadh", "region": "North Riyadh", "district": "An-Narjis",
            "property_type": "villa",
        }
        for key, value in expected.items():
            with self.subTest(field=key):
                self.assertEqual(p[key], value)
        self.assertNotIn("rooms_description_mismatch", p["quality_flags"])
        self.assertIn("125 ألف دفعتين", p["description_clean"])
        self.assertIn("120 ألف دفعة", p["description_clean"])

    def test_source_preservation_and_cleaning(self):
        for raw in (self.sale_raw, self.rent_raw):
            with self.subTest(listing=raw["listing_id"]):
                before = copy.deepcopy(raw)
                p = normalize_property(raw)
                self.assertEqual(raw, before)
                self.assertEqual(p["description_original"], raw["json_ld"]["description"])
                self.assertEqual(p["scraped_at"], raw["extracted_at"])
                self.assertRegex(p["description_clean"], r"[\u0600-\u06ff]")
                self.assertIn("\n\n", p["description_clean"])
                self.assertNotRegex(p["description_clean"], r"<[^>]+>")
                phones = re.findall(r"\b05\d{8}\b", raw["json_ld"]["description"])
                self.assertTrue(phones)
                for phone in phones:
                    self.assertNotIn(phone, p["description_clean"])

    def test_phone_formats_and_measurements(self):
        cleaned = clean_description("<p>اتصل +966 55 123 4567</p><p>٠٥٥١٢٣٤٥٦٧</p><p>250 متر 6 حمامات</p>")
        self.assertEqual(cleaned.count("[phone removed]"), 2)
        self.assertIn("250 متر 6 حمامات", cleaned)

    def test_nulls_and_optional_fields(self):
        p = normalize_property({"json_ld": {"address": None, "offers": None, "image": []}})
        for key in ("listing_id", "title", "bathrooms", "description_clean", "image_url", "price_sar"):
            self.assertIsNone(p[key])
        self.assertIn("invalid_source_url", p["quality_flags"])
        self.assertIn("missing_price_sar", p["quality_flags"])
        self.assertIsNone(normalize_property({"json_ld": None})["title"])

    def test_structured_values_take_priority(self):
        raw = copy.deepcopy(self.sale_raw)
        raw["json_ld"].update({"propertyType": "Villa", "floorSize": {"value": "130.5", "unitCode": "MTK"}})
        raw["json_ld"]["offers"][0]["price"] = "435,000"
        p = normalize_property(raw)
        self.assertEqual(p["property_type"], "villa")
        self.assertEqual((p["area_sqm"], p["area_source"]), (130.5, "structured"))
        self.assertEqual(p["price_sar"], 435000)

    def test_ambiguous_offers_and_unknown_frequency(self):
        raw = copy.deepcopy(self.rent_raw)
        raw["json_ld"]["offers"][0]["priceCurrency"] = "SAR"
        self.assertIn("unclear_price_frequency", normalize_property(raw)["quality_flags"])
        raw["json_ld"]["offers"].append({"price": 125000, "priceCurrency": "SAR /Year"})
        p = normalize_property(raw)
        self.assertIsNone(p["price_sar"])
        self.assertIn("multiple_offers", p["quality_flags"])

    def test_all_ten_sample_records(self):
        expected = {
            "5906160": ("apartment", 490000, 235.28, "Jazan"),
            "5893906": ("land", 3200400, 504, "Jeddah"),
            "5923219": ("building", 15500000, 2400, "Riyadh"),
            "5938174": ("villa", 1400000, 360, "Riyadh"),
            "5878482": ("floor", 850000, 232.36, "Riyadh"),
            "5868948": ("apartment", 56000, 130, "Riyadh"),
            "5896807": ("villa", 80000, 650, "Riyadh"),
            "5918685": ("building", 1140000, 2500, "Riyadh"),
            "5920675": ("land", 550080, 1800, "Khobar"),
            "5860435": ("floor", 80000, 342, "Riyadh"),
        }
        with (DATA_ROOT / "sample_10.csv").open() as handle:
            sample = list(csv.DictReader(handle))
        self.assertEqual({r["listing_id"] for r in sample}, set(expected))
        for row in sample:
            with self.subTest(listing=row["listing_id"]):
                path = DATA_ROOT / "raw" / row["purpose"] / (row["listing_id"] + ".json")
                before_bytes = path.read_bytes()
                raw = json.loads(before_bytes)
                before = copy.deepcopy(raw)
                p = normalize_property(raw)
                self.assertEqual((p["property_type"], p["price_sar"], p["area_sqm"], p["city"]), expected[row["listing_id"]])
                self.assertEqual(p["area_source"], "title")
                self.assertEqual(p["schema_org_type"], raw["json_ld"]["@type"])
                self.assertEqual(p["price_currency"], "SAR")
                self.assertEqual(p["price_period"], "year" if row["purpose"] == "rent" else None)
                for key in ("source", "source_url", "listing_id", "purpose"):
                    self.assertEqual(p[key], raw[key])
                self.assertEqual(p["scraped_at"], raw["extracted_at"])
                self.assertEqual(p["district"], raw["json_ld"]["address"]["streetAddress"])
                self.assertEqual(p["description_original"], raw["json_ld"]["description"])
                self.assertIn("\n\n", p["description_clean"])
                for word in re.findall(r"[\u0621-\u064a]+", raw["json_ld"]["description"]):
                    self.assertIn(word, p["description_clean"])
                self.assertIsNone(p["bathrooms"])
                if p["property_type"] in {"land", "building"}:
                    self.assertIsNone(p["bedrooms"])
                    self.assertIsNone(p["rooms"])
                    self.assertNotIn("missing_bedrooms", p["quality_flags"])
                    self.assertNotIn("missing_bathrooms", p["quality_flags"])
                self.assertEqual(raw, before)
                self.assertEqual(path.read_bytes(), before_bytes)
                if row["listing_id"] == "5906160":
                    self.assertIn("area_description_mismatch", p["quality_flags"])

    def test_contact_redaction_preserves_prices(self):
        cleaned = clean_description('<p>Price: 15500000 SAR</p><p>Phone: 12345678</p><p>agent@example.com</p><p><a href="https://wa.me/966551234567">اسم البائع</a></p><p>instagram: @agent.name</p><p>https://t.me/agent</p>')
        self.assertIn("15500000 SAR", cleaned)
        for secret in ("12345678", "agent@example.com", "اسم البائع", "agent.name", "t.me/agent"):
            self.assertNotIn(secret, cleaned)

    def test_never_uses_url_area(self):
        raw = copy.deepcopy(self.sale_raw)
        raw["json_ld"]["name"] = "Apartment for Sale"
        p = normalize_property(raw)
        self.assertIsNone(p["area_sqm"])
        self.assertIsNone(p["area_source"])

    def test_malformed_inputs(self):
        for raw in (None, {}, {"source_url": "https://[broken", "json_ld": {"offers": "invalid", "address": []}}):
            with self.subTest(raw=raw):
                self.assertIn("invalid_source_url", normalize_property(raw)["quality_flags"])
        raw = copy.deepcopy(self.sale_raw)
        raw["json_ld"].update(numberOfBedrooms="unknown", numberOfBathroomsTotal=False)
        raw["json_ld"]["offers"][0]["price"] = "NaN"
        p = normalize_property(raw)
        for key in ("price_sar", "bedrooms", "bathrooms"):
            self.assertIsNone(p[key])

    def test_explicit_floor_type(self):
        raw = copy.deepcopy(self.sale_raw)
        raw["json_ld"]["propertyType"] = "Floor"
        self.assertEqual(normalize_property(raw)["property_type"], "floor")

    def test_quality_status_optional_fields_and_invalid_identity(self):
        sale = normalize_property(self.sale_raw)
        self.assertIsNone(sale["bathrooms"])
        self.assertEqual(validation_status(sale), "valid_with_warnings")
        self.assertEqual(validation_status(normalize_property({})), "invalid")
        broken = copy.deepcopy(self.sale_raw)
        broken["listing_id"] = "999"
        self.assertEqual(validation_status(normalize_property(broken)), "invalid")

    def test_new_types_and_multiword_precedence(self):
        titles = {"Rest House 449.535 SQM": "rest_house", "Rest-House 120 SQM": "rest_house", "Room for Rent": "room", "Chalet 625 SQM with 2 Guest Rooms": "chalet", "Duplex 315 SQM with 6 Bedrooms": "duplex"}
        for title, expected in titles.items():
            with self.subTest(title=title):
                raw = copy.deepcopy(self.sale_raw)
                raw["json_ld"]["name"] = title
                p = normalize_property(raw)
                self.assertEqual(p["property_type"], expected)
                self.assertNotIn("ambiguous_property_type", p["quality_flags"])
                self.assertEqual(p["schema_org_type"], "SingleFamilyResidence")
        for explicit in ("Rest House", "rest_house", "rest-house"):
            raw = copy.deepcopy(self.sale_raw)
            raw["json_ld"]["propertyType"] = explicit
            self.assertEqual(normalize_property(raw)["property_type"], "rest_house")

    def test_missing_description_stays_null_and_useful_record_valid(self):
        raw = copy.deepcopy(self.rent_raw)
        del raw["json_ld"]["description"]
        p = normalize_property(raw)
        self.assertIsNone(p["description_original"])
        self.assertIsNone(p["description_clean"])
        self.assertIn("missing_description_clean", p["quality_flags"])
        self.assertEqual(validation_status(p), "valid_with_warnings")

    def test_room_missing_counts_not_assumed_or_warned(self):
        raw = copy.deepcopy(self.rent_raw)
        raw["json_ld"]["name"] = "Room for Rent"
        for field in ("numberOfBedrooms", "numberOfBathroomsTotal", "numberOfRooms"):
            raw["json_ld"].pop(field, None)
        p = normalize_property(raw)
        for field in ("bedrooms", "bathrooms", "rooms", "area_sqm"):
            self.assertIsNone(p[field])
        self.assertNotIn("missing_bedrooms", p["quality_flags"])
        self.assertNotIn("missing_bathrooms", p["quality_flags"])

    def test_all_fifty_sample_records(self):
        from scripts.wasalt.wasalt_export_markdown import contains_contact

        with (DATA_ROOT / "sample_50.csv").open() as handle:
            sample = list(csv.DictReader(handle))
        self.assertEqual(len(sample), 50)
        seen_types = set()
        missing_descriptions = 0
        for item in sample:
            with self.subTest(listing=item["listing_id"]):
                path = DATA_ROOT / "raw" / item["purpose"] / (item["listing_id"] + ".json")
                before_bytes = path.read_bytes()
                raw = json.loads(before_bytes)
                before = copy.deepcopy(raw)
                p = normalize_property(raw)
                prop = raw["json_ld"]
                self.assertEqual(p["property_type"], item["property_type_hint"])
                seen_types.add(p["property_type"])
                for key in ("source", "listing_id", "source_url", "purpose"):
                    self.assertEqual(p[key], raw[key])
                self.assertEqual(p["scraped_at"], raw["extracted_at"])
                self.assertEqual(p["schema_org_type"], prop["@type"])
                self.assertEqual(p["price_sar"], prop["offers"][0]["price"])
                self.assertEqual(p["price_currency"], "SAR")
                self.assertEqual(p["price_period"], "year" if item["purpose"] == "rent" else None)
                self.assertEqual(p["city"], prop["address"].get("addressLocality"))
                self.assertEqual(p["region"], prop["address"].get("addressRegion"))
                self.assertEqual(p["district"], prop["address"].get("streetAddress"))
                area = re.search(r"(\d+(?:\.\d+)?)\s+SQM\b", prop["name"])
                if area:
                    self.assertEqual(Decimal(str(p["area_sqm"])), Decimal(area.group(1)))
                    self.assertEqual(p["area_source"], "title")
                else:
                    self.assertIsNone(p["area_sqm"])
                    self.assertIsNone(p["area_source"])
                for source, target in (("numberOfBedrooms", "bedrooms"), ("numberOfBathroomsTotal", "bathrooms"), ("numberOfRooms", "rooms")):
                    if prop.get(source) is None:
                        self.assertIsNone(p[target])
                    else:
                        self.assertEqual(p[target], int(prop[source]))
                self.assertEqual(p["description_original"], prop.get("description"))
                if prop.get("description") is None:
                    missing_descriptions += 1
                    self.assertIsNone(p["description_clean"])
                    self.assertIn("missing_description_clean", p["quality_flags"])
                else:
                    self.assertTrue(p["description_clean"])
                    self.assertFalse(contains_contact(p["description_clean"]))
                    if re.search(r"[\u0621-\u064a]", prop["description"]):
                        self.assertRegex(p["description_clean"], r"[\u0621-\u064a]")
                    if prop["description"].count("</p>") > 1:
                        self.assertIn("\n\n", p["description_clean"])
                self.assertNotEqual(validation_status(p), "invalid")
                self.assertEqual(raw, before)
                self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(missing_descriptions, 3)
        self.assertEqual(seen_types, {"apartment", "villa", "land", "floor", "building", "rest_house", "room", "chalet", "duplex"})


if __name__ == "__main__":
    unittest.main()
