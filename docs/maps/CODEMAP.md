# CODEMAP

Arquivo → responsabilidade → camada. Estado: 2026-11-21. Conferido contra o disco nesta entrega (listagem de arquivos; leitura dos módulos alterados). Excluídos: `.venv`, `node_modules`, `dist`, `__pycache__`, caches (`.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.import_linter_cache`) e `reader_backend.egg-info/` (gerados).

## Raiz

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `AGENTS.md` | Regras gerais para agentes | docs |
| `CLAUDE.md` | Modo orquestrador | docs |
| `README.md` | Entrada do projeto | docs |
| `CHANGELOG.md` | Histórico de versões | docs |
| `.gitignore` | Ignorados do git | config |
| `.gitattributes` | Fim de linha: `*.sh` em LF; `*.ps1` em CRLF | config |
| `.dockerignore` | Contexto de build: exclui venv, `node_modules`, `.env*` (exceto `.env.example`), `docs`, `scripts`, testes, bancos, `library`, `data`; em `infra/` só `constraints.txt` e `entrypoint.sh` | config |
| `.env.example` | Modelo de variáveis, sem segredos. Obrigatórias: `SECRET_KEY`, `FORWARDED_ALLOW_IPS` (vazia: preencher). `ALLOWED_ORIGINS` opcional (vazia = mesma origem). Demais comentadas | config |
| `.claude/agents/*.md` (8) | Subagentes | config |
| `.claude/skills/*/SKILL.md` (5) | Skills de briefing | config |
| `docs/PLANO.md` | Roteiro, requisitos, arquitetura, estado por fase | docs |
| `docs/AGENTS.md` | Regras de documentação | docs |
| `docs/DEPLOY.md` | Guia de operação com Docker (configurar, subir, admin, backup, troubleshooting) | docs |
| `docs/maps/*.md` (7) | Mapas: CODEMAP, ARCHITECTURE, DATAMODEL, API, ROUTES, SECURITY_MAP, TEST_MAP | docs |
| `docs/adr/0001..0016-*.md` (16) | Decisões; todas `Aceito` (0014 a 0016 em 2026-11-21) | docs |
| `docs/history/*.md` (7) | Diário de entregas | docs |
| `docs/security/AGENTS.md`, `AUDIT_PROTOCOL.md` | Protocolo de auditoria | docs |
| `docs/security/AUDIT_REPORT_2026-11-19.md` | Relatório da auditoria (histórico) | docs |
| `docs/security/REMEDIATION_QUEUE.md` | Fila de remediação e seção "Estado após correções" | docs |
| `docs/security/findings/FIND-2026-001..012.md` (12; sem 013) | Um finding por arquivo. Status: 11 `fixed`, 1 `open` (009) | docs |
| `docs/security/poc/*.py`, `poc/README.md` | PoCs da auditoria (limites relaxados; só instância local) | docs |
| `infra/AGENTS.md` | Regras de infra e variáveis | docs |
| `infra/Dockerfile` | Imagem única em 3 estágios: (1) `node:24.21.0-slim` builda o frontend (`npm ci`, `npm run build`); (2) `python:3.12.8-slim` instala o backend com `PIP_CONSTRAINT` em `/install`; (3) runtime `python:3.12.8-slim`: usuário `app` uid 10001, pip/setuptools/wheel removidos, `/app/static` (frontend), `migrations`, `entrypoint.sh`. ENV: `MIGRATIONS_DIR`, `FRONTEND_DIST_DIR=/app/static`, `DATABASE_URL`, `LIBRARY_PATH`, `DATA_DIR=/data`. `VOLUME /data`. HEALTHCHECK em Python. `ENTRYPOINT` | infra |
| `infra/entrypoint.sh` | Valida `SECRET_KEY` (≥ 32) e `FORWARDED_ALLOW_IPS` (sem padrão); `ALLOWED_ORIGINS` vazia é removida; aviso se `/library` não existe; `python -m app.cli migrate`; `exec uvicorn` com `--no-server-header`, `--proxy-headers --forwarded-allow-ips`, `--limit-concurrency`, `--timeout-keep-alive`, `--timeout-graceful-shutdown` (por `UVICORN_*`) | infra |
| `infra/gen_constraints.sh` | Gera os pins dentro de `python:3.12.8-slim` (runtime do `pyproject` + setuptools/wheel) | infra |
| `infra/constraints.txt` | Pins gerados (33 linhas, sem hashes: M8) | infra |
| `infra/compose.example.yml` | Serviço `backend`: build da imagem; `SECRET_KEY` e `FORWARDED_ALLOW_IPS` obrigatórias (`:?`); `ALLOWED_ORIGINS` `[]` por padrão; defaults de sessão, login, rate limit e uvicorn; porta `${BIND_ADDRESS:-127.0.0.1}:${HOST_PORT:-8000}`; `read_only`; `tmpfs /tmp`; `no-new-privileges`; `cap_drop: ALL`; `stop_grace_period`; `pids_limit`; `mem_limit`; `restart`; `../library:/library:ro`; volume `app-data` em `/data`, `DATA_DIR=/data`, variáveis `METADATA_*` repassadas; rede com `ipam` em `${NETWORK_SUBNET:-172.30.77.0/24}` | infra |
| `scripts/check.ps1` | Verificação única (Windows): backend, frontend, scan de segredos (com `secret-scan:allow`), resumo | scripts |
| `scripts/check.sh` | Verificação única (Linux/CI; testado só com bash do Git no Windows); mesmo marcador | scripts |
| `scripts/gitleaks.toml` | Config do gitleaks (`regexTarget = "line"`; usado se o binário existir; não instalado) | scripts |
| `scripts/README.md` | Uso do `check`, regras de saída, etapas e marcador `secret-scan:allow` | docs |

