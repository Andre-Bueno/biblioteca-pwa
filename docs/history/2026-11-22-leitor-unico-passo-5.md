# 2026-11-22 · Leitor único: passo 5 (entrada única e direção no EPUB)

## O que foi feito
- Nova pasta `frontend/src/features/reader/input/`: `intents.ts` (puro: `ReaderIntent`, `keyIntent`, `swipeIntent`, `tapIntent`, `VIEWPORT_INPUT`, `scrollFraction`), `useReaderInput.ts` (teclado), `useViewportGestures.ts` (movido de `manga/hooks/`) e `index.ts`.
- Mangá e EPUB usam a mesma entrada. Intenções: `prev`, `next`, `first`, `last`, `scrollPage`, `scrollLine`, `scrollEdge`, `toggleChrome`.
- Direção (`rtl`, `ltr`, `vertical`) e tipo de fonte decidem a tecla. Mangá vertical passa a aceitar ←/→ como página anterior/próxima. EPUB de texto honra a direção (decisão do dono de 2026-11-21): ←/→ e deslize seguem D→E e E→D, e o slider espelha em D→E (`chaptersSource.capabilities.honorsDirection` = `true`).
- Removidos: `manga/navigation.ts`; de `epub/locator.ts`, `readerKeyAction`, `swipeChapterStep`, `isCenterTap` e `SWIPE_MIN_PX`.
- Testes: `reader-navigation.test.ts` renomeado para `reader-input.test.ts`; ajustes em `epub-locator`, `reader-sources`, `reader-epub` e `reg_001` (direção do swipe).

## Escopo
- Sem mudança de API, banco, sandbox do EPUB ou formato do locator.
- Mapas atualizados: `CODEMAP`, `TEST_MAP`, `ARCHITECTURE`, `frontend/AGENTS.md`, READMEs de `reader/manga` e `reader/epub`. `ROUTES` sem mudança (não cita setas).
- ADR 0019: seção "Andamento" com passos 1 a 5 concluídos. Status continua Proposto.

## Decisões
- Nenhuma decisão nova de arquitetura. A direção no EPUB segue a decisão do dono de 2026-11-21. Sem ADR novo.

## Verificação
- Conferido no disco: os quatro arquivos de `reader/input/` existem; `manga/navigation.ts`, `manga/hooks/useViewportGestures.ts` e `reader-navigation.test.ts` não existem mais; nenhum símbolo removido aparece em `frontend/src` nem em `frontend/tests`.
- Contagem de casos por grep (`it(`/`it.each(`, por bloco): `reader-input` 11; `epub-locator` 14; `reader-epub` 53.
- Testes e `scripts/check` não foram executados nesta entrega (só documentação).

## Pendências
- Mudança não commitada (branch `master`), para revisão do dono.
- `CHANGELOG.md`, em `[Não lançado]` > Changed, há uma linha anterior dizendo que o slider do EPUB não espelha. Ficou superada por esta entrega e não foi reescrita.
- ADR 0019: a tabela "Escopo desta decisão" ainda descreve o passo 2. Mantida por ser ADR Proposto e o Andamento já registra o estado.
- Aceite do ADR 0019 pelo dono.
