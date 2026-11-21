# 2026-11-21 · Metadados (capa e descrição) para todos os formatos

## O que foi feito
- Removido o pulo de séries só de livro/EPUB na busca de metadados: `services/metadata_service.py` (`_only_books` e a checagem em `_enrich_one`), `adapters/persistence/series_repository.py` (`list_for_enrichment`) e docstring de `ports/series_repository.py`.
- Busca automática, por série, repositório e busca/seleção manual do admin passam a usar a mesma regra para EPUB, CBZ, CBR, pasta e PDF.

## Escopo
- Backend apenas. Mesmas fontes (lista fixa), mesmos limiares, mesmo `SafeGateway`, sem host novo.
- Sem mudança de API, schema ou frontend.

## Decisões
- Autorizado expressamente pelo dono no chat em 2026-11-21 ("Sim, igualar"). Registrado como emenda do ADR 0015 (texto aceito preservado).
- REG-026 invertido: `test_reg_026_enrichment_skips_series_of_books` virou `test_reg_026_enrichment_does_not_depend_on_format.py`, que afirma que série de EPUB é consultada.
- Risco aceito: casamento por título pode errar livros com título comum; mitigado por estado `manual` e limiares.

## Verificação
- Arquivos conferidos no disco: REG-026 novo existe e o antigo não; `test_book_series_enrichment.py` tem 5 funções (contagem por grep).
- Contagem de backend em `TEST_MAP.md`: 1120 para 1122 funções, 95 arquivos.
- Esta entrega é só de documentação: testes e `scripts/check` não foram executados aqui.

## Pendências
- Mudança não commitada (branch `master`), para revisão do dono.
- `docs/adr/0015` ainda diz "7 hosts" no texto aceito (o código tem 8 com ADR 0018 proposto); não corrigido por ser ADR aceito.
- Confirmar com o dono a ampliação de `api.github.com` (ADR 0018, proposto).
