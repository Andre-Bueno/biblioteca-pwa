"""REG-005: no limit on request body size.

Bug: any /api route would read an arbitrarily large body into memory. Cause: no size limit
existed in the middleware stack. Now a body above MAX_BODY_BYTES (64 KiB) gets a generic 413.
"""

from auth_fakes import Env


def test_oversized_json_body_is_refused_with_413(env: Env) -> None:
    huge = {"username": "alice", "password": "x" * 100_000}
    response = env.client().http.post("/api/v1/auth/login", json=huge)
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