## backend/

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `backend/AGENTS.md` | Regras do backend | docs |
| `backend/pyproject.toml` | Dependências com versão fixa (`fastapi==0.165.0`, `uvicorn==0.54.0`, `pydantic-settings==2.16.3`, `sqlalchemy==2.1.9`, `alembic==1.20.1`, `argon2-cffi==25.1.0`, `PyJWT==2.15.1`); extra `dev` fixo; ruff, mypy strict, pytest, import-linter (8 contratos) | config |
| `backend/app/__init__.py` | Pacote | — |
| `backend/app/main.py` | `create_app(settings=None, *, container=None)`: FastAPI sem docs/OpenAPI e com `redirect_slashes=False`; `app.state.settings`, `container`, `csrf_signer`; handler 422 genérico; routers health, auth, items, series, library, progress, preferences; `install_spa` quando `FRONTEND_DIST_DIR` está definido; middlewares (ordem em `main.py`); aviso no lifespan se `FORWARDED_ALLOW_IPS` vazio ou `*`; `app = create_app()` | composição |
| `backend/app/composition.py` | `Container` (construção lazy sob trava): `clock`, `hasher`, `session_factory`, `user_service`, `item_repository`, `progress_service`, `preferences_service`, `storage`, `extractors`, `scan_runner`, `auth_service`, `series_repository`, `series_service`, `cover_store`, `metadata_service`, `enrich_runner`, `candidates_limiter`. Funções: `build_container`, `build_user_service`, `build_rate_limiters`, `run_migrations`. Único ponto ports → adapters (API e CLI) | composição |
| `backend/app/cli.py` | CLI admin (`python -m app.cli`): `migrate`, `create-user [--admin]`, `reset-password`, `deactivate-user`, `list-users`, `scan`, `enrich [--series <uuid>] [--force]`, `purge`. Senha só por `getpass` | entrada (CLI) |
| `backend/app/core/__init__.py` | Pacote | — |
| `backend/app/core/config.py` | `Settings` (env e `.env`, `hide_input_in_errors=True`): `SECRET_KEY` (≥ 32, ≥ 12 distintos, sem espaço nas pontas, sem bloco ≤ 8 repetido); `ALLOWED_ORIGINS` (exatas); `COOKIE_SECURE`; `LIBRARY_PATH`; `DATABASE_URL`; `MIGRATIONS_DIR`; `FRONTEND_DIST_DIR` (vazio = não serve; sem `index.html` = falha no startup); `DATA_DIR`; `METADATA_*` (`ENABLED`, `PROVIDERS`, `TRANSLATE_ENABLED`, `LANGUAGES`, `HTTP_TIMEOUT_SECONDS`, `MAX_PER_RUN`); `EXTRACTOR_*`; `MAX_BODY_BYTES`; `AUDIT_RETENTION_DAYS`; `FORWARDED_ALLOW_IPS` (só aviso); sessão (`ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`, `SESSION_ABSOLUTE_TTL_SECONDS`, `REFRESH_REUSE_GRACE_SECONDS`); login (`LOGIN_*`); `RATE_LIMIT_*`. Validadores de origem e de limites. `max_failures_from_one_address()`. `get_settings()` com `lru_cache` | core |
| `backend/app/core/keys.py` | `derive_key()`: HKDF-SHA256 com rótulos `access-jwt`, `csrf-token`, `login-attempts` | core |
| `backend/app/api/__init__.py` | Pacote | — |
| `backend/app/api/health.py` | `GET /api/v1/health` | api |
| `backend/app/api/auth.py` | Rotas `/api/v1/auth/*` (csrf, login, refresh, logout, me, change-password); cookies `access_token`, `refresh_token`, `csrf_token`; mapeia erros de domínio para HTTP | api |
| `backend/app/api/auth_schemas.py` | `LoginRequest`, `ChangePasswordRequest` (strict, `extra=forbid`, limites), `UserOut` (inclui `theme_pref`) | api |
| `backend/app/api/csrf.py` | `CsrfTokenSigner` (nonce 32 bytes + HMAC) e `CsrfMiddleware` (só `/api`; cookie + cabeçalho + Origin / Sec-Fetch-Site / Referer; 403 genérico) | api |
| `backend/app/api/rate_limit.py` | `RateLimitMiddleware` (só `/api`): limite global por IP; limite estrito só em `/auth/login`, `/auth/refresh`, `/auth/logout` e `/auth/change-password`; 429 genérico com `Retry-After` | api |
| `backend/app/api/body_limit.py` | `BodySizeLimitMiddleware` (só `/api`): 413 por `Content-Length` e por bytes recebidos; 400 para `Content-Length` inválido | api |
| `backend/app/api/security_headers.py` | `SecurityHeadersMiddleware`: CSP explícita (ADR 0012), nosniff, Referrer-Policy, Permissions-Policy sobrepõem a rota (ADR 0006); `Cache-Control: no-store` e `Pragma` em `/api`; exceção de cache de imagem por marcador interno (ADR 0010; páginas, capa de item e capa de série); 500 JSON genérico; desconexão só em debug; `CancelledError` propaga | api |
| `backend/app/api/spa.py` | `install_spa()` e `SpaApp`: serve `FRONTEND_DIST_DIR` como `router.default` (só fora de `/api`); GET/HEAD; caminhos validados; sem symlink; fallback `index.html`; `assets/*` imutável, demais `no-cache`; `Range` via `FileResponse` | api |
| `backend/app/api/http_utils.py` | Helpers ASGI sem regra de negócio: `is_api_path`, `client_ip` (IPv4-mapeado → IPv4; IPv6 → /64; inválido → "unknown"), `header`, `header_count`, `send_json_error` | api |
| `backend/app/api/errors.py` | `library_error()` (mapeia pela classe: 404, 409, 422, 502, 503); `not_found()`; handler de validação 422 genérico | api |
| `backend/app/api/ids.py` | `item_id_or_404()`: UUID canônico em minúsculas, senão 404 genérico | api |
| `backend/app/api/deps.py` | Dependências de rota: `get_container`, `get_settings_dep`, `get_csrf_signer`, `get_auth_service`, `get_current_user` (cookie `access_token`; 401), `require_admin` (403), `get_user_service`, `get_item_repository`, `get_extractors`, `get_scan_runner` (503 se biblioteca indisponível), `get_progress_service`, `get_preferences_service`, `get_series_service`, `get_series_repository`, `get_metadata_service`, `get_cover_store`, `get_candidates_limiter`, `get_enrich_runner`. Sem cache próprio. Único módulo de `api` que importa `app.composition` | composição |
| `backend/app/api/items.py` | `/api/v1/items`: lista (filtros `type`, `q`; `limit`, `offset`), detalhe, página e capa com ETag e 304; autenticado no router | api |
| `backend/app/api/library.py` | `/api/v1/library`: `POST /scan` (202, em segundo plano) e `GET /scan/status`; `POST /enrich` (202, `force`) e `GET /enrich/status`; só admin | api |
| `backend/app/api/library_schemas.py` | `ItemOut`, `ItemListOut`, `ScanStatusOut`, `EnrichStatusOut`; nunca `rel_path` | api |
| `backend/app/api/progress.py` | `/api/v1/progress`: `GET /continue` (declarada antes de `/{item_id}`), `GET`, `PUT` e `DELETE /{item_id}`; autenticado; erros genéricos | api |
| `backend/app/api/progress_schemas.py` | `SaveProgressRequest` (strict; `locator` 0..2^31-1; `device_id` opcional `^[A-Za-z0-9_-]{1,64}$`), `ProgressOut`, `ContinueItemOut`, `ContinueListOut`, `PreferencesIn` (strict; `theme` e `reading_direction` obrigatórios), `PreferencesOut` | api |
| `backend/app/api/preferences.py` | `/api/v1/me/preferences`: `GET` e `PUT` do próprio usuário | api |
| `backend/app/api/series.py` | `/api/v1/series`: `GET` (lista), `GET /{id}`, `GET /{id}/cover`; admin: `GET /{id}/metadata/candidates` (10/min por usuário), `POST /{id}/metadata/select`, `PUT` e `DELETE /{id}/metadata`; ids opacos; erros genéricos | api |
| `backend/app/api/series_schemas.py` | `SeriesListOut`, `SeriesOut` (`continue` como `resume`), `SeriesMetadataOut`, `CandidateOut`, `SelectCandidateRequest` e `ManualMetadataRequest` (strict, `extra=forbid`); nunca caminho, `cover_path` nem URL de capa | api |
| `backend/app/domain/__init__.py` | Pacote | — |
| `backend/app/domain/errors.py` | `DomainError` e filhos: `UnsafePath`, `UnsupportedFormat`, `ArchiveLimitExceeded`, `CorruptArchive`, `PageOutOfRange`, `ItemNotFound`, `LibraryUnavailable`, `ScanAlreadyRunning`, `DataAccessError`, `ResourceBusy` (mensagens sem caminho nem segredo) | domain |
| `backend/app/domain/user.py` | `User` (imutável; `__repr__` sem hash), `Role` (admin, user), `normalize_username()`, `UserError` e filhos, `UserNotFoundError` | domain |
| `backend/app/domain/password_policy.py` | `validate_password()`: 12–128 caracteres; diferente do username; username (≥ 3 caracteres) não contido, nem invertido; lista de 20 senhas comuns; ≥ 5 caracteres distintos; bloco repetido fraco (< 8, palavra comum ou sequência); sequência de alfabeto, dígitos ou teclado | domain |
| `backend/app/domain/auth.py` | `RefreshToken` (`repr` sem token), `AccessClaims`, erros de autenticação: `InvalidCredentialsError`, `LoginLockedError` (com `retry_after_seconds`), `InvalidSessionError`, `NotAuthenticatedError`, `InvalidTokenError`, `CurrentPasswordError` | domain |
| `backend/app/domain/lockout.py` | `LockoutPolicy` e `locked_until()`: bloqueio progressivo calculado das falhas registradas | domain |
| `backend/app/domain/item.py` | `Item` (id UUID opaco, `rel_path`, `format`, `page_count`, `size`, `mtime_ns`, `content_hash`, `missing`; `has_cover`), `ItemType` (manga, book, pdf) | domain |
| `backend/app/domain/library.py` | `ExtractorLimits`, `ItemMetadata`, `Page`, `ScanError`, `ScanProgress`, `ScanReport` (`removal_skipped`), `sanitize_title()`, `natural_key()` | domain |
| `backend/app/domain/progress.py` | `Progress` (imutável, `device_id` opcional), `ContinueEntry` (item + progresso), `compute_position()` (`percent` e `finished` a partir de `locator` e `page_count`; fora da faixa: `InvalidLocator`) | domain |
| `backend/app/domain/preferences.py` | `Preferences` (`theme`: system, light, dark; `reading_direction`: rtl, ltr, vertical; valida no construtor), `InvalidPreferences` | domain |
| `backend/app/domain/series.py` | Agrupamento puro: `group_entry` (série = pasta pai; avulso na raiz), `parse_chapter_number`, `sort_title` (dígitos preenchidos), `sort_chapters`, `chapter_title`, `pick_continue`, `short_description`; `MetadataState` | domain |
| `backend/app/domain/metadata.py` | Regras puras de metadados: `sanitize_description`, `sanitize_title`, `pick_best` (limiares 0,85 e 0,9, margem, edições penalizadas, desempate por ano), `pick_description`, `sniff_image` (JPEG, PNG, WebP), `chunk_for_translation`, `valid_translation`, `fix_missing_sentence_space` (REG-023), `PROVIDER_LABELS`, `DESCRIPTION_ONLY`, `EnrichReport` | domain |
| `backend/app/services/__init__.py` | Pacote | — |
| `backend/app/services/auth_service.py` | `AuthService` e `AuthConfig` (injetado): `login` (bloqueio e falha reservados antes do hash), `refresh` (rotação com janela de tolerância; reuso revoga a família), `logout`, `change_password` (revoga todas as sessões), `current_user` (valida no banco), `purge_expired`; purga oportunista de hora em hora | services |
| `backend/app/services/user_service.py` | Contas: `create_user`, `reset_password`, `deactivate_user`, `list_users`; grava auditoria | services |
| `backend/app/services/scan.py` | `scan_library()`: varredura incremental por size+mtime; erro por arquivo sem abortar; remoção de sumidos só com caminhada saudável | services |
| `backend/app/services/scan_runner.py` | `ScanRunner`: uma varredura por vez (lock não bloqueante); thread daemon (API) ou síncrona (CLI); status sem caminho nem mensagem; sem cancelamento | services |
| `backend/app/services/catalog.py` | `list_items()` (limite efetivo 1–100, `has_more`) e `get_item()` | services |
| `backend/app/services/pages.py` | `get_page()` e `get_cover()`: valida índice e formato; delega ao extrator | services |
| `backend/app/services/hashing.py` | `ensure_content_hash()`: sha256 sob demanda e persistido. Sem rota que a chame | services |
| `backend/app/services/progress_service.py` | `ProgressService`: `save` (valida locator contra o item, deriva `percent`/`finished`, carimba com o relógio do servidor, upsert), `get`, `clear` (idempotente), `continue_reading` (limite capado em 50) | services |
| `backend/app/services/preferences_service.py` | `PreferencesService`: `get` e `update` (`UserNotFoundError` se o usuário não existe) | services |
| `backend/app/services/series_service.py` | `SeriesService`: `list_series` (limite capado em 100), `get_series` (capítulos, progresso do usuário, `continue`); `get_series_cover` (capa baixada ou do primeiro capítulo legível, até 5 tentativas) | services |
| `backend/app/services/metadata_service.py` | `MetadataService`: `enrich_all` (uma execução, até `METADATA_MAX_PER_RUN`), elegibilidade por estado, fusão de fontes (`_apply_work`, `_resolve_description`), `candidates`, `select`, `set_manual`, `clear`; capa com escrita condicional ao estado atual; falha de fonte não derruba a execução | services |
| `backend/app/services/enrich_runner.py` | `EnrichRunner`: uma execução por vez (thread em segundo plano na API; síncrona no CLI); estado `idle`, `running`, `finished`, `failed` com contagens | services |
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
| `backend/app/ports/item_repository.py` | `ItemRepository`: `add`, `update`, `get`, `get_by_rel_path`, `list`, `search`, `remove_missing` | ports |
| `backend/app/ports/progress_repository.py` | `ProgressRepository`: `upsert` (atômico, último vence), `get`, `delete` (idempotente), `list_continue` (não concluídos, item não ausente, mais recente primeiro); toda operação recebe `user_id` | ports |
| `backend/app/ports/preferences_repository.py` | `PreferencesRepository`: `get` (None = usuário inexistente), `set` (escrita só das duas colunas; False = inexistente) | ports |
| `backend/app/ports/series_repository.py` | `SeriesRepository` (interface): lista de séries, detalhe, capítulos e atualização condicional de metadado | ports |
| `backend/app/ports/cover_store.py` | `CoverStore` (interface): `stage`, `commit`, `discard`, `read`, `delete` de capas | ports |
| `backend/app/ports/http_gateway.py` | `HttpGateway` (interface): `get_json`, `post_json`, `get_image`; só hosts da allowlist | ports |
| `backend/app/ports/metadata_provider.py` | `MetadataProvider` (interface): busca e obtenção por id em uma fonte pública | ports |
| `backend/app/ports/translator.py` | `TextTranslator` (interface): tradução de sinopse; `None` quando indisponível | ports |
| `backend/app/adapters/__init__.py` | Pacote | — |
| `backend/app/adapters/AGENTS.md` | Regras de adapters (área sensível) | docs |
| `backend/app/adapters/gate.py` | `BoundedGate`: N slots, até M em espera por T s; excedente levanta `ResourceBusy` | adapters |
| `backend/app/adapters/http/__init__.py` | Pacote | — |
| `backend/app/adapters/http/safe_gateway.py` | `SafeGateway`: única saída de rede do app. https, porta 443, lista fixa de 7 hosts, sem redirecionamento, IP público verificado e conexão fixada, TLS com verificação, sem cookies, User-Agent `BibliotecaPWA/1.0`, limites (JSON 1 MiB, imagem 5 MiB, POST 16 KiB, URL 2 048), 0,5 s entre requisições por host; `DisabledGateway` (sem socket) quando `METADATA_ENABLED=false` (ADR 0015) | adapters |
| `backend/app/adapters/metadata/__init__.py` | Pacote (sem código) | — |
| `backend/app/adapters/metadata/_json.py` | Leitura defensiva de JSON da rede: tipo errado vira vazio; limites de texto e de itens | adapters |
| `backend/app/adapters/metadata/mangadex.py` | `MangaDexProvider` (obra): capa, descrição pt-br, títulos alternativos; busca com 10 resultados | adapters |
| `backend/app/adapters/metadata/anilist.py` | `AniListProvider` (obra, POST GraphQL): capa e descrição em inglês | adapters |
| `backend/app/adapters/metadata/wikipedia.py` | `WikipediaProvider` (só descrição, pt): busca e resumo, até 2 páginas por busca | adapters |
| `backend/app/adapters/metadata/googlebooks.py` | `GoogleBooksProvider` (só descrição; cota anônima pequena) | adapters |
| `backend/app/adapters/metadata/mymemory.py` | `MyMemoryTranslator` (en → pt-BR, último recurso): trechos de até 400 bytes, tudo ou nada; para 6 h após resposta de cota; aplica `fix_missing_sentence_space` (REG-023) | adapters |
| `backend/app/adapters/persistence/__init__.py` | Pacote | — |
| `backend/app/adapters/persistence/db.py` | `create_db_engine()` (SQLite: WAL, `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL` em toda conexão; `hide_parameters=True`) e `create_session_factory()` | adapters |
| `backend/app/adapters/persistence/models.py` | ORM: `UserRow` (com `reading_direction`), `RefreshTokenRow`, `LoginAttemptRow`, `ItemRow`, `AuditLogRow`, `ReadingProgressRow`; `UTCDateTime` (grava UTC naive, lê UTC aware). Schema é da migração | adapters |
| `backend/app/adapters/persistence/user_repository.py` | `SqlAlchemyUserRepository`: escritas por UPDATE dirigido (CAS de hash com `is_active` e hash esperado); busca de username sem caixa; erro de driver vira `DataAccessError` | adapters |
| `backend/app/adapters/persistence/refresh_token_repository.py` | `SqlAlchemyRefreshTokenRepository`: `rotate` atômico (marca usado e grava sucessor na mesma transação; janela de tolerância); revogação de família e de usuário; purga de famílias mortas | adapters |
| `backend/app/adapters/persistence/login_attempt_store.py` | `SqlAlchemyLoginAttemptStore`: chaves em HMAC-SHA256 por escopo; reserva e liberação de falhas; falhas desde o último sucesso; purga | adapters |
| `backend/app/adapters/persistence/audit_log.py` | `SqlAlchemyAuditLog`: `record` com `at` do relógio (detalhe > 512 bytes vira `{"truncated": true}`); `purge` | adapters |
| `backend/app/adapters/persistence/item_repository.py` | `SqlAlchemyItemRepository`: CRUD de `Item`; listagem por `(lower(title), id)`; busca com LIKE escapado; `remove_missing` em lotes de 500 | adapters |
| `backend/app/adapters/persistence/progress_repository.py` | `SqlAlchemyProgressRepository`: upsert `INSERT ... ON CONFLICT DO UPDATE` (SQLite e PostgreSQL); `get`, `delete`, `list_continue` (JOIN com `items`); erro de driver vira `DataAccessError` | adapters |
| `backend/app/adapters/persistence/preferences_repository.py` | `SqlAlchemyPreferencesRepository`: lê e grava só `users.theme_pref` e `users.reading_direction` | adapters |
| `backend/app/adapters/persistence/series_repository.py` | `SqlAlchemySeriesRepository`: lista só séries com capítulo ativo, por `sort_title`; detalhe; capítulos em ordem; atualização de metadado condicional ao estado atual; capa e atribuição gravadas | adapters |
| `backend/app/adapters/persistence/migrator.py` | `upgrade()` e `downgrade()` do Alembic, programático (sem `alembic.ini`). Diretório: argumento, `MIGRATIONS_DIR` ou `backend/migrations` do checkout | adapters |
| `backend/app/adapters/security/__init__.py` | Pacote | — |
| `backend/app/adapters/security/argon2_hasher.py` | `Argon2Hasher`: Argon2id (t=3, m=64 MiB, p=4); hash dummy com os mesmos parâmetros; senha > 1024 caracteres recusada sem hash; `BoundedGate` de 2 slots, 8 em espera por 1 s | adapters |
| `backend/app/adapters/security/jwt_tokens.py` | `JwtTokenService`: HS256 fixo; claims `sub`, `sid`, `jti`, `iat`, `nbf`, `exp` obrigatórias; tempo pelo relógio injetado; token > 2048 caracteres recusado | adapters |
| `backend/app/adapters/security/rate_limiter.py` | `TokenBucketRateLimiter`: balde de fichas em memória por IP; até 50 000 chaves (LRU) | adapters |
| `backend/app/adapters/security/system_clock.py` | `SystemClock` (UTC) | adapters |
| `backend/app/adapters/storage/__init__.py` | Pacote | — |
| `backend/app/adapters/storage/local.py` | `LocalStorage`: único que resolve caminho relativo. Rejeita `..`, absoluto, unidade, nomes reservados do Windows, caracteres inválidos, > 1024 caracteres, > 16 níveis, symlink e junction reais (não o atributo ReparsePoint do OneDrive); `walk_errors` | adapters |
| `backend/app/adapters/storage/cover_store.py` | `LocalCoverStore`: capas em `DATA_DIR/covers/<uuid>.<ext>`; nome só do UUID do servidor e da extensão dos bytes; escrita temporária exclusiva, `fsync` e renomeação atômica; leitura só de arquivo regular, sem symlink, até 5 MiB (ADR 0016) | adapters |
| `backend/app/adapters/extractors/__init__.py` | Pacote | — |
| `backend/app/adapters/extractors/_common.py` | `sniff_image()` (bytes mágicos: jpeg, png, webp, gif, avif), `has_image_extension()`, `PageIndexCache` (LRU de 64 por `(rel_path, size, mtime_ns)`), `default_read_gate()` (4 leitores, 16 em espera, 2 s) | adapters |
| `backend/app/adapters/extractors/cbz.py` | `CbzExtractor` (`format=cbz`, `item_type=manga`): índice em cache; valida bytes de todas as entradas; limites; rejeita criptografado, symlink e nome inseguro (zip-slip); ordem natural; `ComicInfo.xml` ignorado | adapters |
| `backend/app/adapters/extractors/folder.py` | `FolderExtractor` (`format=folder`, `item_type=manga`): uma pasta = um item; índice valida bytes de todos os arquivos de imagem; limites; leitura limitada a `max_page_bytes + 1` | adapters |
| `backend/app/adapters/extractors/registry.py` | `build_extractors()`: CBZ e pasta com um gate compartilhado. Novo formato entra aqui | adapters |
| `backend/migrations/env.py` | Ambiente Alembic: URL recebida em `config.attributes["url"]` | migrações |
| `backend/migrations/script.py.mako` | Modelo de nova revisão Alembic | migrações |
| `backend/migrations/versions/0001_users_and_auth.py` | Cria `users` (com `theme_pref`), `refresh_tokens`, `login_attempts`, `audit_log` | migrações |
| `backend/migrations/versions/0002_items.py` | Cria `items` (checks de tipo e de `page_count`; índices `ix_items_type`, `ix_items_title`, `ix_items_added_at`, `ix_items_missing`) | migrações |
| `backend/migrations/versions/0003_drop_unused_item_indexes.py` | Remove `ix_items_title` e `ix_items_missing` (reversível) | migrações |
| `backend/migrations/versions/0004_reading_progress_and_preferences.py` | `users.reading_direction` (`ALTER ADD COLUMN`, `NOT NULL DEFAULT 'rtl'`, check) e tabela `reading_progress` (PK `(user_id, item_id)`, FKs com CASCADE, checks de `locator` e `percent`, índice `(user_id, updated_at DESC)`). Reversível | migrações |
| `backend/migrations/versions/0005_series.py` | Cria `series` (CHECK de `metadata_state`; `folder_rel_path` único; índice `sort_title`); `items.series_id` (FK `ON DELETE SET NULL`) e `items.chapter_number` por `ALTER ADD COLUMN`; backfill idempotente. Reversível | migrações |
| `backend/migrations/versions/0006_series_metadata_fields.py` | `series.source_url`, `metadata_checked_at`, `title_original` por `ALTER ADD COLUMN`. Reversível | migrações |
| `backend/migrations/versions/0007_series_description_attribution.py` | `series.description_origin` (CHECK: source, translated, manual), `description_source_name`, `description_source_url`; backfill de descrições anteriores. Reversível | migrações |
| `backend/tests/AGENTS.md` | Regras de teste: nomes, 500 com `TestClient`, `caplog`, casos negativos de arquitetura | docs |
| `backend/tests/conftest.py` | Fixtures de ambiente hermético (remove variáveis do ambiente real; `SECRET_KEY` de teste; diretório de trabalho vazio) e cliente | teste |
| `backend/tests/fakes.py` | Auxiliares (`png`, `make_cbz`, `make_library`), `FixedClock` e falsos (`FakeItemRepository`, `FakeStorage`, `FakeExtractor`). Não é teste | teste |
| `backend/tests/auth_fakes.py` | Falsos de autenticação (`FakeClock`, `FakeHasher`, `FakeUsers`, `FakeRefreshTokens`, `FakeAttempts`, `FakeAudit`), `Rig`, `Env` e `ApiClient` (ambiente HTTP com banco). Não é teste | teste |
| `backend/tests/metadata_fakes.py` | `FakeGateway` (aplica a allowlist real e responde de memória), respostas canônicas das fontes e `fake_translation`. Não é teste | teste |
| `backend/tests/library_env.py` | Helpers de API de biblioteca: `library_env`, `logged_in`, `add_item`, `item_id_by_title`. Não é teste | teste |
| `backend/tests/architecture/test_layers.py` | Executa import-linter de verdade; casos negativos por `forbidden_modules`; positivos de `api.deps`, `composition`, `cli`, `main` | teste |
| `backend/tests/integration/test_health.py` | Health | teste |
| `backend/tests/integration/test_migrations.py` | Sobe e desce; ORM × schema; índices; pragmas; unicidade; checks; `0002`/`0003` reversíveis; `0004` reversível sem perder usuários nem sessões; checks de `reading_progress` | teste |
| `backend/tests/integration/test_migrations_dir.py` | Resolução de `MIGRATIONS_DIR`; Dockerfile define `MIGRATIONS_DIR` | teste |
| `backend/tests/integration/test_user_repository.py` | Repositório de usuário e auditoria contra banco migrado | teste |
| `backend/tests/integration/test_auth_repositories.py` | Refresh (rotação, revogação, famílias, purga) e tentativas (HMAC, escopos, reset por sucesso, purga) | teste |
| `backend/tests/integration/test_item_repository.py` | Persistência de `Item`: roundtrip, ordem, filtros, `remove_missing`, LIKE literal, purga de auditoria | teste |
| `backend/tests/integration/test_auth_api.py` | API de auth ponta a ponta: login, me, refresh, logout, troca de senha, reset pelo admin, auditoria, `require_admin` | teste |
| `backend/tests/integration/test_library_api.py` | Login → scan → listar → página; scan concorrente (409); biblioteca ausente (503); CLI `scan` | teste |
| `backend/tests/integration/test_library_scan.py` | Scan, página e capa com `LocalStorage` e repositório falso | teste |
| `backend/tests/integration/test_cli.py` | CLI ponta a ponta (migrate, create, list, reset, deactivate); senha sem eco; sem argumento de senha | teste |
| `backend/tests/integration/test_progress_api.py` | API de progresso e preferências: cálculo no servidor, cliente não envia `percent`/`finished`, 422 e 404 genéricos, `DELETE` idempotente, `continue` (ordem, filtros, limite), UTC com offset, preferências e rate limit de navegação | teste |
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
| `backend/tests/unit/test_progress_service.py` | `compute_position`, `save` (percent/finished e relógio do servidor), locator fora do item não grava, progresso por usuário, limite do `continue` capado, preferências e domínio | teste |
| `backend/tests/integration/test_series_api.py` | API de séries sobre biblioteca real: agrupamento, lista, detalhe, `continue`, capa, varredura | teste |
| `backend/tests/integration/test_metadata_enrich.py` | Enriquecimento ponta a ponta (rotas, serviços e providers reais; só o gateway é falso): fontes, estados, capa, desligado | teste |
| `backend/tests/integration/test_metadata_fusion.py` | Fusão de fontes, descrição pt-br primeiro, tradução marcada; caso real de obra sem pt-br no MangaDex | teste |
| `backend/tests/unit/test_series_domain.py` | Regras puras de agrupamento: nome, ordem, títulos, onde continuar | teste |
| `backend/tests/unit/test_metadata_domain.py` | Sanitização de descrição, casamento de títulos, escolha de idioma, detecção de imagem | teste |
| `backend/tests/unit/test_metadata_providers.py` | MangaDex e AniList com respostas canônicas: parsing, idioma, formas hostis, o que é (e não é) enviado | teste |
| `backend/tests/unit/test_metadata_describers.py` | Wikipédia, Google Livros e MyMemory com respostas canônicas | teste |
| `backend/tests/unit/.gitkeep` | Pasta de unidade | teste |
| `backend/tests/security/test_security_headers.py` | Cabeçalhos (inclui 404), 500 genérico, reraise após início, `CancelledError`, desconexão, substituição de cabeçalhos da rota | teste |
| `backend/tests/security/test_settings.py` | `SECRET_KEY` (ausente, curta, baixa entropia, espaços); limites; coerência do lockout; fórmula | teste |
| `backend/tests/security/test_password_storage.py` | Senha só como Argon2id; fora de logs, erros e auditoria | teste |
| `backend/tests/security/test_local_storage.py` | Caminhos hostis, links reais, pasta OneDrive, raiz inexistente | teste |
| `backend/tests/security/test_cbz_extractor.py` | CBZ: ordem, zip-slip, symlink, zip bomb, limites, arquivo falso, criptografado, corrompido, leitura parcial | teste |
| `backend/tests/security/test_folder_extractor.py` | Pasta: ordem, extensão falsa, página gigante, excesso de arquivos | teste |
| `backend/tests/security/test_csrf.py` | CSRF: token, cookie, assinatura, Origin, Referer, Fetch Metadata, métodos, respostas genéricas | teste |
| `backend/tests/security/test_cookies_and_cache.py` | Atributos de cookies; `no-store` em toda rota `/api`; regra sem relaxamento | teste |
| `backend/tests/security/test_cache_exception.py` | Exceção de cache de imagem: só GET 200/304 em páginas e capa, marcador exato | teste |
| `backend/tests/security/test_login_bruteforce.py` | Bloqueio por par, conta e IP; resposta idêntica; progressivo; expiração; distribuído; hash só HMAC | teste |
| `backend/tests/security/test_session_attacks.py` | JWT forjado, expirado, sem claims, sessão alheia, troca de senha, segredos fora de logs | teste |
| `backend/tests/security/test_jwt_tokens.py` | HS256: `alg:none`, algoritmos trocados, assinatura, claims, tempo, erro sem token | teste |
| `backend/tests/security/test_rate_limit_and_cors.py` | Rate limit (global, auth, IP normalizado, IPv6 /64); CORS exato; origens inválidas | teste |
| `backend/tests/security/test_body_limit.py` | 413 por `Content-Length` e por corpo recebido; 400 para `Content-Length` inválido | teste |
| `backend/tests/security/test_items_api.py` | Autorização de itens e scan; IDs e páginas hostis; ETag/304; tipos de mídia; erros genéricos | teste |
| `backend/tests/security/test_progress_authz.py` | Anônimo recebe 401 em tudo; usuário nunca lê nem altera progresso ou preferências alheios; escrita exige CSRF; IDs malformados = 404 genérico; respostas `no-store` sem caminhos | teste |
| `backend/tests/security/test_safe_gateway.py` | `SafeGateway`: allowlist, https e porta, IP público, sem redirecionamento, tipos, limites, espaçamento, sem socket (gateway falso) | teste |
| `backend/tests/security/test_cover_store.py` | Capas: nome só do UUID, extensões, tamanho, symlink, escrita atômica, concorrência | teste |
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

