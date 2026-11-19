# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Versionamento: [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Added
- `docs/PLANO.md`: stack, arquitetura, requisitos, segurança, modelo de dados, API e roteiro por fases.
- ADRs `0001` (arquitetura hexagonal e frontend por feature), `0002` (segurança no app), `0003` (PWA para iOS), `0004` (dependency-cruiser e versões travadas), `0005` (padrões fechados na verificação e na exposição) e `0006` (cabeçalhos do middleware sobrepõem a rota).
- Backend: teste de regressão `test_reg_001_secret_key_not_in_error` (REG-001) e `backend/tests/AGENTS.md` (regras de teste).
- `AGENTS.md` raiz, `docs/AGENTS.md`, `CLAUDE.md`, `README.md` e este `CHANGELOG.md`.
- Subagentes em `.claude/agents/` e skills em `.claude/skills/`.
- Protocolo de auditoria de segurança em `docs/security/AUDIT_PROTOCOL.md`.
- Fase 0 (fundação) iniciada: pastas `backend/`, `frontend/` e `infra/` com `AGENTS.md`.
- Backend (scaffold): FastAPI com `create_app()`, `GET /api/v1/health`, camadas vazias (`services`, `domain`, `ports`, `adapters`), `Settings` em `app/core/config.py`.
- Backend: contratos de camadas do import-linter em `backend/pyproject.toml`, com teste em `backend/tests/architecture/`.
- Backend: `SECRET_KEY` validada no startup (`create_app()`); testes em `backend/tests/security/test_settings.py`.
- Infra: `infra/Dockerfile` (Python 3.12.8, usuário não-root, HEALTHCHECK) e `infra/compose.example.yml` (exemplo, sem segredos).
- Infra: `.dockerignore` e `.env.example` na raiz; variáveis `BIND_ADDRESS`, `HOST_PORT` e `FORWARDED_ALLOW_IPS`.
- Frontend (scaffold): PWA com Vite, React e TypeScript; manifest, ícones e service worker (precache do shell).
- Frontend: tema claro/escuro/sistema (`shared/theme`, `shared/ui`), em memória.
- Frontend: `shared/api-client` com credenciais, cabeçalho CSRF, erro 429 genérico e mapeamento de erros.
- Frontend: arquitetura por feature (`app/`, `features/`, `shared/`) com dependency-cruiser (`npm run arch`) e testes de regras ESLint e de tokens CSS.
- `scripts/check.ps1` e `scripts/check.sh`: verificação única (lint, tipos, testes, arquitetura, auditoria de dependências e scan de segredos), com `scripts/README.md` e `scripts/gitleaks.toml`.
- Mapas em `docs/maps/`: CODEMAP, ARCHITECTURE, DATAMODEL, API, ROUTES, SECURITY_MAP, TEST_MAP.
- Entradas de histórico: `docs/history/2026-11-19-fase-0-scaffold.md`, `docs/history/2026-11-19-planejamento-e-fase-0.md` e `docs/history/2026-11-19-correcoes-revisao-fase-0.md`.

