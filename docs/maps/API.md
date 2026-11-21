# API

Base: `/api/v1`. Estado: 2026-11-21. Fonte: `backend/app/api/`. Manual: OpenAPI, Swagger e ReDoc **desligados** (`backend/app/main.py`: `docs_url`, `redoc_url`, `openapi_url` = None). `redirect_slashes=False`: barra final não redireciona (404).

Fora de `/api`: a SPA (`api/spa.py`, ver abaixo), só quando `FRONTEND_DIST_DIR` está definido.

## Rotas

| Método | Caminho | Auth | Papel | Sucesso | Erros | CSRF | Consumido por (frontend) | Arquivo |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/v1/health` | não | — | 200 `{"status":"ok"}` | — | não | — (healthcheck da imagem) | `api/health.py` |
| GET | `/api/v1/auth/csrf` | não | — | 204 + cookie `csrf_token` | — | não | `shared/api-client` (antes da 1ª escrita) | `api/auth.py` |
| POST | `/api/v1/auth/login` | não | — | 200 `UserOut` + cookies de sessão | 401 credenciais; 422 esquema; 429 bloqueio (`Retry-After`); 503 ocupado (`Retry-After: 1`) | sim | `shared/session` (`postLogin`) | `api/auth.py` |
| POST | `/api/v1/auth/refresh` | cookie `refresh_token` | — | 204 + cookies novos | 401 (apaga os cookies); 429 | sim | `shared/api-client` (refresh compartilhado) | `api/auth.py` |
| POST | `/api/v1/auth/logout` | cookies (opcional) | — | 204 (sempre) + apaga cookies | 429 | sim | `shared/session` (`postLogout`) | `api/auth.py` |
| GET | `/api/v1/auth/me` | access | usuário | 200 `UserOut` | 401 | não | `shared/session` (`fetchMe`) na carga | `api/auth.py` |
| POST | `/api/v1/auth/change-password` | access | usuário | 204 + cookies novos | 401; 403 senha atual errada; 422 política ou igual à atual; 429 bloqueio; 503 ocupado | sim | `features/settings` (`postChangePassword`) | `api/auth.py` |
| GET | `/api/v1/items` | access | usuário | 200 `ItemListOut` | 401; 422 query inválida | não | — (sem uso no frontend; a biblioteca usa `/series`) | `api/items.py` |
| GET | `/api/v1/items/{item_id}` | access | usuário | 200 `ItemOut` | 401; 404 | não | `shared/items` (`getItem`) | `api/items.py` |
| GET | `/api/v1/items/{item_id}/pages/{n}` | access | usuário | 200 imagem; 304 | 401; 404; 422; 503 (`Retry-After: 1` se ocupado) | não | `shared/items` (`pageUrl`) em `<img>` | `api/items.py` |
| GET | `/api/v1/items/{item_id}/cover` | access | usuário | 200 imagem; 304 | 401; 404 (sem capa); 422; 503 | não | `shared/items` (`coverUrl`) em `<img>` (só `ContinueReading`) | `api/items.py` |
| GET | `/api/v1/items/{item_id}/book` | access | usuário | 200 `BookOut` (título, autores, capítulos, sumário) | 401; 404 (id inválido, item ausente ou não é livro); 503 | não | `shared/items` (`getBook`) no leitor EPUB | `api/books.py` |
| GET | `/api/v1/items/{item_id}/book/chapters/{n}?theme=&size=` | access | usuário | 200 `text/html` sanitizado (ETag); 304 | 401; 404 (`n` não numérico ou fora do livro); 422 `theme` ou `size` fora da lista; 503 | não | `shared/items` (`bookChapterUrl`) como `src` do `iframe sandbox` | `api/books.py` |
| GET | `/api/v1/items/{item_id}/book/res/{rid}` | access | usuário | 200 imagem; 304 | 401; 404; 503 | não | HTML do capítulo (`<img>` por `rid`) | `api/books.py` |
| GET | `/api/v1/series` | access | usuário | 200 `SeriesListOut` | 401; 422 query inválida | não | `shared/series` (`listSeries`) na biblioteca | `api/series.py` |
| GET | `/api/v1/series/{series_id}` | access | usuário | 200 `SeriesOut` (capítulos, progresso do usuário, `continue`, `kind`) | 401; 404 série desconhecida ou sem capítulo ativo; 503 | não | `shared/series` (`getSeries`) em `/serie/:id` e no leitor | `api/series.py` |
| GET | `/api/v1/series/{series_id}/cover` | access | usuário | 200 imagem; 304 | 401; 404 (sem capa legível); 422; 503 | não | `shared/series` (`seriesCoverUrl`) em `<img>` | `api/series.py` |
| GET | `/api/v1/series/{series_id}/metadata/candidates?q=` | access, admin | admin | 200 `CandidateListOut` | 401; 403; 422 `q` longo; 429 (10 por minuto por usuário, `Retry-After`); 502 fonte indisponível | não | `features/series` (`MetadataPanel`, só por ação do admin) | `api/series.py` |
| POST | `/api/v1/series/{series_id}/metadata/select` | access, admin | admin | 200 `SeriesMetadataOut` | 401; 403; 404; 422 esquema; 502 | sim | `features/series` (`selectMetadata`) | `api/series.py` |
| PUT | `/api/v1/series/{series_id}/metadata` | access, admin | admin | 200 `SeriesMetadataOut` (estado `manual`) | 401; 403; 404; 422 | sim | `features/series` (`saveMetadataText`) | `api/series.py` |
| DELETE | `/api/v1/series/{series_id}/metadata` | access, admin | admin | 200 `SeriesMetadataOut` (volta a `none`; apaga capa baixada) | 401; 403; 404 | sim | `features/series` (`removeMetadata`) | `api/series.py` |
| POST | `/api/v1/library/enrich?force=` | access, admin | admin | 202 `EnrichStatusOut` (em segundo plano) | 401; 403; 409 já em execução; 503 metadados desligados | sim | `features/library` (`EnrichControl`, "Atualizar metadados") | `api/library.py` |
| GET | `/api/v1/library/enrich/status` | access, admin | admin | 200 `EnrichStatusOut` | 401; 403 | não | `features/library` (`useEnrich`, consulta periódica) | `api/library.py` |
| POST | `/api/v1/library/scan` | access, admin | admin | 202 `ScanStatusOut` (scan em segundo plano) | 401; 403; 409 já em execução; 503 biblioteca indisponível | sim | — (CLI e API; sem tela) | `api/library.py` |
| GET | `/api/v1/library/scan/status` | access, admin | admin | 200 `ScanStatusOut` | 401; 403; 503 biblioteca indisponível | não | — | `api/library.py` |
| GET | `/api/v1/progress/continue` | access | usuário | 200 `ContinueListOut` | 401; 422 `limit` < 1; 503 | não | `shared/progress` (`listContinue`, limite 12) na biblioteca | `api/progress.py` |
| GET | `/api/v1/progress/{item_id}` | access | usuário | 200 `ProgressOut` | 401; 404 (sem progresso ou item inexistente/ausente); 503 | não | `shared/progress` (`getProgress`; 404 vira `null`) nos leitores | `api/progress.py` |
| PUT | `/api/v1/progress/{item_id}` | access | usuário | 200 `ProgressOut` | 401; 404 item inexistente ou ausente; 422 esquema ou locator fora do item; 503 | sim | `shared/progress` (`putProgress`, `keepalive` ao ocultar a página) | `api/progress.py` |
| DELETE | `/api/v1/progress/{item_id}` | access | usuário | 204 (idempotente) | 401; 503 | sim | `shared/progress` (`deleteProgress`) | `api/progress.py` |
| GET | `/api/v1/me/preferences` | access | usuário | 200 `PreferencesOut` | 401; 503 | não | `shared/preferences` (`fetchPreferences`) na carga | `api/preferences.py` |
| PUT | `/api/v1/me/preferences` | access | usuário | 200 `PreferencesOut` | 401; 422 valor fora das opções; 503 | sim | `shared/preferences` (`savePreferences`, objeto completo) | `api/preferences.py` |
| GET | `/api/v1/system/version` | access | qualquer usuário | 200 `PublicVersionOut` (usuário comum) ou `AdminVersionOut` (admin) | 401 | não | `shared/system` (`getVersion`) na carga e a cada 30 min com a aba visível | `api/system.py` |
| POST | `/api/v1/system/update/check` | access, admin | admin | 200 `AdminVersionOut` (consulta forçada) | 401; 403; 429 `Too many requests` (3 por minuto por admin, `Retry-After`) | sim | `shared/system` (`checkForUpdate`) em `features/settings` | `api/system.py` |
| POST | `/api/v1/system/update` | access, admin | admin | 202 `UpdateAcceptedOut` (webhook enviado; atualização roda no host) | 401; 403; 409 não disponível ou já pedida; 422 tag inválida; 502 webhook falhou; 503 não configurado | sim | `shared/system` (`requestUpdate`) no aviso de versão | `api/system.py` |

Não existe ainda: arquivo PDF (`/items/{id}/file`), leitor PDF, progresso de PDF, criação de conta pela API (só CLI), `PUT`/`DELETE` de itens. EPUB é servido pelas rotas `/book` (capítulos sanitizados, sem arquivo bruto).

## Corpos

| Schema | Campos | Regra |
|---|---|---|
| `LoginRequest` | `username` (1–128), `password` (1–1024) | strict, `extra=forbid` |
| `ChangePasswordRequest` | `current_password`, `new_password` (1–1024) | strict, `extra=forbid` |
| `UserOut` | `id`, `username`, `role`, `theme_pref` | sem hash, sem datas |
| `ItemOut` | `id`, `type` (manga, book, pdf), `title`, `format`, `page_count`, `added_at`, `has_cover` | sem `rel_path` nem nome de arquivo |
| `ItemListOut` | `items`, `limit`, `offset`, `has_more` | `limit` efetivo: 1–100 (acima é limitado, não rejeitado) |
| `ScanStatusOut` | `state` (idle, running, finished, failed), `processed`, `total`, `started_at`, `finished_at`, `added`, `updated`, `unchanged`, `removed`, `skipped`, `error_count`, `errors_by_reason` | só contagens e nomes de classe de erro |
| `BookOut` | `title`, `authors` (lista), `language`, `chapters` (`ChapterOut`: `index`, `title`), `toc` (`TocEntryOut`: `title`, `index`, `anchor`), `has_cover` | sem caminho nem nome interno de arquivo |
| `SaveProgressRequest` | `locator` (inteiro 0 a 2 147 483 647), `device_id` (opcional, `^[A-Za-z0-9_-]{1,64}$`) | strict, `extra=forbid`. Cliente **não** envia `percent` nem `finished` (são rejeitados) |
| `ProgressOut` | `item_id`, `locator`, `percent` (float 0–100), `finished` (bool), `updated_at` (UTC com offset) | `extra=forbid` |
| `ContinueListOut` | `items`: lista de `ContinueItemOut` | — |
| `ContinueItemOut` | `item` (`ItemOut`), `locator`, `percent`, `finished`, `updated_at` | — |
| `PreferencesIn` | `theme` (system, light, dark) e `reading_direction` (rtl, ltr, vertical) **obrigatórias**; `book_font_scale` (80–200, opcional, padrão 100) e `book_theme` (auto, light, dark, sepia; opcional, padrão auto) | strict, `extra=forbid` |
| `PreferencesOut` | `theme`, `reading_direction`, `book_font_scale`, `book_theme` | `extra=forbid` |
| `SeriesListOut` | `items` (`SeriesItemOut`: `id`, `title`, `chapter_count`, `has_cover`, `description` (prévia de até 300 caracteres), `description_lang`, `metadata_state`, `kind` (manga, book, mixed), `progress` (`read_chapters`, `last_item_id`)), `limit`, `offset`, `has_more` | `extra=forbid`; sem caminho |
| `SeriesOut` | `id`, `title`, `description`, `description_lang`, `description_origin` (source, translated, manual, null), `description_source` (`name`, `url` https ou null), `source` (`name`, `url`), `metadata_state`, `kind` (manga, book, mixed), `chapter_count`, `has_cover`, `chapters` (`ChapterOut`: `id`, `title`, `number`, `type` (manga, book, pdf), `page_count`, `progress` (`locator`, `percent`, `finished`, ou null)), `continue` (`item_id`, `locator`, ou null) | `extra=forbid`; nunca `folder_rel_path`, `cover_path` nem URL de capa |
| `SeriesMetadataOut` | `id`, `title`, `description`, `description_lang`, `description_origin`, `description_source`, `source`, `metadata_state`, `cover_downloaded` (bool) | resposta das ações de metadado |
| `CandidateOut` / `CandidateListOut` | `provider` (mangadex, anilist, wikipedia, googlebooks), `external_id`, `title`, `year`, `description`, `cover_available`, `url` (https) / `items` | até 10 candidatos |
| `SelectCandidateRequest` | `provider` (`^[a-z]{1,32}$`), `external_id` (1 a 128, sem `/ \ ? # < > %` nem controles) | strict, `extra=forbid` |
| `ManualMetadataRequest` | `title` (até 200, opcional), `description` (até 4 000, opcional) | strict, `extra=forbid`; estado vira `manual` |
| `EnrichStatusOut` | `state` (idle, running, finished, failed), `started_at`, `finished_at`, `matched`, `not_found`, `skipped`, `errors` (só contagens) | `extra=forbid`; sem URL, host ou detalhe de fonte |
| `PublicVersionOut` | `current` (versão em execução ou `dev`), `update_available` (bool) | `extra=forbid`; nada sobre releases |
| `AdminVersionOut` | `current`, `update_available`, `latest` (`LatestOut` ou null), `checked_at`, `webhook_configured` (bool), `update` (`state`: idle, requested, failed; `tag`; `requested_at`) | `extra=forbid`; a URL e o segredo do webhook nunca aparecem |
| `LatestOut` | `tag`, `version`, `name`, `notes` (texto puro), `published_at`, `url` (página `https://github.com/<repo>/releases/...` do próprio repositório, ou null) | `extra=forbid`; notas e nomes tratados como texto |
| `UpdateRequestIn` | `tag` (2–64; `^v\d{1,9}\.\d{1,9}\.\d{1,9}(-[0-9A-Za-z.]{1,40})?$`) | strict, `extra=forbid`; tem de ser a última release conhecida e mais nova que `current` |
| `UpdateAcceptedOut` | `state` (requested), `tag`, `requested_at` | `extra=forbid` |

