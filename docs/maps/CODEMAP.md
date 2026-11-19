# CODEMAP

Arquivo → responsabilidade → camada. Estado: 2026-11-19. Excluídos: `.venv`, `node_modules`, `dist`, `__pycache__`, caches (`.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.import_linter_cache`) e `reader_backend.egg-info/` (gerados).

## Raiz

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `AGENTS.md` | Regras gerais para agentes | docs |
| `CLAUDE.md` | Modo orquestrador | docs |
| `README.md` | Entrada do projeto | docs |
| `CHANGELOG.md` | Histórico de versões | docs |
| `.gitignore` | Ignorados do git | config |
| `.dockerignore` | Exclui do contexto de build: venv, node_modules, `.env*` (exceto `.env.example`), docs, scripts, frontend, testes do backend, bancos | config |
| `.env.example` | Modelo de variáveis (sem segredos); copiar para `.env` | config |
| `.claude/agents/*.md` (8) | Subagentes | config |
| `.claude/skills/*/SKILL.md` (5) | Skills de briefing | config |
| `docs/PLANO.md` | Roteiro, requisitos, arquitetura | docs |
| `docs/AGENTS.md` | Regras de documentação | docs |
| `docs/maps/*.md` (7) | Mapas: CODEMAP, ARCHITECTURE, DATAMODEL, API, ROUTES, SECURITY_MAP, TEST_MAP | docs |
| `docs/adr/0001..0006-*.md` | Decisões | docs |
| `docs/history/*.md` | Diário de entregas | docs |
| `docs/security/AGENTS.md`, `AUDIT_PROTOCOL.md` | Protocolo de auditoria | docs |
| `infra/AGENTS.md` | Regras de infra | docs |
| `infra/Dockerfile` | Imagem do backend (Python 3.12.8-slim, usuário `app` uid 10001, HEALTHCHECK, uvicorn com proxy headers; `ENV FORWARDED_ALLOW_IPS=127.0.0.1`) | infra |
| `infra/compose.example.yml` | Exemplo de compose do app (sem segredos; porta em loopback por padrão; biblioteca `../library` montada `:ro`; `FORWARDED_ALLOW_IPS` padrão `172.17.0.1`) | infra |
| `scripts/check.ps1` | Verificação única (Windows): backend, frontend, scan de segredos, resumo | scripts |
| `scripts/check.sh` | Verificação única (Linux/CI; testado só com bash do Git no Windows) | scripts |
| `scripts/gitleaks.toml` | Config do gitleaks (usado se o binário existir; não instalado) | scripts |
| `scripts/README.md` | Uso do `check`, regras de saída e etapas | docs |