Não existem ainda: `backend/tests/fixtures/` (o `check` de segredos já a exclui se existir), adaptador de progresso para EPUB/PDF, extratores CBR, EPUB e PDF, rota de arquivo com `Range` para EPUB/PDF (`/items/{id}/file`).

## frontend/

| Caminho | Responsabilidade | Camada |
|---|---|---|
| `frontend/AGENTS.md` | Regras do frontend | docs |
| `frontend/package.json` | Dependências (versões exatas); scripts `dev`, `build` (só `vite build`), `lint`, `typecheck` (app + node), `test`, `arch`, `format:check`, `test:e2e` | config |
| `frontend/package-lock.json` | Lockfile npm | config |
| `frontend/.npmrc` | `save-exact=true` | config |
| `frontend/vite.config.ts` | Vite, vite-plugin-pwa (`registerType: autoUpdate`; manifest `id`/`scope` `/`; workbox: `runtimeCaching: []`, `skipWaiting: false`, `clientsClaim: false`, denylist `/api`), proxy `/api` para `localhost:8000`, Vitest | config |
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
| `frontend/src/app/App.tsx` | Raiz: `Providers` + `AppRoutes` | app |
| `frontend/src/app/Providers.tsx` | `ThemeProvider` → `BrowserRouter` → `SessionProvider` → `PreferencesProvider` | app |
| `frontend/src/app/routes.tsx` | `AppRoutes`: `/login`; grupo protegido por `RequireAuth` com `/`, `/ler/:itemId`, `/ajustes`; `*` → `/` | app |
| `frontend/src/app/registerServiceWorker.ts` | Registro do SW (`virtual:pwa-register`, só em produção) | app |
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
| `frontend/src/features/library/components/LibraryPage.tsx` | Tela `/`: "Continuar lendo", grade de séries, busca com debounce, "carregar mais", "Atualizar metadados" (só admin) | features |
| `frontend/src/features/library/components/ContinueReading.tsx` | Prateleira "Continuar lendo" com barra de progresso | features |
| `frontend/src/features/library/components/SeriesCard.tsx` | Cartão de série com capa same-origin e versão para recarregar a capa após atualização | features |
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
| `frontend/src/features/reader-manga/hooks/useReaderNav.ts` | Navegação entre capítulos da série (`chapterNeighbours`); "voltar" leva à série quando houver | features |
| `frontend/src/features/reader-epub/README.md` | Esqueleto (Fase 4) | docs |
| `frontend/src/features/reader-pdf/README.md` | Esqueleto (Fase 4) | docs |
| `frontend/src/features/settings/index.ts` | Exporta `SettingsPage` | features |
| `frontend/src/features/settings/README.md` | Escopo da tela de ajustes | docs |
| `frontend/src/features/settings/settings.css` | Estilos dos ajustes | features |
| `frontend/src/features/settings/components/SettingsPage.tsx` | Tela `/ajustes`: aparência, sentido de leitura, conta (troca de senha e sair) | features |
| `frontend/src/features/settings/components/ChangePasswordForm.tsx` | Formulário de troca de senha | features |
| `frontend/src/features/settings/hooks/useChangePassword.ts` | Estado e envio da troca de senha | features |
| `frontend/src/features/series/index.ts` | Exporta `SeriesPage` | features |
| `frontend/src/features/series/series.css` | Estilos da tela de série e do painel de metadados | features |
| `frontend/src/features/series/components/SeriesPage.tsx` | Tela `/serie/:id`: estados de carregamento e erro, cabeçalho com capa, descrição, "continuar", lista de capítulos e painel admin | features |
| `frontend/src/features/series/components/ChapterList.tsx` | Lista de capítulos em janelas de 50, com ir-para-número (`parseChapterNumber`) | features |
| `frontend/src/features/series/components/ChapterRow.tsx` | Linha de capítulo: título, páginas, progresso e link para o leitor (`?serie=`) | features |
| `frontend/src/features/series/components/SeriesDescription.tsx` | Descrição em texto puro, badges de origem ("tradução automática") e atribuição (CC BY-SA na Wikipédia); link só https | features |
| `frontend/src/features/series/components/MetadataPanel.tsx` | Painel admin (recolhido por padrão): busca só por ação explícita, escolher fonte, editar título e descrição, remover | features |
| `frontend/src/features/series/hooks/useChapterList.ts` | Janela de capítulos e interpretação de número (`12`, `12.5`, `12,5`) | features |
| `frontend/src/features/series/hooks/useMetadataAdmin.ts` | Busca e ações do painel admin; mensagens sem detalhe técnico; limites de título (200) e descrição (4 000) | features |
| `frontend/src/features/progress/README.md` | Reservada: o código de progresso fica em `shared/progress` | docs |
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
| `frontend/src/shared/preferences/index.ts` | Exportações de preferências | shared |
| `frontend/src/shared/preferences/types.ts` | `Preferences`, `ReadingDirection`, `ThemeChoice`, `DEFAULT_PREFERENCES` (`system`, `rtl`), `normalizePreferences` (valida cada campo do servidor) | shared |
| `frontend/src/shared/preferences/api.ts` | `fetchPreferences` (GET) e `savePreferences` (PUT do objeto completo) | shared |
| `frontend/src/shared/preferences/PreferencesProvider.tsx` | Carrega preferências ao autenticar e aplica o tema; PUT sempre sobre dados do servidor, nunca sobre padrões; enquanto o GET não responde, guarda a alteração; PUTs em série | shared |
| `frontend/src/shared/preferences/preferences-context.ts` | Contexto (`preferences`, `loaded`, `loadFailed`, `saveFailed`, `update`, `reload`) | shared |
| `frontend/src/shared/preferences/usePreferences.ts` | Hook `usePreferences` | shared |
| `frontend/src/shared/progress/index.ts` | Exportações de progresso | shared |
| `frontend/src/shared/progress/types.ts` | `Progress`, `ContinueEntry`, `ContinueList`, `SaveStatus` | shared |
| `frontend/src/shared/progress/api.ts` | `getProgress` (404 → `null`), `putProgress` (envia só `locator`), `deleteProgress`, `listContinue` (limite 12) | shared |
| `frontend/src/shared/progress/progress-saver.ts` | `createProgressSaver`: debounce de 800 ms, um envio por vez, valor mais novo vence, retry de 5 s, `flush` com `keepalive` | shared |
| `frontend/src/shared/progress/useProgressSaver.ts` | Liga o salvador ao leitor; `flush` ao ocultar a página e ao sair (sem `sendBeacon`) | shared |
| `frontend/src/shared/items/index.ts` | Exportações de itens | shared |
| `frontend/src/shared/items/paths.ts` | `readerPath(itemId, seriesId?)` (`/ler/:id?serie=`) e `seriesPath(id)` | shared |
| `frontend/src/shared/items/types.ts` | `Item`, `ItemList`, `ItemType`, `isReadable` (hoje só mangá) | shared |
| `frontend/src/shared/items/api.ts` | `listItems`, `getItem`, `coverUrl`, `pageUrl` (URLs same-origin, com cookie) | shared |
| `frontend/src/shared/series/index.ts` | Exportações de séries | shared |
| `frontend/src/shared/series/types.ts` | `SeriesSummary`, `SeriesDetail`, `Chapter`, `MetadataCandidate`, `EnrichStatus`, `DescriptionOrigin`; `safeHttpsUrl` (só https); `chapterNeighbours` | shared |
| `frontend/src/shared/series/api.ts` | `listSeries`, `getSeries`, `seriesCoverUrl` (same-origin, com versão), `startEnrich`, `getEnrichStatus`, `searchMetadataCandidates`, `selectMetadata`, `saveMetadataText`, `removeMetadata` | shared |
| `frontend/src/shared/series/useSeriesDetail.ts` | Carrega uma série; a resposta fica com a chave a que pertence (resposta atrasada de outra série é descartada) | shared |
| `frontend/src/shared/hooks/index.ts` | Exportações de hooks genéricos | shared |
| `frontend/src/shared/hooks/useCountdown.ts` | Contagem regressiva em segundos (login com 429 e troca de senha) | shared |
| `frontend/src/shared/hooks/useDebouncedValue.ts` | Valor com atraso (busca da biblioteca) | shared |
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
| `frontend/tests/unit/api-client.test.ts` | api-client: credenciais, CSRF, 429, 500, rede, 204, não-JSON, AbortError, 2xx vazio, junção de `baseUrl` | teste |
| `frontend/tests/unit/api-client-session.test.ts` | Recuperação de sessão (401 → refresh compartilhado → retry uma vez; refresh rejeitado notifica); bootstrap de CSRF (uma busca compartilhada; retry só se o token mudou); `keepalive` sem `sendBeacon` | teste |
| `frontend/tests/unit/architecture.test.ts` | dependency-cruiser em `src` e em 8 fixtures negativas | teste |
| `frontend/tests/unit/eslint-rules.test.ts` | ESLint: formas proibidas em feature (`it.each`); permissões por pasta (api-client, offline) | teste |
| `frontend/tests/unit/theme-css.test.ts` | Tokens do tema: cada valor escuro uma vez; dois gatilhos escuros; todos os tokens em `:root` | teste |
| `frontend/tests/unit/theme.test.tsx` | Tema: sistema por padrão; troca explícita; sem localStorage | teste |
| `frontend/tests/unit/auth.test.tsx` | Guarda de rota (carregando, anônimo, autenticado, sessão encerrada); login (sucesso, retorno, erro genérico, 429 com contagem, 503); `safeRedirect` | teste |
| `frontend/tests/unit/library.test.tsx` | Biblioteca: capas, livros e PDFs desabilitados, busca com debounce, filtro por tipo, "carregar mais", "Continuar lendo" (falha não bloqueia) | teste |
| `frontend/tests/unit/reader.test.tsx` | Leitor de mangá: retomada (página salva, 404 = página 1, item sem páginas), modos RTL/LTR/vertical, zoom, pré-carregamento, salvamento (debounce, `pagehide` com `keepalive`, aba oculta, saída, falha com aviso) | teste |
| `frontend/tests/unit/reader-navigation.test.ts` | Lógica pura de navegação: zonas de toque, deslize, teclas, `clampPage` | teste |
| `frontend/tests/unit/reader-vertical.test.tsx` | Modo vertical: não regride o progresso salvo ao retomar; janela de páginas montadas; memória limitada do pré-carregamento; região viva e teclado | teste |
| `frontend/tests/unit/progress-saver.test.ts` | Debounce, um envio por vez, retry, `flush` com `keepalive`, `dispose` | teste |
| `frontend/tests/unit/preferences.test.tsx` | Não sobrescreve o servidor com padrões; edição enquanto o GET está pendente é mesclada; PUTs em série | teste |
| `frontend/tests/unit/session-images.test.tsx` | Verificação de sessão na carga (só 401 = saiu); recuperação de imagem compartilhada, sem `/auth/me`, uma tentativa por janela | teste |
| `frontend/tests/unit/series.test.tsx` | Tela de série: capa, "continuar"/"começar a ler", capítulos em janela, "ir para o capítulo N", descrição (texto puro, badge de idioma, link https), vazio, 404 e erro com nova tentativa | teste |
| `frontend/tests/unit/reader-series.test.tsx` | Leitor com série: próximo e anterior, "voltar" para a série | teste |
| `frontend/tests/unit/metadata.test.tsx` | Painel admin (invisível para usuário comum, recolhido, busca só por clique, usar candidato, edição com limites, remoção com confirmação, 429); botão "Atualizar metadados" (polling, 409, parada ao sair); origem e atribuição da descrição; links só https; capa e `Cover` | teste |
| `frontend/tests/unit/settings.test.tsx` | Ajustes: tema, sentido de leitura, troca de senha, sair | teste |
| `frontend/tests/fixtures/arch-*/` (8) | Fixtures que devem violar uma regra cada (`arch-violation`, `arch-feature-app`, `arch-shared-feature`, `arch-shared-app`, `arch-cycle`, `arch-type-only`, `arch-unresolvable`, `arch-dev-dep`) | teste |
| `frontend/tests/e2e/.gitkeep` | Pasta vazia (E2E ainda não existe) | teste |
| `frontend/tests/regression/.gitkeep` | Pasta vazia (nenhum `reg_NNN` de frontend ainda) | teste |

Removidos (entrega do MVP, 2026-11-20): `frontend/src/app/HomePage.tsx`, `frontend/src/app/useHealth.ts`, `frontend/tests/unit/home.test.tsx`. Removido em 2026-11-21: `frontend/src/features/library/components/ItemCard.tsx` (substituído por `SeriesCard.tsx`).

## Gerado (não versionar, não listar)

`frontend/dist/` (build), `frontend/node_modules/`, `backend/.venv/`, `backend/reader_backend.egg-info/`, `backend/**/__pycache__/`.
