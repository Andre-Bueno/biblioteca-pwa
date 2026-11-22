# 2026-11-21 · Leitor único: passos 3 e 4 (hook de dados, shell compartilhado)

## O que foi feito
- Passo 3: `features/reader/hooks/useReaderData.ts` (dados únicos: item, fonte, livro, locator salvo, posição) e `useReaderProgress.ts` (linha de base, primeira visita). `features/reader/shell/` (chrome comum: barras, pílula, slider, gavetas Índice e Ajustes, fim de unidade, `ReaderGate`) usado pelo mangá e pelo EPUB.
- Passo 4: `app/ReaderRoute.tsx` chama `useReaderData` e `useReaderNav`; `app/useReaderKind.ts` escolhe a tela pela fonte. EPUB com `createResumeStore` (retoma a posição ao alternar modo).
- Removidos: `epub/components/{Drawer,TocDrawer,SettingsDrawer,EpubEnd,EpubControls}.tsx`, `manga/components/{ChapterEnd,ReaderControls}.tsx`, `manga/hooks/useReaderData.ts`, `epub/hooks/useEpubData.ts`, `clampPage` em `manga/navigation.ts`.
- Testes: `frontend/tests/unit/reader-data.test.tsx` (novo, 11 casos) e acréscimos em `reader.test.tsx`, `reader-epub.test.tsx`, `reader-vertical.test.tsx`, `reader-sources.test.ts`. Testids do EPUB não mudaram; slider do mangá passou a 0-based.
- Mangá: barras ocultas ao abrir e auto-ocultar após 4 s em toque; pílula "n / N"; modo de leitura no painel Aa salvo como `reading_direction`.
- Documentação: `CODEMAP`, `TEST_MAP`, `ROUTES`, `frontend/AGENTS.md`, READMEs de `reader/epub`, ADR 0019 (seção Andamento; decisão não alterada).

## Escopo
- Sem mudança de API, banco, sandbox do EPUB ou formato do locator.
- EPUB ainda não honra direção (`honorsDirection` = `false`); passo 5.

## Decisões
- Nenhuma decisão nova. ADR 0019 continua Proposto.

## Verificação
- Conferido no disco: arquivos de `reader/hooks/` e `reader/shell/` existem; os cinco componentes EPUB, os dois do mangá, `useEpubData.ts`, `manga/hooks/useReaderData.ts` e `clampPage` em `manga/navigation.ts` não existem mais.
- Contagem de casos por grep (`it(`/`test(`) em `reader-data`: 11; `reader`: 32; `reader-epub`: 51; `reader-navigation`: 9.
- Testes e `scripts/check` não foram executados nesta entrega (só documentação).

## Pendências
- Mudança não commitada (branch `master`), para revisão do dono.
- Passo 5 (EPUB honra direção) e 6 a 8: não detalhados nos documentos do repositório.
- Classes próprias das features (`epub-*`, `viewport`, `strip`) continuam fora de `reader-*`; só o shell usa `reader-*`.
- ADR 0019 aguarda aceite do dono.
