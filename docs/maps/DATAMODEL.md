# DATAMODEL

Estado: 2026-11-21. Migrações em `backend/migrations/versions/`: `0001` (contas e autenticação), `0002` (itens), `0003` (remove dois índices de `items`), `0004` (progresso de leitura e `users.reading_direction`), `0005` (séries e `items.series_id`/`chapter_number`), `0006` (campos de metadados em `series`), `0007` (atribuição da descrição). Banco: SQLite em WAL (ADR 0007). `DATABASE_URL` padrão do `Settings`: `sqlite:///./data/app.db`; compose e imagem: `sqlite:////data/app.db`. ORM: `backend/app/adapters/persistence/models.py`. O schema é da migração; o ORM não cria tabelas.

## Entidades

| Entidade (tabela) | Campos | Estado |
|---|---|---|
| User (`users`) | id (UUID texto), username, password_hash (Argon2id), role (admin, user), is_active, theme_pref (system, light, dark; padrão system), reading_direction (rtl, ltr, vertical; padrão rtl), created_at, updated_at, password_changed_at | implementado |
| RefreshToken (`refresh_tokens`) | id, user_id → users (CASCADE), family_id, token_hash (SHA-256 hex, único), created_at, expires_at, used_at, revoked_at, user_agent, ip | implementado; `user_agent` e `ip` não são preenchidos (pendência) |
| LoginAttempt (`login_attempts`) | id, scope (ip, account, ip_account), key_hash (HMAC-SHA256 hex, 64), attempted_at, success | implementado |
| AuditLog (`audit_log`) | id, at, event, user_id → users (SET NULL), ip, detail (JSON, ≤ 512 bytes) | implementado; `ip` nunca preenchido (pendência) |
| Item (`items`) | id (UUID texto, opaco), type (manga, book, pdf), title, rel_path (único, relativo, nunca enviado à API), format (cbz, folder), page_count, content_hash (opcional), size, mtime_ns, added_at, updated_at, missing, series_id (→ series, `ON DELETE SET NULL`, opcional), chapter_number (real, opcional, do nome do arquivo) | implementado (`0002`, `0003`, `0005`) |
| ReadingProgress (`reading_progress`) | user_id → users (CASCADE), item_id → items (CASCADE), locator (índice da página, 0-based), percent (0–100), finished, device_id (opcional, até 64), updated_at (UTC). PK `(user_id, item_id)` | implementado (`0004`) |
| Series (`series`) | id (UUID), title, sort_title (dígitos preenchidos a 12), folder_rel_path (único; nulo = série avulsa; nunca enviado à API), description, description_lang, description_origin (source, translated, manual), description_source_name, description_source_url, metadata_source (mangadex, anilist, wikipedia, googlebooks), external_id, source_url (https), title_original, metadata_state (none, matched, manual, not_found), metadata_checked_at, cover_path (só `<uuid>.<ext>`; nunca caminho), created_at, updated_at | implementado (`0005`, `0006`, `0007`; ADR 0014, 0015, 0016) |
| Chapter | não é tabela: é um `item` com `series_id` e `chapter_number` | implementado (ADR 0014) |

Eventos de `audit_log` hoje: `user.created`, `user.password_reset`, `user.deactivated`, `login.success`, `login.failure`, `login.locked`, `token.refresh`, `token.reuse_detected`, `logout`, `password.changed`. Escaneamento, agrupamento, progresso e enriquecimento de metadados não geram evento.

## Migrações

| Revisão | Conteúdo | Reversível |
|---|---|---|
| `0001` | `users`, `refresh_tokens`, `login_attempts`, `audit_log` e seus índices | sim |
| `0002` | `items`, `ix_items_type`, `ix_items_title`, `ix_items_added_at`, `ix_items_missing` | sim |
| `0003` | Remove `ix_items_title` e `ix_items_missing` (dados intactos) | sim |
| `0004` | `users.reading_direction` por `ALTER TABLE ADD COLUMN` (`NOT NULL DEFAULT 'rtl'`, check); tabela `reading_progress` e `ix_reading_progress_user_updated`. Sem recriar `users`: recriar apagaria as sessões em cascata | sim (`downgrade` remove tabela e coluna) |
| `0005` | Tabela `series` (CHECK de `metadata_state`; `folder_rel_path` único; `ix_series_sort_title`); `items.series_id` (FK `ON DELETE SET NULL`, `ix_items_series_id`) e `items.chapter_number` por `ALTER ADD COLUMN`; backfill idempotente (uma série por pasta pai, uma avulsa por item na raiz). Sem recriar `items` (recriar apagaria o progresso) | sim (remove índice, colunas e tabela; itens e progresso intactos) |
| `0006` | `series.source_url`, `series.metadata_checked_at`, `series.title_original` por `ALTER ADD COLUMN` | sim (remove as três colunas) |
| `0007` | `series.description_origin` (CHECK: source, translated, manual) e `description_source_name`/`description_source_url` por `ALTER ADD COLUMN`; backfill de descrições da versão anterior (com fonte: `source`; sem fonte: `manual`) | sim (remove as três colunas) |

## Índices e restrições (estado final após 0004)

