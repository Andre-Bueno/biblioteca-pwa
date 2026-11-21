"""Port for the automatic translation of a synopsis (interface only)."""

from typing import Protocol


class TextTranslator(Protocol):
    """English to Brazilian Portuguese, as the LAST resort for a description.

    Only an already sanitized public synopsis is ever passed in. Returns None whenever a
    trustworthy translation is not available (quota used up, service down, suspicious answer): the
    caller then keeps the original. Never raises.
    """

    def translate(self, text: str) -> str | None: ...
