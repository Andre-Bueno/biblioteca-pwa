"""REG-001: SECRET_KEY value leaked in the startup validation error.

Bug: when SECRET_KEY failed validation (e.g. too short), pydantic's ValidationError
included `input_value='...'`, so the (near-)secret ended up in the startup log.
Cause: Settings did not set `hide_input_in_errors=True` in its model config.
"""

import pytest
from app.core.config import Settings
from pydantic import ValidationError

SHORT_KEY = "very-short-leaky-secret"


@pytest.mark.parametrize(
    "key",
    [SHORT_KEY, "abcdefgh" * 4, f"  {SHORT_KEY}-padded-to-be-long-enough-xyz  "],
)
def test_reg_001_secret_key_not_in_error(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setenv("SECRET_KEY", key)
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    exc = info.value
    # Not exc.errors(): that programmatic API always carries `input`; it is never logged by us.
    for text in (str(exc), repr(exc)):
        assert key.strip() not in text
        assert "input_value" not in text
