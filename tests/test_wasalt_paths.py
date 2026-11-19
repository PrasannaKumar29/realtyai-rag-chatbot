"""Migration path compatibility and temporary-output isolation."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.wasalt.wasalt_paths import DATA_ROOT, resolve_data_path


class WasaltPathTests(unittest.TestCase):
    def test_old_new_and_dataset_relative_paths(self):
        expected=DATA_ROOT/'properties/sale/5906160.md'
        for value in ('wasalt_data/properties/sale/5906160.md','data/wasalt/properties/sale/5906160.md','properties/sale/5906160.md'):
            self.assertEqual(resolve_data_path(value),expected)

    def test_absolute_and_escaping_paths_rejected(self):
        for value in ('/content/wasalt_data/raw/a.json','/Users/other/raw.json','../raw.json','wasalt_data/../other.json','C:\\old\\raw.json','https://wasalt.sa/en'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                resolve_data_path(value)

    def test_injected_root_keeps_test_output_outside_production(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'fixture'
            resolved=resolve_data_path('wasalt_data/raw/sale/test.json',data_root=root)
            self.assertEqual(resolved,root/'raw/sale/test.json')
            self.assertFalse(resolved.is_relative_to(DATA_ROOT))
            resolved.parent.mkdir(parents=True)
            resolved.write_text('{}')
            self.assertTrue(resolved.is_file())

    def test_all_recorded_manifest_journal_and_sitemap_paths_resolve(self):
        checked=0
        for path in DATA_ROOT.rglob('*.csv'):
            with path.open(encoding='utf-8',newline='') as handle:
                for row in csv.DictReader(handle):
                    for key in ('output_path','output_file_path','local_output_path'):
                        if row.get(key):
                            self.assertTrue(resolve_data_path(row[key]).is_file(),(str(path),row[key]))
                            checked+=1
        for path in DATA_ROOT.glob('*.journal/*.result.json'):
            value=json.loads(path.read_text())
            if value.get('output_file_path'):
                self.assertTrue(resolve_data_path(value['output_file_path']).is_file())
                checked+=1
        for sitemap in json.loads((DATA_ROOT/'discovery_report.json').read_text())['sitemaps']:
            self.assertTrue(resolve_data_path(sitemap['local_path']).is_file())
            checked+=1
        self.assertGreater(checked,700)


if __name__=='__main__':
    unittest.main()
