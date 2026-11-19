"""Offline checks of atomic storage and explicit resumption; no browsers."""

from scripts.wasalt.wasalt_paths import DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.wasalt.wasalt_extract_batch as batch


class BatchSafetyTests(unittest.TestCase):
    def test_failure_gate_unavailable_continues_and_transient_errors_stop(self):
        for status in (404,410,"404","410"):
            self.assertEqual(batch.failure_gate({'http_status':status,'extraction_status':'failed'},1),(0,None))
        row={'http_status':503,'extraction_status':'failed'}
        streak,reason=batch.failure_gate(row)
        self.assertEqual(streak,1)
        self.assertIsNone(reason)
        self.assertIsNotNone(batch.failure_gate({'http_status':'','extraction_status':'failed'},streak)[1])
        self.assertEqual(batch.failure_gate({'http_status':200,'extraction_status':'success'},1),(0,None))
        self.assertIsNotNone(batch.failure_gate({'http_status':403,'extraction_status':'blocked'})[1])
        self.assertIsNotNone(batch.failure_gate({'http_status':429,'extraction_status':'blocked'})[1])
        self.assertEqual(batch.failure_gate({'http_status':200,'extraction_status':'invalid'},1),(0,None))

    def test_atomic_json_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'raw.json'
            batch.write_json_exclusive(path,{'description':'نص عربي'})
            before=path.read_bytes()
            with self.assertRaises(FileExistsError):
                batch.write_json_exclusive(path,{'changed':True})
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(json.loads(before),{'description':'نص عربي'})
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_serialization_failure_does_not_publish_partial_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'raw.json'
            with self.assertRaises(ValueError):
                batch.write_json_exclusive(path,{'price':float('nan')})
            self.assertFalse(path.exists())

    def test_existing_raw_skips_without_browser(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(batch,'ROOT',Path(directory)), patch.object(batch,'DATA_ROOT',Path(directory)/'data/wasalt'):
            item={'listing_id':'123','purpose':'sale','source_url':'https://wasalt.sa/en/property/sale/apartment-123'}
            path=Path(directory)/'data/wasalt/raw/sale/123.json'
            batch.write_json_exclusive(path,{**item,'json_ld':{'name':'Apartment'}})
            result=batch.extract_one(None,item)
            self.assertEqual(result['extraction_status'],'skipped')
            self.assertEqual(result['main_property_found'],'Yes')

    def test_interrupted_and_failed_attempts_not_retried_and_blocked_not_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old.csv'; path.write_text('partial CSV deliberately ignored')
            journal=path.with_suffix('.csv.journal'); journal.mkdir()
            sample=[{'listing_id':'1','purpose':'sale','source_url':'one'}, {'listing_id':'2','purpose':'rent','source_url':'two'}]
            batch.write_json_exclusive(journal/'batch.json',{'listings':sample})
            batch.write_json_exclusive(journal/'1.started.json',{'listing_id':'1'})
            batch.write_json_exclusive(journal/'2.result.json',{'listing_id':'2','extraction_status':'failed'})
            self.assertEqual(batch.previous_attempts(path,sample),{'1','2'})
            batch.write_json_exclusive(journal/'3.result.json',{'listing_id':'3','extraction_status':'blocked'})
            with self.assertRaises(ValueError):
                batch.previous_attempts(path,sample)


if __name__=='__main__':
    unittest.main()