## backend/

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `backend/AGENTS.md` | Regras do backend | docs |
| `backend/pyproject.toml` | Dependências, ruff, mypy, pytest, import-linter (6 contratos; `api.deps` aceita `app.adapters.**`) | config |
| `backend/app/__init__.py` | Pacote | — |
| `backend/app/main.py` | `create_app()`: carrega `get_settings()` (falha sem `SECRET_KEY` válida), guarda em `app.state.settings`, FastAPI sem docs/OpenAPI, middleware, routers | composição |
| `backend/app/core/config.py` | `Settings` (env): SECRET_KEY (≥32 caracteres, ≥12 distintos, sem espaço nas pontas, sem bloco de ≤8 repetido), ALLOWED_ORIGINS, COOKIE_SECURE, LIBRARY_PATH, DATABASE_URL; `hide_input_in_errors=True`; `get_settings()` com cache | core |
| `backend/app/core/__init__.py` | Pacote | — |
| `backend/app/api/health.py` | `GET /api/v1/health` | api |
| `backend/app/api/security_headers.py` | Middleware ASGI: cabeçalhos de segurança em toda resposta HTTP, sobrepondo os da rota; exceção não tratada vira 500 JSON genérico com `Cache-Control: no-store`; desconexão após início só em debug; `CancelledError` propaga | api |
| `backend/app/api/deps.py` | Ponto de composição (docstring; sem código) | composição |
| `backend/app/api/__init__.py` | Pacote | — |
| `backend/app/services/__init__.py` | Pacote (sem casos de uso ainda) | services |
| `backend/app/domain/__init__.py` | Pacote (sem entidades ainda) | domain |
| `backend/app/ports/__init__.py` | Pacote (sem interfaces ainda) | ports |
| `backend/app/adapters/__init__.py` | Pacote | adapters |
| `backend/app/adapters/AGENTS.md` | Regras de adapters (área sensível) | docs |
| `backend/app/adapters/persistence/__init__.py` | Pacote (sem banco ainda) | adapters |
| `backend/app/adapters/storage/__init__.py` | Pacote (sem storage ainda) | adapters |
| `backend/app/adapters/extractors/__init__.py` | Pacote (sem leitores ainda) | adapters |
| `backend/tests/AGENTS.md` | Regras de teste: nomes, 500 com TestClient, `caplog`, casos negativos de arquitetura | docs |
| `backend/tests/conftest.py` | Fixture `client` (TestClient); define `SECRET_KEY` de teste | teste |
| `backend/tests/architecture/test_layers.py` | Executa import-linter de verdade; 33 casos negativos parametrizados (todo `forbidden_modules` coberto), controle positivo e testes de `api.deps` | teste |
| `backend/tests/integration/test_health.py` | Teste do health | teste |
| `backend/tests/security/test_security_headers.py` | Cabeçalhos (inclui 404), 500 genérico com cabeçalhos, reraise após resposta iniciada, `CancelledError` não engolido, desconexão só em debug, substituição de cabeçalhos da rota | teste |
| `backend/tests/security/test_settings.py` | `SECRET_KEY`: ausente, curta, baixa entropia (7 casos), espaços nas pontas (3), válida | teste |
| `backend/tests/regression/test_reg_001_secret_key_not_in_error.py` | REG-001: valor de `SECRET_KEY` não aparece no erro de validação | teste |
| `backend/tests/regression/README.md` | Convenção `test_reg_<NNN>_<slug>.py`, um por bug/finding corrigido | teste |
| `backend/tests/unit/.gitkeep` | Pasta vazia | teste |

Não existem ainda: `backend/migrations/`, `backend/app/cli*`, `backend/tests/fixtures/`.

