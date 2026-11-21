"""REG-012 (FIND-2026-007): predictable passwords passed the policy.

Bug: only length, 5 distinct characters, a 20-entry list and `password == username` were checked,
so `user1user1user1` (repeated username) or `qwertyqwerty` were accepted. Fix (no new dependency):
reject passwords that contain the username (or its reverse), that are a short block repeated, or
that are a trivial sequence (alphabet, digits, keyboard rows, ascending or descending).
"""

import pytest
from app.domain.password_policy import PasswordPolicyError, validate_password


@pytest.mark.parametrize(
    "password",
    [
        "user1user1user1",  # username repeated
        "xxUSER1yyzz9812",  # contains the username (case-insensitive)
        "abc1resuXYZ78wq",  # contains the username reversed
        "passwordpassword",  # block repeated
        "qwertyqwerty",  # block repeated
        "abcabcabcabcabc",  # block repeated
        "abcdefghijklmnop",  # alphabet run
        "zyxwvutsrqponm",  # descending run
        "123456789012345",  # digit run
        "098765432109876",  # descending digits
        "qwertyuiopasdfgh",  # keyboard row
        "asdfghjklzxcvbnm",  # keyboard rows
    ],
)
def test_predictable_passwords_are_rejected(password: str) -> None:
    with pytest.raises(PasswordPolicyError) as info:
        validate_password(password, "user1")
    assert password not in str(info.value)


@pytest.mark.parametrize(
    "password",
    [
        "correct horse battery staple",
        "another good passphrase",
        "Tr0ub4dor&3-and-more",
        "blue-sky-over-the-lake-9",
    ],
)
def test_reasonable_passwords_are_still_accepted(password: str) -> None:
    validate_password(password, "user1")


def test_short_usernames_do_not_reject_everything() -> None:
    validate_password("correct horse battery staple", "bob")  # 'bob' is not inside
    validate_password("Tr0ub4dor&3-and-more", "tr")  # usernames shorter than 3 are ignored here
