# features/reader-epub

Leitor de EPUB (`/ler/:itemId` quando o item é `book`; a rota em `app/ReaderRoute.tsx` escolhe pelo tipo).
O servidor entrega cada capítulo como documento HTML já saneado; ele vive **apenas** num `<iframe sandbox="allow-same-origin">` (nunca `allow-scripts`). O app lê só geometria de rolagem e `a[href]` do iframe.

- `locator.ts`: lógica pura (`capítulo*10000 + offset_bp`, links `?goto=`, teclas, gesto).
- `hooks/useEpubData` (item + estrutura + progresso), `hooks/useEpubFrame` (iframe: restaurar posição, rolagem, cliques), `hooks/useEpubReader` (estado, painéis, preferências, progresso).
- `components/`: página, barras, índice (TOC) e ajustes em gavetas (`Drawer`), fim de capítulo/livro.

- Modo contínuo (preferência `reading_direction = vertical`): `components/EpubStrip` empilha um iframe por capítulo (mesmo sandbox), dimensionado ao conteúdo; `hooks/useEpubStrip` mantém só uma janela de capítulos montada (`strip.ts`: `STRIP_BEHIND`/`STRIP_AHEAD`), reserva a altura dos demais e salva `capítulo*10000+offset`.

- Altura dos capítulos no modo contínuo: `strip.ts#unlockDocumentHeight` força `height:auto`/`min-height:0` (via CSSOM, `!important`) em `html` e `body` de cada capítulo antes de medir. Livros (mangá) costumam trazer `html, body { height: 100% }`; sem isso a medida só repete a altura do iframe, o capítulo fica do tamanho da tela e a página aparece cortada/rolando dentro de uma "moldura". O sandbox não muda e nenhum script roda no livro.
- Controles (barras): `shared/hooks/useAutoHideControls`. Em dispositivo de toque (`(hover: none) and (pointer: coarse)`) o leitor abre em tela cheia (barras ocultas, só um indicador `capítulo/total · %` no canto), toque no centro mostra/oculta e as barras somem após 4 s sem interação (toque, foco ou tecla dentro delas reinicia a espera; painel aberto ou slider em uso mantém). Botão ☰ "Mostrar controles" e a tecla `m` revelam sem toque; safe-area do iOS nas barras e no botão. Com mouse, as barras continuam visíveis até alternar.

Não importar outras features.
