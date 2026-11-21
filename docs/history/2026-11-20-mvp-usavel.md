# 2026-11-20 — MVP usável (Fase 2, leitor de mangá e progresso)

Esta entrada é só documentação: nenhum código, teste, migração ou configuração foi alterado nesta entrega. Os números de testes são os últimos resultados informados pelo dev (não reexecutados aqui). Contagens por arquivo foram lidas do disco (`def test_` por grep). Verificações estáticas (arquivos, CSP, rotas, migrações) foram conferidas no disco.

## O que foi feito

| Área | Entrega | Onde |
|---|---|---|
| API de progresso | `PUT`/`GET`/`DELETE /api/v1/progress/{item_id}` e `GET /api/v1/progress/continue` (limite padrão 10, máximo 50) | `backend/app/api/progress.py`, `progress_schemas.py`, `services/progress_service.py`, `domain/progress.py` |
| API de preferências | `GET`/`PUT /api/v1/me/preferences` (tema e sentido de leitura) | `backend/app/api/preferences.py`, `services/preferences_service.py`, `domain/preferences.py` |
| Persistência | Migração `0004`: tabela `reading_progress` e coluna `users.reading_direction` (por `ALTER ADD COLUMN`, sem recriar `users`) | `backend/migrations/versions/0004_reading_progress_and_preferences.py`, `adapters/persistence/progress_repository.py`, `preferences_repository.py` |
| Servir o frontend | `FRONTEND_DIST_DIR`; fallback de SPA fora de `/api`; cache por tipo; CSP explícita | `backend/app/api/spa.py`, `main.py`, `api/security_headers.py`; ADR 0012 (resolve M5) |
| Rate limit | Limite estrito só em login, refresh, logout e troca de senha; `me` e `csrf` ficam só no limite global | `backend/app/api/rate_limit.py`; `test_reg_019` |
| Helper de ids | Validação de UUID canônico compartilhada pelos routers | `backend/app/api/ids.py` |
| Docker | Imagem em 3 estágios (frontend, instalação do backend, runtime); `entrypoint.sh` (valida variáveis, migra, sobe o uvicorn); constraints gerados em `python:3.12.8-slim`; compose endurecido; `.dockerignore`; `.env.example`; guia de operação | `infra/Dockerfile`, `infra/entrypoint.sh`, `infra/gen_constraints.sh`, `infra/constraints.txt`, `infra/compose.example.yml`, `.dockerignore`, `.env.example`, `docs/DEPLOY.md` |
| Frontend: telas | Login (`/login`), biblioteca com "Continuar lendo" (`/`), leitor de mangá com três modos (RTL, LTR e vertical) (`/ler/:itemId`), ajustes (`/ajustes`) | `frontend/src/features/` |
| Frontend: compartilhado | `shared/{session,preferences,items,progress,hooks,ui,api-client}`; refresh compartilhado, retry de CSRF e Web Locks entre abas | `frontend/src/shared/` |
| Frontend: imagens | `ProtectedImage` e `useImageRecovery`: uma recuperação de sessão por janela, sem `/auth/me` | `frontend/src/shared/ui/` |
| Frontend: progresso | Salvamento com debounce, serializado, com `keepalive` ao ocultar a página | `frontend/src/shared/progress/` |
| Frontend: PWA | Manifest, meta tags de iOS, `skipWaiting` desligado, sem cache de `/api` | `frontend/vite.config.ts`, `frontend/index.html` |
| Frontend: remoção | `HomePage.tsx` e `useHealth.ts` removidos (substituídos pela biblioteca) | — |
| Scripts | Marcador `secret-scan:allow` (na mesma linha, só para valores fictícios de teste) | `scripts/check.ps1`, `scripts/check.sh`, `scripts/README.md` |

Decisões: ADR 0012 (backend serve o frontend) e ADR 0013 (progresso e preferências no servidor). ADR 0006 não foi alterado.

## Estado verificado

| Item | Resultado |
|---|---|
| Backend, pytest (informado pelo dev) | 1050 passed e 4 skipped no Windows, Python 3.14 |
| Backend, pytest (informado pelo dev) | 1054 passed, sem skips, dentro de `python:3.12.8-slim` com SQLite 3.40 |
| Frontend, Vitest (informado pelo dev) | 198 testes em 15 arquivos (no disco: 15 arquivos de teste em `frontend/tests/unit/`) |
| Contratos do import-linter | 8 (no disco: `backend/pyproject.toml`) |
| Migrações | `0001` a `0004` (no disco) |
| Regressões | `test_reg_001` a `013` e `015` a `019` (no disco). `014` reservado ao FIND-2026-009. Próximo livre: `020` |
| Funções `def test_` no backend | 568 em 59 arquivos (grep no disco; parametrizados não expandidos) |
| Blocos `it`/`test` no frontend | 144 em 15 arquivos (grep no disco; `it.each` não expandido) |
| Docker | Build, `up`, `healthy`, `/`, `/assets/*`, fallback de SPA, login com CSRF, scan e listagem, usuário não-root e sistema de arquivos somente leitura (validado em 2026-11-20, relatado em `infra/AGENTS.md` e `docs/DEPLOY.md`) |

