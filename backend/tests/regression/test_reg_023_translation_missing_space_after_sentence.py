"""Bug: MyMemory sometimes glues sentences together: `Apocalipse".Mas quando...` (seen in the real
test of the Omniscient Reader series). Cause: the service drops the space after the sentence end.
Fix: a post-processing step inserts one space only where it is safe (see
`fix_missing_sentence_space`). Decision on abbreviations: `Sr.Silva` / `etc.Mas` DO get a space."""

import pytest
from app.adapters.metadata.mymemory import MyMemoryTranslator
from app.domain.metadata import fix_missing_sentence_space

from metadata_fakes import FakeGateway, mymemory_answer

REAL = 'sua webnovel favorita, "Três Maneiras de Sobreviver ao Apocalipse".Mas quando o romance'


def test_reg_023_the_real_case_gets_its_space() -> None:
    fixed = fix_missing_sentence_space(REAL)
    assert 'Apocalipse". Mas quando' in fixed
    assert fixed.count("  ") == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Fim.Começo", "Fim. Começo"),
        ("Será?Sim", "Será? Sim"),
        ("Não!Ótimo", "Não! Ótimo"),
        ('Disse "sim."Então', 'Disse "sim." Então'),
        ("(ver isso.)Depois", "(ver isso.) Depois"),
        ("etc.Mas", "etc. Mas"),  # decision: abbreviations glued to a capital get the space
        ("Sr.Silva", "Sr. Silva"),
    ],
)
def test_reg_023_inserts_exactly_one_space(raw: str, expected: str) -> None:
    assert fix_missing_sentence_space(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Custa 3.5 reais",
        "Versão 3.Beta",  # a digit before the mark
        "Os U.S.A. venceram",
        "Os U.S.A.Também",  # acronym glued: untouched (previous char is uppercase)
        "Espere...Mas",  # ellipsis
        "visite site.com agora",
        "arquivo.txt e Site.com",  # next char lowercase after the dot
        "veja www.exemplo.Com hoje",
        "veja https://exemplo.org/a.Mas ok",
        "escreva a joao.Silva@exemplo.com por favor",
        "Já tem espaço. Mas sim",
        "",
        "sem pontuação Mas",
    ],
)
def test_reg_023_leaves_everything_else_alone(text: str) -> None:
    assert fix_missing_sentence_space(text) == text


def test_reg_023_applied_to_the_translator_output() -> None:
    gateway = FakeGateway()
    gateway.route("mymemory", mymemory_answer('Ele leu "Apocalipse".Mas nada mudou aqui para ele.'))
    out = MyMemoryTranslator(gateway).translate("He read it. But nothing changed here for him.")
    assert out == 'Ele leu "Apocalipse". Mas nada mudou aqui para ele.'
