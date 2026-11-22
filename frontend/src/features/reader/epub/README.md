# features/reader/epub

Leitor de EPUB (`/ler/:itemId` quando a fonte é `chapters`; a rota em `app/ReaderRoute.tsx` escolhe pela fonte). Barras, índice, ajustes e fim de livro vêm de `features/reader/shell` (compartilhado com o mangá).
O servidor entrega cada capítulo como documento HTML já saneado; ele vive **apenas** num `<iframe sandbox="allow-same-origin">` (nunca `allow-scripts`). O app lê só geometria de rolagem e `a[href]` do iframe.

- `locator.ts`: lógica pura (`capítulo*10000 + offset_bp`, links `?goto=`, ajuste de fonte).
- Teclado, toque e deslize: `features/reader/input/` (compartilhado com o mangá). ←/→ e o deslize avançam e voltam conforme a direção (D→E: ← avança; E→D: → avança); ↑/↓ rolam 10%, PgUp/PgDn 90%, Home/End vão ao topo e ao fim do capítulo; o slider espelha em D→E.
- Dados (item, fonte, livro, progresso inicial): `features/reader/hooks/useReaderData.ts`. `hooks/useEpubFrame` (iframe: restaurar posição, rolagem, cliques), `hooks/useEpubReader` (estado, preferências do livro, progresso).
- `components/`: `EpubReaderPage` (monta o `ReaderShell` e o `ReaderGate`), `EpubStrip` (tira vertical).

- Modo contínuo (preferência `reading_direction = vertical`): `components/EpubStrip` empilha um iframe por capítulo (mesmo sandbox), dimensionado ao conteúdo; `hooks/useEpubStrip` mantém só uma janela de capítulos montada (`strip.ts`: `STRIP_BEHIND`/`STRIP_AHEAD`), reserva a altura dos demais e salva `capítulo*10000+offset`.

- Altura dos capítulos no modo contínuo: `strip.ts#unlockDocumentHeight` força `height:auto`/`min-height:0` (via CSSOM, `!important`) em `html` e `body` de cada capítulo antes de medir. Livros (mangá) costumam trazer `html, body { height: 100% }`; sem isso a medida só repete a altura do iframe, o capítulo fica do tamanho da tela e a página aparece cortada/rolando dentro de uma "moldura". O sandbox não muda e nenhum script roda no livro.
- Controles (barras): `shared/hooks/useAutoHideControls`. Em dispositivo de toque (`(hover: none) and (pointer: coarse)`) o leitor abre em tela cheia (barras ocultas, só um indicador `capítulo/total · %` no canto), toque no centro mostra/oculta e as barras somem após 4 s sem interação (toque, foco ou tecla dentro delas reinicia a espera; painel aberto ou slider em uso mantém). Botão ☰ "Mostrar controles" e a tecla `m` revelam sem toque; safe-area do iOS nas barras e no botão. Com mouse, as barras continuam visíveis até alternar.

- Zoom (issue #7): pinça (2+ toques), ctrl+scroll e ctrl+/ctrl- ampliam a página sem trocar de capítulo nem alterar o progresso salvo. `pinch.ts` concentra as regras e constantes:
  - `createPinchGuard`: marca o multitoque e bloqueia enquanto durar e por 600 ms depois. Um touchstart de 1 dedo, touchcancel, blur da janela e página oculta encerram o bloqueio; sem evento de toque por 2 s ele expira.
  - `createReflowHold`: segura a posição só quando a **largura** da janela muda (zoom do navegador, rotação). Resize só de altura (barras do Safari) não segura nem reaplica; resize logo após rolagem do usuário (150 ms) também não; rolar durante o hold o encerra.
- Durante a pinça ou o hold, a rolagem não vira swipe, toque central nem relatório de posição; ao fim da janela há uma única reavaliação da posição (nada se perde). Wheel com ctrlKey não conta como gesto.
- Modo contínuo: reaplica capítulo e offset relativo (anchor) a cada mudança de altura durante o hold. Capítulo único: reaplica a posição só no resize de largura. A altura de reserva dos capítulos não montados é fixada na abertura.
- Testes: `frontend/tests/regression/reg_001_epub_zoom_no_page_change.test.tsx` e `frontend/tests/unit/epub-pinch.test.ts`.

Não importar outras features.
