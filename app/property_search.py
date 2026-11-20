"""Exact search over historical JSONL; missing values are never mismatches."""
from dataclasses import dataclass, field
import json
import re


def normalize(text):
    return str(text).lower().translate(str.maketrans('٠١٢٣٤٥٦٧٨٩أإآى', '0123456789اااي')).replace('٬', ',')


@dataclass
class Interpretation:
    route: str
    filters: dict = field(default_factory=dict)
    clarification: str = ''


ALIASES = {
    'purpose': {'rent': ['rent', 'rental', 'للإيجار', 'للايجار', 'ايجار'], 'sale': ['sale', 'للبيع', 'شراء']},
    'city': {'Riyadh': ['riyadh', 'الرياض', 'بالرياض'], 'Jeddah': ['jeddah', 'جدة'],
             'Makkah Al Mukarramah': ['makkah', 'مكة'], 'Madinah': ['madinah', 'المدينة'],
             'Khobar': ['khobar', 'الخبر'], 'Aldammam': ['dammam', 'الدمام']},
    'district': {'An-Narjis': ['an-narjis', 'narjis', 'النرجس']},
    'property_type': {'villa': ['villa', 'villas', 'فيلا', 'فلل'], 'apartment': ['apartment', 'apartments', 'شقة', 'شقق'],
                      'land': ['land', 'ارض'], 'building': ['building', 'عمارة'], 'floor': ['floor', 'دور'],
                      'room': ['room', 'غرفة'], 'rest_house': ['rest house', 'استراحة'],
                      'chalet': ['chalet', 'شاليه'], 'duplex': ['duplex', 'دوبلكس']}}


def contains(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(phrase)) + r'(?!\w)', text))


def listing_identifiers(text):
    """Return contextual numeric IDs with spans in normalized query text.

    Identity comes from listing context, not the digit count observed in this
    sample. A property/listing noun must introduce the number; quantities,
    phone numbers and bare year-like references are excluded.
    """
    noun = r'(?:listing|property|villa|apartment|عقار|العقار|اعلان|الاعلان|فيلا|شقة)'
    brand = r'(?:wasalt|وصلت)'
    marker = r'(?:id|number|no\.?|reference|رقم|برقم|معرف)'
    separators = r'[\s:#：-]*'
    pattern = (r'(?<!\w)' + noun + r'(?!\w)'
               + r'(?:\s+' + brand + r')?'
               + r'(?:\s+(?:for rent|for sale|للايجار|للبيع))?'
               + r'(?:\s+(?:with|the))?'
               + separators + r'(?:(?P<marker>' + marker + r')' + separators + r')?'
               + r'(?P<id>[0-9]+)(?!\w|[.,]\d)')
    identifiers = []
    for match in re.finditer(pattern, text):
        start, end = match.span('id')
        if not match['marker'] and len(match['id']) == 4 and 1900 <= int(match['id']) <= 2100:
            continue
        # Reject quantities and formatted/extended contact numbers, even when
        # immediately preceded by a property noun.
        suffix = text[end:]
        if re.match(r'\s*(?:[/.,-]\s*\d|\d|/?\s*(?:sar|ريال|sqm|sq\.?\s*m|m2|m²|square|متر|years?|yearly|annual|months?|monthly|days?|daily|سنة|شهر|phone|هاتف|جوال)(?!\w))', suffix):
            continue
        if re.search(r'(?:phone|telephone|هاتف|جوال)\s+(?:\w+\s+){0,2}$', text[:match.start()]):
            continue
        identifiers.append((match['id'], (start, end)))
    return identifiers


