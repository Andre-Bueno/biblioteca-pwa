# 2026-11-21 · Zoom e pinça no leitor EPUB não trocam capítulo nem salvam posição

## O que foi feito
- Correção da issue #7: pinça (2+ toques), ctrl+scroll e ctrl+/ctrl- no leitor EPUB trocavam de capítulo, moviam a posição e salvavam progresso.
- Novo `frontend/src/features/reader-epub/pinch.ts`: `createPinchGuard` (bloqueia durante o multitoque e 600 ms depois) e `createReflowHold` (segura a posição só na mudança de largura).
- Usado em `hooks/useEpubStrip.ts` (tira vertical) e `hooks/useEpubFrame.ts` (capítulo único).

## Escopo
- Só frontend; sem mudança de rota, API, sandbox ou progresso no servidor.
- Resize só de altura (barras do Safari) não é tratado como zoom.

## Decisões
- Sem ADR novo: a regra "zoom não altera posição" é de comportamento de leitor, não de segurança ou arquitetura.

## Verificação
- Testes novos: `frontend/tests/regression/reg_001_epub_zoom_no_page_change.test.tsx` (19 blocos) e `frontend/tests/unit/epub-pinch.test.ts` (9 blocos).
- Esta entrega é só de documentação: testes e `scripts/check` não foram executados aqui.

## Pendências
- Mudança não commitada (branch `master`), para revisão do dono.
- Sem verificação em navegador ou dispositivo de toque real (iOS Safari).
- Tag `0.1.4` ainda não criada.
