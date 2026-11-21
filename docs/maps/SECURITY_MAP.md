# SECURITY_MAP

Estado: 2026-11-21. Fonte de requisitos: `docs/PLANO.md` §6. Decisões: ADR 0002 (segurança no app), ADR 0005 (padrões fechados), ADR 0006 (cabeçalhos sobrepõem a rota), ADR 0007 (usuários, SQLite, Argon2id), ADR 0008 (sessão e CSRF), ADR 0009 (lockout), ADR 0010 (exceção de cache de imagem), ADR 0011 (proxy e IP real), ADR 0012 (backend serve o frontend; resolve M5), ADR 0013 (progresso e preferências no servidor), ADR 0014 (séries por pasta), ADR 0015 (metadados de fontes públicas; exceção autorizada à regra 7 em 2026-11-20), ADR 0016 (capas), ADR 0017 (CSP e iframe do capítulo EPUB; **Proposto**), ADR 0018 (oitavo host de release e webhook; **Proposto**). Auditoria: `docs/security/` (12 findings; 11 `fixed`, 1 `open`; nenhum `verified`; estado em `REMEDIATION_QUEUE.md`). Testes por arquivo: `TEST_MAP.md`.

## Implementado

### Sessão e autenticação

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Senha em claro ou em hash fraco | Argon2id (t=3, m=64 MiB, p=4); só o hash vai ao banco | `adapters/security/argon2_hasher.py`, `persistence/user_repository.py` | `unit/test_argon2_hasher.py`, `security/test_password_storage.py` | Implementado |
| Enumeração por resposta ou tempo | Mesmo 401, corpo, cabeçalhos e custo para conta inexistente, inativa ou senha errada (hash dummy) | `services/auth_service.py`, `argon2_hasher.py` | `security/test_login_bruteforce.py` (`test_lockout_is_identical…`, `test_response_time…`), `unit/test_auth_service.py` | Implementado |
| Senha fraca | Política: 12–128; diferente do username; username (≥ 3) não contido nem invertido; 20 senhas comuns; ≥ 5 distintos; bloco repetido fraco; sequências de alfabeto, dígitos e teclado. Mensagens fixas, sem eco | `domain/password_policy.py` | `unit/test_password_policy.py`, `regression/test_reg_012…` | Implementado (denylist grande não feita, FIND-007) |
| Senha só em `getpass`; nunca em argumento ou saída | CLI | `cli.py` | `integration/test_cli.py` | Implementado |
| Cadastro público | Não existe. Conta só pela CLI (`create-user`); sem rota de registro nem de "esqueci a senha" | `cli.py` | `integration/test_cli.py` | Implementado (CLI); endpoint admin planejado |
| Token em JavaScript (XSS) | Cookies `HttpOnly`; tokens nunca no corpo; ESLint bloqueia `localStorage`/`sessionStorage` | `api/auth.py`, `frontend/eslint.config.js` | `security/test_cookies_and_cache.py`, `frontend/tests/unit/eslint-rules.test.ts` | Implementado |
| Cookie sem atributos corretos | `access_token` Path=/api; `refresh_token` Path=/api/v1/auth; `csrf_token` Path=/ legível; todos `SameSite=Strict`, host-only, `Secure` por `COOKIE_SECURE` | `api/auth.py` | `security/test_cookies_and_cache.py` | Implementado; `Secure` verificado no `Set-Cookie` (HTTPS real fora de escopo) |
| Access token forjado, `alg:none`, algoritmo trocado | HS256 fixo; chave HKDF própria; `exp`, `nbf`, `sub`, `sid`, `jti`, `iat` obrigatórios; tipos checados; ≤ 2048 caracteres | `adapters/security/jwt_tokens.py`, `core/keys.py` | `security/test_jwt_tokens.py`, `security/test_session_attacks.py` | Implementado |
| Access válido após revogação ou desativação | Validado no banco a cada requisição: usuário ativo, família não revogada, `iat` ≥ última troca de senha | `services/auth_service.py` (`current_user`) | `security/test_session_attacks.py`, `unit/test_auth_service.py` | Implementado |
| Refresh roubado ou reutilizado | Rotação atômica; reuso fora da janela (10 s) revoga a família e audita; só o hash SHA-256 fica no banco | `services/auth_service.py`, `persistence/refresh_token_repository.py` | `unit/test_auth_service.py`, `integration/test_auth_repositories.py`, `integration/test_auth_api.py` | Implementado (ladrão dentro da janela não é detectado, FIND-005) |
| Corrida de dois refresh derruba a sessão | Janela `REFRESH_REUSE_GRACE_SECONDS` (padrão 10, máx. 60) emite sessão irmã | `services/auth_service.py` | `regression/test_reg_010_…` | Implementado (FIND-005) |
| Sessão que não expira | TTL de refresh 30 dias; teto absoluto da sessão 90 dias, mesmo com rotação | `services/auth_service.py` | `unit/test_auth_service.py` (`test_session_has_an_absolute_lifetime…`) | Implementado |
| Troca de senha não invalida sessões | Revoga todas as famílias do usuário; `iat` anterior à troca é recusado; reset pelo CLI e desativação valem na hora | `services/auth_service.py`, `services/user_service.py` | `integration/test_auth_api.py`, `unit/test_auth_service.py` | Implementado |
| Token de sessão alheia | `sid` precisa pertencer ao `sub` no banco | `services/auth_service.py` | `security/test_session_attacks.py` (`test_session_of_another_user…`) | Implementado |
| Logout que não revoga | Revoga a família (por refresh ou access); idempotente | `services/auth_service.py`, `api/auth.py` | `integration/test_auth_api.py` | Implementado |
| Token bruto no banco | Só SHA-256 de refresh; access não é gravado | `persistence/refresh_token_repository.py` | `integration/test_auth_repositories.py` (`test_keys_are_stored_hashed…`) | Implementado |