## Validação no navegador (relatada pelo dev; não reproduzida aqui)

| Fluxo | Resultado |
|---|---|
| Login | OK |
| Biblioteca | OK |
| Leitor de mangá | OK |
| Retomada na página 2 após recarregar | OK |
| Tema claro salvo no servidor e aplicado em outro acesso | OK |
| "Continuar lendo" com item a 67% | OK |

## Não validado

| Item | Motivo |
|---|---|
| Service worker e instalação do PWA | O navegador embutido não registrou o SW; não foi possível provar |
| iOS real (Safari, Tela de Início) | Sem aparelho nesta entrega |
| Proxy, HTTPS e HSTS | Fora de escopo do app; não testado com proxy real |
| Backup e restauração pelo PowerShell (`docs/DEPLOY.md` §6) | Não executado |
| gitleaks e semgrep | Não instalados |
| `scripts/check.sh` em Linux real | Testado só com bash do Git no Windows |
| CI | Não existe (`.github/` ausente) |
| E2E (Playwright) | `frontend/tests/e2e/` vazio; navegadores do Playwright não instalados |

## Alterações de segurança

- CSP ampliada e explícita (ADR 0012): antes, `default-src 'self'` cobria scripts, conexões e fontes. Agora há diretivas explícitas para `script-src`, `connect-src`, `worker-src`, `manifest-src` e `font-src`. Continua sem `unsafe-inline` e sem `unsafe-eval`.
- Rate limit estrito deixou de contar `me` e `csrf` (são chamados a cada carga da SPA; o teste de regressão mostra que consumiam o balde de login). `test_reg_019`.
- Caminhos estáticos: GET e HEAD apenas; sem symlink; resolvidos dentro da raiz; sem consumo do limite da API.
- Progresso e preferências filtram sempre pelo `user_id` do token (`backend/tests/security/test_progress_authz.py`).

## Pendências e riscos

| Item | Situação | Próximo passo |
|---|---|---|
| FIND-2026-009 (lock por conta em IP novo) | `open` | Dono decide: `accepted-risk` ou mitigação (`test_reg_014`) |
| FIND-2026-001 (raio de dano do proxy) | Mitigado por obrigatoriedade e avisos | Operador confere o IP/CIDR do proxy |
| FIND-2026-002 (flood de login) | Corrigido; reverificação ao vivo pendente | Auditor reexecuta `docs/security/poc/flood_login.py` |
| M8 (lockfile com hashes e digest das imagens base) | Pendente | Antes de publicar |
| Colunas sem uso: `audit_log.ip`, `refresh_tokens.user_agent`, `refresh_tokens.ip` | Nunca preenchidas | Preencher ou remover em migração nova (apagar exige autorização) |
| `ComicInfo.xml` | Ignorado (sem parser seguro) | Dono decide a biblioteca XML |
| EPUB, PDF e CBR | Fase 4, não iniciados | Novos extratores e ADR se a CSP mudar |
| Flash de tema | Quem tem tema explícito diferente do sistema vê o tema do sistema por um instante, até `/auth/me` responder. `index.html` não tem script inline | Avaliar script inline com hash na CSP, ou aceitar |
| `finished` sem "reler do início" | Reabrir item concluído começa na última página | Decidir se há botão de reinício |
| Last-write-wins (ADR 0013) | Duas escritas concorrentes de dois aparelhos: a última gravada vence | Revisar só com caso real de conflito |
| Rate limit por rota (páginas, scan) | Não existe; só o global de `/api` e o estrito de credenciais | Decidir com o dono (FIND-010) |
| Token CSRF não amarrado à sessão | Só a checagem de origem protege | FIND-2026-010, item 4 |
| Cache de imagem por 1 h após logout | Não mitigado | FIND-2026-010, item 7 (`Clear-Site-Data` ou TTL menor) |
| Lockfile, CI, E2E | Pendentes | Ver `docs/PLANO.md` §9 |
| Atomicidade de rate limit e lockout | Só por processo (uma worker) | Limitação aceita (ADR 0009) |

## Próximo passo

Dono: decidir FIND-2026-009 e os itens de FIND-2026-010; decidir o botão de reinício e o flash de tema. Próxima entrega de código: teste E2E (login, mangá na página 5 e retomada, tema, offline) e validação do service worker em navegador real.