def interpret(question, records=(), chunks_path=None):
    """No LLM routing calls. Unsupported/ambiguous constraints request clarification."""
    q = normalize(question)
    dar = bool(re.search(r'dar\s*global|دار\s*جلوبال', q))
    wasalt = bool(re.search(r'wasalt|وصلت', q))
    listing_ids = listing_identifiers(q)
    if len({identifier for identifier, _ in listing_ids}) > 1:
        return Interpretation('properties', clarification='يرجى تحديد رقم عقار واحد في كل طلب.' if re.search('[\u0600-\u06ff]', q) else 'Please request one property listing ID at a time.')
    listing = listing_ids[0][0] if listing_ids else None
    procedure = bool(re.search(r'\blist my\b|\blist a property\b|\blisting procedure\b|\bhow\b.*(?:\blist\b|\bwasalt\b)|\bwasalt\b.*(?:\bservices\b|\bprocedure\b)|كيف.*(اعرض|اضيف|ادرج)|\bfaq\b|خدمات', q))
    property_intent = bool(listing) or (bool(re.search(r'for rent|for sale|للبيع|للايجار|ايجار|rentals?|villas?|apartments?|فلل|فيلا|شقق|شقة', q)) and not procedure)
    ambiguous = False
    if not dar and not listing:
        from .development_evidence import development_index
        match = development_index(chunks_path).resolve(question)
        ambiguous = bool(match['ambiguous'])
        if match['resolved']:
            dar = True
            if not wasalt:
                property_intent = False
    if dar and not wasalt and not listing:
        property_intent = False  # An explicit company scope outranks a generic property noun.
    route = 'both' if dar and wasalt else 'properties' if property_intent else 'darglobal' if dar else 'wasalt' if wasalt or procedure else 'clarify' if ambiguous or q.strip(' .!?') in ('hello', 'hi', 'مرحبا') else 'general'
    if property_intent and dar and wasalt:
        route = 'both_properties'
    if route == 'clarify':
        return Interpretation(route, clarification='هل تقصد دار جلوبال أم وصلت؟ يرجى تحديد الموضوع.' if re.search('[\u0600-\u06ff]', q) else 'Please specify DarGlobal, Wasalt, or a property search with its location and purpose.')
    filters = {}
    problems = []
    numeric_spans = []
    if property_intent:
        if listing:
            filters['listing_id'] = listing
            numeric_spans.extend(span for _, span in listing_ids)
        for key, groups in ALIASES.items():
            groups = {value: list(words) for value, words in groups.items()}
            if key in ('city', 'district', 'property_type'):
                for row in records:
                    if row.get(key):
                        groups.setdefault(row[key], []).append(row[key])
            found = [value for value, words in groups.items() if any(contains(q, word) for word in words)]
            if len(found) > 1:
                problems.append(f'Multiple {key} values; choose one.')
            elif found:
                filters[key] = found[0]
                for word in groups[found[0]]:
                    numeric_spans.extend(m.span() for m in re.finditer(r'(?<!\w)' + re.escape(normalize(word)) + r'(?!\w)', q))
        # Amounts must have an explicit comparison. Bare budgets request clarification.
        price = re.search(r'(under|below|less than|up to|at most|maximum|max|اقل من|تحت|حتى|بحد اقصى)\s*(?:sar\s*)?([\d,]+(?:\.\d+)?)\s*(k|thousand|الف)?', q)
        if price:
            numeric_spans.append(price.span())
            value = float(price[2].replace(',', '')) * (1000 if price[3] else 1)
            filters['max_price'] = value
            filters['price_exclusive'] = price[1] in ('under', 'below', 'less than', 'اقل من', 'تحت')
        minimum_price = re.search(r'(?:price at least|minimum price|min price)\s*(?:sar\s*)?([\d,]+)\s*(k|thousand)?', q)
        if minimum_price:
            numeric_spans.append(minimum_price.span())
            filters['min_price'] = float(minimum_price[1].replace(',', '')) * (1000 if minimum_price[2] else 1)
        if re.search(r'/year|per year|yearly|annual|سنو|سنة', q):
            filters['price_period'] = 'year'
        elif re.search(r'/month|monthly|per month|شهر', q):
            filters['price_period'] = 'month'
        elif re.search(r'/day|daily|per day|يومي', q):
            filters['price_period'] = 'day'
        if ('max_price' in filters or 'min_price' in filters) and filters.get('purpose') == 'rent' and 'price_period' not in filters:
            problems.append('Specify the rental budget period (year, month or day).')
        if ('max_price' in filters or 'min_price' in filters) and 'purpose' not in filters and 'price_period' not in filters and not listing:
            problems.append('Specify sale or rent, and the budget period for rent.')
        place = re.search(r'\bin\s+([a-z][a-z -]*?)(?=\s+(?:under|below|with|at least|for|up to)|[.,?!]|$)', q)
        if place and not any(key in filters for key in ('city', 'district')):
            problems.append('Location not recognized; choose a city or district from the exact-search form.')
        for field, unit in [('bedrooms', r'bedrooms?|beds|غرف نوم'), ('bathrooms', r'bathrooms?|دورات مياه'), ('area_sqm', r'sqm|m2|m²|square met(?:er|re)s?|متر(?: مربع)?')]:
            match = re.search(r'(at least|min(?:imum)?|exactly|بحد ادنى|لا تقل عن)?\s*(\d+(?:\.\d+)?)\s*(' + unit + r')(?!\w)', q)
            if match:
                numeric_spans.append(match.span())
                filters[('min_' if match[1] and match[1] != 'exactly' else 'exact_') + field] = float(match[2])
        # A small interpreter must expose what it cannot safely understand.
        if re.search(r'between|\bor\b|\bnot\b|except|furnished|pool|garage|between|مفروش|مسبح|بين|بدون', q):
            problems.append('Use the explicit property filters for supported attributes; this additional condition cannot be verified automatically.')
        if any(not any(start <= m.start() and m.end() <= end for start, end in numeric_spans)
               for m in re.finditer(r'\d+(?:[,.]\d+)*', q)):
            problems.append('Please express numeric constraints as “under SAR …/year”, “at least … bedrooms”, or “… sqm”.')
        if not filters:
            problems.append('Specify a location, listing ID, purpose or property type.')
    return Interpretation(route, filters, ' '.join(problems))


def load_properties(path):
    with open(path, encoding='utf-8') as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    if len({r['listing_id'] for r in records}) != len(records):
        raise ValueError('Duplicate listing IDs')
    return records


