"""Offline integration checks for the complete portable Wasalt dataset."""

from scripts.wasalt.wasalt_paths import DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import csv
import hashlib
import json
from pathlib import Path
import unittest

from scripts.wasalt.wasalt_finalize_dataset import DATA, ROOT, audit_dataset
from scripts.wasalt.wasalt_normalize import normalize_property


class FinalDatasetTests(unittest.TestCase):
    def test_full_source_to_corpus_audit(self):
        records,corpus,report=audit_dataset()
        self.assertEqual(len(records),261)
        self.assertEqual(len(corpus),266)
        self.assertEqual(report['sale_rent_distribution'],{'sale':131,'rent':130})
        self.assertTrue(report['integration_ready'])

    def test_successful_expansion_records_match_current_normalizer(self):
        selected=[]
        for i in range(1,5):
            with (DATA/f'expansion_batch_{i:02d}_manifest.csv').open() as handle:
                selected.extend(row for row in csv.DictReader(handle) if row['extraction_status']=='success')
        self.assertEqual(len(selected),199)
        for row in selected:
            with self.subTest(listing=row['listing_id']):
                raw=json.loads((DATA/'raw'/row['purpose']/(row['listing_id']+'.json')).read_text())
                actual=json.loads((DATA/'normalized'/row['purpose']/(row['listing_id']+'.json')).read_text())
                self.assertEqual(actual,normalize_property(raw))

    def test_manifest_paths_and_distinct_categories(self):
        with (DATA/'corpus_manifest.csv').open() as handle:
            rows=list(csv.DictReader(handle))
        self.assertEqual(len(rows),266)
        self.assertEqual(len({row['document_id'] for row in rows}),266)
        self.assertEqual(sum(row['content_category']=='property_sale' for row in rows),131)
        self.assertEqual(sum(row['content_category']=='property_rent' for row in rows),130)
        self.assertEqual(sum(row['content_category'].startswith('informational_') for row in rows),5)
        for row in rows:
            path=Path(row['local_output_path'])
            self.assertFalse(path.is_absolute())
            self.assertNotIn('..',path.parts)
            self.assertTrue((DATA/path).is_file())

    def test_all_recorded_file_hashes_and_manual_source_copy(self):
        inventory=json.loads((DATA/'file_integrity.json').read_text())['sha256']
        self.assertEqual(sum(path.startswith('raw/') for path in inventory),261)
        for path,digest in inventory.items():
            self.assertEqual(hashlib.sha256((DATA/path).read_bytes()).hexdigest(),digest,path)
        self.assertEqual((DATA/'raw/sale/5891090.json').read_bytes(),(MANUAL_EXPORTS/'wasalt_5891090.json').read_bytes())

    def test_unavailable_listing_is_only_in_acquisition_evidence(self):
        with (DATA/'expansion_batch_02_manifest.csv').open() as handle:
            failed=next(row for row in csv.DictReader(handle) if row['listing_id']=='5842008')
        self.assertEqual(failed['http_status'],'404')
        self.assertEqual(failed['extraction_status'],'failed')
        for category,suffix in [('raw','json'),('normalized','json'),('properties','md')]:
            self.assertFalse((DATA/category/'rent'/f'5842008.{suffix}').exists())
        report=json.loads((DATA/'final_audit_report.json').read_text())
        self.assertEqual(report['excluded_unavailable_listing']['listing_id'],'5842008')


if __name__=='__main__':
    unittest.main()
