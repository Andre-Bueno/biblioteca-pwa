"""Defensive readers for JSON that came from the network: wrong types become empty values."""

MAX_TEXT = 20_000
MAX_ITEMS = 200


def as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str)}


def as_list(value: object) -> list[object]:
    return value[:MAX_ITEMS] if isinstance(value, list) else []


def as_text(value: object, limit: int = MAX_TEXT) -> str | None:
    """A non-empty string (cut to `limit`), else None. Not sanitized: callers sanitize on use."""
    if isinstance(value, str) and value.strip():
        return value[:limit]
    return None


def as_year(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 1000 <= value <= 2200:
        return value
    return None
