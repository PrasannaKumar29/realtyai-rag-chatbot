"""Offline corpus/tokenizer/word-boundary regression and integration tests."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import tiktoken

from app.config import CorpusConfig,REPO_ROOT
from app.documents import Document,flat_metadata,load_documents,parse_markdown
from app.chunking import OfflineTokenizer,chunk_document,sections
from app.prepare_corpus import iter_chunks,jsonl_text,prepare


def fixture(body,kind='blog',**metadata):
    return Document('fixture:1',body,{'document_id':'fixture:1','source':'wasalt' if kind.startswith(('property_','informational_')) else 'darglobal',
                                   'content_type':kind,'title':'Villa example' if kind.startswith('property_') else 'Example',
                                   'source_url':'https://example.test/source',**metadata})


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=CorpusConfig()
        cls.tokenizer=OfflineTokenizer(cls.config)

    def test_frontmatter_excluded_and_body_preserved(self):
        metadata,body=parse_markdown('---\ntitle: "Example"\nprice: null\n---\n# Example\n\nنص عربي\n')
        self.assertEqual(metadata['title'],'Example')
        self.assertEqual(body,'# Example\n\nنص عربي\n')
        with self.assertRaises(ValueError):parse_markdown('# No frontmatter')

    def test_metadata_is_scalar_and_lists_are_reversible(self):
        result=flat_metadata({'price':None,'price_sar':120000,'quality_flags':['missing_bathrooms'],'source_urls':['https://example.test']})
        self.assertNotIn('price',result)
        self.assertEqual(json.loads(result['quality_flags_json']),['missing_bathrooms'])
        self.assertTrue(all(isinstance(x,(str,int,float,bool)) for x in result.values()))

    def test_local_encoding_matches_tiktoken_official_constructor(self):
        with patch.dict(os.environ,{'TIKTOKEN_CACHE_DIR':str(self.config.tokenizer_cache)}),patch('tiktoken.load.read_file',side_effect=AssertionError('No downloads allowed')):
            official=tiktoken.encoding_for_model('text-embedding-3-small')
        for text in ('Villa 250 SQM — SAR 120,000/year','فيلا للإيجار في الرياض','<|endoftext|> is ordinary source text'):
            self.assertEqual(self.tokenizer.encoding.encode(text,disallowed_special=()),official.encode(text,disallowed_special=()))

    def test_missing_cache_fails_without_network(self):
        with tempfile.TemporaryDirectory() as directory,patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            with self.assertRaises(RuntimeError):OfflineTokenizer(replace(self.config,tokenizer_cache=Path(directory)))

    def test_short_document_one_chunk_and_stable_id(self):
        doc=fixture('# Example\n\nA short source paragraph.')
        first=chunk_document(doc,self.tokenizer,self.config)
        self.assertEqual(len(first),1)
        self.assertEqual(first,chunk_document(doc,self.tokenizer,self.config))
        self.assertNotEqual(first[0]['chunk_id'],chunk_document(replace(doc,body=doc.body+' Changed.'),self.tokenizer,self.config)[0]['chunk_id'])

    def test_fenced_heading_is_not_a_section_boundary(self):
        body='# Example\n\n```python\n# a code comment\n```\n\n## Actual section\nText.'
        self.assertEqual([section.heading for section in sections(body)],['# Example','## Actual section'])

    def test_word_safe_arabic_slices_and_overlap(self):
        body='# Example\n\n'+' '.join('كلمة'+str(i) for i in range(300))
        config=replace(self.config,target_tokens=100,max_tokens=150,overlap_tokens=15)
        rows=chunk_document(fixture(body),self.tokenizer,config)
        self.assertGreater(len(rows),1)
        seen=[]
        for row in rows:
            self.assertLessEqual(row['token_count'],150)
            self.assertNotIn('\ufffd',row['text'])
            for a,b in json.loads(row['source_spans_json']):
                self.assertTrue(a==0 or body[a-1].isspace())
                self.assertTrue(b==len(body) or body[b].isspace())
                self.assertIn(body[a:b].strip(),row['text'])
                seen.append((a,b))
        overlaps=[self.tokenizer.count(body[a:old_b]) for (_,old_b),(a,_) in zip(seen,seen[1:]) if a<old_b]
        self.assertTrue(overlaps)
        self.assertTrue(all(count<=15 for count in overlaps))

    def test_markdown_link_with_spaced_title_is_not_cut(self):
        link='[Read this](https://example.test/source "A complete link title")'
        body='# Example\n\n'+('word '*90)+link+' '+('tail '*90)
        config=replace(self.config,target_tokens=100,max_tokens=120,overlap_tokens=10)
        rows=chunk_document(fixture(body),self.tokenizer,config)
        self.assertTrue(any(link in row['text'] for row in rows))
        for row in rows:
            for a,b in json.loads(row['source_spans_json']):
                self.assertFalse(body.index(link)<a<body.index(link)+len(link))
                self.assertFalse(body.index(link)<b<body.index(link)+len(link))

    def test_long_property_repeats_context_before_description(self):
        body='# Villa example\n\n## Property Overview\n\n- Purpose: Long-term rent\n- Location: Riyadh\n- Price: SAR 120,000/year\n\n## Description\n\n'+' '.join('عقار'+str(i) for i in range(200))
        rows=chunk_document(fixture(body,'property_rent',listing_id='123',purpose='rent'),self.tokenizer,self.config)
        self.assertGreater(len(rows),1)
        for row in rows:
            self.assertEqual(row['listing_id'],'123')
            self.assertTrue(row['text'].startswith('# Villa example'))
            self.assertIn('SAR 120,000/year',row['text'])
            self.assertIn('Riyadh',row['text'])
            self.assertLess(row['text'].index('# Villa example'),row['text'].index('## Description'))

    def test_faq_pairs_stay_atomic(self):
        pairs=[f'## Question {i}?\n\n'+('answer '+str(i)+' ')*20 for i in range(4)]
        doc=fixture('# Example\n\n'+'\n\n'.join(pairs),'informational_faq')
        rows=chunk_document(doc,self.tokenizer,replace(self.config,target_tokens=100,max_tokens=150,overlap_tokens=10))
        for pair in pairs:self.assertTrue(any(pair.strip() in row['text'] for row in rows))
        # Tail rebalancing must not split an otherwise valid FAQ pair.
        longer=[f'## Question {i}?\n\n'+('answer '+str(i)+' ')*34 for i in range(7)]
        larger=chunk_document(fixture('# Example\n\n'+'\n\n'.join(longer),'informational_faq'),self.tokenizer,self.config)
        for pair in longer:self.assertTrue(any(pair.strip() in row['text'] for row in larger))
        impossible=fixture('# Example\n\n## One question?\n\n'+('longanswer '*700),'informational_faq')
        with self.assertRaisesRegex(ValueError,'FAQ pair'):chunk_document(impossible,self.tokenizer,self.config)

    def test_rebalance_does_not_leave_a_form_only_tiny_chunk(self):
        doc=fixture('# Example\n\n'+('Useful property detail. '*180)+'\n\n## ENQUIRE NOW\n\nFull Name\nPhone\nEmail')
        rows=chunk_document(doc,self.tokenizer,self.config)
        ending=next(row for row in rows if '## ENQUIRE NOW' in row['text'])
        self.assertIn('Useful property detail.',ending['text'])
        self.assertGreaterEqual(ending['token_count'],120)

    def test_complete_loader_counts_and_no_jsonl_documents(self):
        documents=load_documents()
        self.assertEqual(len(documents),685)
        self.assertEqual(sum(d.metadata['source']=='darglobal' for d in documents),419)
        self.assertEqual(len({d.metadata['listing_id'] for d in documents if d.metadata['content_type'].startswith('property_')}),261)
        self.assertTrue(all(d.metadata['source_path'].endswith('.md') for d in documents))
        self.assertTrue(all(not d.body.startswith('---\n') for d in documents))

    def test_saved_artifacts_full_coverage_and_reproducibility(self):
        chunks,documents,summary=prepare()
        path=REPO_ROOT/'artifacts/chunks/chunks.jsonl'
        self.assertEqual(path.read_text(encoding='utf-8'),jsonl_text(chunks))
        self.assertEqual(list(iter_chunks(path)),chunks)
        self.assertEqual(summary['chunks_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(summary['documents_loaded'],685)
        self.assertTrue(summary['source_nonwhitespace_coverage_verified'])
        self.assertTrue(summary['repeated_run_identical'])
        self.assertEqual(summary['unique_property_listing_ids'],261)
        self.assertEqual(sum(summary['missing_metadata_counts'].values()),0)
        self.assertLessEqual(summary['token_counts']['maximum'],500)


if __name__=='__main__':
    unittest.main()
