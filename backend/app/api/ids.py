"""Validation of path identifiers shared by the routers (no business rules)."""

import uuid

from app.api.errors import not_found


def item_id_or_404(raw: str) -> str:
    """Canonical lowercase UUID, or a generic 404 (a malformed id is simply 'not found')."""
    if len(raw) != 36:
        raise not_found()
    try:
        canonical = str(uuid.UUID(raw))
    except ValueError:
        raise not_found() from None
    if canonical != raw.lower():
        raise not_found()
    return canonical