### Changed
- Arquitetura: MVC adaptado substituído por Hexagonal (Ports & Adapters) leve no backend e organização por feature no frontend (ADR 0001).
- Backend: contratos do import-linter reforçados de 5 para 6; `domain` proíbe pydantic, starlette e httpx; `core` coberto por contrato; `api.deps` aceita `app.adapters.**`.
- Backend: `TRUSTED_PROXY_COUNT` removido (`Settings`, compose, `.env.example`). Única fonte do IP real: `FORWARDED_ALLOW_IPS` (uvicorn).
- Backend: `SECRET_KEY` exige ≥12 caracteres distintos, sem espaços nas pontas e sem bloco de até 8 caracteres repetido.
- Backend: middleware de cabeçalhos sobrepõe cabeçalhos da rota (ADR 0006); desconexão do cliente após início da resposta vai para debug; `CancelledError` propaga.
- Infra: compose monta `../library:/library:ro` (relativo a `infra/`).
- Frontend: api-client lê o corpo com `text()` + `JSON.parse`; 2xx vazio retorna `undefined`; `baseUrl` sem barra dupla; `AbortError` propagado na leitura do corpo.
- Frontend: ESLint proíbe `XMLHttpRequest`, `WebSocket` e `navigator.sendBeacon` fora do api-client, e `indexedDB` fora de `shared/offline`.
- Backend: `create_app()` passa a carregar `Settings` e guardá-la em `app.state.settings`.
- Frontend: `tsconfig.json` vira só referências, com `tsconfig.app.json` (src, sem tipos do node) e `tsconfig.node.json`; `typecheck` roda os dois; `build` é só `vite build`.
- Frontend: dependency-cruiser ganha `not-to-unresolvable` e `not-to-dev-dep`, com `tsPreCompilationDeps`.
- Frontend: tema com tokens `--if-dark`/`--if-light`, sem duplicar a paleta.
- Infra: Dockerfile com HEALTHCHECK em Python e uvicorn com `--proxy-headers --forwarded-allow-ips`; compose publica a porta em `${BIND_ADDRESS:-127.0.0.1}:${HOST_PORT:-8000}`.
- Scripts: `-Fast` e `-Only` (`--fast`, `--only`) declaram MODO RAPIDO / MODO PARCIAL no resumo.
- Docs: `API.md` é manual (OpenAPI desligado); teste de módulo fora do CODEMAP marcado como planejado.

### Fixed
- Teste de arquitetura não executava nada e sempre passava. Agora roda import-linter e tem casos negativos por contrato.
- `check.sh` dava OK sem executar etapas.
- Código de saída e resumo escondiam etapas não executadas.
- Regex de detecção de falta de rede amplo demais.
- App subia sem `SECRET_KEY` válida.
- Erro 500 sem cabeçalhos de segurança; agora devolve JSON genérico com cabeçalhos e `Cache-Control: no-store`.
- Brechas nos contratos de camadas.
- Contexto de build sem `.dockerignore`.
- ESLint passa a bloquear `fetch`, `localStorage` e `sessionStorage` também via `window`, `globalThis` e `self`.
- api-client: `credentials` conforme `baseUrl`; corpo não-JSON vira `ApiError`; `AbortError` propagado.
- Scan de segredos: padrões ampliados; fallback de `grep` corrigido e stderr não descartado.
- `SECRET_KEY` inválida aparecia no erro de validação (log): `hide_input_in_errors=True` (REG-001, achado M-1).
- `SECRET_KEY` aceitava bloco repetido e chaves com 8 caracteres distintos; agora exige 12 distintos e rejeita bloco repetido e espaços nas pontas.
### Security
- Requisitos definidos: segurança dentro do app (anti brute force, CSRF, rate limit, cabeçalhos de segurança) e sem cadastro público (ADR 0002).
- Cabeçalhos de segurança no backend: CSP sem `'unsafe-inline'` (fixada em teste), `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`.
- `SECRET_KEY` obrigatória (mínimo 32 caracteres e 12 distintos, sem espaços nas pontas, sem bloco de até 8 caracteres repetido; sem default), validada no startup.
- Frontend: ESLint bloqueia canais de rede alternativos (XHR, WebSocket, `sendBeacon`) e `indexedDB` fora de suas pastas permitidas. Acessos indiretos dependem de revisão.
- Cabeçalhos da rota não podem enfraquecer os de segurança (ADR 0006).
- Porta publicada pelo compose em loopback por padrão; exposição exige `BIND_ADDRESS` explícito.
- Verificação sem rede falha por padrão; `-AllowOffline` / `--allow-offline` vira aviso declarado (ADR 0005).
- Frontend: ESLint bloqueia `fetch` fora do api-client, `localStorage`, `sessionStorage`, `eval` e `dangerouslySetInnerHTML`.
- Service worker não faz cache de `/api`.
- Pendentes: controles de login, CSRF no servidor, rate limit, CORS e `Cache-Control: no-store` em respostas autenticadas (ver `docs/maps/SECURITY_MAP.md`); quem serve o HTML da SPA (M5) aguarda decisão do dono.
