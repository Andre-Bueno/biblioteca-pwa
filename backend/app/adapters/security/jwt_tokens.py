import uuid
from datetime import UTC, datetime

import jwt

from app.domain.auth import AccessClaims, InvalidTokenError

ALGORITHM = "HS256"  # fixed: never read from the token header
MAX_TOKEN_LENGTH = 2048
_REQUIRED = ("exp", "iat", "nbf", "sub", "sid", "jti")
# Time claims are checked against the injected clock below (so tests and the service share one
# notion of "now"); PyJWT still enforces signature, algorithm and presence of required claims.
_OPTIONS = {
    "require": list(_REQUIRED),
    "verify_signature": True,
    "verify_exp": False,
    "verify_nbf": False,
    "verify_iat": False,
    "verify_aud": False,
    "verify_iss": False,
    "verify_sub": False,
    "verify_jti": False,
}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class JwtTokenService:
    """HS256 access tokens signed with a key derived from SECRET_KEY (injected as bytes)."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("signing key too short")
        self._key = key

    def issue_access_token(
        self, *, user_id: str, session_id: str, issued_at: datetime, expires_at: datetime
    ) -> str:
        iat = int(issued_at.timestamp())
        payload = {
            "sub": user_id,
            "sid": session_id,
            "jti": uuid.uuid4().hex,
            "iat": iat,
            "nbf": iat,
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, self._key, algorithm=ALGORITHM)

    def decode_access_token(self, token: str, *, now: datetime) -> AccessClaims:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            raise InvalidTokenError("invalid token")
        try:
            claims = jwt.decode(token, self._key, algorithms=[ALGORITHM], options=_OPTIONS)  # type: ignore[arg-type]
        except jwt.PyJWTError:
            raise InvalidTokenError("invalid token") from None
        sub, sid, jti = claims["sub"], claims["sid"], claims["jti"]
        iat, nbf, exp = claims["iat"], claims["nbf"], claims["exp"]
        if not all(isinstance(v, str) and v for v in (sub, sid, jti)):
            raise InvalidTokenError("invalid token")
        if not all(_is_int(v) for v in (iat, nbf, exp)):
            raise InvalidTokenError("invalid token")
        now_ts = now.timestamp()
        if exp <= now_ts or nbf > now_ts:
            raise InvalidTokenError("invalid token")
        try:
            return AccessClaims(
                user_id=sub,
                session_id=sid,
                token_id=jti,
                issued_at=datetime.fromtimestamp(iat, UTC),
                expires_at=datetime.fromtimestamp(exp, UTC),
            )
        except (OverflowError, OSError, ValueError):
            raise InvalidTokenError("invalid token") from None
