from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str | None, password: str) -> bool:
        """Constant-effort check. With `password_hash=None` (unknown user) it still does the
        same work against a dummy hash and returns False, so timing does not reveal existence."""
        ...

    def needs_rehash(self, password_hash: str) -> bool: ...
