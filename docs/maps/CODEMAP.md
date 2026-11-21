# CODEMAP

Arquivo → responsabilidade → camada. Estado: 2026-11-21. Conferido contra o disco nesta entrega (listagem de arquivos; leitura dos módulos alterados). Excluídos: `.venv`, `node_modules`, `dist`, `__pycache__`, caches (`.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.import_linter_cache`), `reader_backend.egg-info/` e `.github/scripts/__pycache__`, `infra/deploy-hook/__pycache__` (gerados).

## Raiz

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `AGENTS.md` | Regras gerais para agentes (regra 7: exceções de saída de rede) | docs |
| `CLAUDE.md` | Modo orquestrador | docs |
| `README.md` | Entrada do projeto | docs |
| `CHANGELOG.md` | Histórico de versões | docs |
| `SECURITY.md` | Política de reporte de vulnerabilidade (canal privado do GitHub; escopo; versões suportadas) | docs |
| `.gitignore` | Ignorados do git | config |
| `.gitattributes` | Fim de linha: `*.sh` em LF; `*.ps1` em CRLF | config |
| `.dockerignore` | Contexto de build: exclui venv, `node_modules`, `.env*` (exceto `.env.example`), `docs`, `scripts`, testes, bancos, `library`, `data`; em `infra/` só `constraints.txt`, `entrypoint.sh` | config |
| `.env.example` | Modelo de variáveis, sem segredos. Obrigatórias: `SECRET_KEY`, `FORWARDED_ALLOW_IPS` (vazias: preencher). `ALLOWED_ORIGINS` opcional. `APP_TAG` e `UPDATE_*` comentadas | config |
| `.github/workflows/ci.yml` | CI em push para `master`, pull request e `workflow_call`: jobs `backend` (ruff, mypy, lint-imports, pytest, bandit, pip-audit), `frontend` (lint, typecheck, test, arch, format, build, npm audit), `infra-tests` (deploy-hook e release_notes), `secrets` (gitleaks, versão fixada com checksum), `docker-build` (sem push) | ci |
| `.github/workflows/release.yml` | Release por tag `vX.Y.Z`: `prepare` (valida tag e seção do CHANGELOG; commit na `master`) → `verify` (chama `ci.yml`) → `publish` (GHCR, proveniência) → `release` (GitHub Release com as notas) | ci |
| `.github/dependabot.yml` | Atualizações semanais: actions, pip (`/backend`), npm (`/frontend`), docker (`/infra`) | ci |
| `.github/scripts/release_notes.py` | Valida a tag e extrai a seção do `CHANGELOG.md` para as notas da release | ci |
| `.github/scripts/test_release_notes.py` | Testes do extrator de notas (`unittest`, rodado no `infra-tests`) | teste |
| `.claude/agents/*.md` (8) | Subagentes | config |
| `.claude/skills/*/SKILL.md` (5) | Skills de briefing | config |
| `docs/PLANO.md` | Roteiro, requisitos, arquitetura, estado por fase | docs |
| `docs/AGENTS.md` | Regras de documentação | docs |
| `docs/DEPLOY.md` | Guia de operação com Docker (configurar, subir, admin, backup, atualização por release, webhook, troubleshooting) | docs |
| `docs/maps/*.md` (7) | Mapas: CODEMAP, ARCHITECTURE, DATAMODEL, API, ROUTES, SECURITY_MAP, TEST_MAP | docs |
| `docs/adr/README.md` | Índice dos ADRs (número, título, status, data) | docs |
| `docs/adr/0001..0018-*.md` (18) | Decisões. Aceitos: 0001 a 0016. Propostos (aguardam aceite do dono): 0017 (CSP do capítulo EPUB) e 0018 (oitavo host e webhook) | docs |
| `docs/history/*.md` (8) | Diário de entregas | docs |
| `docs/security/AGENTS.md`, `AUDIT_PROTOCOL.md` | Protocolo de auditoria | docs |
| `docs/security/AUDIT_REPORT_2026-11-19.md` | Relatório da auditoria (histórico) | docs |
| `docs/security/REMEDIATION_QUEUE.md` | Fila de remediação e seção "Estado após correções" | docs |
| `docs/security/findings/FIND-2026-001..012.md` (12; sem 013) | Um finding por arquivo. Status: 11 `fixed`, 1 `open` (009) | docs |
| `docs/security/poc/*.py`, `poc/README.md` | PoCs da auditoria (limites relaxados; só instância local) | docs |
| `infra/AGENTS.md` | Regras de infra e variáveis | docs |
| `infra/Dockerfile` | Imagem única em 3 estágios: (1) `node:24.21.0-slim` builda o frontend; (2) `python:3.12.8-slim` instala o backend com `PIP_CONSTRAINT` em `/install`; (3) runtime `python:3.12.8-slim`: usuário `app` uid 10001, pip/setuptools/wheel removidos, `/app/static` (frontend), `migrations`, `entrypoint.sh`. `ARG APP_VERSION=dev` (vem da release); ENV: `MIGRATIONS_DIR`, `FRONTEND_DIST_DIR=/app/static`, `DATABASE_URL`, `LIBRARY_PATH`, `DATA_DIR=/data`, `APP_VERSION`. `VOLUME /data`. HEALTHCHECK em Python. `ENTRYPOINT` | infra |
| `infra/entrypoint.sh` | Valida `SECRET_KEY` (≥ 32) e `FORWARDED_ALLOW_IPS` (sem padrão); `ALLOWED_ORIGINS` vazia é removida; aviso se `/library` não existe; `python -m app.cli migrate`; `exec uvicorn` com `--no-server-header`, `--proxy-headers --forwarded-allow-ips`, `--limit-concurrency`, `--timeout-keep-alive`, `--timeout-graceful-shutdown` (por `UVICORN_*`) | infra |
| `infra/gen_constraints.sh` | Gera os pins dentro de `python:3.12.8-slim` (runtime do `pyproject` + setuptools/wheel) | infra |
| `infra/constraints.txt` | Pins gerados (sem hashes: M8) | infra |
| `infra/compose.example.yml` | Serviço `backend`: `image: ghcr.io/andre-bueno/biblioteca-pwa:${APP_TAG:-latest}` com `build:` local; `SECRET_KEY` e `FORWARDED_ALLOW_IPS` obrigatórias (`:?`); defaults de sessão, login, rate limit, uvicorn e metadados; `UPDATE_CHECK_*` e `UPDATE_WEBHOOK_*` repassadas (padrões vazios ou seguros); porta `${BIND_ADDRESS:-127.0.0.1}:${HOST_PORT:-8000}`; `read_only`; `tmpfs /tmp`; `no-new-privileges`; `cap_drop: ALL`; `stop_grace_period`; `pids_limit`; `mem_limit`; `restart`; `../library:/library:ro`; volume `app-data` em `/data`, `DATA_DIR=/data`; rede com `ipam` em `${NETWORK_SUBNET:-172.30.77.0/24}` | infra |
| `infra/deploy-hook/receiver.py` | Receptor de REFERÊNCIA do webhook, no host (só biblioteca padrão): `POST /update`; HMAC, janela de 300 s, nonce, repositório e tag; grava `APP_TAG` no `.env`, `docker compose pull` e `up -d`, espera `healthy`, reverte se falhar. Escuta em `127.0.0.1` por padrão | infra |
| `infra/deploy-hook/README.md` | Contrato do webhook, verificações obrigatórias, variáveis `UPDATE_HOOK_*`, unidade systemd e teste manual | docs |
| `infra/deploy-hook/test_receiver.py` | Testes do receptor (`unittest`, runner falso, sem rede e sem Docker) | teste |
| `scripts/check.ps1` | Verificação única (Windows): backend, frontend, `infra: deploy-hook tests`, `ci: release_notes tests`, scan de segredos (com `secret-scan:allow`), resumo | scripts |
| `scripts/check.sh` | Verificação única (Linux/CI; testado só com bash do Git no Windows); mesmas etapas e marcador | scripts |
| `scripts/gitleaks.toml` | Config do gitleaks (`regexTarget = "line"`; usado no CI e se o binário existir localmente) | scripts |
| `scripts/README.md` | Uso do `check`, regras de saída, etapas e marcador `secret-scan:allow` | docs |