### Anti brute force (ADR 0009)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Adivinhar senha de uma conta | Bloqueio por par (IP, conta): 5 falhas; janela 900 s; bloqueio 300 s dobrando até 3600 s | `services/auth_service.py`, `domain/lockout.py` | `security/test_login_bruteforce.py`, `unit/test_lockout.py` | Implementado |
| Ataque distribuído contra uma conta | Bloqueio por conta em todos os IPs: 15 falhas; só para IPs sem login recente (30 dias) | `services/auth_service.py` | `security/test_login_bruteforce.py` (`test_distributed_attack…`) | Implementado; **risco residual FIND-009 (aberto)** |
| Spray de usernames | Bloqueio por IP: 20 falhas, qualquer conta | `services/auth_service.py` | `unit/test_auth_service.py` (`test_changing_username…`) | Implementado |
| Vítima trancada pelo atacante | Um IP sozinho não atinge o limite da conta para todos (fórmula validada no startup) | `core/config.py` (`max_failures_from_one_address`) | `security/test_settings.py` (`test_one_address…`, `test_formula…`) | Implementado |
| Corrida: N tentativas simultâneas passam do limite | Verificação e reserva de falha sob trava antes do Argon2; libera só em sucesso ou aborto | `services/auth_service.py` (`_begin_attempt`) | `regression/test_reg_009_…` | Implementado (FIND-004); atômico só por processo |
| Senha correta burla bloqueio | Bloqueio é verificado antes da senha | `services/auth_service.py` | `unit/test_auth_service.py` (`test_lock_check_happens_before…`) | Implementado |
| Variação de caixa ou espaço no username | Chave normalizada | `services/auth_service.py` (`_account_key`) | `unit/test_auth_service.py`, `security/test_login_bruteforce.py` | Implementado |
| Log de tentativas com dado claro | Chaves em HMAC truncado por escopo; auditoria sem IP ou username | `adapters/persistence/login_attempt_store.py`, `services/auth_service.py` | `integration/test_auth_repositories.py`, `security/test_login_bruteforce.py` (`test_attempts_table…`) | Implementado |
| Auditoria inflada por tentativas bloqueadas | `login.locked` no máximo 1 por IP a cada 60 s (tabela limitada a 10 000); purga isolada, também em login falho e refresh | `services/auth_service.py`, `cli.py` (`purge`) | `regression/test_reg_011_…` | Implementado (FIND-006) |
| Falha de purga derruba login | Purga isolada; log genérico; nova tentativa em 5 min | `services/auth_service.py` | `regression/test_reg_011_…` (`test_a_failing_purge…`) | Implementado |
| Flood de login esgota as threads da API | Argon2 com 2 slots, 8 em espera por até 1 s; excedente recebe 503 + `Retry-After` sem registrar falha | `adapters/security/argon2_hasher.py`, `adapters/gate.py` | `regression/test_reg_007_…` | Implementado (FIND-002); **reverificação ao vivo pendente** |

### CSRF, CORS, origem

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| CSRF em toda escrita sob `/api` | Cookie `csrf_token` assinado (nonce + HMAC com subchave); cabeçalho `X-CSRF-Token` igual ao cookie; aplica-se a login, refresh, logout, troca de senha, scan, `PUT`/`DELETE` de progresso, `PUT` de preferências, enriquecimento, metadados e atualização (`check` e `update`). Fora de `/api` não há escrita | `api/csrf.py` | `security/test_csrf.py` (23 funções), `security/test_progress_authz.py` (`test_writes_require_csrf`), `security/test_update_api.py` | Implementado |
| Origem estrangeira | `Origin` deve ser permitido; sem `Origin`, `Sec-Fetch-Site` ou `Referer` permitido; `Origin` repetido → 403 | `api/csrf.py` | `security/test_csrf.py`, `regression/test_reg_015_…` (`test_5_…`) | Implementado |
| Token CSRF de outra sessão ou plantado | Assinatura HMAC com subchave; token forjado com a chave crua é recusado | `api/csrf.py`, `core/keys.py` | `security/test_csrf.py` (`test_token_made_with_the_raw_secret…`) | Implementado (token não é amarrado à sessão, FIND-010 item 4) |
| CORS permissivo com credenciais | Lista exata (`ALLOWED_ORIGINS`), sem `*`, sem caminho nem barra final; CORS só existe se a lista não estiver vazia. Na imagem, a SPA é mesma origem e CORS não é necessário | `core/config.py`, `main.py` | `security/test_rate_limit_and_cors.py` | Implementado |
| Redirect com `Host` refletido | `redirect_slashes=False`; barra final dá 404 sem `Location` | `main.py` | `regression/test_reg_013_…` | Implementado (FIND-008) |