## frontend/

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `frontend/AGENTS.md` | Regras do frontend | docs |
| `frontend/package.json` | Dependências (versões exatas); scripts `dev`, `build` (só `vite build`), `lint`, `typecheck` (app + node), `test`, `arch`, `format:check`, `test:e2e` | config |
| `frontend/package-lock.json` | Lockfile npm | config |
| `frontend/.npmrc` | `save-exact=true` | config |
| `frontend/vite.config.ts` | Vite, vite-plugin-pwa (manifest, workbox: `runtimeCaching: []`, denylist `/api`), proxy `/api`, Vitest | config |
| `frontend/tsconfig.json` | Só referências (`tsconfig.app.json`, `tsconfig.node.json`) | config |
| `frontend/tsconfig.app.json` | Projeto de `src/` (sem tipos do node) | config |
| `frontend/tsconfig.node.json` | Projeto de `tests/`, `vite.config.ts`, `playwright.config.ts` (tipos node) | config |
| `frontend/eslint.config.js` | ESLint: plugin security; `fetch`, `XMLHttpRequest`, `WebSocket`, `navigator.sendBeacon` só no api-client (`sendBeacon`/XHR/WS também em `shared/api-client`); `indexedDB` só em `shared/offline`; `localStorage`/`sessionStorage` proibidos em todo lugar (também via `window`/`globalThis`/`self`); `react/no-danger`; `no-eval`. Acessos indiretos não são detectados | config |
| `frontend/.dependency-cruiser.cjs` | 6 regras: fronteiras app/features/shared, ciclos, não resolvível, dependência de dev | config |
| `frontend/.prettierrc.json`, `.prettierignore` | Formatação | config |
| `frontend/playwright.config.ts` | Config E2E (sem testes ainda) | config |
| `frontend/index.html` | Shell HTML (pt-BR, meta iOS, ícones) | app |
| `frontend/public/apple-touch-icon.png`, `icon-192.png`, `icon-512.png` | Ícones PWA | assets |
| `frontend/src/main.tsx` | Bootstrap React; registra service worker | app |
| `frontend/src/vite-env.d.ts` | Tipos de ambiente Vite | app |
| `frontend/src/app/App.tsx` | Raiz: Providers + rotas | app |
| `frontend/src/app/Providers.tsx` | ThemeProvider + BrowserRouter | app |
| `frontend/src/app/routes.tsx` | Rotas (`/` → HomePage) | app |
| `frontend/src/app/HomePage.tsx` | Tela inicial: status do servidor e `ThemeToggle` | app |
| `frontend/src/app/useHealth.ts` | Hook: chama `/api/v1/health` | app |
| `frontend/src/app/registerServiceWorker.ts` | Registro do SW (só em produção) | app |
| `frontend/src/app/app.css` | Estilos globais | app |
| `frontend/src/shared/api-client/client.ts` | Cliente HTTP central: `credentials` same-origin ou include conforme `baseUrl`; `baseUrl` sem barra dupla; CSRF; 429; 204 e 2xx vazio → `undefined`; corpo lido com `text()` + `JSON.parse` (não-JSON vira `ApiError`); `AbortError` propagado, inclusive na leitura do corpo | shared |
| `frontend/src/shared/api-client/csrf.ts` | `readCookie`, `isStateChanging` | shared |
| `frontend/src/shared/api-client/errors.ts` | `ApiError`, `RateLimitError`, `NetworkError` | shared |
| `frontend/src/shared/api-client/index.ts` | Exportações públicas do api-client | shared |
| `frontend/src/shared/theme/ThemeProvider.tsx` | Estado de tema (preferência em memória; não persiste) | shared |
| `frontend/src/shared/theme/theme-context.ts` | Contexto e tipos de tema | shared |
| `frontend/src/shared/theme/useTheme.ts` | Hook de tema | shared |
| `frontend/src/shared/theme/useSystemTheme.ts` | Hook de `prefers-color-scheme` | shared |
| `frontend/src/shared/theme/theme.css` | Tokens de cor com `--if-dark`/`--if-light`, declarados uma vez | shared |
| `frontend/src/shared/theme/index.ts` | Exportações do tema | shared |
| `frontend/src/shared/ui/ThemeToggle.tsx` | Botões Sistema/Claro/Escuro | shared |
| `frontend/src/shared/ui/ui.css` | Estilos do toggle | shared |
| `frontend/src/shared/ui/index.ts` | Exportações de UI | shared |
| `frontend/src/shared/offline/README.md` | Reservado (estratégia offline; único lugar com `indexedDB`) | shared |
| `frontend/src/features/auth/README.md` | Esqueleto | features |
| `frontend/src/features/library/README.md` | Esqueleto | features |
| `frontend/src/features/progress/README.md` | Esqueleto | features |
| `frontend/src/features/settings/README.md` | Esqueleto | features |
| `frontend/src/features/reader-manga/README.md` | Esqueleto | features |
| `frontend/src/features/reader-epub/README.md` | Esqueleto | features |
| `frontend/src/features/reader-pdf/README.md` | Esqueleto | features |
| `frontend/tests/setup.ts` | jest-dom e cleanup | teste |
| `frontend/tests/unit/api-client.test.ts` | api-client: credenciais, CSRF, 429, 500, rede, 204, não-JSON, AbortError, 2xx vazio, junção de `baseUrl` | teste |
| `frontend/tests/unit/architecture.test.ts` | dependency-cruiser em `src` e em 8 fixtures negativas | teste |
| `frontend/tests/unit/eslint-rules.test.ts` | ESLint: 18 formas proibidas em feature (`it.each`); permissões por pasta (api-client, offline) | teste |
| `frontend/tests/unit/theme-css.test.ts` | Tokens do tema: cada valor escuro uma vez; dois gatilhos escuros; todos os tokens em `:root` | teste |
| `frontend/tests/unit/home.test.tsx` | Tela inicial mostra status | teste |
| `frontend/tests/unit/theme.test.tsx` | Tema: sistema por padrão; troca explícita; sem localStorage | teste |
| `frontend/tests/fixtures/arch-*/` (8) | Fixtures que devem violar uma regra cada (`arch-violation`, `arch-feature-app`, `arch-shared-feature`, `arch-shared-app`, `arch-cycle`, `arch-type-only`, `arch-unresolvable`, `arch-dev-dep`) | teste |
| `frontend/tests/e2e/.gitkeep` | Pasta vazia (E2E ainda não existe) | teste |
| `frontend/tests/regression/.gitkeep` | Pasta vazia (nenhum `reg_NNN` ainda) | teste |

## Gerado (não versionar, não listar)

`frontend/dist/` (build), `frontend/node_modules/`, `backend/.venv/`, `backend/reader_backend.egg-info/`.
