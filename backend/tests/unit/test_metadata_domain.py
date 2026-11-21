"""Pure rules: description sanitizing, title matching, language choice, image sniffing."""

import pytest
from app.domain.metadata import (
    MAX_DESCRIPTION_LENGTH,
    MetadataCandidate,
    chunk_for_translation,
    has_comic_evidence,
    normalize_title,
    pick_best,
    pick_description,
    sanitize_description,
    score_candidate,
    sniff_image,
    title_similarity,
    truncate_for_translation,
    valid_translation,
)

from metadata_fakes import good_jpeg, good_png, good_webp


def _c(
    title: str, *, alts: tuple[str, ...] = (), ident: str = "1", year: int | None = None
) -> MetadataCandidate:
    return MetadataCandidate(
        provider="mangadex", external_id=ident, title=title, alt_titles=alts, year=year
    )


# ------------------------------------------------------------ sanitize_description


def test_html_is_removed_and_the_result_is_plain_text() -> None:
    raw = "Hello <b>world</b><script>alert(1)</script><img src=x onerror=alert(1)>!<br>Next"
    text = sanitize_description(raw)
    assert text == "Hello world !\nNext"
    for bad in ("<", ">", "script", "alert", "onerror"):
        assert bad not in text


def test_entity_encoded_tags_do_not_come_back_as_markup() -> None:
    text = sanitize_description(
        "&lt;script&gt;alert(1)&lt;/script&gt;ok &lt;b&gt;x&lt;/b&gt; &amp; y"
    )
    assert "<" not in text and ">" not in text and "script" not in text
    assert text.endswith("& y")


def test_markdown_links_images_and_emphasis_become_plain_text() -> None:
    raw = "![alt](http://evil/x.png) [click](javascript:alert(1)) **bold** __b2__ ~~gone~~ `code`"
    text = sanitize_description(raw)
    assert text == "alt click bold b2 gone code"
    assert "http" not in text and "javascript" not in text and "](" not in text


def test_anilist_spoiler_marks_and_headings_are_dropped() -> None:
    assert sanitize_description("# Title\n~!spoiler!~") == "Title\nspoiler"


def test_control_and_bidi_characters_are_removed() -> None:
    raw = "a\x00b\x07c‮d‬e⁦f⁩g​h\x1b[31mi\x7fj﻿k"
    text = sanitize_description(raw)
    assert text == "abcdefgh[31mijk"
    assert all(ch == "\n" or ch.isprintable() for ch in text)


def test_blank_lines_are_normalized_and_text_is_trimmed() -> None:
    assert sanitize_description("  a  \r\n\r\n\r\n\r\n\t b \n\n\n\n c  \n") == "a\n\nb\n\nc"


def test_length_is_capped_without_trailing_space() -> None:
    text = sanitize_description("word " * 5000)
    assert len(text) <= MAX_DESCRIPTION_LENGTH and not text.endswith(" ")
    assert sanitize_description("x" * 10, limit=4) == "xxxx"


def test_pathological_input_is_fast_and_bounded() -> None:
    nasty = "<" * 50_000 + "[" * 50_000 + "a" * 100_000
    assert len(sanitize_description(nasty)) <= MAX_DESCRIPTION_LENGTH


def test_empty_after_cleaning_is_empty_string() -> None:
    assert sanitize_description("<script>x</script> \x00 ") == ""


# ------------------------------------------------------------ pick_description


def test_description_prefers_pt_br_then_pt_then_en() -> None:
    descs = {"en": "english", "pt": "portugues", "pt-br": "brasileiro"}
    assert pick_description(descs, ("pt-br", "pt", "en")) == ("brasileiro", "pt-br")
    del descs["pt-br"]
    assert pick_description(descs, ("pt-br", "pt", "en")) == ("portugues", "pt")
    del descs["pt"]
    assert pick_description(descs, ("pt-br", "pt", "en")) == ("english", "en")
    assert pick_description({"ja": "x"}, ("pt-br", "pt", "en")) is None


def test_description_skips_a_language_that_is_empty_after_cleaning() -> None:
    descs = {"pt-br": "<script>x</script>", "en": "fallback"}
    assert pick_description(descs, ("pt-br", "en")) == ("fallback", "en")


def test_description_language_keys_are_normalized() -> None:
    assert pick_description({"PT_BR": "oi"}, ("pt-br",)) == ("oi", "pt-br")


