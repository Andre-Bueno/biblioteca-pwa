"""Anti brute force over HTTP: lockout, identical responses, resets, expiry, timing."""

import statistics
import time

from app.adapters.security.argon2_hasher import Argon2Hasher

from auth_fakes import PASSWORD, ApiClient, Env

LOGIN = "/api/v1/auth/login"
WRONG = "definitely not the password"


def fail(client: ApiClient, times: int, username: str = "alice") -> None:
    for _ in range(times):
        assert client.login(username, WRONG).status_code == 401


def test_lockout_after_n_failures_returns_429_with_retry_after(env: Env) -> None:
    client = env.client()
    fail(client, 5)
    blocked = client.login()  # even the CORRECT password is refused while locked
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "300"
    assert blocked.json() == {"detail": "Too many requests. Try again later."}
    assert "set-cookie" not in blocked.headers


def test_lockout_is_identical_for_existing_and_unknown_users(env: Env) -> None:
    client = env.client()
    fail(client, 5, "alice")
    fail(client, 5, "ghost")
    existing, unknown = client.login("alice"), client.login("ghost")
    assert existing.status_code == unknown.status_code == 429
    assert existing.content == unknown.content
    assert existing.headers["retry-after"] == unknown.headers["retry-after"]
    keys = {k for k in existing.headers if k != "date"}
    assert keys == {k for k in unknown.headers if k != "date"}
    # Same sequence with the clock moving: still identical.
    env.clock.advance(120)
    assert (
        client.login("alice").headers["retry-after"] == client.login("ghost").headers["retry-after"]
    )
    assert client.login("alice").headers["retry-after"] == "180"


def test_failures_before_the_threshold_look_exactly_like_unknown_user_failures(env: Env) -> None:
    client = env.client()
    wrong, unknown = client.login("alice", WRONG), client.login("ghost", WRONG)
    assert (wrong.status_code, wrong.content) == (unknown.status_code, unknown.content)
    assert sorted(wrong.headers) == sorted(unknown.headers)


def test_lock_expires_with_the_clock(env: Env) -> None:
    client = env.client()
    fail(client, 5)
    assert client.login().status_code == 429
    env.clock.advance(301)
    assert client.login().status_code == 200


def test_failure_window_expires(env: Env) -> None:
    client = env.client()
    fail(client, 4)
    env.clock.advance(env.settings.LOGIN_FAILURE_WINDOW_SECONDS + 1)
    fail(client, 4)
    assert client.login().status_code == 200


def test_success_resets_the_counters(env: Env) -> None:
    client = env.client()
    fail(client, 4)
    assert client.login().status_code == 200
    fail(client, 4)
    assert client.login().status_code == 200


def test_lock_grows_progressively(env: Env) -> None:
    client = env.client()
    fail(client, 5)
    env.clock.advance(301)
    fail(client, 5)
    assert client.login().headers["retry-after"] == "600"


def test_lockout_cannot_be_dodged_by_changing_the_username(env: Env) -> None:
    attacker = env.client("6.6.6.6")
    for i in range(20):
        assert attacker.login(f"user{i}", WRONG).status_code == 401
    assert attacker.login("alice", PASSWORD).status_code == 429
    assert attacker.login("anyone-new", PASSWORD).status_code == 429
    assert env.client("7.7.7.7").login().status_code == 200  # other addresses are unaffected


def test_lockout_cannot_be_dodged_with_case_or_spaces(env: Env) -> None:
    client = env.client()
    fail(client, 5)
    for variant in ("ALICE", " alice ", "Alice", "aLiCe  "):
        assert client.login(variant).status_code == 429


def test_attacker_cannot_lock_the_victim_out_from_another_address(env: Env) -> None:
    attacker = env.client("6.6.6.6")
    fail(attacker, 5)
    assert attacker.login().status_code == 429
    assert env.client("10.0.0.1").login().status_code == 200


def test_distributed_attack_locks_new_addresses_but_not_trusted_ones(env: Env) -> None:
    home = env.client("10.0.0.1")
    assert home.login().status_code == 200  # becomes a trusted address for alice
    for i in range(15):
        fail(env.client(f"66.66.66.{i}"), 1)
    assert env.client("10.9.9.9").login().status_code == 429  # unknown address: account lock
    assert home.login().status_code == 200  # usual address still works


def test_ip_failures_are_not_reset_by_a_successful_login_of_another_account(env: Env) -> None:
    env.create_user("mallory")
    attacker = env.client("6.6.6.6")
    for i in range(19):
        attacker.login(f"victim-{i}", WRONG)
        assert attacker.login("mallory").status_code == 200
    attacker.login("victim-x", WRONG)
    assert attacker.login("mallory").status_code == 429


def test_attempts_table_holds_only_hashed_keys(env: Env) -> None:
    from app.adapters.persistence.models import LoginAttemptRow
    from sqlalchemy import select

    client = env.client("203.0.113.9")
    client.login("Some.Victim", WRONG)
    with env.container.session_factory() as session:
        rows = session.scalars(select(LoginAttemptRow)).all()
    assert {r.scope for r in rows} == {"ip", "account", "ip_account"}
    for row in rows:
        assert len(row.key_hash) == 64
        assert "203.0.113.9" not in row.key_hash
        assert "victim" not in row.key_hash.lower()


def test_response_time_does_not_reveal_whether_the_user_exists(db_url: str) -> None:
    env = Env(
        db_url,
        hasher=Argon2Hasher(time_cost=2, memory_cost_kib=4096, parallelism=1),
        LOGIN_MAX_FAILURES_IP=1000,
        LOGIN_MAX_FAILURES_ACCOUNT=1000,
        LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS=10_000,  # must exceed what one address can record
    )
    env.create_user()
    existing: list[float] = []
    unknown: list[float] = []
    for i in range(8):
        for name, bucket in (("alice", existing), ("ghost", unknown)):
            client = env.client(f"10.{i}.0.{len(bucket) + 1}")
            client.csrf()
            start = time.perf_counter()
            assert client.login(name, WRONG).status_code == 401
            bucket.append(time.perf_counter() - start)
    ratio = statistics.median(existing) / statistics.median(unknown)
    # Generous bounds: this guards against "skips the hash for unknown users" (ratio >> 2)
    # without being flaky on a loaded machine.
    assert 0.4 < ratio < 2.5, (statistics.median(existing), statistics.median(unknown))


def test_unknown_user_still_pays_for_a_hash(db_url: str) -> None:
    """Smoke test only (loose bound): an unknown-user login costs about one Argon2 verification.

    The deterministic proof lives in `tests/unit/test_argon2_hasher.py`
    (`test_unknown_user_pays_exactly_one_verify_against_the_dummy_hash`); timing is flaky by
    nature, so the bound is deliberately generous (half of a directly measured hash).
    """
    hasher = Argon2Hasher(time_cost=3, memory_cost_kib=16384, parallelism=1)
    env = Env(db_url, hasher=hasher, LOGIN_MAX_FAILURES_IP=1000)
    client = env.client()
    client.csrf()
    start = time.perf_counter()
    hasher.hash(WRONG)
    one_hash = time.perf_counter() - start
    start = time.perf_counter()
    assert client.login("ghost", WRONG).status_code == 401
    unknown_time = time.perf_counter() - start
    assert unknown_time > one_hash * 0.5, (unknown_time, one_hash)
