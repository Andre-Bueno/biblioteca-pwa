"""REG-019: `/auth/me` and `/auth/csrf` consumed the strict /auth/* bucket (burst 10, 20/min).

Bug: the SPA calls `me` and `csrf` on every load and navigation, so a few page loads exhausted the
strict bucket and the next login got 429. Fix: only login, refresh, logout and change-password use
the strict bucket; `me` and `csrf` stay under the global limit.
"""

import pytest

from auth_fakes import Env

NOT_STRICT = ["/api/v1/auth/me", "/api/v1/auth/csrf"]


@pytest.mark.parametrize("path", NOT_STRICT)
def test_reg_019_reads_do_not_exhaust_the_strict_auth_bucket(db_url: str, path: str) -> None:
    # The production defaults for the strict bucket (the test factory raises them otherwise).
    env = Env(db_url, RATE_LIMIT_AUTH_BURST=10, RATE_LIMIT_AUTH_PER_MINUTE=20)
    env.create_user()
    client = env.client("198.51.100.7")
    for _ in range(30):
        assert client.http.get(path).status_code != 429
    assert client.login().status_code == 200  # the strict bucket is still full


def test_reg_019_login_still_uses_the_strict_bucket(db_url: str) -> None:
    env = Env(db_url, RATE_LIMIT_AUTH_BURST=2, RATE_LIMIT_AUTH_PER_MINUTE=60)
    env.create_user()
    client = env.client("198.51.100.8")
    codes = [client.http.post("/api/v1/auth/refresh").status_code for _ in range(3)]
    assert codes[-1] == 429
