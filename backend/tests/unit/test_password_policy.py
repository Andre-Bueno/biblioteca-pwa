import pytest
from app.domain.password_policy import PasswordPolicyError, validate_password
from app.domain.user import InvalidUsernameError, normalize_username


def test_accepts_good_password() -> None:
    validate_password("correct horse battery", "alice")


def test_length_boundaries() -> None:
    validate_password("Zq7!kXm2Zq7!", "alice")  # exactly 12
    validate_password("Zq7!kXm2" * 16, "alice")  # exactly 128
    with pytest.raises(PasswordPolicyError):
        validate_password("Zq7!kXm2Zq7", "alice")  # 11
    with pytest.raises(PasswordPolicyError):
        validate_password("Zq7!kXm2" * 16 + "x", "alice")  # 129


def test_rejects_password_equal_to_username_case_insensitive() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password("Administrator-Account", "administrator-account")


def test_rejects_common_password() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password("Password1234", "bob")


def test_rejects_repetitive_password() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password("ababababababab", "bob")


@pytest.mark.parametrize("raw", ["ab", "a" * 65, "has space", "-lead", "bad/char", "\u00fcn\u00ef"])
def test_invalid_usernames(raw: str) -> None:
    with pytest.raises(InvalidUsernameError):
        normalize_username(raw)


def test_username_normalized() -> None:
    assert normalize_username("  Alice.Doe_1 ") == "alice.doe_1"


def test_error_message_does_not_contain_password() -> None:
    secret = "tiny-S3cret"
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password(secret, "bob")
    assert secret not in str(exc.value)
