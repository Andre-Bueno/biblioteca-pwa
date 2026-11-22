# 2026-11-21 · Leitor único: passos 1 e 2 (reorganização e ReaderSource)

## O que foi feito
- Passo 1: `features/reader-epub/` → `features/reader/epub/` e `features/reader-manga/` → `features/reader/manga/` (`git mv`). Novo `frontend/src/features/reader/index.ts` exporta `EpubReaderPage` e `MangaReaderPage`. `app/ReaderRoute.tsx` importa de `../features/reader`. Index antigos removidos.
- Passo 2: `frontend/src/features/reader/sources/` com `types.ts`, `pagesSource.ts` (`ImagePagesSource`), `chaptersSource.ts` (`BookChaptersSource`), `selectSource.ts` e `index.ts`. Strategy `ReaderSource`; codec do locator escolhido por `item.type`.
- Testes: `frontend/tests/unit/reader-sources.test.ts` (18 casos). Imports de 4 testes existentes (`epub-locator`, `epub-pinch`, `epub-strip`, `reader-navigation`) trocados para o caminho novo.
- ADR 0019 (proposto): leitor único e contrato `ReaderSource`.

## Escopo
- Sem mudança de comportamento. Sem mudança de rota, API, banco, sandbox ou progresso.
- `sources/` ainda não é usado pela UI.

## Decisões
- Decisão de estrutura registrada em `docs/adr/0019-leitor-unico-com-reader-source.md`. ADR 0001 não é alterado.

## Verificação
- Conferido no disco: `frontend/src/features/reader/{index.ts,epub/,manga/,sources/}` existem; `reader-epub/` e `reader-manga/` não existem mais.
- Contagem de casos do teste novo: 18 (`it(` no arquivo).
- Grep por `reader-epub` e `reader-manga` em `frontend/src` e `frontend/tests`: sem resultado.
- Testes e `scripts/check` não foram executados nesta entrega (só documentação).

## Pendências
- Mudança não commitada (branch `master`), para revisão do dono.
- Passo 3 em diante (UI usando `ReaderSource`, leitor único) ainda não feito.
- ADR 0019 aguarda aceite do dono.
- Documentos antigos (`docs/history/` anteriores, ADRs e entradas antigas do CHANGELOG) mantêm os caminhos antigos por serem registro histórico.
