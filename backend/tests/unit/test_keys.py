from app.core.keys import LABEL_ACCESS_JWT, LABEL_CSRF, LABEL_LOGIN_ATTEMPTS, derive_key

SECRET = "test-only-secret-key-not-for-production-0123456789"


def test_deterministic_and_32_bytes() -> None:
    assert derive_key(SECRET, "x") == derive_key(SECRET, "x")
    assert len(derive_key(SECRET, "x")) == 32


def test_labels_and_secrets_give_independent_keys() -> None:
    keys = {
        derive_key(SECRET, label) for label in (LABEL_ACCESS_JWT, LABEL_CSRF, LABEL_LOGIN_ATTEMPTS)
    }
    assert len(keys) == 3
    assert derive_key(SECRET + "x", LABEL_CSRF) not in keys


def test_never_the_raw_secret() -> None:
    assert SECRET.encode() not in derive_key(SECRET, LABEL_CSRF, 64)
    assert derive_key(SECRET, LABEL_CSRF) != SECRET.encode()[:32]


def test_longer_output_is_supported() -> None:
    assert len(derive_key(SECRET, "x", 80)) == 80
