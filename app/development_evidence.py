"""Small metadata-derived development catalogue and prose-only retrieval signals."""
from collections import defaultdict
from functools import lru_cache
import math
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from .config import REPO_ROOT
from .prepare_corpus import iter_chunks


GENERIC = frozenset('the a an and of at in by for with from property properties luxury branded residential residences residence villas villa apartments apartment hotel international tower homes home buy invest development premium exclusive foreign url ultra'.split())
QUERY_STOP = GENERIC | frozenset('what which where when why how does do is are me tell about main its have has can their compare darglobal dar global wasalt project projects developments portfolio features feature please show some iconic notable different developed develop major market markets all explore'.split())


def canonical(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[^\W_]+', text, re.UNICODE))


def phrase(text, words):
    return bool(re.search(r'(?<!\w)' + re.escape(words) + r'(?!\w)', text))


def prose(text):
    """Ranking view only: omit repeated headings, image captions and link-only nav."""
    lines = []
    for line in text.split('\n'):
        if re.match(r'^\s*#{1,6}\s', line):
            continue
        if re.fullmatch(r'\s*(?:[*-]\s*)?(?:\[[^\]]*\]\([^)]*\)\s*)+', line):
            continue
        line = re.sub(r'!?\[Image[^\]]*\]\([^)]*\)', '', line, flags=re.I)
        line = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', line)
        line = re.sub(r'https?://\S+', '', line)
        lines.append(line)
    return '\n'.join(lines)


class DevelopmentIndex:
    def __init__(self, rows):
        documents = defaultdict(list)
        for row in rows:
            if row['source'] == 'darglobal' and row['content_type'] in ('developments', 'communities'):
                if urlsplit(row['source_url']).path.rstrip('/') not in ('/press', '/en/press'):
                    documents[row['source_url']].append(row)
        self.aliases = defaultdict(set)
        self.by_url = defaultdict(set)
        self.url_terms = {}
        self.inventory = {}
        markets = {canonical(urlsplit(r['source_url']).path.split('properties-in-')[1].split('/')[0])
                   for r in rows if 'properties-in-' in r['source_url']} if isinstance(rows, (list, tuple)) else set()
        for url, chunks in documents.items():
            title = chunks[0]['title']
            name = re.split(r'\||,|\s+by\s+|\s+-\s+DarGlobal', title, maxsplit=1, flags=re.I)[0]
            full_name = re.split(r'\||\s+-\s+DarGlobal', title, maxsplit=1, flags=re.I)[0]
            aliases = {canonical(name), canonical(full_name)}
            slug = canonical(unquote(urlsplit(url).path.rstrip('/').split('/')[-1]))
            if len(slug.split()) <= 2 and phrase(canonical(title), slug):
                aliases.add(slug)
            body = canonical('\n'.join(prose(row['text']) for row in chunks))
            for alias in aliases:
                words = alias.split()
                distinctive = [word for word in words if word not in GENERIC]
                if not words or len(words) > 6 or words[0] in {'buy', 'invest', 'luxury', 'premium', 'exclusive', 'foreign', 'development', 'url', 'ultra', 'live'} or not distinctive:
                    continue
                if not phrase(body, alias):
                    continue  # A heading alone does not establish an entity.
                for candidate in {alias, ' '.join(distinctive)}:
                    if len(candidate.replace(' ', '')) < 3:
                        continue
                    self.aliases[candidate].add(url)
                    self.by_url[url].add(candidate)
                    self.url_terms[url] = frozenset(body.split())
            overview = min(chunks, key=lambda r: r.get('chunk_index', 0))
            if url in self.by_url and re.search(r'property type|unit type', overview['text'], re.I):
                intro = canonical(overview['title'] + ' ' + prose(overview['text']).split('##')[0][:900])
                self.inventory[url] = {'title': overview['title'], 'source_url': url,
                    'chunk_ids': [r['chunk_id'] for r in chunks if 'chunk_id' in r],
                    'overview': overview, 'markets': sorted(m for m in markets if phrase(intro, m))}

    def resolve(self, question):
        q = canonical(question)
        context = bool(set(q.split()) & {'development', 'developments', 'project', 'projects', 'amenities', 'residences', 'community', 'darglobal'})
        matches = [alias for alias in self.aliases if phrase(q, alias)]
        # Prefer a complete longer name over its contained shorter alias.
        matches = [alias for alias in matches if not any(alias != other and phrase(other, alias) for other in matches)]
        resolved, ambiguous = [], []
        for alias in matches:
            distinct = [word for word in alias.split() if word not in GENERIC]
            if len(self.aliases[alias]) != 1 or (len(distinct) < 2 and not context):
                ambiguous.append(alias)
            else:
                resolved.append(alias)
        return {'resolved': bool(resolved) and not ambiguous, 'aliases': resolved,
                'ambiguous': ambiguous, 'urls': sorted({url for alias in resolved for url in self.aliases[alias]})}

    def names_in(self, text):
        text = canonical(text)
        urls = set()
        for alias, locations in self.aliases.items():
            if len(locations) == 1 and phrase(text, alias):
                urls.update(locations)
        return urls


@lru_cache(maxsize=4)
def _cached_index(path, modified, size):
    return DevelopmentIndex(list(iter_chunks(path)))


def development_index(path=None):
    path = Path(path or REPO_ROOT / 'artifacts/chunks/chunks.jsonl').resolve()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return DevelopmentIndex(())
    return _cached_index(str(path), stat.st_mtime_ns, stat.st_size)


def relevance(row, question, catalogue):
    """Query overlap and project coverage must occur in substantive sentences."""
    terms = set(canonical(question).split()) - QUERY_STOP
    body = prose(row['text'])
    best, names = 0.0, 0
    eligible = {url for url, words in catalogue.url_terms.items() if terms & words}
    for passage in re.split(r'\n\s*\n|(?<=[.!?])\s+', body):
        tokens = set(canonical(passage).split())
        overlap = len(terms & tokens) / max(1, len(terms))
        if overlap:
            best = max(best, overlap)
            names = max(names, len(catalogue.names_in(passage) & eligible))
    return best, names


def portfolio_question(question):
    words = set(canonical(question).split())
    return bool(words & {'projects', 'developments', 'portfolio'} or ('properties' in words and words & {'developed', 'develops', 'develop'}))


def broad_portfolio(question, catalogue):
    return portfolio_question(question) and not catalogue.resolve(question)['resolved'] and not (set(canonical(question).split()) - QUERY_STOP)


def inventory_rows(catalogue, available=None):
    """Round-robin recorded markets; no ranking of business importance."""
    groups = defaultdict(list)
    for url, entry in sorted(catalogue.inventory.items()):
        if available is None or url in available:
            groups[tuple(entry['markets']) or ('unspecified',)].append(entry['overview'])
    result = []
    while any(groups.values()):
        for key in sorted(groups):
            if groups[key]:
                result.append(groups[key].pop(0))
    return result


def lexical_candidates(rows, question, catalogue, limit=12):
    candidates = []
    for row in rows:
        if row['source'] != 'darglobal' or urlsplit(row['source_url']).path.rstrip('/') in ('/press', '/en/press'):
            continue
        overlap, names = relevance(row, question, catalogue)
        if overlap >= .5 and names:
            candidates.append((names if portfolio_question(question) else 0, overlap,
                               int(row['source_url'] in catalogue.by_url), row))
    candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]['chunk_id']))
    return [item[3] for item in candidates[:limit]]


def cosine_distance(left, right):
    if len(left) != len(right):
        raise ValueError('Existing vector dimensions differ from query')
    dot = math.fsum(float(a) * float(b) for a, b in zip(left, right))
    norm = math.sqrt(math.fsum(float(a)**2 for a in left) * math.fsum(float(b)**2 for b in right))
    if not norm or not math.isfinite(norm):
        raise ValueError('Invalid existing vector norm')
    return max(0.0, min(2.0, 1 - dot / norm))
