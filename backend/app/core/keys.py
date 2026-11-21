"""Subkey derivation: every use of SECRET_KEY gets its own key (never the raw secret).

HKDF-SHA256 (RFC 5869) with a fixed application salt and one label per purpose, so a signature
produced for one purpose can never validate for another (JWT vs CSRF vs login-attempt hashing).
"""

import hashlib
import hmac

_SALT = b"reader-app/hkdf/v1"

LABEL_ACCESS_JWT = "access-jwt"
LABEL_CSRF = "csrf-token"
LABEL_LOGIN_ATTEMPTS = "login-attempts"


def derive_key(secret: str, label: str, length: int = 32) -> bytes:
    """HKDF extract-and-expand; `length` up to 255 * 32 bytes."""
    prk = hmac.new(_SALT, secret.encode(), hashlib.sha256).digest()
    info = f"reader-app:{label}".encode()
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]
