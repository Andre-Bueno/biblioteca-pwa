"""Signed webhook to the operator's deploy agent (`infra/deploy-hook`): the ONLY outbound call of
the app that is not the SafeGateway.

It is separate on purpose: the destination is chosen by the operator in configuration (never by a
client) and may live on a private network (loopback, LAN, Tailscale), which the SafeGateway forbids.
Rules, none of them overridable at run time:
- https is always accepted; http only with UPDATE_WEBHOOK_ALLOW_HTTP, and only when EVERY address
  the name resolves to is loopback, private or CGNAT (checked after resolving, then the connection
  goes to the checked address: no second lookup);
- TLS with certificate and host-name verification; no redirect is followed (3xx is a failure);
- total time 10 s; the answer is read up to 4 KiB and ignored: only a 2xx status matters;
- generic User-Agent, no cookies;
- nothing about the destination, the secret, the signature or the body is ever logged or raised.

Contract (see infra/deploy-hook/README.md): POST JSON with `X-Update-Timestamp` (unix seconds) and
`X-Update-Signature: sha256=<hex(HMAC_SHA256(secret, timestamp + "." + raw body))>`.
"""

import contextlib
import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import secrets
import socket
import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.domain.errors import UpdateNotifyFailed
from app.domain.release import UpdateRequest, is_operator_network

logger = logging.getLogger(__name__)

USER_AGENT = "BibliotecaPWA/1.0"
TOTAL_TIMEOUT = 10.0
MAX_RESPONSE_BYTES = 4096
REGISTRY = "ghcr.io"

Resolver = Callable[[str, int], list[str]]


def _resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """`X-Update-Signature` value."""
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def iso_utc(moment: datetime) -> str:
    """`2026-11-21T12:00:00Z` (the receiver accepts the `Z` form)."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _PlainConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), timeout=self.timeout)


class _TlsConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, port, timeout=timeout, context=context)
        self._address = address
        self._tls_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self._address, self.port), timeout=self.timeout)
        self.sock = self._tls_context.wrap_socket(sock, server_hostname=self.host)


class WebhookNotifier:
    def __init__(
        self,
        url: str,
        secret: str,
        *,
        allow_http: bool = False,
        resolver: Resolver = _resolve,
        clock: Callable[[], float] = time.time,
        nonce: Callable[[], str] = lambda: secrets.token_hex(16),
    ) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("invalid webhook url")  # config is validated before; defense in depth
        self._tls = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port or (443 if self._tls else 80)
        self._target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        self._secret = secret
        self._allow_http = allow_http
        self._resolver = resolver
        self._clock = clock
        self._nonce = nonce

    def __repr__(self) -> str:  # never shows the URL or the secret
        return "WebhookNotifier(<configured>)"

    def _address(self) -> str:
        """The address to connect to, checked against the policy."""
        try:
            addresses = [str(ipaddress.ip_address(self._host))]
        except ValueError:
            addresses = self._resolver(self._host, self._port)
        if not addresses:
            raise UpdateNotifyFailed
        if not self._tls and not (
            self._allow_http and all(is_operator_network(a) for a in addresses)
        ):
            raise UpdateNotifyFailed  # plain http only inside the operator's own network
        return addresses[0]

    def _body(self, request: UpdateRequest) -> bytes:
        payload = {
            "event": "update_requested",
            "repository": request.repository,
            "tag": request.tag,
            "image": f"{REGISTRY}/{request.repository.lower()}:{request.tag}",
            "requested_at": iso_utc(request.requested_at),
            "nonce": self._nonce(),
        }
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")

    def notify(self, request: UpdateRequest) -> None:
        body = self._body(request)
        timestamp = str(int(self._clock()))
        headers = {
            "Content-Type": "application/json",
            "X-Update-Timestamp": timestamp,
            "X-Update-Signature": sign(self._secret, timestamp, body),
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        conn: http.client.HTTPConnection | None = None
        try:
            address = self._address()
            cls = _TlsConnection if self._tls else _PlainConnection
            conn = cls(self._host, self._port, address, TOTAL_TIMEOUT)
            conn.request("POST", self._target, body, headers)
            response = conn.getresponse()
            response.read(MAX_RESPONSE_BYTES)  # ignored; never logged
            status = response.status
        except UpdateNotifyFailed:
            raise
        except (OSError, http.client.HTTPException, ssl.SSLError, ValueError) as exc:
            logger.warning("Update webhook failed (%s)", type(exc).__name__)
            raise UpdateNotifyFailed from None
        finally:
            if conn is not None:
                with contextlib.suppress(OSError):
                    conn.close()
        if not 200 <= status < 300:
            logger.warning("Update webhook refused (status %d)", status)
            raise UpdateNotifyFailed
