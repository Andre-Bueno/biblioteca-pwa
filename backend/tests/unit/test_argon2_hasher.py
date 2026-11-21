from typing import Any

import pytest
from app.adapters.security.argon2_hasher import MAX_VERIFY_LENGTH, Argon2Hasher


def test_hash_is_argon2id_and_verifies(fast_hasher: Argon2Hasher) -> None:
    hashed = fast_hasher.hash("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert "correct horse" not in hashed
    assert fast_hasher.verify(hashed, "correct horse battery") is True
    assert fast_hasher.verify(hashed, "wrong password!!") is False


def test_hashes_are_salted(fast_hasher: Argon2Hasher) -> None:
    assert fast_hasher.hash("same password 1") != fast_hasher.hash("same password 1")


class _SpyArgon:
    """Records every `verify` call and delegates to the real Argon2 instance."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.calls: list[tuple[str, str]] = []

    def verify(self, password_hash: str, password: str) -> bool:
        self.calls.append((password_hash, password))
        return bool(self._real.verify(password_hash, password))


def test_unknown_user_pays_exactly_one_verify_against_the_dummy_hash(
    fast_hasher: Argon2Hasher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic guard for the user-enumeration defense (replaces timing as the proof).

    `verify(None, ...)` must run exactly one real Argon2 verification against the dummy hash
    (same cost as a real hash) and still return False. An early `return False` would skip it.
    """
    spy = _SpyArgon(fast_hasher._argon)  # noqa: SLF001
    monkeypatch.setattr(fast_hasher, "_argon", spy)
    slots = 0
    real_slot = fast_hasher._gate.slot  # noqa: SLF001

    def counting_slot() -> Any:
        nonlocal slots
        slots += 1
        return real_slot()

    monkeypatch.setattr(fast_hasher._gate, "slot", counting_slot)  # noqa: SLF001

    assert fast_hasher.verify(None, "anything at all") is False
    assert spy.calls == [(fast_hasher._dummy_hash, "anything at all")]  # noqa: SLF001
    assert slots == 1  # the dummy verify is bounded by the same gate as real ones


def test_dummy_hash_never_authenticates_even_with_its_own_password(
    fast_hasher: Argon2Hasher,
) -> None:
    """Even if the dummy verify succeeds (it cannot with a random secret), the result is False."""

    class _AlwaysTrue:
        def verify(self, password_hash: str, password: str) -> bool:
            return True

    fast_hasher._argon = _AlwaysTrue()  # type: ignore[assignment]  # noqa: SLF001
    assert fast_hasher.verify(None, "whatever password") is False


def test_dummy_hash_uses_same_parameters_as_real_hashes(fast_hasher: Argon2Hasher) -> None:
    real = fast_hasher.hash("some password 123")
    assert not fast_hasher.needs_rehash(fast_hasher._dummy_hash)  # noqa: SLF001
    assert fast_hasher._dummy_hash.split("$")[3] == real.split("$")[3]  # noqa: SLF001


def test_garbage_hash_is_a_failed_verification(fast_hasher: Argon2Hasher) -> None:
    assert fast_hasher.verify("not-a-hash", "whatever password") is False


def test_oversized_password_rejected_without_hashing(fast_hasher: Argon2Hasher) -> None:
    hashed = fast_hasher.hash("some password 123")
    assert fast_hasher.verify(hashed, "a" * (MAX_VERIFY_LENGTH + 1)) is False


def test_needs_rehash_detects_weaker_parameters() -> None:
    weak = Argon2Hasher(time_cost=1, memory_cost_kib=8, parallelism=1)
    strong = Argon2Hasher(time_cost=2, memory_cost_kib=16, parallelism=1)
    old = weak.hash("some password 123")
    assert strong.needs_rehash(old) is True
    assert weak.needs_rehash(old) is False
