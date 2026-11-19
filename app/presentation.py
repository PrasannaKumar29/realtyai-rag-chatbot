"""Deterministic presentation of verified property records and exact filters."""
from datetime import datetime


def captured_date(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%d %b %Y')
    except (AttributeError, TypeError, ValueError):
        return 'Unknown'


def number(value):
    if value is None:
        return 'Unknown'
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f'{value:,}' if isinstance(value, (int, float)) else str(value)


def property_summary(properties, in_arabic=False):
    total = properties['total_matches']
    shown = len(properties['matches'])
    evidence = properties.get('evidence_count', 0)
    lookup = properties.get('listing_lookup')
    notice = ''
    if lookup and not lookup['found']:
        notice = (f"العقار رقم {lookup['listing_id']} غير موجود في بيانات وصلت المجمعة. ولا يحدد ذلك ما إذا كان الإعلان موجوداً على موقع وصلت حالياً. " if in_arabic
                  else f"Listing {lookup['listing_id']} is not in the collected Wasalt dataset. This does not establish whether the listing exists on the live Wasalt website. ")
    elif lookup and lookup.get('status') == 'mismatch':
        notice = (f"العقار رقم {lookup['listing_id']} موجود في البيانات، لكنه لا يطابق الشروط الإضافية. " if in_arabic
                  else f"Listing {lookup['listing_id']} is in the collected dataset but does not match the additional filters. ")
    elif lookup and lookup.get('status') == 'unknown':
        notice = (f"العقار رقم {lookup['listing_id']} موجود في البيانات، لكن بعض السمات المطلوبة غير معروفة. " if in_arabic
                  else f"Listing {lookup['listing_id']} is in the collected dataset, but required attributes are unknown. ")
    if in_arabic:
        text = f'النتائج التاريخية المؤكدة: **{total}**. عدد بطاقات العقارات المعروضة: **{shown}**.'
        if evidence:
            text += f' سياق النموذج يقتصر على **{evidence} من {total}** نتيجة مؤكدة.'
        return notice + text
    text = f'Verified historical matches: **{total}**. Displaying **{shown}** listing cards.'
    if evidence:
        text += f' Model evidence covers **{evidence} of {total}** verified matches.'
    return notice + text


def filter_question(filters):
    """Readable form label; the original structured dictionary is never mutated."""
    plurals = {'villa': 'villas', 'apartment': 'apartments', 'land': 'land', 'building': 'buildings',
               'floor': 'floors', 'room': 'rooms', 'rest_house': 'rest houses', 'chalet': 'chalets', 'duplex': 'duplexes'}
    text = 'Find Wasalt ' + plurals.get(filters.get('property_type'), 'properties')
    if filters.get('purpose'):
        text += ' for ' + filters['purpose']
    location = ', '.join(filters[key] for key in ('district', 'city') if filters.get(key))
    if location:
        text += ' in ' + location
    details = []
    period = '/' + filters['price_period'] if filters.get('price_period') else ''
    if 'min_price' in filters:
        details.append('priced at least SAR ' + number(filters['min_price']) + period)
    if 'max_price' in filters:
        details.append(('under SAR ' if filters.get('price_exclusive') else 'up to SAR ') + number(filters['max_price']) + period)
    if filters.get('price_period') and 'min_price' not in filters and 'max_price' not in filters:
        details.append({'year': 'with annual pricing', 'month': 'with monthly pricing', 'day': 'with daily pricing'}.get(filters['price_period'], 'priced per ' + filters['price_period']))
    if filters.get('listing_id'):
        details.append('listing ' + filters['listing_id'])
    for prefix, phrase in (('min_', 'at least '), ('exact_', 'exactly ')):
        for field, unit in (('bedrooms', 'bedrooms'), ('bathrooms', 'bathrooms'), ('area_sqm', 'sqm')):
            key = prefix + field
            if key in filters:
                details.append(phrase + number(filters[key]) + ' ' + unit)
    return text + (', ' + ', '.join(details) if details else '') + '.'


def property_card(record):
    kind = (record.get('property_type') or 'property').replace('_', ' ').title()
    purpose = ' for ' + record['purpose'] if record.get('purpose') else ''
    location = ' · '.join(record[key] for key in ('district', 'city') if record.get(key)) or 'Location unknown'
    if record.get('price_sar') is None:
        price = 'Price: Unknown'
    else:
        price = 'SAR ' + number(record['price_sar'])
        if record.get('price_period'):
            price += ' / ' + record['price_period']
        elif record.get('purpose') == 'rent':
            price += ' / period unknown'
    area = number(record.get('area_sqm')) + (' sqm' if record.get('area_sqm') is not None else '')
    return {'heading': f"Listing {record['listing_id']} · {kind}{purpose}",
            'location': location, 'price': price,
            'attributes': f"Area: {area} · Bedrooms: {number(record.get('bedrooms'))} · Bathrooms: {number(record.get('bathrooms'))}"}