### Limites, concorrência e entrada

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Flood por IP | Balde de fichas por IP, só em `/api`: global 600/min (burst 200); estrito 20/min (burst 10) somado ao global **só** em `login`, `refresh`, `logout` e `change-password`; `me` e `csrf` contam só no global; 429 idêntico ao bloqueio de login; em memória | `api/rate_limit.py`, `adapters/security/rate_limiter.py` | `security/test_rate_limit_and_cors.py`, `unit/test_rate_limiter.py`, `regression/test_reg_019_…` | Implementado (uma worker; limite multiplica com réplicas) |
| Estouro do balde estrito por leitura normal | `me` e `csrf` (chamados a cada carga) não consomem o balde de login | `api/rate_limit.py` (`STRICT_AUTH_PATHS`) | `regression/test_reg_019_…` | Implementado |
| Flood do check de release | 3 consultas forçadas por minuto por admin; 429 com `Retry-After`; a consulta preguiçosa tem cache de `UPDATE_CHECK_INTERVAL_HOURS` e single-flight | `composition.py` (`update_check_limiter`), `api/system.py`, `services/update_service.py` | `security/test_update_api.py`, `unit/test_update_service.py` | Implementado |
| Rate limit por rota de páginas e scan | Não existe. Páginas e scan só têm o limite global e a concorrência do gate | — | — | **Pendente** (decisão do dono) |
| IP forjado por cabeçalho | App ignora `X-Forwarded-For`, `X-Real-IP` e `Forwarded`; IP vem do uvicorn (`FORWARDED_ALLOW_IPS`) | `api/http_utils.py`, `infra/entrypoint.sh` | `security/test_rate_limit_and_cors.py` (`test_forwarded_headers_are_ignored…`) | Implementado; ver risco residual de proxy |
| Rotação de IPv6 dentro do /64 | Chave normalizada para o /64 | `api/http_utils.py` | `security/test_rate_limit_and_cors.py` | Implementado |
| Corpo grande ou sem `Content-Length` | 413 por cabeçalho e por bytes recebidos (64 KiB); 400 para `Content-Length` inválido | `api/body_limit.py` | `security/test_body_limit.py`, `regression/test_reg_005_…` | Implementado |
| Mass assignment e tipos errados | Schemas `extra=forbid` e `strict`; 422 genérico sem eco da entrada | `api/auth_schemas.py`, `api/progress_schemas.py`, `api/errors.py` | `integration/test_auth_api.py` (`test_login_validation_errors_do_not_echo_input`), `integration/test_progress_api.py` (`test_invalid_bodies_are_a_generic_422`) | Implementado |
| Leitura de página cara ou sem limite | Índice de arquivo em cache LRU (64); gate de 4 leitores e 16 em espera (2 s); 503 + `Retry-After` | `adapters/extractors/_common.py`, `cbz.py`, `folder.py` | `regression/test_reg_008_…` | Implementado (FIND-003); pico de memória 4 × 64 MiB, sem streaming |
| Scan que apaga o catálogo | Não marca ausente com erro de caminhada, erro de banco ou raiz vazia com itens | `services/scan.py`, `adapters/persistence/item_repository.py` | `regression/test_reg_017_…` | Implementado (FIND-012) |
| Scan concorrente | Uma varredura por vez; 409 para a segunda | `services/scan_runner.py` | `integration/test_library_api.py` (`test_second_scan…`) | Implementado |
| Erro interno com detalhe | 500 genérico com cabeçalhos; `ValidationError` sem o valor de `SECRET_KEY`; erro de banco sem SQL nem parâmetros | `api/security_headers.py`, `core/config.py`, `persistence/*` | `security/test_security_headers.py`, `regression/test_reg_001_…`, `security/test_session_attacks.py` | Implementado |
| Erro de biblioteca com caminho | Mapeamento por classe; sem caminho nem nome de arquivo na resposta | `api/errors.py` | `security/test_items_api.py` (`test_extractor_errors_never_leak…`) | Implementado |
| Caminho vindo do cliente | Cliente envia só UUID opaco e número de página; `rel_path` nunca sai da API | `api/items.py`, `api/library_schemas.py` | `security/test_items_api.py` (`test_list_never_exposes_paths`) | Implementado |
| Caminho traversal, absoluto, unidade, nome reservado | `LocalStorage` é o único que resolve; `..`, absoluto, `\`, nomes do Windows, bytes nulos, > 1024 caracteres, > 16 níveis recusados | `adapters/storage/local.py` | `security/test_local_storage.py` (`test_rejects_hostile_paths`, parametrizado) | Implementado |
| Link simbólico ou junction para fora | Rejeita `is_symlink` e `is_junction` reais; não usa o atributo ReparsePoint (OneDrive) | `adapters/storage/local.py` | `security/test_local_storage.py` | Implementado; em Windows os casos de link podem ser pulados |
| SQL injection em busca | Parâmetros ligados; `%`, `_` e `\` escapados no LIKE; NUL não casa | `adapters/persistence/item_repository.py` | `integration/test_item_repository.py` (`test_search_*`) | Implementado |
| Zip bomb (CBZ) | Limites: 10 000 entradas; 4 GiB no total; 64 MiB por página; razão 100 (entradas ≥ 64 KiB); leitura em memória, sem extração em disco | `adapters/extractors/cbz.py`, `domain/library.py` | `security/test_cbz_extractor.py` | Implementado (CBZ) |
| Zip-slip, symlink e criptografia no CBZ | Nome com `..`, absoluto, unidade ou `\` recusado; symlink e criptografado recusados | `adapters/extractors/cbz.py` | `security/test_cbz_extractor.py` | Implementado |
| Arquivo falso como imagem | Bytes mágicos (jpeg, png, webp, gif, avif); extensão não basta; conta de página valida todos os arquivos (pasta e CBZ) | `adapters/extractors/_common.py`, `folder.py` | `security/test_cbz_extractor.py`, `security/test_folder_extractor.py`, `regression/test_reg_016_…` | Implementado |
| Imagem servida com tipo errado | `Content-Type` só dos tipos permitidos; `nosniff`; `Content-Disposition: inline` | `api/items.py` | `security/test_items_api.py` (`test_non_allowed_media_types…`) | Implementado |
| Título ou nome hostil | Controles Unicode e `<` `>` viram espaço; título ≤ 200 caracteres | `domain/library.py` (`sanitize_title`) | `unit/test_library_services.py` | Implementado |
| `ComicInfo.xml` (XXE) | Ignorado; sem parser XML | `adapters/extractors/cbz.py` | inspeção | Implementado (sem leitura) |
| IDs hostis | UUID canônico; formato inválido ou inexistente = 404 genérico (itens, páginas, progresso, livros) | `api/ids.py`, `api/items.py`, `api/progress.py`, `api/books.py` | `security/test_items_api.py` (`test_hostile_ids…`), `security/test_progress_authz.py` (`test_malformed_ids…`), `security/test_book_api.py` | Implementado |

### Progresso e preferências (ADR 0013)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Ler ou alterar progresso de outro usuário (IDOR) | Toda consulta filtra por `user_id` do token; o cliente não envia `user_id` | `adapters/persistence/progress_repository.py`, `api/progress.py` | `security/test_progress_authz.py` (`test_a_user_never_reads_or_changes_another_users_progress`) | Implementado |
| Preferências de outro usuário | `GET`/`PUT` só do próprio usuário; UPDATE dirigido às colunas de preferência (incluindo as de livro) | `api/preferences.py`, `adapters/persistence/preferences_repository.py` | `security/test_progress_authz.py` (`test_preferences_are_per_user`), `integration/test_progress_repository.py`, `integration/test_book_preferences.py` | Implementado |
| Cliente forja `percent`, `finished` ou data | Schema `extra=forbid`; `percent`, `finished` e `updated_at` são calculados no servidor | `api/progress_schemas.py`, `domain/progress.py` | `integration/test_progress_api.py` (`test_client_cannot_send_percent_or_finished`) | Implementado |
| Posição fora do item | `locator` entre 0 e `page_count - 1` (mangá e PDF); livro: capítulo existente e offset < 10 000; fora = 422 genérico, nada gravado | `domain/progress.py`, `services/progress_service.py` | `unit/test_progress_service.py`, `unit/test_book_progress.py`, `integration/test_progress_api.py` | Implementado |
| Corrida de dois aparelhos | Upsert atômico; sem duplicata nem erro; último a gravar vence (ADR 0013) | `adapters/persistence/progress_repository.py` | `integration/test_progress_repository.py` (`test_concurrent_upserts…`) | Implementado; perda de uma escrita concorrente é aceita |
| Progresso sobrevive a item ou usuário removido | Não: CASCADE remove | `adapters/persistence/models.py`, `migrations/0004` | `integration/test_progress_repository.py` (`test_cascade…`) | Implementado |
| Dado de leitura no navegador | Nenhum: `localStorage`/`sessionStorage` proibidos; `indexedDB` só em `shared/offline` (vazio) | `frontend/eslint.config.js` | `frontend/tests/unit/eslint-rules.test.ts` | Implementado |
| Resposta de progresso em cache | `no-store` em toda rota `/api` | `api/security_headers.py` | `security/test_progress_authz.py` (`test_responses_are_no_store…`) | Implementado |
| Abuso de navegação (uma página por toque) | Não limitado por rota; uso normal não consome o balde estrito | `api/rate_limit.py` | `integration/test_progress_api.py` (`test_normal_page_turning_is_not_rate_limited`) | Implementado |

### EPUB: leitura e capítulo em iframe (ADR 0017, proposto)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Script no HTML do livro (XSS) | Sanitização por allowlist de tags e atributos antes de servir; sem `script`, formulário ou manipulador de evento; frame sem `allow-scripts`; CSP do capítulo sem `script-src` (fallback `default-src 'none'`) | `adapters/extractors/_epub_html.py`, `api/security_headers.py` (`BOOK_CHAPTER_CSP`), `frontend/src/features/reader-epub/components/EpubReaderPage.tsx` | `unit/test_epub_html.py`, `security/test_book_chapter_headers.py`, `frontend/tests/unit/reader-epub.test.tsx` | Implementado |
| CSS hostil no capítulo | Filtro por allowlist de propriedades e valores; estilo gerado só com valores validados; `style-src 'unsafe-inline'` só na resposta do capítulo | `adapters/extractors/_epub_css.py` | `unit/test_epub_html.py`, `security/test_epub_extractor.py` | Implementado (risco residual: CSS sem script) |
| Navegação ou carregamento externo pelo capítulo | `img-src 'self'`, `form-action 'none'`, `base-uri 'none'`; links internos viram `?goto=`; links externos não são seguidos pelo frame | `api/security_headers.py`, `_epub_html.py` | `security/test_book_chapter_headers.py` | Implementado |
| Frame com DOM do app | `sandbox="allow-same-origin"` só: sem `allow-scripts`, `allow-forms`, `allow-popups` nem `allow-top-navigation`; vale para os dois pontos de iframe (página e tira vertical) | `EpubReaderPage.tsx`, `EpubStrip.tsx` | `frontend/tests/unit/reader-epub.test.tsx`, `frontend/tests/unit/epub-locator.test.ts` (guarda, 2 iframes), `frontend/tests/unit/reader-epub-vertical.test.tsx` | Implementado (ver risco residual) |
| Imagem do livro com caminho interno | Imagens só por `/book/res/{rid}` com índice numérico; o HTML não traz caminho do arquivo | `adapters/extractors/epub.py`, `services/book.py`, `api/books.py` | `security/test_epub_extractor.py`, `security/test_book_api.py` | Implementado |
| Fonte ou SVG servido | Nunca servidos; SVG não é imagem válida no capítulo | `adapters/extractors/epub.py` | `security/test_epub_extractor.py` | Implementado |
| Livro protegido (DRM) | `META-INF/rights.xml` recusado; criptografia que não seja ofuscação de fonte recusada | `adapters/extractors/epub.py` | `security/test_epub_extractor.py` | Implementado |
| Zip-slip, bomba e XML hostil no EPUB | Leitura por `_epub_safe.py` com limites; caminhos internos resolvidos dentro do pacote | `adapters/extractors/_epub_safe.py` | `unit/test_epub_safe.py`, `security/test_epub_extractor.py` | Implementado |
| Capítulo ou livro de outro usuário | Biblioteca é global; progresso de livro filtra por `user_id` | `api/books.py`, `adapters/persistence/progress_repository.py` | `security/test_book_api.py`, `security/test_progress_authz.py` | Implementado |
| Cache do capítulo após logout | Mesma exceção do ADR 0010: privado, 1 h, só 200/304 | `api/security_headers.py` | `security/test_book_chapter_headers.py` | Implementado; **risco residual: 1 h após logout (FIND-010 item 7)** |

### Cache, cabeçalhos e saída HTTP

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Resposta autenticada em cache | `Cache-Control: no-store` e `Pragma: no-cache` em todo `/api` (inclusive erro, 404, 405, 413, 429, 500) | `api/security_headers.py` | `security/test_cookies_and_cache.py`, `security/test_security_headers.py` | Implementado (ADR 0002, 0006) |
| Cache de imagem além da regra | Exceção estreita: GET 200/304 em página, capa de item, capa de série e imagem de livro → `private, max-age=3600`, escrito pelo middleware (ADR 0010) | `api/security_headers.py`, `api/items.py` | `security/test_cache_exception.py`, `security/test_items_api.py` | Implementado; **risco residual: 1 h após logout (FIND-010 item 7)** |
| Rota relaxa cabeçalho de segurança | Middleware sobrepõe cabeçalhos da rota (ADR 0006); única exceção é a CSP do capítulo EPUB (ADR 0017), só GET 200 do caminho exato | `api/security_headers.py` | `security/test_security_headers.py` (`test_preexisting_security_headers_are_replaced`), `security/test_book_chapter_headers.py` | Implementado |
| Clickjacking, sniffing, referrer, APIs | CSP explícita (ADR 0012): `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`; `nosniff`; `Referrer-Policy: no-referrer`; `Permissions-Policy` | `api/security_headers.py` | `security/test_security_headers.py`, `security/test_spa.py` (`test_security_headers_cover_static_responses`) | Implementado |
| Versão do servidor revelada | `--no-server-header` no uvicorn | `infra/entrypoint.sh` | `regression/test_reg_015_…` (`test_1_…`) | Implementado (FIND-010 item 1) |
| Slowloris e conexões abertas | `--limit-concurrency 100`, `--timeout-keep-alive 5`, `--timeout-graceful-shutdown 20` (por env) | `infra/entrypoint.sh` | `regression/test_reg_015_…` (`test_2_…`) | Parcial: timeout de cabeçalho depende do proxy |
| Docs e OpenAPI expostos | Desligados (`docs_url`, `redoc_url`, `openapi_url` = None) | `main.py` | `security/test_spa.py` (`test_docs_are_not_exposed`) | Implementado |
| Erro da SPA com detalhe | Frontend: erro 429 e 500 genéricos; corpo não-JSON vira `ApiError` | `frontend/src/shared/api-client/` | `frontend/tests/unit/api-client.test.ts` | Implementado (cliente) |

### Servir o frontend (ADR 0012)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Traversal, caminho codificado, NUL, `\`, `:` | Caminho validado antes do disco; resolvido e checado contra a raiz | `api/spa.py` | `security/test_spa.py` (`test_traversal_and_malformed_paths…`, `test_encoded_traversal_through_a_real_client`) | Implementado |
| Dotfiles (`.env`, `.git`) | Segmento com ponto nunca é servido | `api/spa.py` | `security/test_spa.py` (`test_dotfiles_are_never_served`) | Implementado |
| Symlink para fora da pasta | Não segue symlink; raiz resolvida uma vez | `api/spa.py` | `security/test_spa.py` (`test_symlink_out_of_the_root…`, `test_symlinked_root…`) | Implementado; casos de link podem ser pulados no Windows |
| `/api` desconhecido devolvendo a SPA | Só fora de `/api`; `/api/**` desconhecido = JSON 404 | `api/spa.py` | `security/test_spa.py` (`test_unknown_api_path…`) | Implementado |
| Métodos inesperados na SPA | Só GET e HEAD; resto 405 | `api/spa.py` | `security/test_spa.py` (`test_unsafe_methods_outside_api_are_405`) | Implementado |
| Shell ou service worker em cache longo | `index.html`, `sw.js`, `manifest` e fallback: `no-cache`; só `assets/*` (hash no nome) é imutável | `api/spa.py` | `security/test_spa.py` (`test_shell_and_service_worker_are_always_revalidated`, `test_fallback_index_is_never_cached_long`) | Implementado |
| Arquivo estático consome limite da API | Não consome | `api/rate_limit.py` | `security/test_spa.py` (`test_static_files_do_not_consume_the_api_rate_limit`) | Implementado |

### Metadados, saída de rede, capas e texto de fonte (ADR 0015, 0016)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| SSRF: o servidor buscar URL arbitrária | Host só da lista fixa de 8 (não configurável); IP literal, userinfo e porta diferente de 443 recusados; https obrigatório | `adapters/http/safe_gateway.py` (`check_url`, `ALLOWED_HOSTS`) | `security/test_safe_gateway.py`, `security/test_safe_gateway_release.py` | Implementado |
| Redirecionamento para rede interna | Nenhum redirecionamento é seguido; 3xx vira erro | `safe_gateway.py` (`_read`) | `security/test_safe_gateway.py` (`redirect`), `security/test_safe_gateway_release.py` | Implementado |
| DNS que aponta para rede interna (rebinding) | Endereço resolvido tem de ser global (`is_global`); conexão fixada ao IP verificado; TLS verifica o nome do host | `safe_gateway.py` (`_public_address`, `_PinnedHTTPSConnection`) | `security/test_safe_gateway.py` | Implementado |
| Vazamento de dado do usuário ou do servidor | Só título limpo e sinopse pública saem; sem cookie, sem credencial, sem IP do cliente; User-Agent genérico (`BibliotecaPWA/1.0`) | `services/metadata_service.py`, `safe_gateway.py` | `security/test_safe_gateway.py`, `integration/test_metadata_enrich.py` | Implementado |
| Resposta grande, lenta ou de tipo errado | JSON até 1 MiB; imagem até 5 MiB; tipo de mídia por lista; tempo total de 1 a 60 s; POST só para AniList | `safe_gateway.py`, `adapters/metadata/_json.py` | `security/test_safe_gateway.py` | Implementado |
| Excesso de requisições à fonte | Espaçamento de 0,5 s por host; espera acima de 10 s falha em vez de bloquear thread | `safe_gateway.py` (`_pace`, `_penalize`) | `security/test_safe_gateway.py` | Implementado |
| Desligar toda saída | `METADATA_ENABLED=false`: gateway sem socket; enriquecimento responde 503 | `composition.py`, `safe_gateway.py` (`DisabledGateway`), `api/library.py` | `security/test_settings.py`, `integration/test_metadata_enrich.py` | Implementado |
| Caminho de capa vindo da rede, do banco ou do cliente | Nome só `<uuid>` + extensão jpg, png ou webp, gerados pelo servidor; nome lido do banco é validado de novo; symlink nunca seguido | `adapters/storage/cover_store.py` | `security/test_cover_store.py` (`test_only_a_server_uuid…`, `test_a_symlink…`) | Implementado |
| Arquivo que não é imagem gravado ou servido | Bytes mágicos (JPEG, PNG, WebP) antes de gravar e antes de servir; tipo vem dos bytes, não da extensão; máximo 5 MiB | `domain/metadata.py` (`sniff_image`), `cover_store.py` | `security/test_cover_store.py` (`test_the_type_served…`, `test_read_refuses…`) | Implementado |
| Escrita de capa interrompida ou concorrente | Temporário com criação exclusiva e `fsync`; renomeação atômica; falha remove o temporário | `cover_store.py` | `security/test_cover_store.py` (`test_commit_is_an_atomic_rename…`, `test_concurrent_commits…`) | Implementado |
| Descrição com HTML, script ou markdown | Sanitizada no domínio (tags, scripts e estilos, markdown, controles); até 4 000 caracteres; exibida como texto puro (React, sem `innerHTML`) | `domain/metadata.py` (`sanitize_description`), `frontend/src/features/series/components/SeriesDescription.tsx` | `unit/test_metadata_domain.py`, `security/test_metadata_api.py`, `frontend/tests/unit/series.test.tsx` | Implementado |
| Link externo malicioso | Link só se https (`safeHttpsUrl`); qualquer outro valor vira texto sem link | `frontend/src/shared/series/types.ts`, `SeriesPage.tsx`, `MetadataPanel.tsx`, `SeriesDescription.tsx` | `frontend/tests/unit/series.test.tsx`, `metadata.test.tsx` | Implementado |
| Atribuição ausente ou falsa | `description_origin` e `description_source_*` gravados com a fonte; tradução marcada; Wikipédia com CC BY-SA na tela | `services/metadata_service.py` (`_resolve_description`), `api/series_schemas.py`, `SeriesDescription.tsx` | `integration/test_metadata_fusion.py`, `frontend/tests/unit/series.test.tsx` | Implementado |
| Casamento errado (obra trocada) | Limiar 0,85 (0,9 para só-descrição); margem de 0,02; edição penalizada; ano incoerente descartado; em dúvida, `not_found` | `domain/metadata.py` (`pick_best`) | `unit/test_metadata_domain.py`, `integration/test_metadata_fusion.py`, `regression/test_reg_022…` | Implementado (risco residual: casamento por título) |
| Automação sobrescreve edição manual | Escrita condicional ao estado atual; `manual` nunca é alvo, nem com `force` | `adapters/persistence/series_repository.py` (`update_metadata`), `services/metadata_service.py` | `regression/test_reg_021…` | Implementado |
| Não admin altera metadados ou dispara enriquecimento | `require_admin` em candidatos, `select`, `PUT`, `DELETE`, `enrich` e status; escrita sob `/api` exige CSRF | `api/series.py`, `api/library.py`, `api/csrf.py` | `security/test_metadata_api.py`, `security/test_series_authz.py` | Implementado |
| Busca ao vivo em massa (custo e cota de terceiros) | 10 por minuto por usuário, checado antes de qualquer saída; 429 com `Retry-After` | `api/series.py` (`metadata_candidates`), `composition.py` (`candidates_limiter`) | `security/test_metadata_api.py` | Implementado |
| Erro de fonte com detalhe | 502 genérico sem host, URL ou motivo; motivo só no log de nível info | `api/errors.py`, `services/metadata_service.py` | `security/test_metadata_api.py` | Implementado |
| Série ou progresso de outro usuário | Série é global (sem dado pessoal); progresso e `continue` sempre do `user_id` do token | `services/series_service.py`, `adapters/persistence/progress_repository.py` | `security/test_series_authz.py` (`test_one_users_reading…`) | Implementado |
| Caminho de arquivo na resposta de série | Nunca: `folder_rel_path`, `cover_path` e URL de capa ficam fora de `series_schemas.py` (`extra=forbid`) | `api/series_schemas.py`, `api/series.py` | `security/test_series_authz.py`, `security/test_metadata_api.py` | Implementado |
| Cache de capa de série | Mesma exceção do ADR 0010: privado, 1 h, só GET 200/304; rota não escolhe o cabeçalho | `api/security_headers.py` (`_CACHEABLE_PATH`) | `security/test_cache_exception.py` | Implementado; **risco residual: 1 h após logout (FIND-010 item 7)** |
| Política de conteúdo da capa | CSP inalterada: `img-src 'self' data: blob:`; capa é sempre same-origin | `api/security_headers.py` | `security/test_security_headers.py` | Implementado |

### Versão, atualização e webhook (ADR 0018, proposto)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Atualizar o servidor por cliente comum | Só admin: `POST /system/update/check` e `POST /system/update`; `GET /system/version` para usuário comum não consulta nada e não mostra release | `api/system.py`, `api/deps.py` (`require_admin`) | `security/test_update_api.py` | Implementado |
| Disparo de atualização sem aprovação | Só por ação do admin; tag igual à última release conhecida e mais nova que a em execução; pedido em memória; 409 dentro de 10 min | `services/update_service.py` (`request_update`) | `unit/test_update_service.py`, `security/test_update_api.py` | Implementado |
| Tag ou release forjada | Tag por regex estrita (tamanho e formato); versão comparada por semântica; `html_url` aceito só em `github.com/<repo>/releases/` | `api/system.py` (`TAG_PATTERN`), `domain/release.py` | `unit/test_release_domain.py`, `security/test_update_api.py` | Implementado |
| Destino do webhook escolhido por cliente ou por rota | Destino só por configuração (`UPDATE_WEBHOOK_URL`); nenhuma rota lê ou mostra a URL | `core/config.py`, `api/system.py` | `security/test_update_config.py`, `security/test_update_api.py` | Implementado |
| Webhook falsificado ou repetido | HMAC-SHA256 com `timestamp.corpo`; segredo ≥ 32 caracteres; receptor recusa assinatura inválida, janela de 300 s e nonce repetido | `adapters/http/webhook_notifier.py`, `infra/deploy-hook/receiver.py` | `security/test_webhook_notifier.py` (inclui o receptor real) | Implementado |
| Webhook para rede pública ou metadados de nuvem | http só se todo endereço resolvido for loopback, privado (RFC 1918, ULA) ou CGNAT; link-local, multicast, não especificado e público recusados; IP literal validado no startup; nome checado na conexão; TLS com verificação; sem redirecionamento | `domain/release.py` (`is_operator_network`), `webhook_notifier.py`, `core/config.py` | `security/test_webhook_notifier.py`, `security/test_update_config.py` | Implementado |
| Segredo do webhook em log, erro ou resposta | Nunca logado, nunca em erro, nunca na resposta da API; `repr` sem URL nem segredo | `webhook_notifier.py`, `api/system.py` | `security/test_webhook_notifier.py`, `security/test_update_api.py` | Implementado |
| App com acesso ao Docker | Não tem. Quem atualiza é o receptor no host, com lista de argumentos (sem shell) e tag só no `.env` após validação | `infra/deploy-hook/receiver.py`, `docs/DEPLOY.md` | `infra/deploy-hook/test_receiver.py` | Implementado |
| Release com notas que contêm HTML ou link malicioso | Notas e nomes em texto puro; link de release só https de GitHub do repositório; limite de 4 000 caracteres no frontend | `domain/release.py`, `frontend/src/shared/system/UpdateNotice.tsx` | `frontend/tests/unit/system-update.test.tsx` | Implementado |
| Consulta de release em excesso | Consulta preguiçosa com cache (6 h padrão), ETag, pausa após falha ou limitação; check forçado 3/min por admin | `services/update_service.py`, `composition.py` | `unit/test_update_service.py`, `security/test_update_api.py` | Implementado |
| Auditoria da atualização | `system.update_requested` e `system.update_failed` com só a tag (sem URL nem segredo) | `services/update_service.py` (`_record`) | `unit/test_update_service.py` | Implementado |

## Quem sai para a rede

Duas saídas, e só elas:

| Saída | Módulo | Quando | Dado que sai |
|---|---|---|---|
| Conteúdo e metadados (allowlist fixa de 8 hosts) | `SafeGateway` (`backend/app/adapters/http/safe_gateway.py`) | Enriquecimento, busca do admin e checagem de release | Ver tabela abaixo |
| Webhook de atualização (destino de configuração) | `WebhookNotifier` (`backend/app/adapters/http/webhook_notifier.py`) | Só quando o admin aprova uma release | Repositório, tag, imagem, horário, nonce e assinatura. Nada do usuário |

Os links de página de fonte (MangaDex, AniList, Wikipédia, Google Livros) são só texto para o usuário; o app não os acessa. Qualquer saída nova exige ADR e teste (`backend/AGENTS.md`).

### Metadados e release: `SafeGateway` (allowlist fixa)

| Host (allowlist fixa) | Quem chama | O que sai | Quando | Limite |
|---|---|---|---|---|
| `api.mangadex.org` | `MangaDexProvider` | título limpo da série (até 100 caracteres); id da obra já devolvido pela fonte | enriquecimento e busca ao vivo do admin | JSON até 1 MiB |
| `uploads.mangadex.org` | `MangaDexProvider` (capa) | só a URL devolvida pela API da fonte | ao baixar a capa | imagem até 5 MiB |
| `graphql.anilist.co` | `AniListProvider` | título limpo, como variável de busca (POST) | enriquecimento e busca ao vivo | POST até 16 KiB |
| `s4.anilist.co` | `AniListProvider` (capa) | só a URL devolvida pela API da fonte | ao baixar a capa | imagem até 5 MiB |
| `pt.wikipedia.org` | `WikipediaProvider` | título limpo | só se as fontes de obra não trouxeram descrição em pt-br | JSON até 1 MiB |
| `www.googleapis.com` | `GoogleBooksProvider` | título limpo | idem | JSON até 1 MiB |
| `api.mymemory.translated.net` | `MyMemoryTranslator` | trechos da sinopse pública já sanitizada (até 1 500 caracteres; até 400 bytes por requisição) | só sem descrição em pt-br e com sinopse em inglês; desligável por `METADATA_TRANSLATE_ENABLED` | para por 6 h após resposta de cota |
| `api.github.com` | `UpdateService` (`get_json_conditional`, só `releases/latest` do repositório configurado) | nada além do caminho com o repositório configurado e o ETag | consulta preguiçosa ao admin ver a versão (cache de `UPDATE_CHECK_INTERVAL_HOURS`) | 8 s no total (`CONDITIONAL_TIMEOUT`); sem cookie; demais limites do `SafeGateway` |

Não sai: usuário, senha, token, cookie, IP do cliente, caminho, nome de arquivo, id interno (exceto o id externo da própria fonte).

### Webhook de atualização (fora do `SafeGateway`)

| Destino | Quem chama | O que sai | Quando | Limite |
|---|---|---|---|---|
| `UPDATE_WEBHOOK_URL` (configuração; https, ou http só em rede do operador com `UPDATE_WEBHOOK_ALLOW_HTTP`) | `WebhookNotifier` | JSON com `event`, `repository`, `tag`, `image`, `requested_at` e `nonce`, com `X-Update-Timestamp` e `X-Update-Signature` | só após aprovação do admin | 10 s; resposta lida até 4 KiB e ignorada; sem redirecionamento |

## Segredos, dependências e verificação

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| `SECRET_KEY` fraca ou ausente | ≥ 32 caracteres, ≥ 12 distintos, sem espaço nas pontas, sem bloco ≤ 8 repetido; app não sobe sem ela; sem padrão; entrypoint valida antes do uvicorn | `core/config.py`, `main.py`, `infra/entrypoint.sh` | `security/test_settings.py` | Implementado; **entropia não medida** (FIND-010 item 10) |
| Chave crua reutilizada | HKDF com rótulos separados (`access-jwt`, `csrf-token`, `login-attempts`) | `core/keys.py` | `unit/test_keys.py` | Implementado |
| Versões de dependências | Backend: versões fixas (`==`) em `pyproject.toml`; constraints gerados em `python:3.12.8-slim` (`infra/constraints.txt`); `pip-audit` no `check` e no CI | `backend/pyproject.toml`, `infra/constraints.txt` | `regression/test_reg_015_…` (`test_3_…`), `integration/test_docker_files.py` (`test_constraints_pin_every_runtime_dependency`) | Parcial: sem hashes (M8) |
| Dependências e ações de CI desatualizadas | Dependabot semanal (actions, pip, npm, docker); actions fixadas por SHA; gitleaks com checksum verificado | `.github/dependabot.yml`, `.github/workflows/ci.yml` | inspeção | Implementado |
| Publicação sem teste | Release só após os mesmos checks do CI (`verify`), tag na `master` e seção do CHANGELOG; imagem com proveniência | `.github/workflows/release.yml` | inspeção | Implementado |
| Acoplamento entre camadas | import-linter com 8 contratos; violação quebra o teste | `backend/pyproject.toml` | `architecture/test_layers.py` | Implementado |
| Segredo no código | `scripts/check`: regex reduzida; `gitleaks` no CI e configurado. Marcador `secret-scan:allow` só na mesma linha, para valor fictício de teste | `scripts/check.ps1`, `check.sh`, `gitleaks.toml`, `scripts/README.md`, `.github/workflows/ci.yml` | — | Implementado no CI; localmente, parcial sem gitleaks |
| Frontend: canais de rede e HTML | ESLint: `fetch`/XHR/WebSocket/`sendBeacon` só no api-client; `indexedDB` só em `shared/offline`; `react/no-danger`; `no-eval` | `frontend/eslint.config.js` | `frontend/tests/unit/eslint-rules.test.ts` | Implementado; acessos indiretos dependem de revisão |
| Frontend: cache de dados autenticados no SW | `runtimeCaching: []`; `/api` fora do fallback; `skipWaiting` desligado; `registerType: 'prompt'` (nova versão só é ativada pelo usuário, com flush do progresso antes) | `frontend/vite.config.ts`, `frontend/src/shared/pwa/pwa-update.ts` | `frontend/tests/unit/pwa-update.test.tsx` | Implementado |
| Frontend: CSRF | Envia `X-CSRF-Token` (valor do cookie `csrf_token`) em métodos que alteram estado (`isStateChanging`); nomes padrão iguais ao backend | `frontend/src/shared/api-client/client.ts`, `csrf.ts` | `frontend/tests/unit/api-client.test.ts`, `api-client-session.test.ts` | Implementado (cliente) |
| Frontend: sessão | Só 401 em `/auth/me` vira "saiu"; 429, 503 e rede mantêm o estado (`error`); refresh rejeitado encerra a sessão | `frontend/src/shared/session/SessionProvider.tsx`, `api-client/client.ts` | `frontend/tests/unit/session-images.test.tsx` (`only a 401 means signed out`), `auth.test.tsx` | Implementado |
| Frontend: recuperação de imagem | Não chama `/auth/me`; uma recuperação de sessão por janela de 60 s, compartilhada | `frontend/src/shared/ui/useImageRecovery.ts` | `frontend/tests/unit/session-images.test.tsx` | Implementado |
| Frontend: preferências | `PUT` sempre com o objeto completo vindo do servidor; nunca a partir de padrões | `frontend/src/shared/preferences/PreferencesProvider.tsx` | `frontend/tests/unit/preferences.test.tsx` | Implementado |

## Riscos residuais (aceitos pela arquitetura ou pendentes de decisão)

| Risco | Efeito | Origem | Situação |
|---|---|---|---|
| Ataque distribuído bloqueia a conta em IP novo por até 3600 s | Negação de acesso direcionada e temporária | FIND-2026-009 (ADR 0009) | `open`: **decisão do dono** (`accepted-risk` ou mitigação) |
| Proxy mal configurado (raio do dano do IP) | Todos os clientes viram um endereço: lock por IP e limites de auth compartilhados; lista ampla permite forjar IP | FIND-2026-001 residual (ADR 0011) | Mitigado por obrigatoriedade e avisos; **operador confere** |
| Ladrão de refresh dentro de 10 s | Não detectado nessa janela | FIND-2026-005 (ADR 0008) | Aceito; janela configurável (0 a 60 s) |
| Imagens e capítulos no cache do navegador 1 h após logout | Dispositivo compartilhado mostra páginas já lidas | FIND-2026-010 item 7 (ADR 0010) | Não mitigado; opções: `Clear-Site-Data` no logout ou TTL menor |
| Limites e bloqueio em memória (rate limit) e atomicidade só por processo | Com mais de uma worker, limite multiplica | ADR 0007, 0009; `adapters/security/rate_limiter.py` | Limitação aceita: uma worker |
| Argon2 com 2 slots sob flood | Logins legítimos recebem 503 durante o flood | FIND-2026-002 | Aceito como disponibilidade; resposta idêntica para existente e inexistente |
| Pico de memória de página | 4 × 64 MiB simultâneos | FIND-2026-003 | Streaming não feito; limite de página é decisão do dono |
| Token CSRF não amarrado à sessão | Só a checagem de origem protege contra token alheio | FIND-2026-010 item 4 | Pendente |
| Rate limit por rota de páginas e scan inexistente | Abuso de leitura de páginas só é limitado pelo global de `/api` (600/min, burst 200) e pelo gate | PLANO §6 | Pendente: decisão do dono |
| Last-write-wins no progresso | Escrita concorrente de dois aparelhos é descartada | ADR 0013 | Aceito; revisar com caso real |
| Cota pública do MyMemory (cerca de 5 000 caracteres por dia por IP, anônimo) | Sinopse fica em inglês ao estourar; tradutor fica quieto por 6 h | ADR 0015 | Aceito; monitorar |
| Google Livros respondeu 429 em todas as tentativas de validação | Fonte fica indisponível na prática | ADR 0015 | Aceito; não validado de ponta a ponta |
| Nome da série sai para fontes públicas | Terceiros (MangaDex, AniList, Wikipédia, Google) recebem o título limpo | ADR 0015 | Aceito: exceção autorizada pelo dono em 2026-11-20 |
| Casamento por título errado | Capa ou sinopse de obra errada | ADR 0015 | Mitigado (limiar, margem, `not_found`, correção manual pelo admin); residual |
| Capa de série fora do backup de `/data` | Restaurar só `app.db` perde as capas | ADR 0016 | Pendente (decisão do dono; `docs/DEPLOY.md` §6) |
| Tradução com erro de sentido | Texto marcado como tradução; pode trocar termo | ADR 0015 | Aceito |
| Oitavo host (`api.github.com`) e webhook fora do `SafeGateway` | Mais uma saída de rede; o webhook é a única saída com destino configurável | ADR 0018 (proposto) | Aceito se o dono confirmar o ADR; controles: configuração fixa, rede do operador, assinatura, sem redirecionamento |
| `allow-same-origin` no iframe do capítulo e `style-src 'unsafe-inline'` na resposta do capítulo | Se algum script entrasse no frame, teria a origem do app | ADR 0017 (proposto) | Aceito se o dono confirmar; sem `allow-scripts` e sem `script-src` (testado) |
| Estado do pedido de atualização em memória | Reinício do app esquece o pedido; o receptor ainda pode concluir a atualização | ADR 0018 | Aceito |
| Receptor de atualização com política mais fraca que a de referência | Disparo de atualização indevido | `infra/deploy-hook/README.md` | Obrigação do operador: preservar as verificações |

## Pendências (segurança)

| Item | Motivo | Ação |
|---|---|---|
| FIND-2026-009 (`open`) | Decisão de risco do dono | Registrar `accepted-risk` ou aprovar mitigação; se mitigar: `test_reg_014_…` (número reservado) |
| Reverificação ao vivo do FIND-2026-002 | Correção medida só em processo separado; p95 não demonstrado | Auditor reverifica (`poc/flood_login.py`) |
| Reteste dos PoCs (FIND-004, 005) | `race_lockout.py` precisa de ajuste de cookie/CSRF | Auditor |
| FIND-2026-010 itens 4, 6, 7, 8, 9, 10, 11, 12, 13 | Subitens não adotados | Ver finding; itens 4, 7 e 9 pedem decisão |
| Lockfile do backend e hashes (M8) | Só versões fixas e constraints sem hashes; digest das imagens base ausente | Antes de publicar |
| Aceite dos ADRs 0017 e 0018 | Propostos; o oitavo host e o iframe com `allow-same-origin` dependem de confirmação do dono | Dono confirma ou pede ajuste |
| PDF: CSP e leitura | Leitor PDF não existe; decidir por ADR se usar iframe próprio | Fase 4 |
| `ComicInfo.xml` | Parser XML exige biblioteca segura (dependência nova) | Decisão do dono |
| CBR (RAR) | Extrator externo com timeout e sem shell, ou conversão | Fase 4 |
| `semgrep` (SAST adicional) | Não está no `check` nem no CI; `gitleaks` roda no CI; SBOM e proveniência ligados no build da imagem (`release.yml`, `sbom: true`) | Incluir `semgrep` se o dono quiser |
| `check.sh` em Linux real | Testado só com bash do Git no Windows; o CI roda Linux, mas `check.sh` local não foi validado em Linux | Validar |
| CAPTCHA e checagem de senha vazada | Serviço externo | Só com autorização do dono (ADR 0002) |
| HSTS | Emitido pelo proxy (fora de escopo) | Confirmar no proxy |
| `Clear-Site-Data`, HEAD em `/health` (405), query string nos logs do uvicorn | FIND-010 itens 7, 8, 12 | Decidir |
| `audit_log.ip` e `refresh_tokens.user_agent`/`ip` sem uso | Colunas nunca preenchidas | Preencher ou remover em migração nova (apagar exige autorização) |
| Denylist de senhas maior | Exige arquivo de dados (dependência) | Decisão do dono (FIND-007) |
| Build da imagem e `migrate` dentro dela | Validados em 2026-11-20 e 2026-11-21 (relatado); reexecutar a cada mudança de Dockerfile | Manter o roteiro de `docs/DEPLOY.md` |
| Reteste ao vivo das fontes, do GitHub e do limite de 429 | Validado com respostas canônicas e biblioteca real; não sob carga nem com cota estourada; webhook testado só contra o receptor local | Dono ou auditor, quando houver janela |
| Backup de `covers/` (`DATA_DIR`) | Fora do roteiro de backup de `docs/DEPLOY.md` §6 | Decisão do dono |
| Teste de rede real do `SafeGateway` | Testes usam gateway falso, sem socket; DNS real verificado só por `nslookup` | Aceito; reexecutar em ambiente com DNS público |