# ------------------------------------------------------------ title matching


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Omniscient Reader's Viewpoint", "omniscient readers viewpoint"),
        ("  Ação  &  Aventura!! ", "acao aventura"),
        ("Berserk v03", "berserk"),
        ("Berserk Vol. 12", "berserk"),
        ("Saga Capitulo 100", "saga"),
        ("One-Punch Man (2012)", "one punch man 2012"),
        ("v03", "v03"),  # never normalize to nothing
        ("Re:Zero", "re zero"),
    ],
)
def test_normalize_title(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


def test_score_exact_alt_and_fuzzy_levels() -> None:
    cand = _c("Jeonjijeok Dokja Sijeom", alts=("Omniscient Reader",))
    assert score_candidate("Jeonjijeok dokja sijeom", cand) == 1.0
    assert score_candidate("Omniscient Reader v02", cand) == 0.97
    fuzzy = score_candidate("Jeonjijeok Dokja Sijeon", cand)
    assert 0.5 < fuzzy < 0.95  # a near miss never reaches an exact score...
    assert pick_best("Jeonjijeok Dokja Sijeon", [cand]) is None  # ...nor the (conservative) bar
    assert score_candidate("Something Else Entirely", cand) < 0.5


def test_best_candidate_must_clear_the_threshold() -> None:
    assert pick_best("Naruto", [_c("Boruto: Naruto Next Generations")]) is None
    assert pick_best("Naruto", []) is None
    assert pick_best("", [_c("Naruto")]) is None
    match = pick_best("Naruto", [_c("Boruto"), _c("Naruto", ident="2")])
    assert match is not None and match.external_id == "2"


def test_equal_matches_are_broken_by_oldest_year_then_by_relevance() -> None:
    twins = [_c("Berserk", ident="1"), _c("Berserk", ident="2")]
    first = pick_best("Berserk", twins)
    assert first is not None and first.external_id == "1"  # no year: the source's own order
    dated = [_c("Berserk", ident="1", year=2010), _c("Berserk", ident="2", year=1989)]
    older = pick_best("Berserk", dated)
    assert older is not None and older.external_id == "2"
    undated_first = [_c("Berserk", ident="1"), _c("Berserk", ident="2", year=1989)]
    chosen = pick_best("Berserk", undated_first)
    assert chosen is not None and chosen.external_id == "2"  # a known year beats an unknown one


def test_strict_mode_refuses_a_near_tie() -> None:
    twins = [_c("Berserk", ident="1"), _c("Berserk", ident="2")]
    assert pick_best("Berserk", twins, tiebreak=False) is None
    assert pick_best("Berserk", twins[:1], tiebreak=False) is not None


@pytest.mark.parametrize(
    "title",
    [
        "Omniscient Reader's Viewpoint (Book Version)",
        "Omniscient Reader's Viewpoint - Blind (Doujinshi)",
        "Omniscient Reader's Viewpoint Fanbook",
        "Omniscient Reader's Viewpoint Anthology",
        "Omniscient Reader's Viewpoint (Light Novel)",
    ],
)
def test_editions_are_penalized_when_the_searched_title_lacks_the_marker(title: str) -> None:
    edition = _c(title, alts=("Omniscient Reader's Viewpoint",))
    assert score_candidate("Omniscient Reader's Viewpoint", edition) < 0.85
    assert pick_best("Omniscient Reader's Viewpoint", [edition]) is None
    # ...but looking for the edition itself is fine
    assert score_candidate(title, edition) == 1.0


def test_the_real_orv_case_picks_the_work_not_the_editions() -> None:
    """MangaDex answered four entries for this title; only the 4th is the work (title in
    romanized Korean, the library title only as an alternative title)."""
    book = _c(
        "Omniscient Reader's Viewpoint (Book Version)",
        alts=("전지적 독자 시점", "Omniscient Reader's Viewpoint"),
        ident="46392cb3",
    )
    blind = _c(
        "Omniscient Reader's Viewpoint - Blind (Doujinshi)",
        alts=("블라인드",),
        ident="7cf4",
        year=2020,
    )
    maid = _c(
        "Omniscient Reader's Viewpoint  - Maid, Make, Mine (Doujinshi)", ident="e806", year=2019
    )
    work = _c(
        "Jeonjijeok Dokja Sijeom",
        alts=("Omniscient Reader's Viewpoint", "ORV", "전독시", "Lecteur omniscient"),
        ident="9a414441",
        year=2020,
    )
    chosen = pick_best("Omniscient Reader's Viewpoint", [book, blind, maid, work])
    assert chosen is not None and chosen.external_id == "9a414441"


def test_several_names_of_one_work_count_as_the_best_one() -> None:
    cand = _c("Jeonjijeok Dokja Sijeom")
    assert score_candidate("Omniscient Reader's Viewpoint", cand) < 0.85
    assert (
        score_candidate(["Omniscient Reader's Viewpoint", "Jeonjijeok Dokja Sijeom"], cand) == 1.0
    )


def test_a_candidate_older_than_the_work_is_incoherent() -> None:
    old = _c("Berserk", year=1950)
    ok = _c("Berserk", ident="2", year=1990)
    assert pick_best("Berserk", [old], work_year=1989) is None
    chosen = pick_best("Berserk", [old, ok], work_year=1989)
    assert chosen is not None and chosen.external_id == "2"
    assert pick_best("Berserk", [_c("Berserk")], work_year=1989) is not None  # unknown year: ok


def test_title_similarity_and_comic_evidence() -> None:
    assert title_similarity("Berserk (mangá)", "Berserk mangá") == 1.0
    assert title_similarity("Boruto", "Naruto") < 0.8
    for yes in (
        "série de manhwa sul-coreana",
        "Mangá japonês",
        "história em quadrinhos",
        "A webtoon about",
        "Comics & Graphic Novels",
        "web novel sul-coreana",
    ):
        assert has_comic_evidence(yes), yes
    for no in ("série de televisão americana", "cantora e atriz sul-coreana", "", "mangueira"):
        assert not has_comic_evidence(no), no


# ------------------------------------------------------------ translation helpers


def test_truncate_cuts_at_a_sentence_end() -> None:
    text = "First sentence. Second sentence. Third one is long enough to be cut off here"
    assert truncate_for_translation(text, 40) == "First sentence. Second sentence."
    assert truncate_for_translation("short", 40) == "short"
    assert truncate_for_translation("x" * 100, 40) == "x" * 40  # no sentence end: hard cut


def test_chunks_respect_the_byte_limit_and_keep_all_the_text() -> None:
    text = "Uma frase com acentuação. " * 60 + "\n" + "word " * 300 + "x" * 1000
    chunks = chunk_for_translation(text, 400)
    assert chunks and all(len(c.encode()) <= 400 for c in chunks)
    joined = " ".join(chunks)
    assert joined.count("Uma frase com acentuação.") == 60
    assert chunk_for_translation("") == [] and chunk_for_translation(" \n ") == []


def test_a_single_huge_word_is_cut_never_sent_whole() -> None:
    chunks = chunk_for_translation("é" * 5000, 400)
    assert all(len(c.encode()) <= 400 for c in chunks)


@pytest.mark.parametrize(
    ("original", "translated", "ok"),
    [
        ("Hello there my friend.", "Olá meu amigo.", True),
        ("Hello there my friend.", "hello there my friend.", False),  # identical
        ("Hello there my friend.", "", False),
        ("Hello there my friend.", "   ", False),
        ("Hello there my friend.", "x", False),  # far too short
        ("Hello", "Olá " * 40, False),  # runaway
        (
            "Hello there my friend.",
            "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY",
            False,
        ),
    ],
)
def test_valid_translation(original: str, translated: str, ok: bool) -> None:
    # (the quota warning is also stopped by the adapter; its size just happens to be refused here)
    assert valid_translation(original, translated) is ok


def test_an_exact_title_beats_an_exact_alternative_title_of_another_work() -> None:
    mixed = [_c("Other", alts=("Berserk",), ident="1"), _c("Berserk", ident="2")]
    chosen = pick_best("Berserk", mixed)
    assert chosen is not None and chosen.external_id == "2"
    # The same work listed twice is not ambiguity.
    assert pick_best("Berserk", [_c("Berserk", ident="1"), _c("Berserk", ident="1")]) is not None


def test_a_prefix_of_a_longer_title_is_not_a_match() -> None:
    assert pick_best("Omniscient Reader", [_c("Omniscient Reader's Viewpoint")]) is None


# ------------------------------------------------------------ image sniffing


def test_sniff_accepts_real_shapes_and_derives_type_from_bytes() -> None:
    assert sniff_image(good_jpeg()) == ("image/jpeg", "jpg")
    assert sniff_image(good_png()) == ("image/png", "png")
    assert sniff_image(good_webp()) == ("image/webp", "webp")


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<html><script>alert(1)</script></html>",
        b"GIF89a" + b"\x00" * 40,
        b"\xff\xd8\xff\xe0" + b"<script>alert(1)</script>",  # JPEG header + HTML, no EOI
        good_jpeg() + b"<script>alert(1)</script>",  # EOI is not last: polyglot tail
        good_png() + b"<script>alert(1)</script>",  # IEND is not last
        good_png()[:20],  # truncated
        b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 100,  # RIFF size disagrees with length
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 30,  # signature without IHDR/IEND
    ],
)
def test_sniff_rejects_non_images_and_polyglots(data: bytes) -> None:
    assert sniff_image(data) is None
