"""Password policy. Messages never echo the password."""

from app.domain.user import UserError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
MIN_DISTINCT_CHARS = 5

COMMON_PASSWORDS = frozenset(
    {
        "password1234",
        "password12345",
        "passw0rd1234",
        "123456789012",
        "1234567890123",
        "12345678901234",
        "qwertyuiop12",
        "qwertyuiopas",
        "qwerty123456",
        "administrator",
        "iloveyou1234",
        "letmein12345",
        "changeme1234",
        "welcome12345",
        "abcdefghijkl",
        "abc123456789",
        "000000000000",
        "111111111111",
        "senha1234567",
        "mudar1234567",
    }
)


# Trivial sequences: a password that is a run inside one of these (or its reverse) is rejected.
# Keyboard rows are listed as typed (top to bottom), plus the digits and the alphabet.
_SEQUENCES = tuple(
    s * 3
    for s in (
        "abcdefghijklmnopqrstuvwxyz",
        "0123456789",
        "qwertyuiopasdfghjklzxcvbnm",
        "1234567890qwertyuiop",
    )
)
MIN_USERNAME_LENGTH_CHECKED = 3  # shorter fragments would reject far too many good passwords
MIN_REPEATED_BLOCK_LENGTH = 8  # a repeated block carries only its own entropy: keep it long
# Words that are weak even when repeated or padded (e.g. "passwordpassword").
_COMMON_BASES = frozenset(
    {
        "password",
        "passw0rd",
        "qwerty",
        "qwertyuiop",
        "letmein",
        "welcome",
        "admin",
        "administrator",
        "iloveyou",
        "changeme",
        "abc123",
        "123456",
        "senha",
        "mudar",
        "dragon",
        "monkey",
        "master",
        "login",
    }
)


class PasswordPolicyError(UserError):
    pass


def _repeated_unit(value: str) -> str | None:
    """Shortest block that, repeated (last copy possibly cut), makes up `value`; None if none."""
    for n in range(1, len(value) // 2 + 1):
        if (value[:n] * (len(value) // n + 1))[: len(value)] == value:
            return value[:n]
    return None


def _is_trivial_sequence(value: str) -> bool:
    return any(value in seq or value in seq[::-1] for seq in _SEQUENCES)


def _is_weak_repetition(value: str) -> bool:
    unit = _repeated_unit(value)
    if unit is None:
        return False
    return (
        len(unit) < MIN_REPEATED_BLOCK_LENGTH or unit in _COMMON_BASES or _is_trivial_sequence(unit)
    )


def validate_password(password: str, username: str) -> None:
    """Raise PasswordPolicyError if the password is not acceptable.

    Messages are generic and never echo the password. No wordlist is shipped (it would need a
    data file or dependency); instead the structural patterns attackers try first are refused:
    the username (or its reverse) inside the password, a weak block repeated (short, common word
    or sequence), a keyboard/alphabet/digit sequence, and a short list of very common passwords.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must have at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must have at most {MAX_PASSWORD_LENGTH} characters")
    lowered = password.lower()
    name = username.strip().lower()
    if lowered == name:
        raise PasswordPolicyError("password must not be equal to the username")
    if len(name) >= MIN_USERNAME_LENGTH_CHECKED and (name in lowered or name[::-1] in lowered):
        raise PasswordPolicyError("password must not contain the username")
    if lowered in COMMON_PASSWORDS:
        raise PasswordPolicyError("password is too common")
    if len(set(password)) < MIN_DISTINCT_CHARS:
        raise PasswordPolicyError("password is too repetitive")
    if _is_weak_repetition(lowered):
        raise PasswordPolicyError("password is too repetitive")
    if _is_trivial_sequence(lowered):
        raise PasswordPolicyError("password is too predictable")
