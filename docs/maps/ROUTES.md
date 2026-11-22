# ROUTES

Estado: 2026-11-21. Fonte: `frontend/src/app/routes.tsx`. Roteador: react-router-dom (`BrowserRouter` em `frontend/src/app/Providers.tsx`). A SPA é servida pelo backend na mesma origem (ADR 0012): qualquer caminho fora de `/api` que não seja arquivo recebe `index.html`.

## Rotas

| Caminho | Componente | Feature | Acesso | Observação |
|---|---|---|---|---|
| `/login` | `LoginPage` | `features/auth` | público | Se já autenticado, redireciona para `safeRedirect(state.from)` |
| `/` | `LibraryPage` | `features/library` | protegida | Aviso de nova versão (só admin); "Continuar lendo"; grade de séries (capas e contagem "N livros"/"N capítulos"/"N itens"); busca com debounce; "carregar mais"; botão "Atualizar metadados" só para admin |
| `/serie/:id` | `SeriesPage` | `features/series` | protegida | Capítulos em ordem natural, busca por número, descrição com origem e atribuição, "continuar"; livros aparecem como "Livro" (sem contagem de páginas); painel de metadados só para admin (busca, escolher fonte, editar texto, remover). Capítulo sem série: não há rota própria |
| `/ler/:itemId` | `ReaderRoute` → `MangaReaderPage` ou `EpubReaderPage` | `features/reader/manga`, `features/reader/epub` (export por `features/reader/index.ts`) | protegida | `app/ReaderRoute.tsx` escolhe pelo tipo do item: `book` abre o leitor EPUB; demais, o leitor de mangá. Com `?serie=<id>`: próximo e anterior capítulo no fim; "voltar" leva à série. Livro: em toque, barras ocultas ao abrir e após 4 s (toque no centro alterna; ☰ e tecla `m`); com mouse, barras visíveis. Mangá: retoma na página salva; "Este formato ainda não é suportado." para PDF; 404: "Item não encontrado." |
| `/ajustes` | `SettingsPage` | `features/settings` | protegida | Versão do app; "Verificar atualizações" (só admin); aparência (tema); sentido de leitura; troca de senha; sair |
| `*` | `Navigate` para `/` | app | — | Qualquer outro caminho |

Grupo protegido: `RequireAuth` (`features/auth/components/RequireAuth.tsx`) envolve `/`, `/serie/:id`, `/ler/:itemId` e `/ajustes`.

Links e texto nas telas de série e de versão: links externos só https (`safeHttpsUrl`); descrição, notas de release e títulos de origem externa são texto puro. Capas usam URL same-origin (`/api/v1/series/{id}/cover`).

Leitor EPUB: o capítulo vive num `<iframe sandbox="allow-same-origin">` (sem `allow-scripts`), servido por `/api/v1/items/{id}/book/chapters/{n}` (ADR 0017). O app lê só geometria de rolagem e `a[href]` do frame. Com preferência "Vertical" (`/ler/:itemId`), a mesma rota mostra uma tira contínua: um iframe por capítulo, janela de 1 antes e 3 depois montada.

## Estados do RequireAuth

| Estado (`SessionStatus`) | Renderiza | Quando | Marcação |
|---|---|---|---|
| `loading` | Splash com spinner | `/auth/me` pendente na carga | `role="status"`, `data-testid="session-loading"` |
| `error` | "Não foi possível verificar a sessão." + botão "Tentar de novo" | `/auth/me` com 429, 503 ou falha de rede. Não é saída de sessão | `role="alert"`, `data-testid="session-error"`, `session-retry` |
| `anonymous` | Redireciona para `/login` com `state.from` (caminho atual) | 401 em `/auth/me`, ou refresh rejeitado em qualquer chamada | — |
| `authenticated` | `Outlet` (a tela) | `/auth/me` 200 ou login bem-sucedido | — |

## Comportamento de sessão nas telas

| Evento | Efeito |
|---|---|
| Login OK | Vai para `safeRedirect(from)`; `from` aceita só caminhos internos (sem `//`, `\`, controles, nem `/login`) |
| Logout | Estado `anonymous` mesmo se a chamada ao servidor falhar |
| Refresh rejeitado (qualquer tela) | Estado `anonymous` e redireciona para `/login` |
| Leitor com erro de imagem | Uma recuperação de sessão por janela (sem `/auth/me`); senão botão "Tentar novamente" na imagem |

## Aviso de nova versão (admin)

| Item | Comportamento |
|---|---|
| Quem vê | Só `role === 'admin'`. Usuário comum não recebe nada sobre releases (`GET /system/version` devolve só `current` e `update_available`) |
| Onde | Aviso em `/` e em `/ajustes` (`UpdateNotice`) |
| Consulta de versão | Ao abrir o app e no máximo a cada 30 min, com a aba visível (`VersionProvider`); falha silenciosa, sem repetição em laço |
| Conteúdo | Versão atual e nova; notas em texto puro; link para a release só https do GitHub do repositório |
| Atualizar agora | Confirmação antes; depois `POST /system/update` com a tag exata; sem webhook configurado, só a instrução manual e o link |
| Acompanhamento | Consulta `/system/version` a cada 5 s, até 60 vezes (cerca de 5 min); para ao sair da tela; se o servidor disser que falhou, mostra a falha |
| "Agora não" | Esconde até recarregar a página (também na outra tela) |
| Verificação manual | "Verificar atualizações" em `/ajustes` (admin): uma chamada por vez; 429 bloqueia o botão pelo `Retry-After` |

## Service worker e PWA

| Item | Valor |
|---|---|
| Registro | `frontend/src/app/registerServiceWorker.ts`, só em produção (`onNeedRefresh` → `shared/pwa`) |
| Modo | `registerType: 'prompt'` (`vite.config.ts`): nova versão espera; nada recarrega sozinho |
| Ativação | "Recarregar" no aviso (`AppUpdatePrompt`): antes faz `flushAllProgress` (progresso pendente salvo, com teto de ~2 s), depois ativa o worker e recarrega. Dentro do leitor, só um indicador compacto |
| Precache | Só o app shell (vite-plugin-pwa) |
| `navigateFallbackDenylist` | `/^\/api\//`: navegação para `/api` nunca cai em `index.html` |
| `runtimeCaching` | `[]`: nenhuma resposta de API é cacheada |
| Atualização | `skipWaiting: false`, `clientsClaim: false`: a ativação depende do usuário |
| Estado verificado | Registro real no navegador não provado (ver `docs/history/2026-11-20-mvp-usavel.md`); há testes de configuração e do aviso (`frontend/tests/unit/pwa-update.test.tsx`) |

## Planejado (PLANO §2; caminhos a definir)

| Tela | Pasta prevista | Fase |
|---|---|---|
| Leitor PDF | `features/reader-pdf/` | 4 |
| Tela própria de progresso (se houver) | `features/progress/` | 4 ou depois |
| Biblioteca com filtro por status (lendo, concluído): requisito do MVP ainda pendente | `features/library/` | 2 (pendente) |
| Offline explícito | `shared/offline/` | 5 |

Entregue em 2026-11-21: leitor EPUB (`features/reader/epub/`, ADR 0017, proposto).
