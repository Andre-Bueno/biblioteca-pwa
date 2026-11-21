"""Small helpers shared by the ASGI middlewares and routers (no business rules)."""

import ipaddress
import json

from starlette.types import Scope, Send

API_PREFIX = "/api"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_api_path(path: str) -> bool:
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


def normalize_client_ip(host: str | None) -> str:
    """Canonical key for a client address.

    IPv4-mapped IPv6 becomes IPv4; IPv6 is collapsed to its /64 (one subscriber typically owns a
    whole /64, so rotating inside it must not bypass limits). Anything unparsable or missing maps
    to one shared "unknown" key (strictest possible treatment).
    """
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def is_non_public_address(host: str | None) -> bool:
    """True for loopback/private/link-local client addresses (a sign that every client is being
    seen as the reverse proxy, i.e. proxy trust is not configured)."""
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def raw_client_host(scope: Scope) -> str | None:
    """The peer address exactly as the server reported it (`scope["client"]`), or None."""
    client = scope.get("client")
    return str(client[0]) if client else None


def client_ip(scope: Scope) -> str:
    """Real client IP. Behind a proxy uvicorn (proxy-headers + FORWARDED_ALLOW_IPS) already put it
    in `scope["client"]`; headers are never read here."""
    return normalize_client_ip(raw_client_host(scope))


def header(scope: Scope, name: bytes) -> str | None:
    """First value of a request header (lowercase `name`), decoded as latin-1."""
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def header_count(scope: Scope, name: bytes) -> int:
    """How many times a request header (lowercase `name`) appears."""
    return sum(1 for key, _ in scope.get("headers", []) if key == name)


async def send_json_error(
    send: Send, status: int, detail: str, extra_headers: list[tuple[bytes, bytes]] | None = None
) -> None:
    # Compact separators: byte-identical to FastAPI's JSONResponse bodies.
    body = json.dumps({"detail": detail}, separators=(",", ":")).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        *(extra_headers or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
