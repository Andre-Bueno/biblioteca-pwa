# ROUTES

Estado: 2026-11-19. Fonte: `frontend/src/app/routes.tsx`. Roteador: react-router-dom (`BrowserRouter` em `frontend/src/app/Providers.tsx`).

## Existente

| Caminho | Componente | Feature/pasta | Observação |
|---|---|---|---|
| `/` | `HomePage` (`frontend/src/app/HomePage.tsx`) | app | Título "Biblioteca", status do servidor (`useHealth`), `ThemeToggle` |

Service worker: `navigateFallbackDenylist: /^\/api\//` (`frontend/vite.config.ts`).

## Planejado (PLANO §2, status: planejado; caminhos a definir)

| Tela | Pasta prevista | Fase |
|---|---|---|
| Login | `features/auth/` | 2 |
| Biblioteca (listar, buscar, filtrar) | `features/library/` | 2 |
| Leitor de mangá (página a página, RTL/LTR, webtoon) | `features/reader-manga/` | 3 |
| Leitor EPUB | `features/reader-epub/` | 4 |
| Leitor PDF | `features/reader-pdf/` | 4 |
| Continuar lendo / progresso | `features/progress/` | 3 |
| Preferências (tema, leitura) | `features/settings/` | 2–3 |
