"""Bounded chatbot runtime with optional, strictly gated free-model fallback."""
from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from threading import Lock
import time
from urllib.parse import urlsplit

from .config import IndexConfig, REPO_ROOT
from .chunking import OfflineTokenizer
from .embeddings import EmbeddingClient
from .evaluate_openrouter import MODELS, OpenRouterAPI
from .answer_prompt import SYSTEM_PROMPT
from .index_embeddings import batches, load_chunks, read_manifest
from .property_search import interpret, load_properties, normalize, search_properties
from .vector_store import ChromaStore, identity
from .openrouter_diagnostics import fallback_eligible
from .presentation import property_summary
from .development_evidence import (DevelopmentIndex, canonical, cosine_distance, development_index,
                                    lexical_candidates, portfolio_question, prose, relevance, broad_portfolio, inventory_rows)

PRIMARY = MODELS[0]
FALLBACK = MODELS[1]
SNAPSHOT = 'Historical dataset snapshots collected on 18 November 2026. Prices and availability are not live or verified current.'
SNAPSHOT_AR = 'هذه سجلات تاريخية جُمعت في 18 نوفمبر 2026؛ الأسعار والتوفر الحالي غير متحقق منهما.'
INSUFFICIENT = 'The collected evidence is insufficient to answer this question.'
INSUFFICIENT_AR = 'الأدلة المجمعة غير كافية للإجابة عن هذا السؤال.'


def runtime_config():
    config = IndexConfig.from_env()
    return replace(config, chunks_path=Path(os.environ.get('CHUNKS_PATH', str(config.chunks_path))),
                   corpus=replace(config.corpus, tokenizer_cache=Path(os.environ.get('TOKENIZER_CACHE', str(config.corpus.tokenizer_cache)))))


def arabic(text):
    return bool(re.search(r'[\u0600-\u06ff]', text))


