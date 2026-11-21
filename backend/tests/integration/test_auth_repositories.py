from datetime import UTC, datetime, timedelta

import pytest
from app.adapters.persistence.login_attempt_store import SqlAlchemyLoginAttemptStore
from app.adapters.persistence.models import LoginAttemptRow
from app.adapters.persistence.refresh_token_repository import SqlAlchemyRefreshTokenRepository
from app.adapters.persistence.user_repository import SqlAlchemyUserRepository
from app.domain.auth import RefreshToken
from app.domain.user import Role, User
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def repo(session_factory: sessionmaker[Session]) -> SqlAlchemyRefreshTokenRepository:
    users = SqlAlchemyUserRepository(session_factory)
    for uid, name in (("u1", "alice"), ("u2", "bob")):
        users.add(User(uid, name, "h", Role.USER, True, "system", T0, T0, T0))
    return SqlAlchemyRefreshTokenRepository(session_factory)


def token(
    tid: str, family: str, user: str = "u1", created: float = 0, ttl: float = 1000
) -> RefreshToken:
    return RefreshToken(tid, user, family, f"{tid:0>64}", at(created), at(created + ttl))


def test_add_and_get_by_hash_roundtrip(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("a", "f1"))
    assert repo.get_by_hash(f"{'a':0>64}") == token("a", "f1")
    assert repo.get_by_hash("0" * 64) is None


def test_mark_used_is_atomic_once(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("a", "f1"))
    assert repo.mark_used("a", at(5)) is True
    assert repo.mark_used("a", at(6)) is False
    stored = repo.get_by_hash(f"{'a':0>64}")
    assert stored is not None
    assert stored.used_at == at(5)


def test_mark_used_refuses_revoked_tokens(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("a", "f1"))
    repo.revoke_family("f1", at(1))
    assert repo.mark_used("a", at(2)) is False


def test_revoke_family_only_touches_that_family(repo: SqlAlchemyRefreshTokenRepository) -> None:
    for tid, family in (("a", "f1"), ("b", "f1"), ("c", "f2")):
        repo.add(token(tid, family))
    repo.revoke_family("f1", at(9))
    assert not repo.is_family_active("f1", "u1")
    assert repo.is_family_active("f2", "u1")


def test_revoke_all_for_user_leaves_other_users(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("a", "f1", "u1"))
    repo.add(token("b", "f2", "u2"))
    repo.revoke_all_for_user("u1", at(9))
    assert not repo.is_family_active("f1", "u1")
    assert repo.is_family_active("f2", "u2")


def test_family_activity_is_scoped_to_the_user(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("a", "f1", "u1"))
    assert repo.is_family_active("f1", "u1")
    assert not repo.is_family_active("f1", "u2")  # someone else's session id
    assert not repo.is_family_active("missing", "u1")


def test_family_started_at_is_the_first_creation(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("a", "f1", created=0))
    repo.add(token("b", "f1", created=500))
    assert repo.family_started_at("f1") == at(0)
    assert repo.family_started_at("nope") is None


def test_purge_dead_families_keeps_live_ones_whole(repo: SqlAlchemyRefreshTokenRepository) -> None:
    repo.add(token("old", "dead", created=0, ttl=100))
    repo.add(token("a", "live", created=0, ttl=100))  # expired row of a still-live family
    repo.add(token("b", "live", created=500, ttl=100000))
    assert repo.purge_dead_families(at(10_000)) == 1
    assert repo.get_by_hash(f"{'old':0>64}") is None
    assert repo.get_by_hash(f"{'a':0>64}") is not None
    assert repo.family_started_at("live") == at(0)


# --------------------------------------------------------------- attempts


@pytest.fixture
def store(session_factory: sessionmaker[Session]) -> SqlAlchemyLoginAttemptStore:
    return SqlAlchemyLoginAttemptStore(session_factory, b"h" * 32)


def test_keys_are_stored_hashed_never_in_clear(
    store: SqlAlchemyLoginAttemptStore, session_factory: sessionmaker[Session]
) -> None:
    store.record("ip", "203.0.113.7", at(0), success=False)
    store.record("account", "alice", at(1), success=False)
    with session_factory() as session:
        rows = session.scalars(select(LoginAttemptRow)).all()
    assert len(rows) == 2
    for row in rows:
        assert len(row.key_hash) == 64
        assert row.key_hash not in ("203.0.113.7", "alice")
        assert "203.0.113.7" not in row.key_hash
        assert "alice" not in row.key_hash


def test_hash_differs_per_scope_and_per_key_and_per_secret(
    store: SqlAlchemyLoginAttemptStore, session_factory: sessionmaker[Session]
) -> None:
    other = SqlAlchemyLoginAttemptStore(session_factory, b"z" * 32)
    assert store.fingerprint("ip", "x") != store.fingerprint("account", "x")
    assert store.fingerprint("ip", "x") != store.fingerprint("ip", "y")
    assert store.fingerprint("ip", "x") != other.fingerprint("ip", "x")
    assert len(store.fingerprint("ip", "x")) == 16


def test_failures_are_scoped_by_scope_and_key(store: SqlAlchemyLoginAttemptStore) -> None:
    store.record("ip", "a", at(1), success=False)
    store.record("ip", "b", at(2), success=False)
    store.record("account", "a", at(3), success=False)
    assert store.failures_since_last_success("ip", "a", at(0)) == [at(1)]
    assert store.failures_since_last_success("account", "a", at(0)) == [at(3)]
    assert store.failures_since_last_success("ip_account", "a", at(0)) == []


def test_success_resets_the_counter_even_with_identical_timestamps(
    store: SqlAlchemyLoginAttemptStore,
) -> None:
    store.record("ip", "a", at(1), success=False)
    store.record("ip", "a", at(1), success=True)
    store.record("ip", "a", at(1), success=False)
    assert store.failures_since_last_success("ip", "a", at(0)) == [at(1)]


def test_failures_older_than_since_are_ignored(store: SqlAlchemyLoginAttemptStore) -> None:
    store.record("ip", "a", at(1), success=False)
    store.record("ip", "a", at(100), success=False)
    assert store.failures_since_last_success("ip", "a", at(50)) == [at(100)]


def test_last_success_at(store: SqlAlchemyLoginAttemptStore) -> None:
    assert store.last_success_at("ip_account", "k") is None
    store.record("ip_account", "k", at(5), success=True)
    store.record("ip_account", "k", at(9), success=True)
    assert store.last_success_at("ip_account", "k") == at(9)


def test_purge_removes_only_old_rows_with_separate_cutoffs(
    store: SqlAlchemyLoginAttemptStore,
) -> None:
    store.record("ip", "a", at(10), success=False)
    store.record("ip", "a", at(1000), success=False)
    store.record("ip_account", "k", at(10), success=True)
    store.record("ip_account", "k", at(1000), success=True)
    assert store.purge(failures_before=at(500), successes_before=at(5)) == 1
    assert store.failures_since_last_success("ip", "a", at(0)) == [at(1000)]
    assert store.last_success_at("ip_account", "k") == at(1000)


def test_short_hash_key_is_refused(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(ValueError):
        SqlAlchemyLoginAttemptStore(session_factory, b"short")
