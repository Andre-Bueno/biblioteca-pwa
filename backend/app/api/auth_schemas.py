"""HTTP schemas for /api/v1/auth. Strict (no extra fields, no type coercion) with size limits."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.user import User

MAX_USERNAME_INPUT = 128
MAX_PASSWORD_INPUT = 1024  # hard cap on what is ever hashed; the policy (<=128) applies later


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LoginRequest(_Strict):
    username: str = Field(min_length=1, max_length=MAX_USERNAME_INPUT)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_INPUT, repr=False)


class ChangePasswordRequest(_Strict):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_INPUT, repr=False)
    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_INPUT, repr=False)


class UserOut(BaseModel):
    """Public view of an account. Never includes the hash or timestamps used for security."""

    model_config = ConfigDict(extra="forbid")

    id: str
    username: str
    role: str
    theme_pref: str

    @classmethod
    def from_domain(cls, user: User) -> "UserOut":
        return cls(
            id=user.id, username=user.username, role=user.role.value, theme_pref=user.theme_pref
        )
