# 2026-11-21 · Barras ocultas em toque e altura dos capítulos no modo contínuo

## O que foi feito
- Leitor EPUB: em dispositivo de toque (`(hover: none) and (pointer: coarse)`) as barras começam ocultas, toque no centro alterna e somem após 4 s sem interação. Botão ☰ "Mostrar controles" e tecla `m` revelam; indicador discreto de capítulo/total e % no canto.
- Hook novo `frontend/src/shared/hooks/useAutoHideControls.ts` (exportado em `shared/hooks/index.ts`); usado por `features/reader-epub/hooks/useEpubReader.ts`.
- Modo contínuo: `strip.ts#unlockDocumentHeight` força `height: auto` e `min-height: 0` (CSSOM, `!important`) em `html` e `body` de cada capítulo antes de medir, chamada em `attachFrame` (`hooks/useEpubStrip.ts`).

## Escopo
- Só frontend; sem mudança de rota, API ou sandbox. Nenhum script roda no livro.
- Com mouse, as barras continuam visíveis até alternar.

## Decisões
- Nenhuma decisão de segurança nova; sandbox do ADR 0017 inalterado. Sem ADR novo: a regra de barras ocultas por padrão só em toque foi para `frontend/AGENTS.md`.

## Verificação
- Testes novos: `frontend/tests/unit/auto-hide-controls.test.ts` (3 blocos) e 3 blocos novos em `frontend/tests/unit/reader-epub-vertical.test.tsx` (11 no total).
- Esta entrega é só de documentação: testes e `scripts/check` não foram executados aqui.

## Pendências
- Mudança não commitada (branch `master`).
- Sem verificação em navegador ou dispositivo de toque real.
- ADR 0017 e 0018 seguem como propostos até confirmação do dono.
