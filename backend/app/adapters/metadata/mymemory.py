"""MyMemory translator (public API, no key): English to Brazilian Portuguese, the last resort.

Contract used (verified against the live service): `GET https://api.mymemory.translated.net/get?q=
..&langpair=en|pt-BR` answers `{"responseData":{"translatedText","match"},"quotaFinished":false,
"responseStatus":200,...}`. A request holds about 500 bytes and the anonymous quota is small (about
5000 characters per day per address). No e-mail or `de` parameter is ever sent.

The synopsis is cut at a sentence end, translated in pieces of at most 400 bytes and put back
together ONLY if every piece is trustworthy: a quota/limit answer (flag, status or the service's
warning text), a non-200 status, a weak match, an empty or identical text or a runaway size stops
everything and the caller keeps the English original. After a quota answer the translator stays
quiet for six hours so the quota is not hammered.
"""

import time
from collections.abc import Callable
from urllib.parse import urlencode

from app.adapters.metadata._json import as_dict, as_text
from app.domain.errors import ExternalFetchError
from app.domain.metadata import chunk_for_translation, fix_missing_sentence_space, valid_translation
from app.ports.http_gateway import HttpGateway

ENDPOINT = "https://api.mymemory.translated.net/get"
LANGPAIR = "en|pt-BR"
MAX_CHUNKS = 8
MIN_MATCH = 0.5
QUIET_SECONDS = 6 * 3600
_WARNING_MARKERS = ("MYMEMORY WARNING", "QUOTA", "INVALID", "PLEASE SELECT")


class MyMemoryTranslator:
    def __init__(
        self, gateway: HttpGateway, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._gateway = gateway
        self._clock = clock
        self._quiet_until = 0.0

    def translate(self, text: str) -> str | None:
        if self._clock() < self._quiet_until:
            return None
        chunks = chunk_for_translation(text)
        if not chunks or len(chunks) > MAX_CHUNKS:
            return None
        pieces: list[str] = []
        for chunk in chunks:
            piece = self._translate_one(chunk)
            if piece is None:
                return None  # all or nothing: never a half-translated synopsis
            pieces.append(piece)
        return fix_missing_sentence_space(" ".join(pieces))

    def _stop_for_a_while(self) -> None:
        self._quiet_until = self._clock() + QUIET_SECONDS

    def _translate_one(self, chunk: str) -> str | None:
        query = urlencode([("q", chunk), ("langpair", LANGPAIR)])
        try:
            body = as_dict(self._gateway.get_json(f"{ENDPOINT}?{query}"))
        except ExternalFetchError as exc:
            if exc.reason in {"rate_limited", "bad_status"}:
                self._stop_for_a_while()
            return None
        status = body.get("responseStatus")
        if body.get("quotaFinished") is True or str(status) == "429":
            self._stop_for_a_while()
            return None
        if str(status) != "200":
            return None
        data = as_dict(body.get("responseData"))
        translated = as_text(data.get("translatedText"), 2000)
        if translated is None:
            return None
        if any(marker in translated.upper() for marker in _WARNING_MARKERS):
            self._stop_for_a_while()  # the service's quota warning arrives as the "translation"
            return None
        match = data.get("match")
        if isinstance(match, int | float) and not isinstance(match, bool) and match < MIN_MATCH:
            return None
        return translated if valid_translation(chunk, translated) else None