## backend/

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `backend/AGENTS.md` | Regras do backend | docs |
| `backend/pyproject.toml` | Dependências com versão fixa (`fastapi==0.165.0`, `uvicorn==0.54.0`, `pydantic-settings==2.16.3`, `sqlalchemy==2.1.9`, `alembic==1.20.1`, `argon2-cffi==25.1.0`, `PyJWT==2.15.1`); extra `dev` fixo; ruff, mypy strict, pytest, import-linter (8 contratos) | config |
| `backend/app/__init__.py` | Pacote | — |
| `backend/app/main.py` | `create_app(settings=None, *, container=None)`: FastAPI sem docs/OpenAPI e com `redirect_slashes=False`; `app.state.settings`, `container`, `csrf_signer`; handler 422 genérico; routers health, auth, items, books, series, library, progress, preferences, system; `install_spa` quando `FRONTEND_DIST_DIR` está definido; middlewares (ordem em `main.py`); aviso no lifespan se `FORWARDED_ALLOW_IPS` vazio ou `*`; `app = create_app()` | composição |
| `backend/app/composition.py` | `Container` (construção lazy sob trava): `clock`, `hasher`, `session_factory`, `user_service`, `item_repository`, `progress_repository`, `progress_service`, `series_repository`, `series_service`, `http_gateway`, `cover_store`, `metadata_service`, `enrich_runner`, `candidates_limiter`, `update_check_limiter` (3/min por admin), `update_gateway`, `update_notifier` (webhook, opcional), `update_service`, `preferences_service`, `storage`, `extractors`, `book_readers`, `scan_runner`, `auth_service`. Funções: `build_container`, `build_user_service`, `build_rate_limiters`, `run_migrations`. Único ponto ports → adapters (API e CLI) | composição |
| `backend/app/cli.py` | CLI admin (`python -m app.cli`): `migrate`, `create-user [--admin]`, `reset-password`, `deactivate-user`, `list-users`, `scan`, `enrich [--series <uuid>] [--force]`, `purge`. Senha só por `getpass` | entrada (CLI) |
| `backend/app/core/__init__.py` | Pacote | — |
| `backend/app/core/config.py` | `Settings` (env e `.env`, `hide_input_in_errors=True`): `SECRET_KEY` (≥ 32, ≥ 12 distintos, sem espaço nas pontas, sem bloco ≤ 8 repetido); `ALLOWED_ORIGINS` (exatas); `COOKIE_SECURE`; `LIBRARY_PATH`; `DATABASE_URL`; `MIGRATIONS_DIR`; `FRONTEND_DIST_DIR` (vazio = não serve; sem `index.html` = falha no startup); `DATA_DIR`; `METADATA_*`; `APP_VERSION` (padrão `dev`; `dev` desliga a checagem); `UPDATE_CHECK_ENABLED`, `UPDATE_REPOSITORY` (`owner/name`), `UPDATE_CHECK_INTERVAL_HOURS` (1 a 168), `UPDATE_WEBHOOK_URL`, `UPDATE_WEBHOOK_SECRET` (≥ 32, sem espaço nas pontas; URL e segredo juntos), `UPDATE_WEBHOOK_ALLOW_HTTP` (http só em rede do operador; IP literal validado no startup); `EXTRACTOR_*`; `MAX_BODY_BYTES`; `AUDIT_RETENTION_DAYS`; `FORWARDED_ALLOW_IPS` (só aviso); sessão (`ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`, `SESSION_ABSOLUTE_TTL_SECONDS`, `REFRESH_REUSE_GRACE_SECONDS`); login (`LOGIN_*`); `RATE_LIMIT_*`. Validadores de origem, de limites e do webhook. `max_failures_from_one_address()`. `get_settings()` com `lru_cache` | core |
| `backend/app/core/keys.py` | `derive_key()`: HKDF-SHA256 com rótulos `access-jwt`, `csrf-token`, `login-attempts` | core |
| `backend/app/api/__init__.py` | Pacote | — |
| `backend/app/api/health.py` | `GET /api/v1/health` | api |
| `backend/app/api/auth.py` | Rotas `/api/v1/auth/*` (csrf, login, refresh, logout, me, change-password); cookies `access_token`, `refresh_token`, `csrf_token`; mapeia erros de domínio para HTTP | api |
| `backend/app/api/auth_schemas.py` | `LoginRequest`, `ChangePasswordRequest` (strict, `extra=forbid`, limites), `UserOut` (inclui `theme_pref`) | api |
| `backend/app/api/csrf.py` | `CsrfTokenSigner` (nonce 32 bytes + HMAC) e `CsrfMiddleware` (só `/api`; cookie + cabeçalho + Origin / Sec-Fetch-Site / Referer; 403 genérico) | api |
| `backend/app/api/rate_limit.py` | `RateLimitMiddleware` (só `/api`): limite global por IP; limite estrito só em `/auth/login`, `/auth/refresh`, `/auth/logout` e `/auth/change-password`; 429 genérico com `Retry-After` | api |
| `backend/app/api/body_limit.py` | `BodySizeLimitMiddleware` (só `/api`): 413 por `Content-Length` e por bytes recebidos; 400 para `Content-Length` inválido | api |
| `backend/app/api/security_headers.py` | `SecurityHeadersMiddleware`: CSP explícita (ADR 0012), nosniff, Referrer-Policy, Permissions-Policy sobrepõem a rota (ADR 0006); `Cache-Control: no-store` e `Pragma` em `/api`; exceção de cache de imagem por marcador interno (ADR 0010; páginas, capa de item, capa de série e capítulo de livro); CSP própria do capítulo EPUB (`BOOK_CHAPTER_CSP`, só GET 200 do caminho exato; ADR 0017); 500 JSON genérico; desconexão só em debug; `CancelledError` propaga | api |
| `backend/app/api/spa.py` | `install_spa()` e `SpaApp`: serve `FRONTEND_DIST_DIR` como `router.default` (só fora de `/api`); GET/HEAD; caminhos validados; sem symlink; fallback `index.html`; `assets/*` imutável, demais `no-cache`; `Range` via `FileResponse` | api |
| `backend/app/api/http_utils.py` | Helpers ASGI sem regra de negócio: `is_api_path`, `client_ip` (IPv4-mapeado → IPv4; IPv6 → /64; inválido → "unknown"), `header`, `header_count`, `send_json_error` | api |
| `backend/app/api/errors.py` | `library_error()` (mapeia pela classe: 404, 409, 422, 502, 503); `not_found()`; handler de validação 422 genérico | api |
| `backend/app/api/ids.py` | `item_id_or_404()`: UUID canônico em minúsculas, senão 404 genérico | api |
| `backend/app/api/deps.py` | Dependências de rota: `get_container`, `get_settings_dep`, `get_csrf_signer`, `get_auth_service`, `get_current_user` (cookie `access_token`; 401), `require_admin` (403), `get_user_service`, `get_item_repository`, `get_extractors`, `get_book_readers`, `get_scan_runner` (503 se biblioteca indisponível), `get_progress_service`, `get_preferences_service`, `get_series_service`, `get_series_repository`, `get_metadata_service`, `get_cover_store`, `get_candidates_limiter`, `get_enrich_runner`, `get_update_service`, `get_update_check_limiter`. Sem cache próprio. Único módulo de `api` que importa `app.composition` | composição |
| `backend/app/api/items.py` | `/api/v1/items`: lista (filtros `type`, `q`; `limit`, `offset`), detalhe, página e capa com ETag e 304; autenticado no router. Helpers `image_response` e `etag_matches` usados por livros | api |
| `backend/app/api/books.py` | `/api/v1/items/{id}/book` (metadados e sumário), `/book/chapters/{n}` (HTML saneado; `theme` e `size` validados; ETag; CSP pelo middleware), `/book/res/{rid}` (imagem por índice numérico). Autenticado no router; erros por classe, 404 genérico | api |
| `backend/app/api/book_schemas.py` | `BookOut` (`title`, `authors`, `language`, `chapters`, `toc`, `has_cover`), `ChapterOut` (`index`, `title`), `TocEntryOut` (`title`, `index`, `anchor`) | api |
| `backend/app/api/library.py` | `/api/v1/library`: `POST /scan` (202, em segundo plano) e `GET /scan/status`; `POST /enrich` (202, `force`) e `GET /enrich/status`; só admin | api |
| `backend/app/api/library_schemas.py` | `ItemOut`, `ItemListOut`, `ScanStatusOut`, `EnrichStatusOut`; nunca `rel_path` | api |
| `backend/app/api/system.py` | `/api/v1/system`: `GET /version` (usuário comum recebe só `current` e `update_available`; admin recebe o estado completo), `POST /update/check` (admin; 3/min; 429), `POST /update` (admin; 202; tag igual à última release; 409, 502 ou 503). Sem leitura nem alteração da URL do webhook | api |
| `backend/app/api/progress.py` | `/api/v1/progress`: `GET /continue` (declarada antes de `/{item_id}`), `GET`, `PUT` e `DELETE /{item_id}`; autenticado; erros genéricos | api |
| `backend/app/api/progress_schemas.py` | `SaveProgressRequest` (strict; `locator` 0..2^31-1; `device_id` opcional `^[A-Za-z0-9_-]{1,64}$`), `ProgressOut`, `ContinueItemOut`, `ContinueListOut`, `PreferencesIn` (strict; `theme` e `reading_direction` obrigatórios; `book_font_scale` 80–200 e `book_theme` opcionais), `PreferencesOut` (inclui os dois campos de livro) | api |
| `backend/app/api/preferences.py` | `/api/v1/me/preferences`: `GET` e `PUT` do próprio usuário | api |
| `backend/app/api/series.py` | `/api/v1/series`: `GET` (lista), `GET /{id}`, `GET /{id}/cover`; admin: `GET /{id}/metadata/candidates` (10/min por usuário), `POST /{id}/metadata/select`, `PUT` e `DELETE /{id}/metadata`; ids opacos; erros genéricos | api |
| `backend/app/api/series_schemas.py` | `SeriesListOut`, `SeriesOut` (`kind` manga/book/mixed; capítulos com `type`; `continue` como `resume`), `SeriesMetadataOut`, `CandidateOut`, `SelectCandidateRequest` e `ManualMetadataRequest` (strict, `extra=forbid`); nunca caminho, `cover_path` nem URL de capa | api |
| `backend/app/domain/__init__.py` | Pacote | — |
| `backend/app/domain/errors.py` | `DomainError` e filhos: `UnsafePath`, `UnsupportedFormat`, `ArchiveLimitExceeded`, `CorruptArchive`, `PageOutOfRange`, `ItemNotFound`, `LibraryUnavailable`, `ScanAlreadyRunning`, `DataAccessError`, `ResourceBusy`; de atualização: `UpdateNotConfigured`, `UpdateNotAvailable`, `UpdateAlreadyRequested`, `UpdateNotifyFailed`; de livro: `InvalidBookOptions` (em `domain/book.py`). Mensagens sem caminho nem segredo | domain |
| `backend/app/domain/user.py` | `User` (imutável; `__repr__` sem hash), `Role` (admin, user), `normalize_username()`, `UserError` e filhos, `UserNotFoundError` | domain |
| `backend/app/domain/password_policy.py` | `validate_password()`: 12–128 caracteres; diferente do username; username (≥ 3 caracteres) não contido, nem invertido; lista de 20 senhas comuns; ≥ 5 caracteres distintos; bloco repetido fraco (< 8, palavra comum ou sequência); sequência de alfabeto, dígitos ou teclado | domain |
| `backend/app/domain/auth.py` | `RefreshToken` (`repr` sem token), `AccessClaims`, erros de autenticação: `InvalidCredentialsError`, `LoginLockedError` (com `retry_after_seconds`), `InvalidSessionError`, `NotAuthenticatedError`, `InvalidTokenError`, `CurrentPasswordError` | domain |
| `backend/app/domain/lockout.py` | `LockoutPolicy` e `locked_until()`: bloqueio progressivo calculado das falhas registradas | domain |
| `backend/app/domain/item.py` | `Item` (id UUID opaco, `rel_path`, `format`, `page_count`, `size`, `mtime_ns`, `content_hash`, `missing`; `has_cover`), `ItemType` (manga, book, pdf) | domain |
| `backend/app/domain/library.py` | `ExtractorLimits`, `ItemMetadata`, `Page`, `ScanError`, `ScanProgress`, `ScanReport` (`removal_skipped`), `sanitize_title()`, `natural_key()` | domain |
| `backend/app/domain/book.py` | Regras puras de livro: `BOOK_THEMES` (auto, light, dark, sepia), tamanho de fonte 80–200 (padrão 100), `validate_book_options`, `ChapterRef`, `TocEntry`, `BookInfo`; URL pública de imagem `/api/v1/items/{item_id}/book/res/{rid}` | domain |
| `backend/app/domain/progress.py` | `Progress` (imutável, `device_id` opcional), `ContinueEntry` (item + progresso), `compute_position()` (manga/PDF: `percent` e `finished` pela página; livro: `compute_book_position`, `locator = capítulo * 10000 + offset_bp`, concluído no último capítulo com offset ≥ 9000); fora da faixa: `InvalidLocator` | domain |
| `backend/app/domain/preferences.py` | `Preferences` (`theme`: system, light, dark; `reading_direction`: rtl, ltr, vertical; `book_font_scale` 80–200; `book_theme`: auto, light, dark, sepia; valida no construtor), `InvalidPreferences` | domain |
| `backend/app/domain/series.py` | Agrupamento puro: `group_entry` (série = pasta pai; avulso na raiz), `parse_chapter_number`, `sort_title` (dígitos preenchidos), `sort_chapters`, `chapter_title`, `pick_continue`, `short_description`, `series_kind` (manga, book ou mixed); `MetadataState` | domain |
| `backend/app/domain/metadata.py` | Regras puras de metadados: `sanitize_description`, `sanitize_title`, `pick_best` (limiares 0,85 e 0,9, margem, edições penalizadas, desempate por ano), `pick_description`, `sniff_image` (JPEG, PNG, WebP), `chunk_for_translation`, `valid_translation`, `fix_missing_sentence_space` (REG-023), `PROVIDER_LABELS`, `DESCRIPTION_ONLY`, `EnrichReport` | domain |
| `backend/app/domain/release.py` | Versão e release: `Version`, `parse_tag`, `parse_app_version` (`dev` = sem checagem), `valid_repository`, `is_operator_network` (loopback, privada, ULA e CGNAT 100.64.0.0/10; link-local recusado), `Release`, `parse_release`, `ConditionalJson` (resposta com ETag), `UpdateRequest`, `UpdateStateName` | domain |
| `backend/app/services/__init__.py` | Pacote | — |
| `backend/app/services/auth_service.py` | `AuthService` e `AuthConfig` (injetado): `login` (bloqueio e falha reservados antes do hash), `refresh` (rotação com janela de tolerância; reuso revoga a família), `logout`, `change_password` (revoga todas as sessões), `current_user` (valida no banco), `purge_expired`; purga oportunista de hora em hora | services |
| `backend/app/services/user_service.py` | Contas: `create_user`, `reset_password`, `deactivate_user`, `list_users`; grava auditoria | services |
| `backend/app/services/scan.py` | `scan_library()`: varredura incremental por size+mtime; erro por arquivo sem abortar; remoção de sumidos só com caminhada saudável; agrupamento em série e número do capítulo (ADR 0014) | services |
| `backend/app/services/scan_runner.py` | `ScanRunner`: uma varredura por vez (lock não bloqueante); thread daemon (API) ou síncrona (CLI); status sem caminho nem mensagem; sem cancelamento | services |
| `backend/app/services/catalog.py` | `list_items()` (limite efetivo 1–100, `has_more`) e `get_item()` | services |
| `backend/app/services/pages.py` | `get_page()` e `get_cover()`: valida índice e formato; delega ao extrator | services |
| `backend/app/services/hashing.py` | `ensure_content_hash()`: sha256 sob demanda e persistido. Sem rota que a chame | services |
| `backend/app/services/progress_service.py` | `ProgressService`: `save` (valida locator contra o item, deriva `percent`/`finished` pelo tipo, carimba com o relógio do servidor, upsert), `get`, `clear` (idempotente), `continue_reading` (limite capado em 50) | services |
| `backend/app/services/preferences_service.py` | `PreferencesService`: `get` e `update` (`UserNotFoundError` se o usuário não existe); grava também os campos de livro | services |
| `backend/app/services/series_service.py` | `SeriesService`: `list_series` (limite capado em 100), `get_series` (capítulos com `type`, progresso do usuário, `continue`, `kind`); `get_series_cover` (capa baixada ou do primeiro capítulo legível, até 5 tentativas) | services |
| `backend/app/services/metadata_service.py` | `MetadataService`: `enrich_all` (uma execução, até `METADATA_MAX_PER_RUN`; pula séries de livro), elegibilidade por estado, fusão de fontes (`_apply_work`, `_resolve_description`), `candidates`, `select`, `set_manual`, `clear`; capa com escrita condicional ao estado atual; falha de fonte não derruba a execução | services |
| `backend/app/services/enrich_runner.py` | `EnrichRunner`: uma execução por vez (thread em segundo plano na API; síncrona no CLI); estado `idle`, `running`, `finished`, `failed` com contagens | services |
| `backend/app/services/book.py` | Casos de uso de livro: `get_book`, `get_chapter` (opções validadas antes de abrir o arquivo), `get_resource`; usa os leitores de livro registrados | services |
| `backend/app/services/update_service.py` | `UpdateService`: consulta preguiçosa da última release (ETag, cache de `UPDATE_CHECK_INTERVAL_HOURS`, single-flight, pausa após falha ou limitação); `request_update` (tag igual à última release e mais nova; webhook; auditoria `system.update_requested` e `system.update_failed`); estado do pedido só em memória | services |
| `backend/app/ports/__init__.py` | Pacote | — |
| `backend/app/ports/user_repository.py` | `UserRepository`: `add`, `replace_password_hash` (compare-and-set), `set_password_hash`, `deactivate`, `get_by_id`, `get_by_username`, `list_all` | ports |
| `backend/app/ports/refresh_token_repository.py` | `RefreshTokenRepository`: `add`, `get_by_hash`, `mark_used` (só teste), `rotate`, `revoke_family`, `revoke_all_for_user`, `family_started_at`, `is_family_active`, `purge_dead_families` | ports |
| `backend/app/ports/login_attempt_store.py` | `LoginAttemptStore`: `fingerprint`, `record`, `reserve_failures`, `release`, `failures_since_last_success`, `last_success_at`, `purge` | ports |
| `backend/app/ports/token_service.py` | `TokenService`: `issue_access_token`, `decode_access_token` | ports |
| `backend/app/ports/password_hasher.py` | `PasswordHasher`: `hash`, `verify` (`None` = hash dummy), `needs_rehash` | ports |
| `backend/app/ports/audit_log.py` | `AuditLog` (`record`, `purge`); `AuditDetail` sem segredos | ports |
| `backend/app/ports/clock.py` | `Clock` (`now()` aware, UTC) | ports |
| `backend/app/ports/rate_limiter.py` | `RateLimiter` e `RateDecision` | ports |
| `backend/app/ports/storage.py` | `StorageBackend` (`walk_errors`, `list_entries`, `list_children`, `stat`, `open`) e `StorageEntry` (caminho relativo POSIX) | ports |
| `backend/app/ports/extractor.py` | `Extractor` (`format`, `item_type`, `can_handle`, `inspect`, `read_page`, `read_cover`) | ports |
| `backend/app/ports/book_reader.py` | `BookReader` (interface): `read_book`, `read_chapter` (HTML saneado, `resource_url` por imagem), `read_resource` (imagem por índice); implementado por `EpubExtractor` | ports |
| `backend/app/ports/item_repository.py` | `ItemRepository`: `add`, `update`, `get`, `get_by_rel_path`, `list`, `search`, `remove_missing` | ports |
| `backend/app/ports/progress_repository.py` | `ProgressRepository`: `upsert` (atômico, último vence), `get`, `delete` (idempotente), `list_continue` (não concluídos, item não ausente, mais recente primeiro); toda operação recebe `user_id` | ports |
| `backend/app/ports/preferences_repository.py` | `PreferencesRepository`: `get` (None = usuário inexistente), `set` (escrita só das colunas de preferência; False = inexistente) | ports |
| `backend/app/ports/series_repository.py` | `SeriesRepository` (interface): lista de séries, detalhe, capítulos e atualização condicional de metadado | ports |
| `backend/app/ports/cover_store.py` | `CoverStore` (interface): `stage`, `commit`, `discard`, `read`, `delete` de capas | ports |
| `backend/app/ports/http_gateway.py` | `HttpGateway` (interface): `get_json`, `get_json_conditional` (só release, com ETag), `post_json`, `get_image`; só hosts da allowlist | ports |
| `backend/app/ports/metadata_provider.py` | `MetadataProvider` (interface): busca e obtenção por id em uma fonte pública | ports |
| `backend/app/ports/translator.py` | `TextTranslator` (interface): tradução de sinopse; `None` quando indisponível | ports |
| `backend/app/ports/update_notifier.py` | `UpdateNotifier` (interface): `notify(UpdateRequest)`; implementado pelo webhook | ports |
| `backend/app/adapters/__init__.py` | Pacote | — |
| `backend/app/adapters/AGENTS.md` | Regras de adapters (área sensível) | docs |
| `backend/app/adapters/gate.py` | `BoundedGate`: N slots, até M em espera por T s; excedente levanta `ResourceBusy` | adapters |
| `backend/app/adapters/http/__init__.py` | Pacote | — |
| `backend/app/adapters/http/safe_gateway.py` | `SafeGateway`: única saída de rede de conteúdo. https, porta 443, lista fixa de 8 hosts (inclui `api.github.com`, só para `get_json_conditional`, ADR 0018), sem redirecionamento, IP público verificado e conexão fixada, TLS com verificação, sem cookies, User-Agent `BibliotecaPWA/1.0`, limites (JSON 1 MiB, imagem 5 MiB, POST 16 KiB, URL 2 048), 0,5 s entre requisições por host; `DisabledGateway` (sem socket) quando `METADATA_ENABLED=false` (ADR 0015) | adapters |
| `backend/app/adapters/http/webhook_notifier.py` | `WebhookNotifier`: POST assinado (`X-Update-Timestamp`, `X-Update-Signature` HMAC-SHA256) para `UPDATE_WEBHOOK_URL`; https sempre; http só se todo endereço resolvido for de rede do operador; conexão ao endereço verificado; sem redirecionamento; 10 s; resposta lida até 4 KiB e ignorada. Única saída fora do `SafeGateway` (ADR 0018) | adapters |
| `backend/app/adapters/metadata/__init__.py` | Pacote (sem código) | — |
| `backend/app/adapters/metadata/_json.py` | Leitura defensiva de JSON da rede: tipo errado vira vazio; limites de texto e de itens | adapters |
| `backend/app/adapters/metadata/mangadex.py` | `MangaDexProvider` (obra): capa, descrição pt-br, títulos alternativos; busca com 10 resultados | adapters |
| `backend/app/adapters/metadata/anilist.py` | `AniListProvider` (obra, POST GraphQL): capa e descrição em inglês | adapters |
| `backend/app/adapters/metadata/wikipedia.py` | `WikipediaProvider` (só descrição, pt): busca e resumo, até 2 páginas por busca | adapters |
| `backend/app/adapters/metadata/googlebooks.py` | `GoogleBooksProvider` (só descrição; cota anônima pequena) | adapters |
| `backend/app/adapters/metadata/mymemory.py` | `MyMemoryTranslator` (en → pt-BR, último recurso): trechos de até 400 bytes, tudo ou nada; para 6 h após resposta de cota; aplica `fix_missing_sentence_space` (REG-023) | adapters |
| `backend/app/adapters/persistence/__init__.py` | Pacote | — |
| `backend/app/adapters/persistence/db.py` | `create_db_engine()` (SQLite: WAL, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL` em toda conexão; `hide_parameters=True`) e `create_session_factory()` | adapters |
| `backend/app/adapters/persistence/models.py` | ORM: `UserRow` (com `reading_direction`, `book_font_scale`, `book_theme`), `RefreshTokenRow`, `LoginAttemptRow`, `ItemRow`, `AuditLogRow`, `ReadingProgressRow`; `UTCDateTime` (grava UTC naive, lê UTC aware). Schema é da migração | adapters |
| `backend/app/adapters/persistence/user_repository.py` | `SqlAlchemyUserRepository`: escritas por UPDATE dirigido (CAS de hash com `is_active` e hash esperado); busca de username sem caixa; erro de driver vira `DataAccessError` | adapters |
| `backend/app/adapters/persistence/refresh_token_repository.py` | `SqlAlchemyRefreshTokenRepository`: `rotate` atômico (marca usado e grava sucessor na mesma transação; janela de tolerância); revogação de família e de usuário; purga de famílias mortas | adapters |
| `backend/app/adapters/persistence/login_attempt_store.py` | `SqlAlchemyLoginAttemptStore`: chaves em HMAC-SHA256 por escopo; reserva e liberação de falhas; falhas desde o último sucesso; purga | adapters |
| `backend/app/adapters/persistence/audit_log.py` | `SqlAlchemyAuditLog`: `record` com `at` do relógio (detalhe > 512 bytes vira `{"truncated": true}`); `purge` | adapters |
| `backend/app/adapters/persistence/item_repository.py` | `SqlAlchemyItemRepository`: CRUD de `Item`; listagem por `(lower(title), id)`; busca com LIKE escapado; `remove_missing` em lotes de 500 | adapters |
| `backend/app/adapters/persistence/progress_repository.py` | `SqlAlchemyProgressRepository`: upsert `INSERT ... ON CONFLICT DO UPDATE` (SQLite e PostgreSQL); `get`, `delete`, `list_continue` (JOIN com `items`); erro de driver vira `DataAccessError` | adapters |
| `backend/app/adapters/persistence/preferences_repository.py` | `SqlAlchemyPreferencesRepository`: lê e grava só `users.theme_pref`, `users.reading_direction`, `users.book_font_scale` e `users.book_theme` | adapters |
| `backend/app/adapters/persistence/series_repository.py` | `SqlAlchemySeriesRepository`: lista só séries com capítulo ativo, por `sort_title`; detalhe; capítulos em ordem; atualização de metadado condicional ao estado atual; capa e atribuição gravadas | adapters |
| `backend/app/adapters/persistence/migrator.py` | `upgrade()` e `downgrade()` do Alembic, programático (sem `alembic.ini`). Diretório: argumento, `MIGRATIONS_DIR` ou `backend/migrations` do checkout | adapters |
| `backend/app/adapters/security/__init__.py` | Pacote | — |
| `backend/app/adapters/security/argon2_hasher.py` | `Argon2Hasher`: Argon2id (t=3, m=64 MiB, p=4); hash dummy com os mesmos parâmetros; senha > 1024 caracteres recusada sem hash; `BoundedGate` de 2 slots, 8 em espera por 1 s | adapters |
| `backend/app/adapters/security/jwt_tokens.py` | `JwtTokenService`: HS256 fixo; claims `sub`, `sid`, `jti`, `iat`, `nbf`, `exp` obrigatórias; tempo pelo relógio injetado; token > 2048 caracteres recusado | adapters |
| `backend/app/adapters/security/rate_limiter.py` | `TokenBucketRateLimiter`: balde de fichas em memória por chave; até 50 000 chaves (LRU) | adapters |
| `backend/app/adapters/security/system_clock.py` | `SystemClock` (UTC) | adapters |
| `backend/app/adapters/storage/__init__.py` | Pacote | — |
| `backend/app/adapters/storage/local.py` | `LocalStorage`: único que resolve caminho relativo. Rejeita `..`, absoluto, unidade, nomes reservados do Windows, caracteres inválidos, > 1024 caracteres, > 16 níveis, symlink e junction reais (não o atributo ReparsePoint do OneDrive); `walk_errors` | adapters |
| `backend/app/adapters/storage/cover_store.py` | `LocalCoverStore`: capas em `DATA_DIR/covers/<uuid>.<ext>`; nome só do UUID do servidor e da extensão dos bytes; escrita temporária exclusiva, `fsync` e renomeação atômica; leitura só de arquivo regular, sem symlink, até 5 MiB (ADR 0016) | adapters |
| `backend/app/adapters/extractors/__init__.py` | Pacote | — |
| `backend/app/adapters/extractors/_common.py` | `sniff_image()` (bytes mágicos: jpeg, png, webp, gif, avif), `has_image_extension()`, `PageIndexCache` (LRU de 64 por `(rel_path, size, mtime_ns)`), `default_read_gate()` (4 leitores, 16 em espera, 2 s) | adapters |
| `backend/app/adapters/extractors/cbz.py` | `CbzExtractor` (`format=cbz`, `item_type=manga`): índice em cache; valida bytes de todas as entradas; limites; rejeita criptografado, symlink e nome inseguro (zip-slip); ordem natural; `ComicInfo.xml` ignorado | adapters |
| `backend/app/adapters/extractors/folder.py` | `FolderExtractor` (`format=folder`, `item_type=manga`): uma pasta = um item; índice valida bytes de todos os arquivos de imagem; limites; leitura limitada a `max_page_bytes + 1` | adapters |
| `backend/app/adapters/extractors/epub.py` | `EpubExtractor` (`format=epub`, `item_type=book`): lê OPF, spine, TOC e capa; recusa DRM (`rights.xml`, criptografia que não seja ofuscação de fonte) e pacote fora dos limites; `read_chapter` sanitiza; imagens por índice numérico (`rid`); fontes e SVG nunca servidos | adapters |
| `backend/app/adapters/extractors/_epub_safe.py` | Leitura segura do pacote EPUB (limites e caminhos internos) | adapters |
| `backend/app/adapters/extractors/_epub_html.py` | Sanitizador de HTML do capítulo por allowlist de tags e atributos; imagens viram URL pública por `rid` (`resource_url`) | adapters |
| `backend/app/adapters/extractors/_epub_css.py` | Filtro de CSS embutido por allowlist de propriedades e valores (cores, comprimentos, enums); estilo gerado só com valores validados | adapters |
| `backend/app/adapters/extractors/registry.py` | `build_extractors()`: CBZ, pasta e EPUB com um gate compartilhado; `book_readers()` filtra os que leem livro. Novo formato entra aqui | adapters |
| `backend/migrations/env.py` | Ambiente Alembic: URL recebida em `config.attributes["url"]` | migrações |
| `backend/migrations/script.py.mako` | Modelo de nova revisão Alembic | migrações |
| `backend/migrations/versions/0001_users_and_auth.py` | Cria `users` (com `theme_pref`), `refresh_tokens`, `login_attempts`, `audit_log` | migrações |
| `backend/migrations/versions/0002_items.py` | Cria `items` (checks de tipo e de `page_count`; índices `ix_items_type`, `ix_items_title`, `ix_items_added_at`, `ix_items_missing`) | migrações |
| `backend/migrations/versions/0003_drop_unused_item_indexes.py` | Remove `ix_items_title` e `ix_items_missing` (reversível) | migrações |
| `backend/migrations/versions/0004_reading_progress_and_preferences.py` | `users.reading_direction` (`ALTER ADD COLUMN`, `NOT NULL DEFAULT 'rtl'`, check) e tabela `reading_progress` (PK `(user_id, item_id)`, FKs com CASCADE, checks de `locator` e `percent`, índice `(user_id, updated_at DESC)`). Reversível | migrações |
| `backend/migrations/versions/0005_series.py` | Cria `series` (CHECK de `metadata_state`; `folder_rel_path` único; índice `sort_title`); `items.series_id` (FK `ON DELETE SET NULL`) e `items.chapter_number` por `ALTER ADD COLUMN`; backfill idempotente. Reversível | migrações |
| `backend/migrations/versions/0006_series_metadata_fields.py` | `series.source_url`, `metadata_checked_at`, `title_original` por `ALTER ADD COLUMN`. Reversível | migrações |
| `backend/migrations/versions/0007_series_description_attribution.py` | `series.description_origin` (CHECK: source, translated, manual), `description_source_name`, `description_source_url`; backfill de descrições anteriores. Reversível | migrações |
| `backend/migrations/versions/0008_book_reader_preferences.py` | `users.book_font_scale` (`NOT NULL DEFAULT 100`, CHECK 80–200) e `users.book_theme` (`NOT NULL DEFAULT 'auto'`, CHECK auto/light/dark/sepia) por `ALTER ADD COLUMN`. Reversível | migrações |
| `backend/tests/AGENTS.md` | Regras de teste: nomes, 500 com `TestClient`, `caplog`, casos negativos de arquitetura | docs |
| `backend/tests/conftest.py` | Fixtures de ambiente hermético (remove variáveis do ambiente real; `SECRET_KEY` de teste; diretório de trabalho vazio) e cliente | teste |
| `backend/tests/fakes.py` | Auxiliares (`png`, `make_cbz`, `make_library`), `FixedClock` e falsos (`FakeItemRepository`, `FakeStorage`, `FakeExtractor`). Não é teste | teste |
| `backend/tests/auth_fakes.py` | Falsos de autenticação (`FakeClock`, `FakeHasher`, `FakeUsers`, `FakeRefreshTokens`, `FakeAttempts`, `FakeAudit`), `Rig`, `Env` e `ApiClient` (ambiente HTTP com banco). Não é teste | teste |
| `backend/tests/metadata_fakes.py` | `FakeGateway` (aplica a allowlist real e responde de memória), respostas canônicas das fontes e `fake_translation`. Não é teste | teste |
| `backend/tests/library_env.py` | Helpers de API de biblioteca: `library_env`, `logged_in`, `add_item`, `item_id_by_title`, `metadata_env`. Não é teste | teste |
| `backend/tests/epub_fixtures.py` | Construtores de EPUB para testes. Não é teste | teste |
| `backend/tests/update_fakes.py` | Falsos para os testes de atualização. Não é teste | teste |
| `backend/tests/architecture/test_layers.py` | Executa import-linter de verdade; casos negativos por `forbidden_modules`; positivos de `api.deps`, `composition`, `cli`, `main` | teste |
| `backend/tests/integration/test_health.py` | Health | teste |
| `backend/tests/integration/test_migrations.py` | Sobe e desce; ORM × schema; índices; pragmas; unicidade; checks; `0002`/`0003` reversíveis; `0004` reversível sem perder usuários nem sessões; checks de `reading_progress` e das colunas de livro (`0008`) | teste |
| `backend/tests/integration/test_migrations_dir.py` | Resolução de `MIGRATIONS_DIR`; Dockerfile define `MIGRATIONS_DIR` | teste |
| `backend/tests/integration/test_user_repository.py` | Repositório de usuário e auditoria contra banco migrado | teste |
| `backend/tests/integration/test_auth_repositories.py` | Refresh (rotação, revogação, famílias, purga) e tentativas (HMAC, escopos, reset por sucesso, purga) | teste |
| `backend/tests/integration/test_item_repository.py` | Persistência de `Item`: roundtrip, ordem, filtros, `remove_missing`, LIKE literal, purga de auditoria | teste |
| `backend/tests/integration/test_auth_api.py` | API de auth ponta a ponta: login, me, refresh, logout, troca de senha, reset pelo admin, auditoria, `require_admin` | teste |
| `backend/tests/integration/test_library_api.py` | Login → scan → listar → página; scan concorrente (409); biblioteca ausente (503); CLI `scan` | teste |
| `backend/tests/integration/test_library_scan.py` | Scan, página e capa com `LocalStorage` e repositório falso | teste |
| `backend/tests/integration/test_cli.py` | CLI ponta a ponta (migrate, create, list, reset, deactivate); senha sem eco; sem argumento de senha | teste |
| `backend/tests/integration/test_progress_api.py` | API de progresso e preferências: cálculo no servidor, cliente não envia `percent`/`finished`, 422 e 404 genéricos, `DELETE` idempotente, `continue`, UTC com offset, preferências e rate limit de navegação | teste |
| `backend/tests/integration/test_progress_repository.py` | Upsert e `get` (roundtrip), upserts concorrentes sem falha, cascata de item e de usuário, `list_continue` por usuário, repositório de preferências só nas suas colunas | teste |
| `backend/tests/integration/test_docker_files.py` | Checagens estáticas da imagem: `entrypoint.sh` LF e estrito; `.gitattributes`; Dockerfile fixado e não-root; constraints cobrem o runtime; hardening do compose; `.dockerignore` | teste |
| `backend/tests/unit/test_argon2_hasher.py` | Argon2id, sal, hash dummy, senha longa, rehash | teste |
| `backend/tests/unit/test_password_policy.py` | Política de senha e validação de username | teste |
| `backend/tests/unit/test_user_service.py` | `UserService` com falsos: criação, auditoria, reset, desativação | teste |
| `backend/tests/unit/test_library_services.py` | `natural_key`, `sanitize_title`, scan incremental, páginas, hash de conteúdo | teste |
| `backend/tests/unit/test_scan_runner_and_catalog.py` | `ScanRunner` (exclusão, falhas, relógio, liberação de trava); catálogo; purga de auditoria | teste |
| `backend/tests/unit/test_auth_service.py` | `AuthService` com falsos: login, bloqueio por escopo, refresh, logout, troca de senha, `current_user` | teste |
| `backend/tests/unit/test_lockout.py` | `locked_until()` e `lookback` | teste |
| `backend/tests/unit/test_rate_limiter.py` | Balde de fichas: burst, recarga, chaves, memória limitada, limites inválidos | teste |
| `backend/tests/unit/test_keys.py` | HKDF: determinístico, rótulos independentes, nunca o segredo cru | teste |
| `backend/tests/unit/test_progress_service.py` | `compute_position`, `save` (percent/finished e relógio do servidor), locator fora do item não grava, progresso por usuário, limite do `continue`, preferências e domínio | teste |
| `backend/tests/unit/test_series_domain.py` | Regras puras de agrupamento: nome, ordem, títulos, onde continuar | teste |
| `backend/tests/unit/test_metadata_domain.py` | Sanitização de descrição, casamento de títulos, escolha de idioma, detecção de imagem | teste |
| `backend/tests/unit/test_metadata_providers.py` | MangaDex e AniList com respostas canônicas: parsing, idioma, formas hostis, o que é (e não é) enviado | teste |
| `backend/tests/unit/test_metadata_describers.py` | Wikipédia, Google Livros e MyMemory com respostas canônicas | teste |
| `backend/tests/unit/test_book_progress.py` | Locator de livro: encode/decode, `percent` e concluído | teste |
| `backend/tests/unit/test_book_scan.py` | Scan de arquivo EPUB: item do tipo `book` | teste |
| `backend/tests/unit/test_epub_safe.py` | Leitura segura do pacote EPUB | teste |
| `backend/tests/unit/test_epub_html.py` | Sanitizador de capítulo: allowlist de tags e atributos | teste |
| `backend/tests/unit/test_release_domain.py` | Versão, tag, repositório e rede do operador (`is_operator_network`) | teste |
| `backend/tests/unit/test_update_service.py` | `UpdateService` com falsos: ETag, 304, limitação, falha, aprovação (tag igual à última), webhook e auditoria | teste |
| `backend/tests/integration/test_series_api.py` | API de séries sobre biblioteca real: agrupamento, lista, detalhe, `continue`, capa, varredura | teste |
| `backend/tests/integration/test_series_kind.py` | `kind` da série (manga, book, mixed) e `type` dos capítulos | teste |
| `backend/tests/integration/test_metadata_enrich.py` | Enriquecimento ponta a ponta (rotas, serviços e providers reais; só o gateway é falso): fontes, estados, capa, desligado | teste |
| `backend/tests/integration/test_metadata_fusion.py` | Fusão de fontes, descrição pt-br primeiro, tradução marcada; caso real de obra sem pt-br no MangaDex | teste |
| `backend/tests/integration/test_book_progress_api.py` | Progresso de livro pela API | teste |
| `backend/tests/integration/test_book_preferences.py` | Preferências de livro: `book_font_scale` e `book_theme` | teste |
| `backend/tests/integration/test_book_series_enrichment.py` | Enriquecimento não consulta séries de livro | teste |
| `backend/tests/security/test_security_headers.py` | Cabeçalhos (inclui 404), 500 genérico, reraise após início, `CancelledError`, desconexão, substituição de cabeçalhos da rota | teste |
| `backend/tests/security/test_settings.py` | `SECRET_KEY` (ausente, curta, baixa entropia, espaços); limites; coerência do lockout; fórmula; metadados (`METADATA_*`, `DATA_DIR`) | teste |
| `backend/tests/security/test_password_storage.py` | Senha só como Argon2id; fora de logs, erros e auditoria | teste |
| `backend/tests/security/test_local_storage.py` | Caminhos hostis, links reais, pasta OneDrive, raiz inexistente | teste |
| `backend/tests/security/test_cbz_extractor.py` | CBZ: ordem, zip-slip, symlink, zip bomb, limites, arquivo falso, criptografado, corrompido, leitura parcial | teste |
| `backend/tests/security/test_folder_extractor.py` | Pasta: ordem, extensão falsa, página gigante, excesso de arquivos | teste |
| `backend/tests/security/test_epub_extractor.py` | Extrator EPUB com casos hostis (DRM, limites, imagens e fontes) | teste |
| `backend/tests/security/test_book_api.py` | Rotas de livro: autenticação, IDs e números hostis, erros sem caminho | teste |
| `backend/tests/security/test_book_chapter_headers.py` | CSP do capítulo só para GET 200 do caminho exato; cache privado 1 h; marcador interno nunca sai | teste |
| `backend/tests/security/test_csrf.py` | CSRF: token, cookie, assinatura, Origin, Referer, Fetch Metadata, métodos, respostas genéricas | teste |
| `backend/tests/security/test_cookies_and_cache.py` | Atributos de cookies; `no-store` em toda rota `/api`; regra sem relaxamento | teste |
| `backend/tests/security/test_cache_exception.py` | Exceção de cache de imagem: só GET 200/304 em página, capa de item e capa de série; marcador exato | teste |
| `backend/tests/security/test_login_bruteforce.py` | Bloqueio por par, conta e IP; resposta idêntica; progressivo; expiração; distribuído; hash só HMAC | teste |
| `backend/tests/security/test_session_attacks.py` | JWT forjado, expirado, sem claims, sessão alheia, troca de senha, segredos fora de logs | teste |
| `backend/tests/security/test_jwt_tokens.py` | HS256: `alg:none`, algoritmos trocados, assinatura, claims, tempo, erro sem token | teste |
| `backend/tests/security/test_rate_limit_and_cors.py` | Rate limit (global, auth, IP normalizado, IPv6 /64); CORS exato; origens inválidas | teste |
| `backend/tests/security/test_body_limit.py` | 413 por `Content-Length` e por corpo recebido; 400 para `Content-Length` inválido | teste |
| `backend/tests/security/test_items_api.py` | Autorização de itens e scan; IDs e páginas hostis; ETag/304; tipos de mídia; erros genéricos | teste |
| `backend/tests/security/test_progress_authz.py` | Anônimo recebe 401 em tudo; usuário nunca lê nem altera progresso ou preferências alheios; escrita exige CSRF; IDs malformados = 404 genérico; respostas `no-store` sem caminhos | teste |
| `backend/tests/security/test_safe_gateway.py` | `SafeGateway`: allowlist, https e porta, IP público, sem redirecionamento, tipos, limites, espaçamento, sem socket (gateway falso) | teste |
| `backend/tests/security/test_safe_gateway_release.py` | Consulta de release: `api.github.com` é o 8º host e o único condicional; ETag, 304, limitação, redirecionamento recusado, URLs parecidas recusadas | teste |
| `backend/tests/security/test_webhook_notifier.py` | Contrato do webhook: cabeçalhos, assinatura, destino, redirecionamento e tamanho; carrega o receptor real de `infra/deploy-hook` (pula se ausente) | teste |
| `backend/tests/security/test_update_api.py` | API de atualização: `GET /version` por papel, check com 3/min, `POST /update` (202, 409, 502, 503) e erros genéricos | teste |
| `backend/tests/security/test_update_config.py` | `UPDATE_*` e `APP_VERSION`: validações, par URL+segredo, http só em rede do operador, segredo mínimo | teste |
| `backend/tests/security/test_cover_store.py` | Capas: nome só pelo UUID, extensões, tamanho, symlink, escrita atômica, concorrência | teste |
| `backend/tests/security/test_metadata_api.py` | API de gestão: anônimo, usuário e admin; CSRF; entradas estritas; erros genéricos; limite de 10/min; precedência da capa | teste |
| `backend/tests/security/test_series_authz.py` | Séries exigem sessão; progresso é sempre do usuário; sem escrita em séries; sem caminho na resposta | teste |
| `backend/tests/security/test_spa.py` | Frontend servido: sem `FRONTEND_DIST_DIR` nada é servido; env vazia; pasta sem `index.html` falha no startup; fallback; `/api` desconhecido = JSON 404; traversal, dotfiles e symlink recusados; métodos; cache por tipo; `Range`; cabeçalhos; sem consumo do rate limit da API; docs não expostas | teste |
| `backend/tests/regression/README.md` | Convenção `test_reg_<NNN>_<slug>.py`, um por bug ou finding corrigido | teste |
| `backend/tests/regression/test_reg_001_secret_key_not_in_error.py` | REG-001 (M-1): valor de `SECRET_KEY` fora do erro de validação | teste |
| `backend/tests/regression/test_reg_002_migrations_dir_after_install.py` | Migrações rodam de diretório alheio ao pacote instalado | teste |
| `backend/tests/regression/test_reg_003_scan_uses_injected_clock.py` | `added_at` vem da porta `Clock` | teste |
| `backend/tests/regression/test_reg_004_audit_log_retention.py` | Retenção da auditoria aplicada no login | teste |
| `backend/tests/regression/test_reg_005_request_body_size_limit.py` | JSON acima do limite recebe 413 | teste |
| `backend/tests/regression/test_reg_006_forwarded_allow_ips_defaults_consistent.py` | FIND-001: `FORWARDED_ALLOW_IPS` obrigatória e coerente em compose, Dockerfile e `.env.example`; avisos | teste |
| `backend/tests/regression/test_reg_007_login_flood_does_not_starve_api.py` | FIND-002: hasher com limite de concorrência; 503 rápido sem falha registrada | teste |
| `backend/tests/regression/test_reg_008_page_read_does_not_scan_all_entries.py` | FIND-003: índice em cache; uma entrada por página; limite do gate | teste |
| `backend/tests/regression/test_reg_009_lockout_concurrent_attempts.py` | FIND-004: reserva de tentativa antes do hash; liberação; construção única do serviço | teste |
| `backend/tests/regression/test_reg_010_concurrent_refresh_grace_window.py` | FIND-005: janela de tolerância do refresh; reuso tardio revoga | teste |
| `backend/tests/regression/test_reg_011_audit_log_not_flooded_by_locked_attempts.py` | FIND-006: `login.locked` deduplicado; purga isolada; comando `purge` | teste |
| `backend/tests/regression/test_reg_012_password_policy_username_and_denylist.py` | FIND-007: username contido e padrões fracos recusados | teste |
| `backend/tests/regression/test_reg_013_no_trailing_slash_redirect.py` | FIND-008: barra final não redireciona | teste |
| `backend/tests/regression/test_reg_015_hardening_bundle.py` | FIND-010: `--no-server-header`, limites do uvicorn, dependências fixas, `Origin` repetido | teste |
| `backend/tests/regression/test_reg_016_folder_page_count_ignores_fake_images.py` | FIND-011: `page_count` de pasta ignora arquivo falso | teste |
| `backend/tests/regression/test_reg_017_scan_empty_root_keeps_items.py` | FIND-012: raiz vazia, ilegível ou com erro de caminhada não marca itens como ausentes | teste |
| `backend/tests/regression/test_reg_018_user_writes_do_not_lose_concurrent_changes.py` | Escritas de usuário por CAS: rehash e troca não desfazem desativação ou reset concorrentes | teste |
| `backend/tests/regression/test_reg_019_auth_reads_do_not_use_strict_bucket.py` | `me` e `csrf` não consomem o balde estrito; login continua nele | teste |
| `backend/tests/regression/test_reg_020_chapters_sort_naturally_by_number.py` | REG-020: capítulos em ordem numérica (2 < 10 < 100) | teste |
| `backend/tests/regression/test_reg_021_manual_metadata_wins_over_a_running_enrichment.py` | REG-021: edição manual vence enriquecimento em andamento | teste |
| `backend/tests/regression/test_reg_022_orv_work_not_lost_to_editions.py` | REG-022: obra do MangaDex não perdida para edições | teste |
| `backend/tests/regression/test_reg_023_translation_missing_space_after_sentence.py` | REG-023: espaço faltando após ponto final na tradução do MyMemory | teste |
| `backend/tests/regression/test_reg_024_book_locator_is_read_by_item_type.py` | REG-024: o locator é lido conforme o tipo do item (livro ≠ página) | teste |
| `backend/tests/regression/test_reg_025_preferences_put_keeps_book_settings.py` | REG-025: `PUT` de preferências preserva os campos de livro | teste |
| `backend/tests/regression/test_reg_026_enrichment_skips_series_of_books.py` | REG-026: enriquecimento pula séries de livro | teste |
| `backend/tests/regression/test_reg_027_series_chapters_expose_type_and_kind.py` | REG-027: capítulos trazem `type` e a série traz `kind` | teste |

Não existem ainda: adaptador de progresso para PDF, extratores CBR e PDF, rota de arquivo com `Range` para PDF (`/items/{id}/file`), leitor PDF, `backend/tests/fixtures/` (o `check` de segredos já a exclui se existir).

## frontend/

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `frontend/AGENTS.md` | Regras do frontend | docs |
| `frontend/package.json` | Dependências (versões exatas); scripts `dev`, `build` (só `vite build`), `lint`, `typecheck` (app + node), `test`, `arch`, `format:check`, `test:e2e` | config |
| `frontend/package-lock.json` | Lockfile npm | config |
| `frontend/.npmrc` | `save-exact=true` | config |
| `frontend/vite.config.ts` | Vite, vite-plugin-pwa (`registerType: 'prompt'`: nova versão só é ativada pelo usuário; manifest `id`/`scope` `/`; workbox: `runtimeCaching: []`, `skipWaiting: false`, `clientsClaim: false`, denylist `/api`), proxy `/api` para `localhost:8000`, Vitest | config |
| `frontend/tsconfig.json` | Só referências (`tsconfig.app.json`, `tsconfig.node.json`) | config |
| `frontend/tsconfig.app.json` | Projeto de `src/` (sem tipos do node) | config |
| `frontend/tsconfig.node.json` | Projeto de `tests/`, `vite.config.ts`, `playwright.config.ts` (tipos node) | config |
| `frontend/eslint.config.js` | ESLint: plugin security; `fetch`, `XMLHttpRequest`, `WebSocket`, `navigator.sendBeacon` só no api-client (`sendBeacon`/XHR/WS também em `shared/api-client`); `indexedDB` só em `shared/offline`; `localStorage`/`sessionStorage` proibidos em todo lugar (também via `window`/`globalThis`/`self`); `react/no-danger`; `no-eval`. Acessos indiretos não são detectados | config |
| `frontend/.dependency-cruiser.cjs` | 6 regras: fronteiras app/features/shared, ciclos, não resolvível, dependência de dev | config |
| `frontend/.prettierrc.json`, `.prettierignore` | Formatação | config |
| `frontend/playwright.config.ts` | Config E2E (sem testes ainda) | config |
| `frontend/index.html` | Shell HTML (pt-BR, viewport com `viewport-fit=cover`, `color-scheme`, meta de iOS, ícones, título "Biblioteca"). Sem script inline | app |
| `frontend/public/apple-touch-icon.png`, `icon-192.png`, `icon-512.png` | Ícones PWA | assets |
| `frontend/src/main.tsx` | Bootstrap React (`StrictMode`); registra o service worker | app |
| `frontend/src/vite-env.d.ts` | Tipos de ambiente Vite (inclui `VITE_CSRF_COOKIE_NAME`, `VITE_CSRF_HEADER_NAME`) | app |
| `frontend/src/app/App.tsx` | Raiz: `Providers`, `AppRoutes` e `AppUpdatePrompt` (aviso de nova versão do app) | app |
| `frontend/src/app/Providers.tsx` | `ThemeProvider` → `BrowserRouter` → `SessionProvider` → `PreferencesProvider` → `VersionProvider` | app |
| `frontend/src/app/routes.tsx` | `AppRoutes`: `/login`; grupo protegido por `RequireAuth` com `/`, `/serie/:id`, `/ler/:itemId` (`ReaderRoute`), `/ajustes`; `*` → `/` | app |
| `frontend/src/app/ReaderRoute.tsx` | `/ler/:itemId`: item `book` abre o leitor EPUB; demais, o leitor de mangá | app |
| `frontend/src/app/useReaderKind.ts` | Descobre o tipo do item da rota (`itemState`, `retryItem`) para escolher o leitor | app |
| `frontend/src/app/registerServiceWorker.ts` | Registro do SW (`virtual:pwa-register`, só em produção) com `onNeedRefresh` → `shared/pwa`; nada recarrega sozinho | app |
| `frontend/src/app/useAppUpdate.ts` | Estado do aviso "Nova versão do app": faz `flushAllProgress` antes de recarregar; "Depois" esconde | app |
| `frontend/src/app/AppUpdatePrompt.tsx` | Aviso de nova versão do app ("Recarregar" / "Depois"; versão compacta dentro do leitor) | app |
| `frontend/src/app/update-prompt.css` | Estilos do aviso de nova versão | app |
| `frontend/src/app/app.css` | Estilos globais | app |
| `frontend/src/features/auth/index.ts` | Exporta `LoginPage`, `RequireAuth`, `safeRedirect` | features |
| `frontend/src/features/auth/README.md` | Escopo da feature (tela de login e guarda de rota) | docs |
| `frontend/src/features/auth/auth.css` | Estilos do login | features |
| `frontend/src/features/auth/components/LoginPage.tsx` | Tela `/login`; se já autenticado, redireciona para `safeRedirect(from)` | features |
| `frontend/src/features/auth/components/RequireAuth.tsx` | Guarda de rota com 4 estados: `loading`, `error`, `anonymous`, `authenticated` | features |
| `frontend/src/features/auth/hooks/useLoginForm.ts` | Formulário de login: envio, mensagens, 429 com contagem regressiva | features |
| `frontend/src/features/auth/hooks/safeRedirect.ts` | Aceita só caminhos internos (sem `//`, `\`, controles, `/login`) | features |
| `frontend/src/features/library/index.ts` | Exporta `LibraryPage` | features |
| `frontend/src/features/library/README.md` | Escopo da feature (biblioteca e "Continuar lendo") | docs |
| `frontend/src/features/library/library.css` | Estilos da biblioteca | features |
| `frontend/src/features/library/components/LibraryPage.tsx` | Tela `/`: aviso de versão (`UpdateNotice`), "Continuar lendo", grade de séries, busca com debounce, "carregar mais", "Atualizar metadados" (só admin) | features |
| `frontend/src/features/library/components/ContinueReading.tsx` | Prateleira "Continuar lendo" com barra de progresso | features |
| `frontend/src/features/library/components/SeriesCard.tsx` | Cartão de série com capa same-origin, contagem ("N livros", "N capítulos" ou "N itens") e versão para recarregar a capa após atualização | features |
| `frontend/src/features/library/components/EnrichControl.tsx` | Botão "Atualizar metadados" (só admin, via `LibraryPage`); mostra progresso resumido | features |
| `frontend/src/features/library/hooks/useEnrich.ts` | Dispara `POST /library/enrich` e consulta `GET /library/enrich/status` a cada 2 s, no máximo 150 vezes | features |
| `frontend/src/features/library/hooks/useLibrary.ts` | Lista de séries (`listSeries`), busca com debounce (350 ms), tamanho de página 30 | features |
| `frontend/src/features/library/hooks/useContinueReading.ts` | Carrega a prateleira; falha só esconde a prateleira | features |
| `frontend/src/features/reader-manga/index.ts` | Exporta `MangaReaderPage` | features |
| `frontend/src/features/reader-manga/README.md` | Escopo do leitor de mangá | docs |
| `frontend/src/features/reader-manga/reader.css` | Estilos do leitor | features |
| `frontend/src/features/reader-manga/navigation.ts` | Lógica pura: `clampPage`, `tapZone`, `swipeStep`, `keyAction`; constantes de toque | features |
| `frontend/src/features/reader-manga/components/MangaReaderPage.tsx` | Tela `/ler/:itemId`: estados de carregamento, não encontrado, erro, formato não suportado e item sem páginas | features |
| `frontend/src/features/reader-manga/components/PagedViewport.tsx` | Modos RTL e LTR (uma página por vez), `aria-label` com instruções | features |
| `frontend/src/features/reader-manga/components/VerticalViewport.tsx` | Modo vertical (tira contínua), monta só a janela ao redor da página atual | features |
| `frontend/src/features/reader-manga/components/ReaderControls.tsx` | Barra de controles: voltar, seletor de página, zoom (`aria-pressed`), modo de leitura (`SegmentedControl`) | features |
| `frontend/src/features/reader-manga/hooks/useReaderData.ts` | Carrega item e progresso (404 = começar na página 0) antes de montar o leitor | features |
| `frontend/src/features/reader-manga/hooks/useReaderState.ts` | Estado do leitor: página, modo, zoom, controles, teclado, pré-carregamento e salvamento de progresso | features |
| `frontend/src/features/reader-manga/hooks/usePagePreload.ts` | Pré-carrega 2 páginas à frente; mantém no máximo 8 e 2 atrás | features |
| `frontend/src/features/reader-manga/hooks/useVerticalStrip.ts` | Janela da tira vertical (`STRIP_WINDOW` = 3, ou seja 7 páginas) e posição inicial | features |
| `frontend/src/features/reader-manga/hooks/useViewportGestures.ts` | Toque, deslize e duplo toque (com limite de movimento) | features |
| `frontend/src/features/reader-manga/components/ChapterEnd.tsx` | Fim do capítulo com série: próximo e anterior capítulo | features |
| `frontend/src/features/reader-epub/index.ts` | Exporta `EpubReaderPage` | features |
| `frontend/src/features/reader-epub/README.md` | Escopo do leitor EPUB: capítulo em `iframe sandbox="allow-same-origin"`, sem `allow-scripts` | docs |
| `frontend/src/features/reader-epub/epub.css` | Estilos do leitor EPUB e do frame | features |
| `frontend/src/features/reader-epub/locator.ts` | Lógica pura do locator de livro (`capítulo * 10000 + offset_bp`), links `?goto=`, teclas e gestos | features |
| `frontend/src/features/reader-epub/components/EpubReaderPage.tsx` | Tela do leitor EPUB (`/ler/:itemId` para livros): estados, frame, barras, painéis, botão ☰ "Mostrar controles" e indicador de canto (`epub-pill`) | features |
| `frontend/src/features/reader-epub/components/EpubControls.tsx` | Barra de controles do leitor EPUB (botão "Índice"; indicador `chapter-indicator` capítulo/total · %) | features |
| `frontend/src/features/reader-epub/components/Drawer.tsx` | Gaveta (painel) genérica usada pelos painéis do leitor EPUB | features |
| `frontend/src/features/reader-epub/components/TocDrawer.tsx` | Gaveta de índice (TOC) do livro | features |
| `frontend/src/features/reader-epub/components/SettingsDrawer.tsx` | Gaveta de ajustes do livro (tamanho de fonte e tema do livro) | features |
| `frontend/src/features/reader-epub/components/EpubEnd.tsx` | Fim de capítulo ou de livro | features |
| `frontend/src/features/reader-epub/hooks/useEpubData.ts` | Carrega item, estrutura do livro e progresso | features |
| `frontend/src/features/reader-epub/hooks/useEpubFrame.ts` | Frame do capítulo: restaura posição, lê rolagem e cliques em `a[href]` | features |
| `frontend/src/features/reader-epub/hooks/useEpubReader.ts` | Estado do leitor: capítulo, painéis, preferências do livro, barras (`useAutoHideControls`; tecla `m`) e salvamento de progresso | features |
| `frontend/src/features/reader-epub/hooks/useEpubStrip.ts` | Leitura vertical contínua: janela de iframes, posição, progresso e rolagem (modo "Vertical") | features |
| `frontend/src/features/reader-epub/components/EpubStrip.tsx` | Tira vertical do livro: um iframe por capítulo, reserva de altura nos não montados | features |
| `frontend/src/features/reader-epub/strip.ts` | Lógica pura da tira vertical: janela (1 antes, 3 depois), posição e altura do capítulo; `unlockDocumentHeight` (libera `html`/`body` 100% via CSSOM antes de medir) | features |
| `frontend/src/features/reader-epub/pinch.ts` | Zoom sem efeito de posição: `createPinchGuard` (multitoque, bloqueio até 600 ms após o fim, expira em 2 s) e `createReflowHold` (segura a posição só na mudança de largura); constantes `PINCH_SETTLE_MS`, `PINCH_STALE_MS`, `RESIZE_HOLD_MS`, `RESIZE_EXTEND_MS`, `USER_SCROLL_MS` | features |
| `frontend/src/features/reader-pdf/README.md` | Esqueleto (Fase 4). Não importar outras features | docs |
| `frontend/src/features/progress/README.md` | Reservada: o código de progresso fica em `shared/progress` | docs |
| `frontend/src/features/settings/index.ts` | Exporta `SettingsPage` | features |
| `frontend/src/features/settings/README.md` | Escopo da tela de ajustes | docs |
| `frontend/src/features/settings/settings.css` | Estilos dos ajustes | features |
| `frontend/src/features/settings/components/SettingsPage.tsx` | Tela `/ajustes`: versão do app, "Verificar atualizações" (só admin), aparência, sentido de leitura, conta (troca de senha e sair) | features |
| `frontend/src/features/settings/components/ChangePasswordForm.tsx` | Formulário de troca de senha | features |
| `frontend/src/features/settings/hooks/useChangePassword.ts` | Estado e envio da troca de senha | features |
| `frontend/src/features/settings/hooks/useCheckUpdates.ts` | Verificação manual de atualização (admin): uma chamada por vez; 429 bloqueia o botão pelo `Retry-After` | features |
| `frontend/src/features/series/index.ts` | Exporta `SeriesPage` | features |
| `frontend/src/features/series/series.css` | Estilos da tela de série e do painel de metadados | features |
| `frontend/src/features/series/components/SeriesPage.tsx` | Tela `/serie/:id`: estados de carregamento e erro, cabeçalho com capa, descrição, "continuar", lista de capítulos e painel admin | features |
| `frontend/src/features/series/components/ChapterList.tsx` | Lista de capítulos em janelas de 50, com ir-para-número (`parseChapterNumber`) | features |
| `frontend/src/features/series/components/ChapterRow.tsx` | Linha de capítulo: título, páginas (só mangá), progresso e link para o leitor (`?serie=`) | features |
| `frontend/src/features/series/components/SeriesDescription.tsx` | Descrição em texto puro, badges de origem ("tradução automática") e atribuição (CC BY-SA na Wikipédia); link só https | features |
| `frontend/src/features/series/components/MetadataPanel.tsx` | Painel admin (recolhido por padrão): busca só por ação explícita, escolher fonte, editar título e descrição, remover | features |
| `frontend/src/features/series/hooks/useChapterList.ts` | Janela de capítulos e interpretação de número (`12`, `12.5`, `12,5`) | features |
| `frontend/src/features/series/hooks/useMetadataAdmin.ts` | Busca e ações do painel admin; mensagens sem detalhe técnico; limites de título (200) e descrição (4 000) | features |
| `frontend/src/shared/api-client/client.ts` | Cliente HTTP central: `credentials` conforme `baseUrl`; CSRF no cabeçalho em métodos que alteram estado (com um retry se o token mudou); refresh compartilhado com Web Locks entre abas; 401 em chamada autenticada → um refresh e um retry; 429 e 2xx vazio tratados; `keepalive` opcional; `AbortError` propagado | shared |
| `frontend/src/shared/api-client/csrf.ts` | `readCookie`, `isStateChanging` | shared |
| `frontend/src/shared/api-client/errors.ts` | `ApiError`, `RateLimitError` (com `Retry-After`), `NetworkError` | shared |
| `frontend/src/shared/api-client/index.ts` | Exportações públicas do api-client | shared |
| `frontend/src/shared/session/index.ts` | Exportações da sessão | shared |
| `frontend/src/shared/session/types.ts` | `SessionUser` (`id`, `username`, `role`, `theme_pref`), `SessionStatus` (`loading`, `authenticated`, `anonymous`, `error`) | shared |
| `frontend/src/shared/session/api.ts` | `fetchMe`, `postLogin`, `postLogout`, `postChangePassword` | shared |
| `frontend/src/shared/session/SessionProvider.tsx` | Estado da sessão: `/auth/me` na carga; só 401 vira `anonymous`; 429, 503 e rede viram `error`; refresh rejeitado encerra a sessão | shared |
| `frontend/src/shared/session/session-context.ts` | Contexto da sessão | shared |
| `frontend/src/shared/session/useSession.ts` | Hook `useSession` | shared |
| `frontend/src/shared/session/useSessionKeepAlive.ts` | Rotaciona a sessão a cada 10 min e ao voltar para a aba (intervalo mínimo de 5 min) | shared |
| `frontend/src/shared/system/index.ts` | Exportações de versão e aviso (`VersionProvider`, `useVersion`, `UpdateNotice`, `POLL_MS`, `POLL_MAX_TICKS`) | shared |
| `frontend/src/shared/system/types.ts` | Tipos de versão; só URL `https` sobrevive (senão `null`); campos de admin com padrão para usuário comum | shared |
| `frontend/src/shared/system/api.ts` | `getVersion` (`GET /system/version`), `checkForUpdate` (`POST /system/update/check`), `requestUpdate` (`POST /system/update` com a tag exata) | shared |
| `frontend/src/shared/system/version-context.ts` | Contexto de versão: estado, verificação manual, "Agora não" até recarregar a página | shared |
| `frontend/src/shared/system/useVersion.ts` | Hook `useVersion` | shared |
| `frontend/src/shared/system/VersionProvider.tsx` | Pergunta `/system/version` ao abrir o app e no máximo a cada 30 min, com aba visível | shared |
| `frontend/src/shared/system/useUpdateFlow.ts` | Fluxo de atualização do admin: confirmação, pedido ao servidor e consulta a cada 5 s (até 60 tentativas) até a versão mudar | shared |
| `frontend/src/shared/system/UpdateNotice.tsx` | Aviso de nova versão (só admin): notas em texto puro, link https da release, "Atualizar agora" quando há webhook; mensagens de erro sem detalhe técnico | shared |
| `frontend/src/shared/system/reload.ts` | `reloadPage()` isolado para os testes poderem substituí-lo | shared |
| `frontend/src/shared/system/system.css` | Estilos do aviso de versão | shared |
| `frontend/src/shared/pwa/index.ts` | Exportações do estado de atualização do service worker | shared |
| `frontend/src/shared/pwa/pwa-update.ts` | Loja mínima de "nova versão esperando": `markNeedRefresh`, `subscribePwaUpdate`, `applyPwaUpdate` (ativa o worker e recarrega); nada recarrega sozinho | shared |
| `frontend/src/shared/progress/index.ts` | Exportações de progresso | shared |
| `frontend/src/shared/progress/types.ts` | `Progress`, `ContinueEntry`, `ContinueList`, `SaveStatus` | shared |
| `frontend/src/shared/progress/api.ts` | `getProgress` (404 → `null`), `putProgress` (envia só `locator`), `deleteProgress`, `listContinue` (limite 12) | shared |
| `frontend/src/shared/progress/progress-saver.ts` | `createProgressSaver`: debounce de 800 ms, um envio por vez, valor mais novo vence, retry de 5 s, `flush` com `keepalive` | shared |
| `frontend/src/shared/progress/useProgressSaver.ts` | Liga o salvador ao leitor; `flush` ao ocultar a página e ao sair (sem `sendBeacon`); registra o salvador no flush-registry | shared |
| `frontend/src/shared/progress/flush-registry.ts` | Registro dos salvadores ativos; `flushAllProgress` (com teto de ~2 s) antes de recarregar por atualização | shared |
| `frontend/src/shared/items/index.ts` | Exportações de itens | shared |
| `frontend/src/shared/items/paths.ts` | `readerPath(itemId, seriesId?)` (`/ler/:id?serie=`) e `seriesPath(id)` | shared |
| `frontend/src/shared/items/types.ts` | `Item`, `ItemList`, `ItemType`, `isReadable` (mangá e livro; PDF ainda "em breve"), `BookInfo` e `BookChapter` | shared |
| `frontend/src/shared/items/api.ts` | `listItems`, `getItem`, `coverUrl`, `pageUrl`, `getBook` (`/book`) e `bookChapterUrl` (`/book/chapters/{n}?theme&size`); URLs same-origin, com cookie | shared |
| `frontend/src/shared/items/useItem.ts` | Carrega um item pela id da rota (`itemState`, `retry`); usado pelo leitor | shared |
| `frontend/src/shared/series/index.ts` | Exportações de séries | shared |
| `frontend/src/shared/series/types.ts` | `SeriesSummary`, `SeriesDetail`, `Chapter`, `MetadataCandidate`, `EnrichStatus`, `DescriptionOrigin`; `safeHttpsUrl` (só https); `chapterNeighbours` | shared |
| `frontend/src/shared/series/api.ts` | `listSeries`, `getSeries`, `seriesCoverUrl` (same-origin, com versão), `startEnrich`, `getEnrichStatus`, `searchMetadataCandidates`, `selectMetadata`, `saveMetadataText`, `removeMetadata` | shared |
| `frontend/src/shared/series/useSeriesDetail.ts` | Carrega uma série; a resposta fica com a chave a que pertence (resposta atrasada de outra série é descartada) | shared |
| `frontend/src/shared/series/useReaderNav.ts` | Navegação entre capítulos da série (`chapterNeighbours`); "voltar" leva à série quando houver. Movido de `features/reader-manga/hooks/` | shared |
| `frontend/src/shared/hooks/index.ts` | Exportações de hooks genéricos | shared |
| `frontend/src/shared/hooks/useAutoHideControls.ts` | Visibilidade das barras de leitor: oculta por padrão só em toque (`(hover: none) and (pointer: coarse)`), auto-ocultar após 4 s, `toggle`/`show`/`keepAlive`; `isTouchPrimary` | shared |
| `frontend/src/shared/hooks/useCountdown.ts` | Contagem regressiva em segundos (login com 429 e troca de senha) | shared |
| `frontend/src/shared/hooks/useDebouncedValue.ts` | Valor com atraso (busca da biblioteca) | shared |
| `frontend/src/shared/preferences/index.ts` | Exportações de preferências | shared |
| `frontend/src/shared/preferences/types.ts` | `Preferences` (tema, sentido de leitura, `book_font_scale`, `book_theme`), `ReadingDirection`, `ThemeChoice`, `DEFAULT_PREFERENCES`, `normalizePreferences` (valida cada campo do servidor) | shared |
| `frontend/src/shared/preferences/api.ts` | `fetchPreferences` (GET) e `savePreferences` (PUT do objeto completo) | shared |
| `frontend/src/shared/preferences/PreferencesProvider.tsx` | Carrega preferências ao autenticar e aplica o tema; PUT sempre sobre dados do servidor, nunca sobre padrões; enquanto o GET não responde, guarda a alteração; PUTs em série | shared |
| `frontend/src/shared/preferences/preferences-context.ts` | Contexto (`preferences`, `loaded`, `loadFailed`, `saveFailed`, `update`, `reload`) | shared |
| `frontend/src/shared/preferences/usePreferences.ts` | Hook `usePreferences` | shared |
| `frontend/src/shared/theme/index.ts` | Exportações do tema | shared |
| `frontend/src/shared/theme/ThemeProvider.tsx` | Estado do tema em memória (`system` por padrão); aplica `data-theme` no `<html>`. A persistência é feita por `PreferencesProvider` | shared |
| `frontend/src/shared/theme/theme-context.ts` | Contexto e tipos de tema | shared |
| `frontend/src/shared/theme/useTheme.ts` | Hook de tema | shared |
| `frontend/src/shared/theme/useSystemTheme.ts` | Hook de `prefers-color-scheme` | shared |
| `frontend/src/shared/theme/theme.css` | Tokens de cor com `--if-dark`/`--if-light`, declarados uma vez | shared |
| `frontend/src/shared/ui/index.ts` | Exportações de UI | shared |
| `frontend/src/shared/ui/ui.css` | Estilos de botões, segmentado, imagem e fallback | shared |
| `frontend/src/shared/ui/Cover.tsx` | Capa same-origin ou letra inicial quando não há capa | shared |
| `frontend/src/shared/ui/ThemeToggle.tsx` | Botões Sistema/Claro/Escuro | shared |
| `frontend/src/shared/ui/SegmentedControl.tsx` | Controle segmentado acessível (`aria-pressed`) | shared |
| `frontend/src/shared/ui/ProtectedImage.tsx` | `<img>` com placeholder, uma recuperação e botão de tentar de novo | shared |
| `frontend/src/shared/ui/useImageRecovery.ts` | Erro de imagem: se suspeitar de sessão, um refresh compartilhado por janela de 60 s, sem `/auth/me`; senão, falha com retry manual | shared |
| `frontend/src/shared/offline/README.md` | Reservado: estratégia offline (único lugar com `indexedDB`); sem código ainda | shared |
| `frontend/src/vite-env.d.ts` | Tipos de ambiente Vite | app |
| `frontend/tests/setup.ts` | jest-dom e cleanup | teste |
| `frontend/tests/helpers/fake-api.ts` | API falsa (respostas por rota e chamadas gravadas, com `keepalive`) para testes de tela | teste |
| `frontend/tests/helpers/render-app.tsx` | Renderiza as rotas reais com os providers, em `MemoryRouter` | teste |
| `frontend/tests/helpers/epub-frame.ts` | Frame de EPUB falso para os testes do leitor | teste |
| `frontend/tests/unit/api-client.test.ts` | api-client: credenciais, CSRF, 429, 500, rede, 204, não-JSON, AbortError, 2xx vazio, junção de `baseUrl` | teste |
| `frontend/tests/unit/api-client-session.test.ts` | Recuperação de sessão (401 → refresh compartilhado → retry uma vez; refresh rejeitado notifica); bootstrap de CSRF (uma busca compartilhada; retry só se o token mudou); `keepalive` sem `sendBeacon` | teste |
| `frontend/tests/unit/architecture.test.ts` | dependency-cruiser em `src` e em 8 fixtures negativas | teste |
| `frontend/tests/unit/eslint-rules.test.ts` | ESLint: formas proibidas em feature (`it.each`); permissões por pasta (api-client, offline) | teste |
| `frontend/tests/unit/theme-css.test.ts` | Tokens do tema: cada valor escuro uma vez; dois gatilhos escuros; todos os tokens em `:root` | teste |
| `frontend/tests/unit/theme.test.tsx` | Tema: sistema por padrão; troca explícita; sem localStorage | teste |
| `frontend/tests/unit/auth.test.tsx` | Guarda de rota (carregando, anônimo, autenticado, sessão encerrada); login (sucesso, retorno, erro genérico, 429 com contagem, 503); `safeRedirect` | teste |
| `frontend/tests/unit/library.test.tsx` | Biblioteca: capas, livros e PDFs desabilitados, busca com debounce, filtro por tipo, "carregar mais", "Continuar lendo" (falha não bloqueia) | teste |
| `frontend/tests/unit/series.test.tsx` | Tela de série: capa, "continuar"/"começar a ler", capítulos em janela, "ir para o capítulo N", descrição (texto puro, badge de idioma, link https), vazio, 404 e erro com nova tentativa | teste |
| `frontend/tests/unit/series-books.test.tsx` | Série de livros: rótulo "Livro" sem contagem de páginas, progresso em %, `kind` e `type` (com fallback para respostas antigas), "continuar" de livro e cartão na biblioteca | teste |
| `frontend/tests/unit/metadata.test.tsx` | Painel admin (invisível para usuário comum, recolhido, busca só por clique, usar candidato, edição com limites, remoção com confirmação, 429); botão "Atualizar metadados" (polling, 409, parada ao sair); origem e atribuição da descrição; links só https; capa e `Cover` | teste |
| `frontend/tests/unit/reader.test.tsx` | Leitor de mangá: retomada (página salva, 404 = página 1, item sem páginas), modos RTL/LTR/vertical, zoom, pré-carregamento, salvamento (debounce, `pagehide` com `keepalive`, aba oculta, saída, falha com aviso) | teste |
| `frontend/tests/unit/reader-navigation.test.ts` | Lógica pura de navegação: zonas de toque, deslize, teclas, `clampPage` | teste |
| `frontend/tests/unit/reader-series.test.tsx` | Leitor com série: próximo e anterior no fim do capítulo, "voltar" para a série | teste |
| `frontend/tests/unit/reader-vertical.test.tsx` | Modo vertical: não regride o progresso salvo ao retomar; janela de páginas montadas; memória limitada do pré-carregamento; região viva e teclado | teste |
| `frontend/tests/unit/reader-epub.test.tsx` | Leitor EPUB: capítulos, progresso, painéis e preferências do livro | teste |
| `frontend/tests/unit/epub-locator.test.ts` | Locator de livro (`capítulo * 10000 + offset_bp`) e lógica pura do leitor EPUB; guarda de sandbox dos dois iframes (página e tira vertical) | teste |
| `frontend/tests/unit/epub-strip.test.ts` | Lógica pura da tira vertical: janela, posição, altura e progresso | teste |
| `frontend/tests/unit/epub-pinch.test.ts` | `createPinchGuard` (multitoque, toque perdido, reset, expiração) e `createReflowHold` (só largura, rolagem do usuário, extensão) | teste |
| `frontend/tests/unit/reader-epub-vertical.test.tsx` | Leitor EPUB em modo vertical: tira, janela de capítulos, progresso e fim do livro; altura de capítulo com `html`/`body` 100%; barras em toque (tela cheia, toque no centro, ☰) | teste |
| `frontend/tests/unit/auto-hide-controls.test.ts` | `useAutoHideControls`: em toque começa oculto, toque mostra e oculta após o atraso; `keepAlive` reinicia a espera e `paused` mantém; com mouse nunca oculta por tempo | teste |
| `frontend/tests/unit/progress-saver.test.ts` | Debounce, um envio por vez, retry, `flush` com `keepalive`, `dispose` | teste |
| `frontend/tests/unit/preferences.test.tsx` | Não sobrescreve o servidor com padrões; edição enquanto o GET está pendente é mesclada; PUTs em série | teste |
| `frontend/tests/unit/session-images.test.tsx` | Verificação de sessão na carga (só 401 = saiu); recuperação de imagem compartilhada, sem `/auth/me`, uma tentativa por janela | teste |
| `frontend/tests/unit/settings.test.tsx` | Ajustes: tema, sentido de leitura, troca de senha, sair | teste |
| `frontend/tests/unit/system-update.test.tsx` | Aviso de versão e atualização: quem vê (só admin), notas em texto puro, confirmação, polling limitado, "Agora não", verificação manual e polling de versão de 30 min | teste |
| `frontend/tests/unit/pwa-update.test.tsx` | Service worker em modo `prompt`: nunca recarrega sozinho; "Recarregar" faz flush do progresso antes; "Depois" só esconde; configuração sem `skipWaiting` | teste |
| `frontend/tests/fixtures/arch-*/` (8) | Fixtures que devem violar uma regra cada (`arch-violation`, `arch-feature-app`, `arch-shared-feature`, `arch-shared-app`, `arch-cycle`, `arch-type-only`, `arch-unresolvable`, `arch-dev-dep`) | teste |
| `frontend/tests/e2e/.gitkeep` | Pasta vazia (E2E ainda não existe) | teste |
| `frontend/tests/regression/.gitkeep` | Pasta de regressão do frontend | teste |
| `frontend/tests/regression/reg_001_epub_zoom_no_page_change.test.tsx` | reg_001 (issue #7): zoom/pinça no EPUB não troca capítulo, não move a posição e não salva progresso; tira vertical e capítulo único | teste |

Removidos (entrega do MVP, 2026-11-20): `frontend/src/app/HomePage.tsx`, `frontend/src/app/useHealth.ts`, `frontend/tests/unit/home.test.tsx`. Removido em 2026-11-21: `frontend/src/features/library/components/ItemCard.tsx` (substituído por `SeriesCard.tsx`). Movido em 2026-11-21: `features/reader-manga/hooks/useReaderNav.ts` → `shared/series/useReaderNav.ts`.

## Gerado (não versionar, não listar)

`frontend/dist/` (build), `frontend/node_modules/`, `backend/.venv/`, `backend/reader_backend.egg-info/`, `backend/**/__pycache__/`, `infra/deploy-hook/__pycache__/`, `.github/scripts/__pycache__/`.
