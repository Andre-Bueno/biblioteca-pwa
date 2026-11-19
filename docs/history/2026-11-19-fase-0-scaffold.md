# 2026-11-19 — Fase 0: scaffold de backend, frontend e mapas

## O que foi feito

| Área | Entrega | Onde |
|---|---|---|
| Backend | `create_app()`, `GET /api/v1/health`, middleware de cabeçalhos | `backend/app/main.py`, `backend/app/api/` |
| Backend | Camadas vazias (services, domain, ports, adapters) e `Settings` | `backend/app/*/` |
| Backend | Contratos do import-linter e teste de arquitetura | `backend/pyproject.toml`, `backend/tests/architecture/` |
| Backend | Testes de health e cabeçalhos | `backend/tests/integration/`, `backend/tests/security/` |
| Infra | Dockerfile e compose de exemplo | `infra/` |
| Frontend | PWA (Vite, React, TS), manifest, ícones, service worker | `frontend/` |
| Frontend | Tema claro/escuro/sistema | `frontend/src/shared/theme/`, `frontend/src/shared/ui/` |
| Frontend | api-client (credenciais, CSRF, 429) | `frontend/src/shared/api-client/` |
| Frontend | Fronteiras por feature (dependency-cruiser) e lint de segurança | `frontend/.dependency-cruiser.cjs`, `frontend/eslint.config.js` |
| Scripts | `scripts/check` (em criação) | `scripts/` |
| Docs | Mapas, CHANGELOG, ADR 0004 | `docs/maps/`, `docs/adr/`, `CHANGELOG.md` |

## Decisões

| Tema | Decisão | Registro |
|---|---|---|
| Dependency-cruiser para fronteiras do frontend | Adotado | ADR 0004 |
| TypeScript 6.0.3 | Versão exata, travada por compatibilidade de plugins | ADR 0004 |
| ESLint 9.39.5 | Versão exata, travada por compatibilidade de plugins | ADR 0004 |
| npm audit | 4 achados moderados, só no build; aceitos por ora | — |

## Pendências

| # | Item |
|---|---|
| 1 | Dockerfile sem lockfile do backend (instala por `pyproject.toml`) |
| 2 | `httpx2` no TestClient: a resolver |
| 3 | Playwright sem navegadores instalados (E2E não roda) |
| 4 | Build do Docker não validado |
| 5 | `SECRET_KEY` obrigatória ainda não é lida no startup |
| 6 | Contrato CSRF (cookie `csrf_token`, cabeçalho `X-CSRF-Token`) a alinhar com o backend |
| 7 | `Cache-Control: no-store` não implementado |
| 8 | Ponto de composição ports → adapters (Fase 1) |
| 9 | Teste de módulo fora do CODEMAP (exigido por `docs/AGENTS.md`) não existe |
| 10 | Checagem de senha vazada e CAPTCHA: dependem de autorização do dono (serviço externo) |
| 11 | Perguntas abertas do dono (PLANO §11) |

## Próximo passo

Fase 1: auth, modelos, migrações e scan (PLANO §9).
