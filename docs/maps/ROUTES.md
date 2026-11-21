# ROUTES

Estado: 2026-11-21. Fonte: `frontend/src/app/routes.tsx`. Roteador: react-router-dom (`BrowserRouter` em `frontend/src/app/Providers.tsx`). A SPA é servida pelo backend na mesma origem (ADR 0012): qualquer caminho fora de `/api` que não seja arquivo recebe `index.html`.

## Rotas

| Caminho | Componente | Feature | Acesso | Observação |
|---|---|---|---|---|
| `/login` | `LoginPage` | `features/auth` | público | Se já autenticado, redireciona para `safeRedirect(state.from)` |
| `/` | `LibraryPage` | `features/library` | protegida | "Continuar lendo", grade de séries (capas), busca com debounce, "carregar mais"; botão "Atualizar metadados" só para admin |
| `/serie/:id` | `SeriesPage` | `features/series` | protegida | Capítulos em ordem natural, busca por número, descrição com origem e atribuição, "continuar"; painel de metadados só para admin (busca, escolher fonte, editar texto, remover). Capítulo sem série: não há rota própria |
| `/ler/:itemId` | `MangaReaderPage` | `features/reader-manga` | protegida | Com `?serie=<id>`: próximo e anterior capítulo no fim do capítulo; "voltar" leva à série. Carrega item e progresso; retoma na página salva. Não mangá: "Este formato ainda não é suportado."; sem páginas: mensagem; 404: "Item não encontrado." |
| `/ajustes` | `SettingsPage` | `features/settings` | protegida | Aparência (tema), sentido de leitura, troca de senha, sair |
| `*` | `Navigate` para `/` | app | — | Qualquer outro caminho |

Grupo protegido: `RequireAuth` (`features/auth/components/RequireAuth.tsx`) envolve `/`, `/serie/:id`, `/ler/:itemId` e `/ajustes`.

Links e texto nas telas de série: links externos só https (`safeHttpsUrl`); descrição e títulos de origem externa são texto puro. Capas usam URL same-origin (`/api/v1/series/{id}/cover`).

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

## Service worker e PWA

| Item | Valor |
|---|---|
| Registro | `frontend/src/app/registerServiceWorker.ts`, só em produção |
| Precache | Só o app shell (vite-plugin-pwa) |
| `navigateFallbackDenylist` | `/^\/api\//`: navegação para `/api` nunca cai em `index.html` |
| `runtimeCaching` | `[]`: nenhuma resposta de API é cacheada |
| Atualização | `skipWaiting: false`, `clientsClaim: false`: a nova versão espera a reabertura do app |
| Estado verificado | Não registrado no navegador embutido de validação; instalação e offline não provados (ver `docs/history/2026-11-20-mvp-usavel.md`) |

## Planejado (PLANO §2; caminhos a definir)

| Tela | Pasta prevista | Fase |
|---|---|---|
| Leitor EPUB | `features/reader-epub/` | 4 |
| Leitor PDF | `features/reader-pdf/` | 4 |
| Tela própria de progresso (se houver) | `features/progress/` | 4 ou depois |
| Biblioteca com filtro por status (lendo, concluído): requisito do MVP ainda pendente | `features/library/` | 2 (pendente) |
| Offline explícito | `shared/offline/` | 5 |