def classify(record, filters):
    unknown, mismatched = [], []
    for key, expected in filters.items():
        if key == 'price_exclusive':
            continue
        field = 'price_sar' if key in ('max_price', 'min_price') else re.sub(r'^(min_|exact_)', '', key)
        actual = record.get(field)
        if actual is None:
            unknown.append(field)
            continue
        if key == 'max_price':
            ok = actual < expected if filters.get('price_exclusive') else actual <= expected
        elif key.startswith('min_'):
            ok = actual >= expected
        else:
            ok = normalize(actual) == normalize(expected) if isinstance(expected, str) else actual == expected
        if not ok:
            mismatched.append(field)
    return {'status': 'mismatch' if mismatched else 'unknown' if unknown else 'exact', 'unknown_fields': unknown, 'mismatched_fields': mismatched}


CARD_FIELDS = ('listing_id', 'title', 'purpose', 'property_type', 'city', 'district', 'price_sar',
               'price_period', 'area_sqm', 'bedrooms', 'bathrooms', 'source_url', 'scraped_at', 'quality_flags')


def search_properties(records, filters, limit=10):
    matches, unknown = [], []
    lookup = None
    if 'listing_id' in filters:
        record = next((row for row in records if row['listing_id'] == filters['listing_id']), None)
        lookup = {'listing_id': filters['listing_id'], 'found': record is not None}
        if record is not None:
            lookup.update(classify(record, filters))
    for record in records:
        result = classify(record, filters)
        if result['status'] == 'exact':
            matches.append({key: record.get(key) for key in CARD_FIELDS})
        elif result['status'] == 'unknown':
            unknown.append({'listing_id': record['listing_id'], 'unknown_fields': result['unknown_fields']})
    matches.sort(key=lambda r: (r['price_sar'] is None, r['price_sar'] or 0, r['listing_id']))
    result = {'matches': matches[:limit], 'total_matches': len(matches), 'unknown_count': len(unknown), 'unknown': unknown[:limit], 'filters': filters}
    if lookup is not None:
        result['listing_lookup'] = lookup
    return result


def conversation_plan(question, history, records=(), chunks_path=None):
    """Resolve only marked elliptical turns, using at most the last four turns.

    State belongs to the caller's history, never the shared cached Chatbot.
    The existing interpreter still validates every new structured constraint.
    """
    plan = interpret(question, records, chunks_path)
    q = normalize(question)
    from .development_evidence import development_index
    catalogue = development_index(chunks_path)
    named = catalogue.resolve(question)
    explicit = (re.search(r'dar\s*global|دار\s*جلوبال|wasalt|وصلت|for rent|for sale|للايجار|للبيع', q)
                or listing_identifiers(q) or named['resolved'] or named['ambiguous'])
    elliptical = re.search(
        r'\b(tell me more|what about|only those|only these|how much|where is it|where are they|'
        r'what are the (?:prices|main features)|what amenities|explain that|explain it)\b|'
        r'\b(?:it|they|their|those|these)\b|المرافق|ماذا عن|فقط|اقل من|اشرح ذلك|اين يقع|كم سعر', q)
    if explicit or not elliptical:
        return plan, question
    recent = list(history)[-4:]
    prior = next((turn for turn in reversed(recent) if turn.get('role') == 'user'), None)
    last = recent[-1].get('result', {}) if recent and recent[-1].get('role') == 'assistant' else {}
    clarify = Interpretation('clarify', clarification=(
        'أي مشروع أو مجموعة عقارات تقصد؟' if re.search('[\u0600-\u06ff]', q)
        else 'Which development or set of properties do you mean?'))
    if not prior:
        return clarify, question
    previous = str(last.get('context_question') or prior.get('content', ''))[:1500]
    old = interpret(previous, records, chunks_path)
    route = last.get('route', old.route)
    if route == 'properties':
        inherited = dict(last.get('filters', old.filters))
        # Seed only categorical context and a budget period, not old numeric
        # constraints. New constraints override old values after validation.
        seed = str(inherited.get('property_type', 'property'))
        if inherited.get('purpose'):
            seed += ' for ' + inherited['purpose']
        if inherited.get('price_period') and not re.search(r'year|month|day|annual|سنو|سنة|شهر|يومي', q):
            seed += ' per ' + inherited['price_period']
        delta = interpret(seed + ' ' + question, records, chunks_path)
        if not inherited or delta.route != 'properties':
            return clarify, question
        delta.filters = {**inherited, **delta.filters}
        return delta, question
    if route not in ('darglobal', 'wasalt'):
        return clarify, question
    subject = 'Wasalt' if route == 'wasalt' else 'DarGlobal'
    if route == 'darglobal':
        entity = catalogue.resolve(previous)
        if entity['ambiguous'] or len(entity['urls']) > 1:
            return clarify, question
        if entity['resolved']:
            subject += ' project ' + max(entity['aliases'], key=len)
    effective = subject + ': ' + question
    return Interpretation(route), effective
