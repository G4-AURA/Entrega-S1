from __future__ import annotations

from django.conf import settings


_QUOTA_HINTS = (
    '429',
    'quota',
    'resource_exhausted',
    'rate limit',
    'too many requests',
    'insufficient_quota',
)


def get_gemini_api_keys() -> list[str]:
    """Returns configured Gemini API keys in effective fallback order."""
    configured = getattr(settings, 'GEMINI_API_KEYS', ()) or ()
    keys: list[str] = []
    for raw_key in configured:
        key = str(raw_key or '').strip()
        if key and key not in keys:
            keys.append(key)

    if keys:
        return keys

    legacy_key = str(getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if legacy_key:
        keys.append(legacy_key)
    return keys


def iter_gemini_api_keys(preferred_key: str | None = None):
    """
    Iterates Gemini keys in fallback order.

    If preferred_key is provided, it is tried first and then the configured pool
    excluding duplicates.
    """
    seen: set[str] = set()

    preferred = str(preferred_key or '').strip()
    if preferred:
        seen.add(preferred)
        yield preferred

    for key in get_gemini_api_keys():
        if key in seen:
            continue
        seen.add(key)
        yield key


def is_quota_or_rate_limit_error(
    *,
    status_code: int | None = None,
    detail: str | None = None,
    exception: Exception | None = None,
) -> bool:
    if status_code == 429:
        return True

    payload = ' '.join(
        part for part in (str(detail or ''), str(exception or '')) if part
    ).lower()

    if status_code == 403 and any(hint in payload for hint in _QUOTA_HINTS):
        return True

    return any(hint in payload for hint in _QUOTA_HINTS)
