import secrets

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from app.adapters.gate import BoundedGate

# Anything longer than this cannot match (policy max is 128); skip hashing to avoid CPU abuse.
MAX_VERIFY_LENGTH = 1024


class Argon2Hasher:
    """Argon2id. Defaults follow RFC 9106 "low memory" profile (t=3, m=64 MiB, p=4).

    Concurrency is bounded (`max_concurrent` hashing, `max_waiting` queued for at most
    `wait_seconds`); beyond that `hash`/`verify` raise `ResourceBusy` immediately, so a flood of
    logins cannot hold every worker thread of the server.
    """

    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost_kib: int = 65536,
        parallelism: int = 4,
        max_concurrent: int = 2,
        max_waiting: int = 8,
        wait_seconds: float = 1.0,
    ) -> None:
        # Each hash takes `memory_cost_kib`; bounding concurrency keeps a burst of logins from
        # exhausting memory.
        self._gate = BoundedGate(
            slots=max_concurrent, max_waiting=max_waiting, timeout=wait_seconds
        )
        self._argon = _Argon2(
            time_cost=time_cost, memory_cost=memory_cost_kib, parallelism=parallelism
        )
        # Same parameters as real hashes, so verifying it costs the same time.
        self._dummy_hash = self._argon.hash(secrets.token_urlsafe(24))

    def hash(self, password: str) -> str:
        with self._gate.slot():
            return self._argon.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        if len(password) > MAX_VERIFY_LENGTH:
            return False
        target = self._dummy_hash if password_hash is None else password_hash
        try:
            with self._gate.slot():
                result = self._argon.verify(target, password)
        except (VerificationError, InvalidHashError):
            return False
        return result and password_hash is not None

    def needs_rehash(self, password_hash: str) -> bool:
        return self._argon.check_needs_rehash(password_hash)