Parâmetros de `GET /api/v1/items`: `type` (manga, book, pdf), `q` (até 100 caracteres; busca com `%`, `_` e `\` literais), `limit` (≥ 1), `offset` (0 a 1 000 000). Padrão de `limit`: 50. Ordem: `lower(title)`, `id`.

Parâmetros de `GET /api/v1/series`: `q` (até 100 caracteres), `limit` (≥ 1; padrão 50; acima de 100 é limitado a 100), `offset` (0 a 1 000 000). Ordem: `sort_title`, `id`. Série só aparece com capítulo ativo. `continue` no detalhe é um campo, não uma rota: é o capítulo não concluído mais recente, ou o primeiro capítulo sem progresso depois do último concluído (ADR 0014). `chapter_number` vem do nome do arquivo; capítulos sem número vão para o fim. `kind` é derivado dos capítulos (`manga`, `book` ou `mixed`); não é armazenado.

Parâmetros de `GET /api/v1/items/{id}/book/chapters/{n}`: `theme` (auto, light, dark, sepia; padrão auto), `size` (80 a 200; padrão 100). Validados antes de abrir o arquivo.

Parâmetros de `GET /api/v1/progress/continue`: `limit` (≥ 1; padrão 10; acima de 50 é limitado a 50, não rejeitado). Ordem: `updated_at` decrescente. Exclui concluídos e itens ausentes.

`{item_id}`: UUID canônico em minúsculas; maiúsculas são aceitas e normalizadas; qualquer outra forma é 404. `{n}` de página: só dígitos ASCII, até 9 dígitos; fora da faixa é 404. `{n}` de capítulo e `{rid}` de imagem de livro: só dígitos, até 6; fora disso é 404.

Progresso de mangá e PDF: `percent = (locator + 1) / page_count * 100`; `finished` = `locator` é a última página. Progresso de livro (`type = book`): `locator = capítulo * 10000 + offset_bp`; `percent = (capítulo + offset_bp / 10000) / capítulos * 100`; concluído no último capítulo com `offset_bp ≥ 9000`. Locator de livro fora de um capítulo existente é 422. O servidor grava `updated_at` com o próprio relógio (ADR 0013).

## Erros genéricos (todas as rotas)

| Caso | Status | Corpo | Cabeçalhos extras |
|---|---|---|---|
| Sem sessão válida | 401 | `{"detail":"Not authenticated"}` ou `"Invalid credentials"` (login) | — |
| Não é admin | 403 | `{"detail":"Forbidden"}` | — |
| CSRF ou Origin rejeitado | 403 | `{"detail":"Forbidden"}` | — |
| Corpo acima de `MAX_BODY_BYTES` (64 KiB) | 413 | `{"detail":"Request body too large"}` | — |
| `Content-Length` inválido | 400 | `{"detail":"Invalid Content-Length"}` | — |
| Limite de taxa (global ou estrito) | 429 | `{"detail":"Too many requests. Try again later."}` | `Retry-After` |
| Bloqueio de login | 429 | `{"detail":"Too many requests. Try again later."}` (idêntico ao limite) | `Retry-After` (segundos restantes) |
| Validação de entrada | 422 | `{"detail":"Invalid request"}` (não ecoa a entrada) | — |
| Rota inexistente em `/api` | 404 | `{"detail":"Not Found"}` (padrão do FastAPI; nunca `index.html`) | cabeçalhos de segurança |
| Método não permitido | 405 | padrão do FastAPI | cabeçalhos de segurança |
| Progresso, item ou livro não encontrado | 404 | `{"detail":"Not found"}` | — |
| Ocupado (gate de concorrência) | 503 | `{"detail":"Service busy. Try again later."}` | `Retry-After: 1` |
| Banco ou serviço indisponível (progresso e preferências) | 503 | `{"detail":"Service unavailable"}` | — |
| Biblioteca indisponível | 503 | `{"detail":"Library unavailable"}` | — |
| Limite de busca de metadados (por usuário, 10/min) | 429 | `{"detail":"Too many requests. Try again later."}` | `Retry-After` |
| Limite de consulta forçada de release (por admin, 3/min) | 429 | `{"detail":"Too many requests"}` (rota de sistema usa esta mensagem) | `Retry-After` |
| Fonte de metadados indisponível (sem detalhe de host, URL ou motivo) | 502 | `{"detail":"Metadata source unavailable"}` | — |
| Enriquecimento já em execução | 409 | `{"detail":"An enrichment is already running"}` | — |
| Metadados desligados (`METADATA_ENABLED=false`) | 503 | `{"detail":"Metadata lookup is disabled"}` | — |
| Metadado inválido (edição manual) | 422 | `{"detail":"Invalid request"}` | — |
| Atualização não configurada (webhook ausente) | 503 | `{"detail":"Update is not configured"}` | — |
| Versão pedida não disponível (não é a última release) | 409 | `{"detail":"That update is not available"}` | — |
| Atualização já pedida (dentro de 10 min) | 409 | `{"detail":"An update was already requested"}` | — |
| Webhook de atualização falhou | 502 | `{"detail":"Update request failed"}` (sem URL nem segredo) | — |
| Exceção não tratada | 500 | `{"detail":"Internal Server Error"}` | `Cache-Control: no-store` |

Exceções documentadas à regra genérica (mensagens fixas, sem eco da entrada, só em usuário já autenticado): `change-password` 403 `Current password is incorrect`; `change-password` 422 com a mensagem fixa da política (ex.: `password is too common`).

Mapeamento de erros de biblioteca (`api/errors.py::library_error`, pela classe, nunca pela mensagem):

| Classe | Status |
|---|---|
| `ItemNotFound`, `PageOutOfRange`, `FileNotFoundError` | 404 `Not found` |
| `ResourceBusy` | 503 `Service busy...` + `Retry-After: 1` |
| `LibraryUnavailable`, `DataAccessError`, `OSError` | 503 `Library unavailable` |
| `ScanAlreadyRunning` | 409 `A scan is already running` |
| Demais `DomainError` (corrompido, não suportado, limites, caminho inseguro, opções de livro inválidas) | 422 `Item cannot be read` |
| `ExternalFetchError` (qualquer motivo de fonte) | 502 `Metadata source unavailable` |
| `EnrichAlreadyRunning` | 409 `An enrichment is already running` |
| `MetadataDisabled` | 503 `Metadata lookup is disabled` |
| `InvalidMetadata` | 422 `Invalid request` |
| Outra exceção | não mapeada: 500 genérico |

Séries, metadados e livros também usam `library_error` (`api/errors.py`). Os motivos de falha de fonte (`rate_limited`, `bad_status`, `host_not_allowed`, `too_large` etc.) ficam só no servidor (log de nível info, sem dado do cliente). Rotas de sistema têm mapeamento próprio, descrito na tabela de rotas.

Progresso e preferências não usam `library_error`: mapeiam por exceção de domínio (`ItemNotFound`, `InvalidLocator`, `UserNotFoundError`) e `DataAccessError`.

## CSRF (`api/csrf.py`)

Aplica-se a todo método que não seja GET, HEAD ou OPTIONS sob `/api`, inclusive login. Fora de `/api` não se aplica (a SPA só serve GET e HEAD). Ordem: `Origin` repetido → 403; `Origin` presente deve ser permitido; sem `Origin`, `Sec-Fetch-Site` deve ser `same-origin` ou `none`; sem ambos, `Referer` deve ser permitido. Depois: cabeçalho `X-CSRF-Token` e cookie `csrf_token` iguais, e assinatura válida. Origem permitida = `ALLOWED_ORIGINS` (exata); vazia = mesma origem (compara com `Host`). Rejeição sempre 403 genérico.

## CORS

Só com `ALLOWED_ORIGINS` não vazio. Métodos: GET, POST, PUT, PATCH, DELETE. Cabeçalhos: `Content-Type`, `Accept`, `X-CSRF-Token`. Credenciais sempre ligadas. Com a SPA na mesma origem, não há CORS.

## Cookies

| Cookie | Path | HttpOnly | Secure | SameSite | Max-Age | Emitido por | Apagado por |
|---|---|---|---|---|---|---|---|
| `access_token` | `/api` | sim | `COOKIE_SECURE` | Strict | `ACCESS_TOKEN_TTL_SECONDS` (900) | login, refresh, change-password | refresh 401, logout |
| `refresh_token` | `/api/v1/auth` | sim | `COOKIE_SECURE` | Strict | restante da sessão (≤ 30 dias, ≤ 90 dias absolutos) | login, refresh, change-password | refresh 401, logout |
| `csrf_token` | `/` | não (JS lê) | `COOKIE_SECURE` | Strict | `REFRESH_TOKEN_TTL_SECONDS` | `GET /auth/csrf` (reusa o válido) | não é apagado |

Tokens nunca vão no corpo da resposta. Sem prefixo `__Host-` (ADR 0008).

## Cache

| Resposta | `Cache-Control` | `Pragma` |
|---|---|---|
| Todo `/api`, exceto as linhas abaixo | `no-store` | `no-cache` |
| `GET /api/v1/items/{uuid}/pages/{n}` e `/cover`, `GET /api/v1/series/{uuid}/cover` e `GET /api/v1/items/{uuid}/book/chapters/{n}`, status 200 ou 304 | `private, max-age=3600` | ausente |
| `GET /api/v1/items/{uuid}/book/res/{rid}`, status 200 ou 304 | `private, max-age=3600` (regra de imagem) | ausente |
| Qualquer erro das rotas acima | `no-store` | `no-cache` |
| SPA: `assets/*` (nome com hash) | `public, max-age=31536000, immutable` | — |
| SPA: `index.html`, `sw.js`, `workbox-*.js`, `manifest.webmanifest` e demais arquivos | `no-cache` | — |
| SPA: fallback (`index.html` servido em outra URL) | `no-cache` | — |
| SPA: 404 e 405 | `no-store` | — |

Marcador interno `x-internal-cache-class` nunca sai da aplicação (ADR 0010). Cabeçalhos de segurança em toda resposta HTTP, inclusive da SPA: `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (câmera, microfone, geolocalização e pagamento negados) — `api/security_headers.py` (ADR 0006, ADR 0012).

CSP (explícita, sem `unsafe-inline` nem `unsafe-eval`): `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.

Exceção de CSP do capítulo de livro (ADR 0017): só para `GET /api/v1/items/<uuid>/book/chapters/<n>` com status 200 e marcador interno da rota. Substitui a CSP global por: `default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'`. Nenhum outro caminho recebe essa CSP.

## Cabeçalhos de imagem

`Content-Type` pelos bytes do arquivo (jpeg, png, webp, gif, avif); outro tipo é 422. `ETag` = SHA-256 do conteúdo entre aspas; `If-None-Match` (fraco) → 304 sem corpo, ainda exigindo sessão. `Content-Disposition: inline`, `X-Content-Type-Options: nosniff`.

## SPA (`api/spa.py`, fora de `/api`)

Ativa só com `FRONTEND_DIST_DIR` (imagem: `/app/static`). Responde só GET e HEAD (outros métodos: 405). Caminhos com `..`, dotfile, `\`, `:`, NUL ou segmento vazio: 404. Symlink não é seguido. `Range` é atendido pelo `FileResponse` (206), testado em `security/test_spa.py`. Não consome o rate limit da API. Caminho sem extensão que não existe recebe `index.html`; com extensão, 404 (texto `Not Found`).

## CLI (não é HTTP, referência)

`python -m app.cli`: `migrate`, `create-user <nome> [--admin]`, `reset-password <nome>`, `deactivate-user <nome>`, `list-users`, `scan`, `enrich [--series <uuid>] [--force]`, `purge`. Senha só por `getpass`. Ver `infra/AGENTS.md` (primeiro admin) e `docs/DEPLOY.md`.