| Tabela | Índice ou restrição |
|---|---|
| users | `ux_users_username_lower` (único em `lower(username)`); `ck_users_role` (admin, user); `ck_users_theme_pref` (system, light, dark); `ck_users_reading_direction` (rtl, ltr, vertical) |
| refresh_tokens | `token_hash` único; `ix_refresh_tokens_user_id`; `ix_refresh_tokens_family_id`; `ix_refresh_tokens_expires_at` |
| login_attempts | `ck_login_attempts_scope`; `ix_login_attempts_lookup` (scope, key_hash, attempted_at); `ix_login_attempts_attempted_at` |
| audit_log | `ix_audit_log_at`; `ix_audit_log_event_at` (event, at); `ix_audit_log_user_id` |
| items | `rel_path` único; `ck_items_type` (manga, book, pdf); `ck_items_page_count` (≥ 0); `ix_items_type`; `ix_items_added_at` |
| reading_progress | PK `(user_id, item_id)`; `ck_reading_progress_locator` (≥ 0); `ck_reading_progress_percent` (0 a 100); `ix_reading_progress_user_updated` (user_id, updated_at DESC); FKs com CASCADE |
| series | `folder_rel_path` único; `ck_series_metadata_state` (none, matched, manual, not_found); `ck_series_description_origin` (source, translated, manual); `ix_series_sort_title` (sort_title, id) |
| items (série) | `ix_items_series_id`; `series_id` com FK `ON DELETE SET NULL` |

## Conexão SQLite (`adapters/persistence/db.py`, em toda conexão)

| Pragma | Valor |
|---|---|
| `journal_mode` | WAL |
| `foreign_keys` | ON |
| `busy_timeout` | 5000 ms |
| `synchronous` | NORMAL |

`hide_parameters=True`: valores ligados não aparecem em erro do SQLAlchemy. Erro de driver vira `DataAccessError` genérico (`from None`).

## Diferenças em relação ao PLANO §4

| Tema | PLANO §4 | Implementado |
|---|---|---|
| Identificador da conta | `email` | `username` (ADR 0007) |
| Campos extras de User | — | `is_active`, `updated_at`, `password_changed_at`, `reading_direction` |
| Item | `path_rel`, `cover`, `added_at` | `rel_path`; sem `cover` (a capa é a primeira página: `has_cover` = `page_count > 0`); inclui `size`, `mtime_ns`, `format`, `page_count`, `missing` |
| Session | tabela `Session` | sessão é a família de `refresh_tokens` (`family_id`); sem tabela própria |
| ReadingProgress | `(user_id, item_id, locator, percent, device_id, updated_at, finished)` | igual; `percent` e `finished` são derivados no servidor (ADR 0013) |
| Series | `Series` com capítulos como tabela própria | série por pasta (`series`) com capítulos em `items` (ADR 0014) |
| Conflito entre dispositivos | vence o maior `updated_at` | último a gravar vence (ADR 0013); o servidor não compara timestamps do cliente |

## Regras

| Tema | Regra | Estado |
|---|---|---|
| Username | 3–64 caracteres, `[a-z0-9._-]`, início alfanumérico, minúsculas; único sem caixa | implementado |
| Token | Só o SHA-256 do refresh é gravado; access é JWT (não gravado) | implementado |
| Hash de senha | Argon2id em `password_hash`; nunca em log, `repr` ou auditoria | implementado |
| Chaves de tentativa | IP e conta só como HMAC-SHA256 truncado (16 hex) por escopo | implementado |
| Auditoria | Sem senha, token, hash, IP ou username em claro; `detail` > 512 bytes vira `{"truncated": true}` | implementado |
| Caminho | `rel_path` relativo; caminho absoluto nunca vem do cliente; resolução só em `LocalStorage` | implementado |
| Itens ausentes | `missing = true` some de `get`, `list` e `search`; reaparecer no scan mantém o id | implementado |
| Isolamento | Toda consulta de dado de usuário filtra por `user_id` do token (progresso, preferências, prateleira). A biblioteca é global | implementado (progresso e preferências); biblioteca não é por usuário |
| Progresso | `locator` entre 0 e `page_count - 1` do item; `percent = (locator + 1) / page_count * 100`; `finished` = última página | implementado |
| Progresso e item ausente | Item marcado como ausente: progresso não aparece em "continuar lendo" e `PUT` responde 404; progresso não é apagado | implementado |
| Remoção de item | Apaga o progresso (CASCADE) | implementado |
| Remoção de usuário | Apaga progresso e sessões (CASCADE) | implementado |
| Preferências | Duas colunas com check; `PUT` grava as duas (objeto completo) | implementado |
| Locator | manga/PDF = índice da página; EPUB = CFI | manga implementado; EPUB planejado (Fase 4) |
| Conflito entre dispositivos | Último a gravar vence; `updated_at` do servidor | implementado (ADR 0013) |
| Série | Chave é a pasta pai (`folder_rel_path`); renomear pasta cria série nova (limitação, ADR 0014) | implementado |
| Ordem de série | `sort_title` = caixa baixa com cada bloco de dígitos preenchido a 12 posições; listagem por `(sort_title, id)` | implementado (ADR 0014) |
| Ordem de capítulo | `chapter_number` primeiro (sem número, no fim), depois ordem natural do nome, depois id | implementado (ADR 0014) |
| Metadado manual | `metadata_state = manual` nunca é sobrescrito por enriquecimento automático; a escrita confere o estado atual | implementado (REG-021) |
| Estados de metadado | none → matched (fonte) ou not_found (sem casamento seguro; reavaliado após 7 dias); manual (admin) | implementado (ADR 0015) |
| Atribuição | `description_origin` e `description_source_*` dizem de quem é o texto; tradução marcada como `translated` | implementado (ADR 0015) |
| Visibilidade de série | Série só aparece com pelo menos um capítulo ativo (`missing = false`); item ausente sai da série e mantém `series_id` | implementado |
| Série apagada | `items.series_id` vira nulo (`ON DELETE SET NULL`); progresso não é apagado | implementado (FK) |
