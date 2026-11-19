"""20E: metadata entity routing and corpus-based retrieval without network calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.chatbot import Chatbot, Retrieval, safe_answer, select_evidence
from app.config import REPO_ROOT
from app.development_evidence import DevelopmentIndex, development_index, lexical_candidates, prose, relevance
from app.prepare_corpus import iter_chunks
from app.property_search import interpret, load_properties, search_properties


class DarGlobalRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = list(iter_chunks(REPO_ROOT / 'artifacts/chunks/chunks.jsonl'))
        cls.catalogue = DevelopmentIndex(cls.rows)
        cls.by_id = {row['chunk_id']: row for row in cls.rows}
        cls.records = load_properties(REPO_ROOT / 'data/wasalt/listings.jsonl')
        cls.blog = next(r for r in cls.rows if r['source_url'].endswith('/redefining-real-estate-development-for-the-discerning-buyer') and r['chunk_index'] == 1)
        cls.crypto = next(r for r in cls.rows if r['source_url'].endswith('/Invest-crypto') and r['chunk_index'] == 0)
        cls.marea = next(r for r in cls.rows if r['source_url'].endswith('/marea') and r['chunk_index'] == 2)
        cls.tierra = next(r for r in cls.rows if r['source_url'].endswith('/tierra-viva') and r['chunk_index'] == 2)
        cls.aida = next(r for r in cls.rows if r['source_url'].endswith('/invest-in-aida') and r['chunk_index'] == 0)
        cls.spain = 'What developments does DarGlobal have in Spain?'

    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('20E permits no live API requests'))
        self.network.start(); self.addCleanup(self.network.stop)

    def test_exact_aida_question_reaches_darglobal_and_grounded_prompt(self):
        question = 'What is the AIDA development in Oman, and what are its main features?'
        self.assertEqual(interpret(question, self.records).route, 'darglobal')
        retrieval = Mock(); retrieval.retrieve.return_value = [self.aida]
        generator = Mock(); generator.generate.return_value = {'response_text': 'AIDA is in Muscat, Oman, with a golf club and wellness centres. [S1]'}
        result = Chatbot(retrieval, generator, self.records).answer(question)
        retrieval.retrieve.assert_called_once_with(question, 'darglobal')
        self.assertIn(self.aida['source_url'], result['answer'])
        evidence = json.loads(generator.generate.call_args.args[0][-1]['content'].split('\nEVIDENCE\n')[1])
        self.assertEqual(evidence[0]['chunk_id'], self.aida['chunk_id'])
        self.assertIn('Trump International Golf Club', evidence[0]['text'])

    def test_other_known_names_are_resolved_without_a_company(self):
        for question in ('Tell me about Tierra Viva', 'Tell me about Urban Oasis',
                         'What amenities does Les Vagues offer?', 'What is Marea, Interiors by Missoni?',
                         'What is the Amour Sans Detour 2 project?', 'What amenities does Trump Dubai offer?'):
            with self.subTest(question=question):
                self.assertEqual(interpret(question, self.records).route, 'darglobal')

    def test_ambiguous_names_do_not_force_development_routing(self):
        for question in ('What is AIDA?', 'Who composed AIDA?', 'What is Neptune?', 'What is Marea?'):
            with self.subTest(question=question):
                self.assertEqual(interpret(question, self.records).route, 'clarify')

    def test_new_entities_and_collisions_come_from_metadata(self):
        rows = [{'source': 'darglobal', 'content_type': 'developments', 'title': title,
                 'source_url': url, 'text': '# ' + title + '\n\n' + title + ' is a residential development.'}
                for title, url in [('Orion Terraces', 'https://darglobal.co.uk/orion-terraces'),
                                   ('Harbour', 'https://darglobal.co.uk/harbour-one'),
                                   ('Harbour', 'https://darglobal.co.uk/harbour-two')]]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'chunks.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            self.assertEqual(interpret('Tell me about Orion Terraces', chunks_path=path).route, 'darglobal')
            self.assertEqual(interpret('Describe the Harbour development', chunks_path=path).route, 'clarify')

    def test_saved_spain_passage_really_contains_both_projects_and_is_preserved(self):
        old = json.loads((REPO_ROOT / 'artifacts/checkpoint_19b/retrieval_results.json').read_text())
        query = next(q for q in old['queries'] if q['query_id'] == 'q02')
        candidates = [(self.by_id[row['chunk_id']], row['cosine_distance']) for row in query['results']]
        result = select_evidence(candidates, self.spain, catalogue=self.catalogue)
        self.assertIn(self.blog, result)
        self.assertIn('Tierra Viva', self.blog['text'])
        self.assertIn('Marea Interiors by Missoni', self.blog['text'])
        self.assertFalse(any(r['source_url'].rstrip('/') == 'https://darglobal.co.uk/press' for r in result))
        inputs = json.loads((REPO_ROOT / 'artifacts/checkpoint_19d/inputs.json').read_text())
        self.assertTrue(all('adjustment_responses/q02_' in r['source_path'] for r in inputs['reused_spain']))

    def test_tangential_category_boost_cannot_displace_substantive_portfolio_passage(self):
        # Controlled distances, not claims about the unavailable manual query vector.
        candidates = [(self.crypto, .35), (self.blog, .39229095), (self.marea, .55), (self.tierra, .50)]
        old_crypto_score = .35 - .025 - .15
        old_blog_score = .39229095 - .025
        self.assertLess(old_crypto_score, old_blog_score)
        result = select_evidence(candidates, self.spain, limit=3, catalogue=self.catalogue)
        self.assertEqual(result[0]['chunk_id'], self.blog['chunk_id'])
        self.assertEqual({r['source_url'] for r in result}, {self.blog['source_url'], self.marea['source_url'], self.tierra['source_url']})
        self.assertNotIn(self.crypto, result)

    def test_ranking_ignores_headings_and_concatenated_navigation(self):
        row = {**self.crypto, 'text': '# Spain Marea Tierra Viva\n\n[Marea](https://example.test/Spain)[Tierra Viva](https://example.test/Spain)'}
        self.assertEqual(relevance(row, self.spain, self.catalogue), (0, 0))
        self.assertNotIn('Spain', prose(row['text']))
        overlap, count = relevance(self.blog, self.spain, self.catalogue)
        self.assertEqual(overlap, 1)
        self.assertGreaterEqual(count, 2)

    def test_lexical_recovery_is_bounded_and_includes_useful_original_passage(self):
        result = lexical_candidates(self.rows, self.spain, self.catalogue)
        self.assertLessEqual(len(result), 12)
        self.assertIn(self.blog, result)
        self.assertIn(self.marea, result)
        self.assertNotIn(self.crypto, result)

    def test_missing_semantic_candidate_is_recovered_using_existing_vectors_only(self):
        retrieval = Retrieval.__new__(Retrieval)
        retrieval.rows = {r['chunk_id']: r for r in (self.blog, self.crypto, self.marea, self.tierra)}
        retrieval.developments = self.catalogue
        retrieval.client = Mock(); retrieval.tokenizer = Mock(); retrieval.store = Mock()
        vector = [1.0] + [0.0] * 1535  # Deterministic mocked query embedding.
        retrieval.client.embed_query.return_value = vector
        retrieval.store.collection.query.return_value = {'ids': [[self.crypto['chunk_id']]], 'distances': [[.3]]}
        def existing_vectors(ids, include):
            self.assertEqual(include, ['embeddings'])
            return {'ids': ids, 'embeddings': [vector for _ in ids]}
        retrieval.store.collection.get.side_effect = existing_vectors
        trace = {}
        result = retrieval.retrieve(self.spain, 'darglobal', diagnostics=trace)
        self.assertIn(self.blog, result)
        self.assertNotIn(self.crypto, result)
        retrieval.client.embed_query.assert_called_once_with(self.spain, retrieval.tokenizer)
        retrieval.store.collection.get.assert_called_once()
        self.assertEqual(len(retrieval.store.collection.query.call_args_list), 2)
        self.assertEqual(trace['darglobal']['final_chunk_ids'][0], self.blog['chunk_id'])
        self.assertFalse(any(call[0].endswith('upsert') for call in retrieval.store.mock_calls))

    def test_threshold_and_url_diversity_remain_bounded(self):
        too_far = select_evidence([(self.blog, .81)], self.spain, catalogue=self.catalogue)
        self.assertFalse(too_far)
        duplicated = {**self.tierra, 'chunk_id': 'second-test-chunk'}
        selected = select_evidence([(self.tierra, .2), (duplicated, .21), (self.blog, .4), (self.marea, .5)], self.spain, 3, self.catalogue)
        self.assertEqual(len({row['source_url'] for row in selected}), 3)

    def test_generic_press_hub_cannot_become_project_evidence(self):
        hub = {**self.blog, 'chunk_id': 'contaminated', 'source_url': 'https://darglobal.co.uk/press', 'content_type': 'press', 'title': 'AIDA Marea Tierra Viva'}
        self.assertFalse(select_evidence([(hub, .01)], self.spain, catalogue=self.catalogue))
        self.assertFalse(DevelopmentIndex([hub]).aliases)

    def test_cross_source_and_wasalt_routes_remain_correct(self):
        for question, route in [('Compare DarGlobal and Wasalt services', 'both'),
                                ('Compare AIDA development and Wasalt services', 'both'),
                                ('How can I list my property on Wasalt?', 'wasalt'),
                                ('Show listing 5891036', 'properties'), ('Show listing 99999999', 'properties')]:
            self.assertEqual(interpret(question, self.records).route, route)
        plan = interpret('Villas for rent in Riyadh under SAR 100000/year', self.records)
        self.assertEqual(plan.route, 'properties')
        self.assertEqual(search_properties(self.records, plan.filters)['total_matches'], 8)

    def test_cross_source_retrieval_still_collects_both_companies(self):
        faq = next(row for row in self.rows if row['content_type'] == 'informational_faq')
        retrieval = Retrieval.__new__(Retrieval)
        retrieval.rows = {r['chunk_id']: r for r in (self.aida, faq)}
        retrieval.developments = self.catalogue
        retrieval.client = Mock(); retrieval.tokenizer = Mock(); retrieval.store = Mock()
        retrieval.client.embed_query.return_value = [1.0] + [0.0] * 1535
        def query(**kwargs):
            row = faq if 'content_type' in kwargs['where'] else self.aida
            return {'ids': [[row['chunk_id']]], 'distances': [[.3]]}
        retrieval.store.collection.query.side_effect = query
        result = retrieval.retrieve('Compare AIDA development and Wasalt services', 'both')
        self.assertEqual({row['source'] for row in result}, {'darglobal', 'wasalt'})

    def test_final_llm_evidence_contains_both_projects_and_only_trusted_urls(self):
        chosen = select_evidence([(self.crypto, .35), (self.blog, .392), (self.marea, .55), (self.tierra, .50)], self.spain, catalogue=self.catalogue)
        retrieval = Mock(); retrieval.retrieve.return_value = chosen
        generator = Mock(); generator.generate.return_value = {'response_text': 'The supplied passage names Tierra Viva and Marea Interiors by Missoni. [S1]'}
        result = Chatbot(retrieval, generator, self.records).answer(self.spain)
        self.assertEqual(result['sources'][0]['source_url'], self.blog['source_url'])
        self.assertIn(self.blog['source_url'], result['answer'])
        evidence = json.loads(generator.generate.call_args.args[0][-1]['content'].split('\nEVIDENCE\n')[1])
        self.assertTrue(any('Tierra Viva' in r['text'] and 'Marea Interiors by Missoni' in r['text'] for r in evidence))
        self.assertFalse(any(r['source_url'] == self.crypto['source_url'] for r in evidence))
        self.assertIsNone(safe_answer('Invented [S99]', result['sources'])[0])
        self.assertIsNone(safe_answer('Invented https://not-a-source.test [S1]', result['sources'])[0])


if __name__ == '__main__':
    unittest.main()
