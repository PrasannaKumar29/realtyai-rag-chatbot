"""Allowlisted error diagnostics. Never retain messages, raw bodies or account data."""
from datetime import datetime
from email.utils import parsedate_to_datetime
import math
import re
from collections.abc import Mapping


UPSTREAM_SOURCES = frozenset({'upstream_provider_shared_pool', 'upstream_provider_capacity',
                              'upstream_provider_rate_limit'})
MINUTE_SOURCES = frozenset({'openrouter_free_tier_per_minute'})
ACCOUNT_SOURCES = frozenset({'openrouter_free_tier_daily', 'openrouter_free_tier_per_day',
                             'openrouter_daily_limit', 'openrouter_account_quota',
                             'openrouter_key_limit', 'openrouter_credits',
                             'openrouter_guardrail_budget', 'openrouter_workspace_budget'})
QUOTA_CODES = frozenset({'insufficient_quota', 'quota_exceeded', 'daily_limit_exceeded',
                         'daily_quota_exceeded', 'account_quota_exhausted',
                         'insufficient_credits', 'credit_limit_exceeded', 'quota_exhausted',
                         'credit_balance_exhausted', 'billing_hard_limit_reached',
                         'billing_not_active', 'organization_spend_limit_exceeded',
                         'project_spend_limit_exceeded', 'organization_usage_limit_exceeded'})
BLOCKED_CODES = QUOTA_CODES | {'authentication_error', 'invalid_api_key', 'permission_denied'}


def label(value, provider=False):
    pattern = r'[A-Za-z][A-Za-z0-9 ._()/-]{0,79}' if provider else r'[a-z][a-z0-9_]{0,95}'
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def timing(value):
    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
        return value
    return None


def reset_value(value, retry=False):
    """Keep only bounded numeric or validated date values, never arbitrary headers."""
    if type(value) in (int, float) and timing(value) is not None:
        value = str(value)
    if not isinstance(value, str) or len(value) > 64:
        return None
    if re.fullmatch(r'\d{1,17}(?:\.\d{1,6})?', value):
        return value
    if not retry and re.fullmatch(r'(?:\d{1,8}(?:\.\d{1,6})?(?:ms|s|m|h|d)){1,5}', value):
        return value
    try:
        date = parsedate_to_datetime(value) if retry else datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is not None:
            return date.isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def classify(diagnostic):
    status = diagnostic.get('http_status')
    if status != 429:
        return 'not_http_429'
    source = diagnostic.get('limit_source')
    codes = {diagnostic.get(k) for k in ('error_type', 'provider_code', 'provider_error_code', 'reason')}
    if source in ACCOUNT_SOURCES or codes & QUOTA_CODES or diagnostic.get('error_code') == 402:
        return 'daily_or_account_quota'
    if codes & (BLOCKED_CODES - QUOTA_CODES) or diagnostic.get('error_code') not in (None, 429):
        return 'unknown_429'
    if source in MINUTE_SOURCES:
        return 'openrouter_free_per_minute'
    if source in UPSTREAM_SOURCES:
        return 'upstream_provider_capacity'
    return 'unknown_429'


def extract_diagnostics(status=None, data=None, headers=None, duration=None, forbidden=()):
    data = data if isinstance(data, dict) else {}
    error = data.get('error')
    error = error if isinstance(error, dict) else {}
    metadata = error.get('metadata')
    metadata = metadata if isinstance(metadata, dict) else {}
    result = {'http_status': status if type(status) is int else None,
              'error_code': error.get('code') if type(error.get('code')) is int else None,
              'limit_source': label(metadata.get('limit_source')),
              'provider_name': label(metadata.get('provider_name'), provider=True) or label(data.get('provider'), provider=True),
              'request_duration_seconds': timing(duration),
              'retry_after': None, 'retry_after_seconds': None, 'rate_limit_reset': {}}
    for key in ('error_type', 'provider_code', 'provider_error_code', 'reason'):
        # These are machine codes only; free-form provider details are dropped.
        result[key] = label(metadata.get(key))
    for prefix, fields in (('', headers), ('metadata.', metadata.get('headers'))):
        if not isinstance(fields, Mapping):
            continue
        for key, value in fields.items():
            name = key.lower() if isinstance(key, str) else ''
            if name == 'retry-after':
                safe = reset_value(value, retry=True)
                if safe is not None and result['retry_after'] is None:
                    result['retry_after'] = safe
            if name in ('x-ratelimit-reset', 'ratelimit-reset', 'x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens'):
                safe = reset_value(value)
                if safe is not None:
                    result['rate_limit_reset'][prefix + name] = safe
    result['retry_after_seconds'] = timing(metadata.get('retry_after_seconds'))
    if result['retry_after'] and re.fullmatch(r'\d+(?:\.\d+)?', result['retry_after']):
        result['retry_after_seconds'] = float(result['retry_after'])
    for key in ('resets_at', 'reset_at', 'reset_time'):
        safe = reset_value(metadata.get(key))
        if safe is not None:
            result['rate_limit_reset']['metadata.' + key] = safe
    # Even allowlisted fields are untrusted: never retain an echoed full prompt.
    def omit_echoes(value):
        if isinstance(value, str):
            return None if any(text and text in value for text in forbidden) else value
        if isinstance(value, dict):
            return {key: omit_echoes(item) for key, item in value.items()}
        return value
    result = omit_echoes(result)
    result['rate_limit_category'] = classify(result)
    return result


def fallback_eligible(result, enabled, fallback_used=False):
    diagnostic = result.get('diagnostics') or {}
    return (enabled is True and not fallback_used and result.get('status') == 'failed'
            and result.get('http_status') == 429 and diagnostic.get('http_status') == 429
            and diagnostic.get('limit_source') in UPSTREAM_SOURCES
            and classify(diagnostic) == 'upstream_provider_capacity')
