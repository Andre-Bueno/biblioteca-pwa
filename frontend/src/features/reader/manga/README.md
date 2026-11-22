# features/reader/manga

Leitor de mangá (`/ler/:itemId`): modos paginado D→E, E→D e vertical (webtoon), toque/deslize/teclado, pré-carregamento das 2 próximas páginas, zoom, retomada e salvamento de progresso (via `shared/progress`). Teclado, toque e deslize vêm de `features/reader/input/` (entrada única; o mangá só trata as intenções). Não importar outras features.