def trusted_url(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.hostname in ('darglobal.co.uk', 'www.darglobal.co.uk', 'wasalt.sa', 'www.wasalt.sa') and not parsed.username


def safe_answer(text, sources, property_context=False):
    """Reject unknown citations, all model URLs/HTML, and current availability claims."""
    mapping = {s['source_id']: s for s in sources}
    refs = re.findall(r'\[([^\]\n]+)\]', text)
    cited = set(ref for ref in refs if re.fullmatch(r'S\d+', ref))
    invalid = [ref for ref in refs if ref.startswith('S') and ref not in mapping]
    if invalid or re.search(r'https?://|www\.|\]\s*\(|<[^>]+>', text, re.I):
        return None, [], 'Untrusted citation or link returned.'
    if property_context and re.search(r'currently available|available now|available today|still available|is available|are available|available (?:for rent|for sale|to rent|to buy)|متاح(?:ة)? (?:حاليا|الآن|الان|للايجار|للبيع)|متوفر(?:ة)? (?:حاليا|الآن|الان)', normalize(text)):
        return None, [], 'Unsupported current availability claim returned.'
    if not cited:
        return None, [], 'No supporting citations returned.'
    if any(not trusted_url(mapping[ref]['source_url']) for ref in cited):
        return None, [], 'Invalid source URL in evidence.'
    used = [s for s in sources if s['source_id'] in cited]
    def links(match):
        ids = dict.fromkeys(re.findall(r'S\d+', match[0]))
        prefix = ' ' if match.start() and not text[match.start() - 1].isspace() else ''
        return prefix + ' · '.join(f"[Source {sid}]({mapping[sid]['source_url']})" for sid in ids)
    text = re.sub(r'\[S\d+\](?:[ \t]*\[S\d+\])*', links, text)
    return text, used, ''


def select_evidence(candidates, question, limit=6, catalogue=None):
    catalogue = catalogue or development_index()
    named = catalogue.resolve(question)
    portfolio = portfolio_question(question)
    ranked = []
    broad = broad_portfolio(question, catalogue)
    inventory = inventory_rows(catalogue, {r['source_url'] for r, _ in candidates})[:limit] if broad else []
    unique = {}
    for row, distance in candidates:
        if distance is None:
            continue  # Inventory aid has provenance, not an invented semantic distance.
        if urlsplit(row['source_url']).path.rstrip('/') in ('/press', '/en/press') or distance > .80:
            continue
        if row['chunk_id'] not in unique or distance < unique[row['chunk_id']][1]:
            unique[row['chunk_id']] = (row, distance)
    for row, distance in unique.values():
        if urlsplit(row['source_url']).path.rstrip('/') in ('/press', '/en/press'):
            continue
        if distance > .80:
            continue
        if row['source'] == 'darglobal' and named['resolved']:
            words = set(canonical(prose(row['text'])).split())
            if not any(set(alias.split()) <= words for alias in named['aliases']):
                continue
        overlap, names = relevance(row, question, catalogue)
        score = distance - .10 * overlap
        if row['source_url'] in catalogue.by_url and overlap:
            score -= .03  # Prefer real project prose, not every category label.
        if named['resolved'] and row['source_url'] in named['urls']:
            score -= .05
        ranked.append((-min(names, 3) if portfolio else 0, score, row))
    if portfolio and any(item[0] < 0 for item in ranked):
        ranked = [item for item in ranked if item[0] < 0]
    ranked.sort(key=lambda item: (item[0], item[1], item[2]['chunk_id']))
    selected = list(inventory)
    if len(selected) == limit:
        return selected
    counts = {r['source_url']: 1 for r in selected}
    seen = {r['chunk_id'] for r in selected}
    # Cover distinct URLs before spending context on a second chunk from one URL.
    for maximum in (1, 2):
        for _, _, row in ranked:
            key = row['source_url']
            if row['chunk_id'] in seen or counts.get(key, 0) >= maximum:
                continue
            seen.add(row['chunk_id']); counts[key] = counts.get(key, 0) + 1
            selected.append(row)
            if len(selected) == limit:
                return selected
    return selected


class Retrieval:
    def __init__(self, config=None):
        self.config = config or runtime_config()
        config = self.config
        if not config.storage_path.is_dir() or (config.storage_path / '.index.lock').exists() or config.pending_path.exists():
            raise ValueError('Prebuilt index is missing, locked or incomplete.')
        rows, checksum = load_chunks(config)
        build = identity(config, checksum)
        manifest = read_manifest(config, build)
        if not manifest or manifest['indexing_status'] != 'complete':
            raise ValueError('A validated complete prebuilt index is required.')
        self.rows = {r['chunk_id']: r for r in rows}
        self.developments = DevelopmentIndex(rows)
        # Chroma may write housekeeping files on open. Never open the protected original.
        self.temporary = tempfile.TemporaryDirectory(prefix='darglobal-chat-')
        runtime_path = Path(self.temporary.name) / 'index'
        shutil.copytree(config.storage_path, runtime_path)
        self.store = ChromaStore(replace(config, storage_path=runtime_path), build, create=False)
        if self.store.ids() != set(self.rows) or self.store.count() != len(rows):
            raise ValueError('Prebuilt index IDs/count differ from the corpus.')
        for batch in batches(rows, config):
            self.store.verify(batch)
        self.tokenizer = OfflineTokenizer(config.corpus)
        self.client = EmbeddingClient(replace(config, max_retries=0))

    def retrieve(self, question, route, diagnostics=None):
        vector = self.client.embed_query(question, self.tokenizer)
        if route in ('both', 'both_properties', 'general'):
            scopes = ['darglobal', 'wasalt']
        else:
            scopes = [route]
        selected = []
        catalogue = getattr(self, 'developments', None) or DevelopmentIndex(self.rows.values())
        broad = route == 'darglobal' and broad_portfolio(question, catalogue)
        for scope in scopes:
            where = {'source': 'darglobal'} if scope == 'darglobal' else {'content_type': {'$in': [
                'informational_faq', 'informational_corporate', 'informational_services', 'informational_auctions', 'informational_project']}}
            queries = [where]
            if scope == 'darglobal':
                queries.append({'$and': [{'source': 'darglobal'}, {'content_type': 'developments'}]})
            candidates = []
            for clause in queries:
                result = self.store.collection.query(query_embeddings=[vector], n_results=30 if scope == 'darglobal' else 9,
                    where=clause, include=['distances'])
                candidates.extend((self.rows[key], distance) for key, distance in zip(result['ids'][0], result['distances'][0]))
            raw = list(candidates)
            if scope == 'darglobal':
                seen = {row['chunk_id'] for row, _ in candidates}
                supplement = [row for row in lexical_candidates(self.rows.values(), question, catalogue) if row['chunk_id'] not in seen]
                if supplement:
                    # Read existing vectors only. No document or extra query embeddings.
                    stored = self.store.collection.get(ids=[row['chunk_id'] for row in supplement], include=['embeddings'])
                    by_id = {key: embedding for key, embedding in zip(stored['ids'], stored['embeddings'])}
                    candidates.extend((row, cosine_distance(vector, by_id[row['chunk_id']])) for row in supplement)
            if broad:
                candidates.extend((row, None) for row in inventory_rows(catalogue))
            chosen = select_evidence(candidates, question, 10 if broad else 4 if len(scopes) > 1 else 6, catalogue)
            if diagnostics is not None:
                def describe(items):
                    return [{'chunk_id': row['chunk_id'], 'source_url': row['source_url'], 'content_type': row['content_type'],
                             'cosine_distance': float(distance) if distance is not None else None, 'prose_overlap': relevance(row, question, catalogue)[0],
                             'named_project_coverage': relevance(row, question, catalogue)[1]} for row, distance in items]
                diagnostics[scope] = {'raw_semantic_candidates': describe(raw), 'candidates_after_lexical_recovery': describe(candidates),
                                      'final_chunk_ids': [row['chunk_id'] for row in chosen]}
            selected.extend(chosen)
        return selected


class GenerationError(RuntimeError):
    """Fixed user-facing message plus safe per-request diagnostics for internal use."""
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


class Generator:
    def __init__(self, api=None):
        model = os.environ.get('OPENROUTER_MODEL', PRIMARY)
        if model != PRIMARY:
            raise ValueError('OPENROUTER_MODEL must be the approved primary ERNIE free endpoint.')
        setting = os.environ.get('OPENROUTER_ENABLE_FALLBACK', 'false').strip().lower()
        if setting not in ('true', 'false'):
            raise ValueError('OPENROUTER_ENABLE_FALLBACK must be true or false.')
        self.fallback_enabled = setting == 'true'
        self.api = api

    def generate(self, messages):
        # A fresh adapter per turn avoids the evaluator's lifetime ten-call limit.
        api = self.api or OpenRouterAPI(os.environ.get('OPENROUTER_API_KEY', ''), attempt_limit=2 if self.fallback_enabled else 1)
        attempts = []
        requested = PRIMARY
        try:
            result = api.generate(requested, messages, reasoning_enabled=True, max_tokens=4000)
            attempts.append({'model_requested': requested, **(result.get('diagnostics') or {})})
            if fallback_eligible(result, self.fallback_enabled):
                # There is exactly one fallback call, with the same bounded evidence.
                requested = FALLBACK
                result = api.generate(requested, messages, reasoning_enabled=True, max_tokens=4000)
                attempts.append({'model_requested': requested, **(result.get('diagnostics') or {})})
        finally:
            if self.api is None:
                api.session.close()
        cost = (result.get('usage') or {}).get('cost')
        if result.get('status') != 'success' or result.get('model_returned') != requested or result.get('truncated') or (cost is not None and Decimal(str(cost)) != 0):
            code = result.get('http_status')
            label = 'Rate limit reached' if code == 429 else 'Answer service unavailable or response rejected'
            detail = ' The approved fallback was attempted once; no further request was made.' if len(attempts) == 2 else ' No automatic retry was made.'
            raise GenerationError(label + '; please try again later.' + detail, attempts)
        result['attempt_diagnostics'] = attempts
        return result


class Chatbot:
    def __init__(self, retrieval=None, generator=None, records=None):
        self.config = runtime_config()
        self.records = records if records is not None else load_properties(Path(os.environ.get('WASALT_LISTINGS_PATH', str(REPO_ROOT / 'data/wasalt/listings.jsonl'))))
        self.retrieval = retrieval
        self._retrieval_lock = Lock()
        self.generator = generator if generator is not None else Generator()

    def _get_retrieval(self):
        # Streamlit shares this cached runtime across sessions. Load only once,
        # and only for semantic queries, never for exact JSONL misses.
        if self.retrieval is None:
            with self._retrieval_lock:
                if self.retrieval is None:
                    self.retrieval = Retrieval(self.config)
        return self.retrieval

    def answer(self, question, history=(), explicit_filters=None, on_status=None, explain_properties=False):
        started = time.perf_counter()
        if not question.strip() or len(question) > 1500:
            raise ValueError('Please enter a question of 1–1500 characters.')
        plan = interpret(question, self.records, chunks_path=self.config.chunks_path)
        if explicit_filters is not None:
            plan.filters = explicit_filters
            plan.clarification = ''
            plan.route = 'properties'
        result = {'route': plan.route, 'filters': plan.filters, 'answer': '', 'sources': [], 'properties': None, 'error': '', 'generation': None}
        if plan.clarification:
            result['answer'] = plan.clarification
            return result
        property_context = plan.route in ('properties', 'both_properties')
        explanation = explain_properties or (explicit_filters is None and bool(re.search(
            r'\b(explain|why|compare|amenities|description)\b|اشرح|لماذا|قارن|وصف|مميزات', question, re.I)))
        if property_context:
            if on_status:
                on_status('Checking Wasalt listings...')
            result['properties'] = search_properties(self.records, plan.filters)
            result['properties']['evidence_count'] = 0
            result['disclaimer'] = SNAPSHOT_AR if arabic(question) else SNAPSHOT
            lookup = result['properties'].get('listing_lookup')
            if (lookup and not lookup['found']) or (plan.route == 'properties' and not explanation):
                # An exact dataset miss is terminal, including mixed-source plans.
                # No query embedding, informational RAG, or generation can fill it.
                result['answer'] = property_summary(result['properties'], arabic(question))
                result['latency_seconds'] = round(time.perf_counter() - started, 3)
                return result
        rows = []
        if plan.route != 'properties':
            try:
                if on_status:
                    on_status('Searching the knowledge base...')
                rows = self._get_retrieval().retrieve(question, plan.route)
            except Exception:
                result['answer'] = 'تعذر البحث في المصادر الآن.' if arabic(question) else 'The evidence search is unavailable. Please try again later.'
                result['error'] = 'Retrieval failed; no ungrounded answer was generated.'
                if property_context:
                    result['answer'] = property_summary(result['properties'], arabic(question))
                result['latency_seconds'] = round(time.perf_counter() - started, 3)
                return result
        evidence = [{**{k: row[k] for k in ('title', 'source_url', 'source', 'content_type', 'text')},
                     'chunk_id': row['chunk_id']} for row in rows]
        if property_context:
            result['properties']['evidence_count'] = min(5, len(result['properties']['matches']))
            evidence += [{'title': r['title'], 'source_url': r['source_url'], 'source': 'wasalt',
                          'content_type': 'verified_property', 'text': json.dumps(r, ensure_ascii=False)} for r in result['properties']['matches'][:5]]
        for index, source in enumerate(evidence, 1):
            source['source_id'] = f'S{index}'
        if not evidence:
            result['answer'] = (INSUFFICIENT_AR if arabic(question) else INSUFFICIENT) if not property_context else ('لا توجد نتائج مؤكدة تطابق الشروط في البيانات التاريخية.' if arabic(question) else 'No verified matches for these constraints in the historical dataset.')
        else:
            system = SYSTEM_PROMPT
            messages = [{'role': 'system', 'content': system}]
            for turn in list(history)[-4:]:
                if turn.get('role') in ('user', 'assistant'):
                    messages.append({'role': turn['role'], 'content': str(turn.get('content', ''))[:1000]})
            counts = ({'total_verified_matches': result['properties']['total_matches'],
                       'displayed_listing_cards': len(result['properties']['matches']),
                       'property_evidence_records': result['properties']['evidence_count'],
                       'unknown_required_attributes': result['properties']['unknown_count']} if property_context else None)
            messages.append({'role': 'user', 'content': 'QUESTION\n' + question + '\nAPPLIED FILTERS\n' + json.dumps(plan.filters)
                             + ('\nVERIFIED SEARCH COUNTS (evidence is a subset, never the full match count)\n' + json.dumps(counts) if counts else '')
                             + '\nEVIDENCE\n' + json.dumps(evidence, ensure_ascii=False)})
            try:
                if on_status:
                    on_status('Generating answer...')
                generated = self.generator.generate(messages)
                text, used, error = safe_answer(generated['response_text'], evidence, property_context or plan.route in ('wasalt', 'both'))
                result['generation'] = {k: generated.get(k) for k in ('model_returned', 'usage', 'latency_seconds', 'request_parameters')}
                result['generation']['attempt_diagnostics'] = generated.get('attempt_diagnostics', [])
                result['answer'] = text or (INSUFFICIENT_AR if arabic(question) else INSUFFICIENT)
                result['sources'] = used
                result['error'] = error
            except (RuntimeError, ValueError) as error:
                result['answer'] = 'تعذر إنشاء الإجابة الآن. يرجى المحاولة لاحقاً.' if arabic(question) else 'An answer could not be generated. Please try again later.'
                if property_context and result['properties']['matches']:
                    result['answer'] = 'نتائج تاريخية مؤكدة تطابق الشروط موضحة أدناه.' if arabic(question) else 'Verified historical matches for your filters are shown below.'
                result['error'] = str(error)
                if isinstance(error, GenerationError):
                    result['generation'] = {'attempt_diagnostics': error.diagnostics}
        if property_context:
            # Property summaries are code-owned. Never display free-form model counts
            # (including spelled-out counts) or feed them back into chat history.
            result['answer'] = property_summary(result['properties'], arabic(question))
            result['sources'] = []  # Each deterministic card carries its own original URL.
        result['latency_seconds'] = round(time.perf_counter() - started, 3)
        return result
