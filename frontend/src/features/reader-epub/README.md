# features/reader-epub

Leitor de EPUB (`/ler/:itemId` quando o item é `book`; a rota em `app/ReaderRoute.tsx` escolhe pelo tipo).
O servidor entrega cada capítulo como documento HTML já saneado; ele vive **apenas** num `<iframe sandbox="allow-same-origin">` (nunca `allow-scripts`). O app lê só geometria de rolagem e `a[href]` do iframe.

- `locator.ts`: lógica pura (`capítulo*10000 + offset_bp`, links `?goto=`, teclas, gesto).
- `hooks/useEpubData` (item + estrutura + progresso), `hooks/useEpubFrame` (iframe: restaurar posição, rolagem, cliques), `hooks/useEpubReader` (estado, painéis, preferências, progresso).
- `components/`: página, barras, índice (TOC) e ajustes em gavetas (`Drawer`), fim de capítulo/livro.

Não importar outras features.
