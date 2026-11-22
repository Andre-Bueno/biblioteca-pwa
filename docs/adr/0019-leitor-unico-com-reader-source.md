# ADR 0019: Leitor único em `features/reader` com ReaderSource (Strategy)

- **Status:** Proposto (aguarda aceite do dono)
- **Data:** 2026-11-21

## Contexto

- Havia dois leitores em features separadas (`reader-manga`, `reader-epub`) com pastas, hooks e controles parecidos (página/capítulo, progresso, barras, teclado).
- O locator muda por formato: mangá e PDF usam página; livro usa `capítulo * 10000 + offset_bp` (ADR 0013, `API.md`).
- ADR 0001 pede frontend por feature e proíbe feature importando feature. Dois leitores com lógica comum tendem a copiar código.
- PDF (Fase 4) deve entrar sem uma terceira feature de leitor.

## Decisão

| Tema | Decisão |
|---|---|
| Pasta | Uma feature `frontend/src/features/reader/` com `manga/`, `epub/` e `index.ts` (exporta `MangaReaderPage` e `EpubReaderPage`) |
| Abstração | `reader/sources/`: contrato `ReaderSource` (Strategy) com `kind` (`pages` ou `chapters`), `unitCount`, `codec` do locator, `toc`, `capabilities`, `clampUnit`, `unitTitle` |
| Escolha | `selectSource(type, data)`: `book` vira capítulos; demais tipos viram páginas. O codec do locator depende do tipo do item |
| Pureza | `sources/` não usa React nem rede. Codecs nunca lançam exceção com valor hostil |
| Escopo desta decisão | Estrutura e contrato. A UI ainda usa os dois leitores atuais; a troca para um leitor único com `ReaderSource` é entrega posterior |
| Fronteira | Nenhuma feature importa outra. Código comum entre leitores fica em `reader/` |
| ADR 0001 | Não substituído: a regra "feature por tela" continua; `reader` vira uma feature com duas subpastas de formato |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Manter `reader-manga` e `reader-epub` separados | Duplica controles e hooks; PDF criaria terceira cópia |
| Um componente único com `if` por formato | Mistura regras de locator e capacidades na tela; difícil de testar sem React |
| Locator único para todos os formatos | Quebra o contrato do servidor (ADR 0013) e o progresso já salvo |

## Consequências

- Positivas: regras de locator e capacidades testáveis em lógica pura (`reader-sources.test.ts`); PDF tem onde entrar; imports de `/ler/:itemId` passam por um ponto (`features/reader/index.ts`).
- Negativas:
  - `sources/chaptersSource.ts` importa `reader/epub/locator.ts`: dependência interna da feature, aceita por ser a mesma feature.
  - Até a UI migrar, o contrato existe sem uso em produção.
- Obrigações:
  - Não mudar o formato do locator sem novo ADR.
  - Ao migrar a UI para `ReaderSource`, atualizar este ADR por um novo que o substitua, se a decisão mudar.

## Andamento

Status continua Proposto. A decisão acima não mudou; esta seção só registra o estado no disco. A linha "Escopo desta decisão" descreve o passo 2; o estado atual é o da tabela abaixo.

| Passo | Estado (2026-11-22) | Onde |
|---|---|---|
| 1. Pasta `features/reader/` | Concluído | `frontend/src/features/reader/` |
| 2. `ReaderSource` e `selectSource` | Concluído | `reader/sources/` |
| 3. Hook único de dados e progresso; shell compartilhado | Concluído | `reader/hooks/`, `reader/shell/` |
| 4. `ReaderRoute` e `useReaderKind` pela fonte; leitor EPUB com `createResumeStore`; remoção dos componentes duplicados | Concluído | `app/ReaderRoute.tsx`, `app/useReaderKind.ts`, `reader/epub/components/EpubReaderPage.tsx` |
| 5. Entrada única de teclado e gesto; fonte EPUB honra direção (`honorsDirection` = `true`) | Concluído | `reader/input/` (`intents.ts`, `useReaderInput.ts`, `useViewportGestures.ts`), `reader/sources/chaptersSource.ts` |
| 6 a 8 | Pendentes; conteúdo não definido nos documentos do repositório | — |

Pendências de documentação: classes próprias das features (`epub-*`, `viewport`, `strip`) continuam fora do padrão `reader-*`; só o shell usa `reader-*`.
