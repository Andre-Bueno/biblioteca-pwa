"""Use cases: enrich series with a cover and a Portuguese description from public sources.

Fusion: every WORK source (MangaDex, AniList) gives its own best match (same thresholds and margins,
editions such as "Book Version" or "(Doujinshi)" penalized); the matches are combined:
- cover, title at the source and "source" = the first match (in configured order, i.e. quality
  order) whose cover could be downloaded;
- description = the best language across all matches: Portuguese from a work source, then a STRONG
  match on a description-only source (Wikipedia, Google Books; attribution kept), then the
  English text automatically translated (marked "translated", attribution = the English source),
  and as the very last resort the English text itself.

Automatic runs only touch series in state `none` (and `not_found` after a week); `manual` is never
overwritten by them (the write itself is conditional on the CURRENT state, so even a manual edit
made while a run is in flight wins). Only the cleaned series title (and, to the translation
service, an already sanitized public synopsis) is ever sent out. A source that fails never raises
out of a run: it is counted and the next one is tried. The cover is downloaded once, staged in a
temporary file, committed only after the database accepted the change.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import timedelta

from app.domain.errors import ExternalFetchError, InvalidMetadata, ItemNotFound, MetadataDisabled
from app.domain.item import ItemType
from app.domain.library import sanitize_title
from app.domain.metadata import (
    MAX_QUERY_LENGTH,
    PROVIDER_LABELS,
    STRONG_THRESHOLD,
    EnrichReport,
    MetadataCandidate,
    MetadataUpdate,
    ResolvedDescription,
    normalize_language,
    pick_best,
    pick_description,
    sanitize_description,
    score_candidate,
    truncate_for_translation,
    valid_translation,
)
from app.domain.series import MetadataState, Series, short_description
from app.ports.clock import Clock
from app.ports.cover_store import CoverStore
from app.ports.http_gateway import HttpGateway
from app.ports.metadata_provider import MetadataProvider
from app.ports.series_repository import SeriesRepository
from app.ports.translator import TextTranslator

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 10
PER_PROVIDER = 5
MAX_EXTRA_NAMES = 10  # alternative titles of the work used to match description-only sources
_NONE = MetadataState.NONE.value
_MATCHED = MetadataState.MATCHED.value
_MANUAL = MetadataState.MANUAL.value
_NOT_FOUND = MetadataState.NOT_FOUND.value
_AUTO_STATES = (_NONE, _NOT_FOUND)
_ALL_STATES = tuple(s.value for s in MetadataState)


@dataclass(frozen=True, slots=True)
class MetadataConfig:
    enabled: bool = True
    languages: tuple[str, ...] = ("pt-br", "pt", "en")
    max_per_run: int = 25
    recheck_not_found_after: timedelta = timedelta(days=7)
    translate_enabled: bool = True


@dataclass(frozen=True, slots=True)
class CandidateView:
    provider: str
    external_id: str
    title: str
    year: int | None
    description: str | None  # sanitized, at most 300 characters
    cover_available: bool
    url: str | None  # https page at the source


def _https(url: str | None) -> str | None:
    return url if url is not None and url.startswith("https://") and len(url) <= 512 else None


def _label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider)


class MetadataService:
    def __init__(
        self,
        series: SeriesRepository,
        providers: Sequence[MetadataProvider],
        gateway: HttpGateway,
        covers: CoverStore,
        clock: Clock,
        config: MetadataConfig,
        translator: TextTranslator | None = None,
    ) -> None:
        self._series = series
        self._providers = tuple(providers) if config.enabled else ()
        self._work = tuple(p for p in self._providers if not p.description_only)
        self._describers = tuple(p for p in self._providers if p.description_only)
        self._gateway = gateway
        self._covers = covers
        self._clock = clock
        self._cfg = config
        self._translator = translator if config.enabled and config.translate_enabled else None
        langs = tuple(normalize_language(lang) for lang in config.languages)
        self._pt = tuple(lang for lang in langs if lang.startswith("pt"))
        self._other = tuple(lang for lang in langs if not lang.startswith("pt"))

    # -- guards ----------------------------------------------------------

    def require_enabled(self) -> None:
        """Raises `MetadataDisabled` when no external lookup may be made."""
        if not self._cfg.enabled or not self._providers:
            raise MetadataDisabled

    def _get(self, series_id: str) -> Series:
        series = self._series.get(series_id)
        if series is None:
            raise ItemNotFound
        return series

    # -- automatic enrichment -------------------------------------------

    def enrich_all(self, *, force: bool = False, series_id: str | None = None) -> EnrichReport:
        """One bounded run (`max_per_run` series)."""
        self.require_enabled()
        report = EnrichReport()
        if series_id is not None:
            targets = [self._get(series_id)]
        else:
            states = (*_AUTO_STATES, _MATCHED) if force else _AUTO_STATES
            cutoff = None if force else self._clock.now() - self._cfg.recheck_not_found_after
            targets = self._series.list_for_enrichment(states, cutoff, self._cfg.max_per_run)
        for series in targets[: self._cfg.max_per_run]:
            try:
                outcome = self._enrich_one(series, force)
            except Exception as exc:  # one series must never stop the run (nor the scan)
                logger.warning("Metadata enrichment failed for a series (%s)", type(exc).__name__)
                report.errors += 1
                continue
            if outcome == "matched":
                report.matched += 1
            elif outcome == "not_found":
                report.not_found += 1
            else:
                report.skipped += 1
        return report

    def _eligible(self, series: Series, force: bool) -> bool:
        state = series.metadata_state
        if state == _MANUAL:
            return False  # never, not even with force
        if state == _NONE:
            return True
        if state == _NOT_FOUND:
            checked = series.metadata_checked_at
            cutoff = self._clock.now() - self._cfg.recheck_not_found_after
            return force or checked is None or checked < cutoff
        return force  # matched

    def _complete(self, accepted: Sequence[MetadataCandidate]) -> bool:
        """Enough to stop asking more work sources: a cover and a Portuguese description."""
        has_cover = any(c.cover_url for c in accepted)
        has_pt = any(pick_description(c.descriptions, self._pt) for c in accepted)
        return has_cover and has_pt

    def _only_books(self, series: Series) -> bool:
        chapters = self._series.list_chapters(series.id)
        return bool(chapters) and all(c.type is ItemType.BOOK for c in chapters)

    def _enrich_one(self, series: Series, force: bool) -> str:
        if not self._eligible(series, force):
            return "skipped"
        if self._only_books(series):
            return "skipped"  # nothing leaves the server for a series of books; state stays `none`
        now = self._clock.now()
        answered = 0
        accepted: list[MetadataCandidate] = []
        for provider in self._work:
            try:
                candidates = provider.search(series.title, self._cfg.languages)
            except ExternalFetchError as exc:
                logger.info("Metadata source failed: %s (%s)", provider.name, exc.reason)
                continue
            answered += 1
            best = pick_best(series.title, candidates)
            if best is not None:
                accepted.append(best)
            if self._complete(accepted):
                break
        if not accepted:
            if answered == 0:
                raise ExternalFetchError("unavailable")  # nothing learned: retry next run
            if series.metadata_state != _MATCHED:  # a forced re-check never downgrades a match
                self._series.update_metadata(
                    series.id, MetadataUpdate(state=_NOT_FOUND, checked_at=now), _AUTO_STATES
                )
            return "not_found"
        allowed = (*_AUTO_STATES, _MATCHED) if force else _AUTO_STATES
        return "matched" if self._apply_work(series, accepted, _MATCHED, allowed) else "skipped"

    # -- description (fusion) -------------------------------------------

    def _first(
        self, accepted: Sequence[MetadataCandidate], langs: Sequence[str]
    ) -> tuple[str, str, MetadataCandidate] | None:
        for lang in langs:  # language priority first, then the sources in quality order
            for candidate in accepted:
                picked = pick_description(candidate.descriptions, (lang,))
                if picked is not None:
                    return picked[0], picked[1], candidate
        return None

    def _translate(self, text: str) -> str | None:
        if self._translator is None:
            return None
        original = truncate_for_translation(text)
        try:
            translated = self._translator.translate(original)
        except ExternalFetchError:
            return None
        if translated is None:
            return None
        clean = sanitize_description(translated)  # sanitized again: it is text from the network
        return clean if clean and valid_translation(original, clean) else None

    def _from_describers(
        self, names: Sequence[str], work_year: int | None
    ) -> ResolvedDescription | None:
        """Portuguese text from an encyclopedia / book catalog, only on a STRONG match."""
        for provider in self._describers:
            try:
                candidates = provider.search(names[0], self._cfg.languages)
            except ExternalFetchError as exc:
                logger.info("Metadata source failed: %s (%s)", provider.name, exc.reason)
                continue
            best = pick_best(
                names, candidates, threshold=STRONG_THRESHOLD, tiebreak=False, work_year=work_year
            )
            if best is None:
                continue
            picked = pick_description(best.descriptions, self._pt)
            if picked is not None:
                return ResolvedDescription(
                    picked[0], picked[1], "source", _label(best.provider), _https(best.source_url)
                )
        return None

    def _resolve_description(
        self, accepted: Sequence[MetadataCandidate], names: Sequence[str]
    ) -> ResolvedDescription | None:
        # 1. Portuguese written by a work source.
        found = self._first(accepted, self._pt)
        if found is not None:
            text, lang, cand = found
            return ResolvedDescription(
                text, lang, "source", _label(cand.provider), _https(cand.source_url)
            )
        # 2. Portuguese from a description-only source (strong match only).
        years = [c.year for c in accepted if c.year is not None]
        resolved = self._from_describers(names, min(years) if years else None)
        if resolved is not None:
            return resolved
        # 3. The other languages: English is translated (marked), anything else kept as is.
        found = self._first(accepted, self._other)
        if found is None:
            return None
        text, lang, cand = found
        if lang.startswith("en"):
            translated = self._translate(text)
            if translated is not None:
                return ResolvedDescription(
                    translated,
                    self._pt[0] if self._pt else "pt-br",
                    "translated",
                    _label(cand.provider),
                    _https(cand.source_url),
                )
        return ResolvedDescription(
            text, lang, "source", _label(cand.provider), _https(cand.source_url)
        )

    # -- shared write ----------------------------------------------------

    def _apply_work(
        self,
        series: Series,
        accepted: Sequence[MetadataCandidate],
        state: str,
        allowed: Sequence[str],
    ) -> bool:
        primary = accepted[0]
        staged = None
        for candidate in accepted:  # quality order: the first cover that downloads wins
            if candidate.cover_url is None:
                continue
            try:
                staged = self._covers.stage(series.id, self._gateway.get_image(candidate.cover_url))
            except (ExternalFetchError, OSError) as exc:
                reason = exc.reason if isinstance(exc, ExternalFetchError) else "storage"
                logger.info("Cover not stored (%s)", reason)
                continue
            primary = candidate  # title and source follow the cover
            break
        names = [series.title, primary.title, *primary.alt_titles[:MAX_EXTRA_NAMES]]
        desc = self._resolve_description(accepted, names)
        update = MetadataUpdate(
            state=state,
            description=None if desc is None else desc.text,
            description_lang=None if desc is None else desc.lang,
            source=primary.provider,
            external_id=primary.external_id,
            source_url=_https(primary.source_url),
            title_original=primary.title[:255],
            cover_path=None if staged is None else staged.rel_path,
            checked_at=self._clock.now(),
            description_origin=None if desc is None else desc.origin,
            description_source_name=None if desc is None else desc.source_name,
            description_source_url=None if desc is None else desc.source_url,
        )
        try:
            written = self._series.update_metadata(series.id, update, allowed)
        except BaseException:
            if staged is not None:
                self._covers.discard(staged)
            raise
        if not written:
            if staged is not None:
                self._covers.discard(staged)
            return False
        if staged is not None:
            try:
                self._covers.commit(staged)
            except OSError:
                logger.warning("Cover could not be saved (OSError)")  # falls back to a chapter
        if series.cover_path and (staged is None or staged.rel_path != series.cover_path):
            self._covers.delete(series.cover_path)
        return True

    @staticmethod
    def _keep(series: Series, **changes: object) -> MetadataUpdate:
        """The series' current metadata as an update (state manual), with `changes` applied."""
        base = MetadataUpdate(
            state=_MANUAL,
            description=series.description,
            description_lang=series.description_lang,
            source=series.metadata_source,
            external_id=series.external_id,
            source_url=series.source_url,
            title_original=series.title_original,
            cover_path=series.cover_path,
            checked_at=series.metadata_checked_at,
            description_origin=series.description_origin,
            description_source_name=series.description_source_name,
            description_source_url=series.description_source_url,
        )
        return replace(base, **changes)  # type: ignore[arg-type]

    # -- admin actions ---------------------------------------------------

    def candidates(self, series_id: str, query: str | None) -> list[CandidateView]:
        """Live search for the admin: at most 10 candidates, best first."""
        self.require_enabled()
        series = self._get(series_id)
        text = (query or "").strip()[:MAX_QUERY_LENGTH]
        text = sanitize_title(text) if text else series.title
        found: list[MetadataCandidate] = []
        failures = 0
        for provider in self._providers:
            try:
                found.extend(provider.search(text, self._cfg.languages)[:PER_PROVIDER])
            except ExternalFetchError as exc:
                failures += 1
                logger.info("Metadata source failed: %s (%s)", provider.name, exc.reason)
        if not found and failures == len(self._providers):
            raise ExternalFetchError("unavailable")
        found.sort(key=lambda c: -score_candidate(text, c))
        return [self._view(c) for c in found[:MAX_CANDIDATES]]

    def _view(self, candidate: MetadataCandidate) -> CandidateView:
        picked = pick_description(candidate.descriptions, self._cfg.languages)
        return CandidateView(
            provider=candidate.provider,
            external_id=candidate.external_id,
            title=candidate.title,
            year=candidate.year,
            description=None if picked is None else short_description(picked[0]),
            cover_available=candidate.cover_url is not None,
            url=_https(candidate.source_url),
        )

    def select(self, series_id: str, provider_name: str, external_id: str) -> Series:
        """Use a chosen candidate (fetched again here, never trusted from the client). A
        description-only source replaces just the description; the cover and source stay."""
        self.require_enabled()
        series = self._get(series_id)
        provider = next((p for p in self._providers if p.name == provider_name), None)
        if provider is None:
            raise ItemNotFound
        match = provider.get(external_id, self._cfg.languages)  # ExternalFetchError propagates
        if match is None:
            raise ItemNotFound
        if provider.description_only:
            picked = pick_description(match.descriptions, self._pt)
            if picked is None:
                raise ItemNotFound
            update = self._keep(
                series,
                description=picked[0],
                description_lang=picked[1],
                checked_at=self._clock.now(),
                description_origin="source",
                description_source_name=_label(match.provider),
                description_source_url=_https(match.source_url),
            )
            self._series.update_metadata(series_id, update, _ALL_STATES)
        elif not self._apply_work(series, [match], _MANUAL, _ALL_STATES):
            raise ItemNotFound
        return self._get(series_id)

    def set_manual(self, series_id: str, title: str | None, description: str | None) -> Series:
        """Manual edit (no network). The displayed title changes; the folder key never does."""
        series = self._get(series_id)
        if title is None and description is None:
            raise InvalidMetadata
        new_title = None
        if title is not None:
            new_title = sanitize_title(title)
            if not title.strip() or (new_title == "Untitled" and title.strip() != "Untitled"):
                raise InvalidMetadata
        changes: dict[str, object] = {"checked_at": self._clock.now(), "title": new_title}
        if description is not None:
            text = sanitize_description(description) or None
            changes |= {
                "description": text,
                "description_lang": None,
                "description_origin": None if text is None else "manual",
                "description_source_name": None,
                "description_source_url": None,
            }
        self._series.update_metadata(series_id, self._keep(series, **changes), _ALL_STATES)
        return self._get(series_id)

    def clear(self, series_id: str) -> Series:
        """Forget description, downloaded cover and source; the state goes back to `none`."""
        series = self._get(series_id)
        self._series.update_metadata(series_id, MetadataUpdate(state=_NONE), _ALL_STATES)
        if series.cover_path:
            self._covers.delete(series.cover_path)
        return self._get(series_id)
