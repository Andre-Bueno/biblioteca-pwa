"""Access-token attacks: algorithm confusion, forgery, expiry, wrong key, missing claims."""

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.adapters.security.jwt_tokens import JwtTokenService
from app.domain.auth import InvalidTokenError

# HS384/HS512 forgeries intentionally use a 32-byte key; the library warns about key length.
pytestmark = pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")

KEY = b"k" * 32
NOW = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)


def good_claims(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": "user-1",
        "sid": "sess-1",
        "jti": "jti-1",
        "iat": int(NOW.timestamp()),
        "nbf": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
    }
    base.update(over)
    return base


def sign(claims: dict[str, object], key: bytes = KEY, alg: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=alg)


def decode(token: str, now: datetime = NOW) -> object:
    return JwtTokenService(KEY).decode_access_token(token, now=now)


def b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_roundtrip() -> None:
    service = JwtTokenService(KEY)
    token = service.issue_access_token(
        user_id="u", session_id="s", issued_at=NOW, expires_at=NOW + timedelta(minutes=15)
    )
    claims = service.decode_access_token(token, now=NOW + timedelta(minutes=1))
    assert (claims.user_id, claims.session_id) == ("u", "s")
    assert claims.token_id
    assert claims.issued_at == NOW


def test_every_token_has_a_unique_jti() -> None:
    service = JwtTokenService(KEY)
    args = {"user_id": "u", "session_id": "s", "issued_at": NOW, "expires_at": NOW + timedelta(1)}
    first, second = service.issue_access_token(**args), service.issue_access_token(**args)
    assert (
        service.decode_access_token(first, now=NOW).token_id
        != service.decode_access_token(second, now=NOW).token_id
    )


def test_alg_none_is_rejected() -> None:
    header = b64({"alg": "none", "typ": "JWT"})
    token = f"{header}.{b64(good_claims())}."
    with pytest.raises(InvalidTokenError):
        decode(token)


def test_alg_none_with_fake_signature_is_rejected() -> None:
    token = f"{b64({'alg': 'none'})}.{b64(good_claims())}.AAAA"
    with pytest.raises(InvalidTokenError):
        decode(token)


@pytest.mark.parametrize("alg", ["HS384", "HS512"])
def test_other_hmac_algorithm_is_rejected_even_with_the_right_key(alg: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode(sign(good_claims(), alg=alg))


def test_invalid_signature_is_rejected() -> None:
    head, body, sig = sign(good_claims()).split(".")
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(InvalidTokenError):
        decode(f"{head}.{body}.{flipped}")


def test_tampered_payload_is_rejected() -> None:
    head, _, sig = sign(good_claims()).split(".")
    with pytest.raises(InvalidTokenError):
        decode(f"{head}.{b64(good_claims(sub='admin'))}.{sig}")


def test_wrong_key_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode(sign(good_claims(), key=b"x" * 32))


def test_expired_token_is_rejected_against_the_injected_clock() -> None:
    token = sign(good_claims())
    decode(token, now=NOW + timedelta(minutes=14))
    with pytest.raises(InvalidTokenError):
        decode(token, now=NOW + timedelta(minutes=15))


def test_not_yet_valid_token_is_rejected() -> None:
    token = sign(good_claims(nbf=int((NOW + timedelta(hours=1)).timestamp())))
    with pytest.raises(InvalidTokenError):
        decode(token)


@pytest.mark.parametrize("missing", ["exp", "iat", "nbf", "sub", "sid", "jti"])
def test_required_claims_are_mandatory(missing: str) -> None:
    claims = good_claims()
    del claims[missing]
    with pytest.raises(InvalidTokenError):
        decode(sign(claims))


@pytest.mark.parametrize(
    "bad",
    [{"exp": "soon"}, {"iat": True}, {"sub": 5}, {"sid": ""}, {"exp": 10**30}],
)
def test_wrongly_typed_claims_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(InvalidTokenError):
        decode(sign(good_claims(**bad)))


@pytest.mark.parametrize("garbage", ["", "x", "a.b", "a.b.c", "....", "é.é.é", "A" * 5000])
def test_garbage_is_rejected(garbage: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode(garbage)


def test_short_key_is_refused() -> None:
    with pytest.raises(ValueError):
        JwtTokenService(b"short")


def test_error_never_contains_token_or_key() -> None:
    token = sign(good_claims(), key=b"x" * 32)
    with pytest.raises(InvalidTokenError) as info:
        decode(token)
    assert token not in str(info.value)
    assert info.value.__cause__ is None
