# 2026-11-21 · Leitura vertical contínua no leitor EPUB

## O que foi feito
- Preferência `reading_direction = vertical` no leitor EPUB: os capítulos viram iframes empilhados num container rolável (`features/reader-epub/components/EpubStrip.tsx`).
- Hook `hooks/useEpubStrip.ts` e lógica pura `strip.ts`: janela montada de 1 capítulo antes e 3 depois; os demais mantêm a altura medida.
- Progresso pelo locator de livro: `capítulo * 10000 + offset_bp`; fim do livro salva `bp 9999`.
- `epub.css`: estilos da tira. `EpubReaderPage.tsx` escolhe entre tira e iframe único; `useEpubReader.ts` expõe o estado do modo.
- Guarda de sandbox (`epub-locator.test.ts`) passa a contar 2 iframes, ambos `sandbox="allow-same-origin"`.

## Escopo
- Só frontend; sem mudança de rota nem de API.
- A janela limita os iframes vivos; os demais capítulos são placeholders com a altura já medida.

## Decisões
- Nenhuma decisão nova de segurança: a tira usa o mesmo sandbox e as mesmas regras do ADR 0017. Sem ADR novo.

## Verificação
- Testes novos: `frontend/tests/unit/epub-strip.test.ts` (7 blocos) e `frontend/tests/unit/reader-epub-vertical.test.tsx` (8 blocos).
- Esta entrega é só de documentação: testes e `scripts/check` não foram executados aqui.

## Pendências
- Mudança não commitada (branch `master`).
- Renderização real no navegador (rolagem, altura dos capítulos com imagens, fontes) não testada; sem E2E para EPUB.
- ADR 0017 segue como proposto até confirmação do dono.
