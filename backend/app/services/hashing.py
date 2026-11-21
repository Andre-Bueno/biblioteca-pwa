"""Use case: compute the content hash of an item on demand."""

import hashlib
from collections.abc import Callable
from dataclasses import replace

from app.domain.errors import ItemNotFound
from app.domain.item import Item
from app.ports.item_repository import ItemRepository
from app.ports.storage import StorageBackend

_CHUNK = 1024 * 1024


def _hash_file(storage: StorageBackend, rel_path: str, update: Callable[[bytes], None]) -> None:
    with storage.open(rel_path) as fh:
        while chunk := fh.read(_CHUNK):
            update(chunk)


def ensure_content_hash(storage: StorageBackend, repo: ItemRepository, item_id: str) -> Item:
    """Return the item with `content_hash` filled (sha256), persisting it if it was missing.

    Files: hash of the bytes. Folders: hash of the sorted (name, size) pairs of the children.
    """
    item = repo.get(item_id)
    if item is None:
        raise ItemNotFound
    if item.content_hash is not None:
        return item

    digest = hashlib.sha256()
    entry = storage.stat(item.rel_path)
    if entry.is_dir:
        for child in sorted(storage.list_children(item.rel_path), key=lambda c: c.rel_path):
            if not child.is_dir:
                digest.update(f"{child.rel_path}\0{child.size}\n".encode())
    else:
        _hash_file(storage, item.rel_path, digest.update)

    updated = replace(item, content_hash=digest.hexdigest())
    repo.update(updated)
    return updated
