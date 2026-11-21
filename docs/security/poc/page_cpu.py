"""PoC FIND-2026-003: every page/cover request re-reads every image entry of the CBZ.

Usage: python page_cpu.py <base_url> <library_dir>
The script writes a CBZ with 9500 tiny PNGs into <library_dir> (a TEMP library of the local test
instance), asks you to scan it (admin) and then measures page requests. Local instance only.
"""

import concurrent.futures as cf
import json
import os
import struct
import sys
import time
import zipfile
import zlib

import httpx

BASE, LIB = sys.argv[1], sys.argv[2]
assert BASE.startswith("http://127.0.0.1:"), "local instances only"


def png() -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"\x00" + b"\xff\x00\x00" * 2
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw * 2)) + chunk(b"IEND", b""))


with zipfile.ZipFile(os.path.join(LIB, "many.cbz"), "w", zipfile.ZIP_DEFLATED) as z:
    for i in range(9500):
        z.writestr(f"{i:05d}.png", png())


def login(user: str, pw: str) -> tuple[httpx.Client, dict]:
    c = httpx.Client(base_url=BASE, timeout=120)
    c.get("/api/v1/auth/csrf")
    h = {"Origin": BASE, "X-CSRF-Token": c.cookies.get("csrf_token")}
    assert c.post("/api/v1/auth/login", json={"username": user, "password": pw}, headers=h).status_code == 200
    return c, h


admin, ah = login("admin1", "Adm1n-Correct-Horse-42")
admin.post("/api/v1/library/scan", headers=ah)
for _ in range(60):
    time.sleep(1)
    if admin.get("/api/v1/library/scan/status").json()["state"] != "running":
        break
items = admin.get("/api/v1/items?q=many").json()["items"]
item_id = items[0]["id"]
user, _ = login("user1", "Us3r-Correct-Horse-42")


def one(_: int) -> float:
    t = time.perf_counter()
    assert user.get(f"/api/v1/items/{item_id}/pages/0").status_code == 200
    return (time.perf_counter() - t) * 1000


print("single request ms:", round(one(0)))  # observed ~175 ms for a 76-byte page
for n in (8, 16):
    t = time.perf_counter()
    with cf.ThreadPoolExecutor(n) as ex:
        lat = sorted(ex.map(one, range(2 * n)))
    print(f"{2*n} requests on {n} threads: total {round((time.perf_counter()-t)*1000)} ms, median {round(lat[len(lat)//2])} ms")
print(json.dumps({"hint": "latency grows linearly with concurrency: the work is CPU bound (GIL)"}))
