# TEST_MAP

Estado: 2026-11-21. Funcionalidade → arquivos que existem no disco → lacunas.

**Como as contagens foram obtidas:** backend = número de linhas `def test` por arquivo (grep no disco; parametrizados **não** expandidos). Frontend = linhas `it(`, `test(` ou `it.each(` por arquivo (grep; `it.each` conta como um bloco, não expandido). Infra e CI = `def test` em `infra/deploy-hook/` e `.github/scripts/`. Os resultados de execução (`scripts/check`, CI) são os informados pelo dono e pelo coordenador, não reexecutados aqui. Totais de contagem: backend 1122 funções em 95 arquivos; frontend 364 blocos em 28 arquivos (27 em `tests/unit`, 1 em `tests/regression`); infra e CI 59 funções em 2 arquivos.

## Backend: arquivo → funções → cobre

| Arquivo | Funções | Cobre |
|---|---|---|
| `backend/tests/architecture/test_layers.py` | 15 | Oito contratos de camadas do import-linter (executa de verdade) e casos negativos |
| `backend/tests/unit/test_auth_service.py` | 48 | `AuthService` com falsos: login, bloqueio por escopo, refresh, logout, troca de senha, `current_user` |
| `backend/tests/unit/test_library_services.py` | 14 | `natural_key`, `sanitize_title`, scan incremental, páginas, hash |
| `backend/tests/unit/test_scan_runner_and_catalog.py` | 15 | `ScanRunner` (exclusão, falhas, relógio, liberação), catálogo, purga de auditoria |
| `backend/tests/unit/test_user_service.py` | 10 | `UserService` com falsos: criação, auditoria, reset, desativação |
| `backend/tests/unit/test_argon2_hasher.py` | 8 | Argon2id: sal, hash dummy, senha longa, rehash |
| `backend/tests/unit/test_password_policy.py` | 8 | Política de senha e username |
| `backend/tests/unit/test_lockout.py` | 8 | `locked_until()` e `lookback` |
| `backend/tests/unit/test_rate_limiter.py` | 6 | Balde de fichas: burst, recarga, chaves, memória limitada, limites inválidos |
| `backend/tests/unit/test_keys.py` | 4 | HKDF: determinístico, rótulos independentes |
| `backend/tests/unit/test_progress_service.py` | 9 | `compute_position`; `save`; progresso por usuário; limite do `continue`; preferências |
| `backend/tests/unit/test_series_domain.py` | 16 | Regras puras de agrupamento: nome do arquivo, ordem, títulos, onde continuar |
| `backend/tests/unit/test_metadata_domain.py` | 30 | Sanitização de descrição, casamento de títulos, escolha de idioma, detecção de imagem por bytes |
| `backend/tests/unit/test_metadata_providers.py` | 21 | MangaDex e AniList com respostas canônicas: parsing, idioma, formas hostis, o que é enviado |
| `backend/tests/unit/test_metadata_describers.py` | 20 | Wikipédia, Google Livros e MyMemory com respostas canônicas (sem rede) |
| `backend/tests/unit/test_book_progress.py` | 7 | Locator de livro: encode/decode, `percent` e concluído |
| `backend/tests/unit/test_book_scan.py` | 3 | Scan de arquivo EPUB: item do tipo `book` |
| `backend/tests/unit/test_epub_safe.py` | 17 | Leitura segura do pacote EPUB |
| `backend/tests/unit/test_epub_html.py` | 39 | Sanitizador de capítulo: allowlist de tags e atributos, links, imagens |
| `backend/tests/unit/test_release_domain.py` | 17 | Versão, tag, repositório e rede do operador (`is_operator_network`) |
| `backend/tests/unit/test_update_service.py` | 26 | `UpdateService` com falsos: ETag, limitação, falha, aprovação, webhook e auditoria |
| `backend/tests/integration/test_auth_api.py` | 20 | Auth ponta a ponta: login, me, refresh, logout, troca de senha, reset, auditoria, `require_admin` |
| `backend/tests/integration/test_auth_repositories.py` | 16 | Refresh (rotação, revogação, famílias, purga) e tentativas (HMAC, escopos, purga) |
| `backend/tests/integration/test_user_repository.py` | 9 | Repositório de usuário e auditoria no banco migrado |
| `backend/tests/integration/test_item_repository.py` | 11 | Persistência de `Item`: roundtrip, ordem, filtros, `remove_missing`, LIKE literal |
| `backend/tests/integration/test_library_api.py` | 10 | Login → scan → listar → página; 409; 503; CLI `scan` |
| `backend/tests/integration/test_library_scan.py` | 1 | Scan ponta a ponta com `LocalStorage` |
| `backend/tests/integration/test_series_api.py` | 17 | API de séries sobre biblioteca temporária real: agrupamento, lista, detalhe, `continue`, capa, varredura |
| `backend/tests/integration/test_series_kind.py` | 3 | `kind` da série (manga, book, mixed) e `type` dos capítulos |
| `backend/tests/integration/test_metadata_enrich.py` | 25 | Enriquecimento ponta a ponta (rotas, serviços e providers reais; só o gateway é falso): estados, capa, desligado |
| `backend/tests/integration/test_metadata_fusion.py` | 22 | Fusão de fontes, descrição pt-br primeiro, tradução marcada; caso real de obra sem pt-br no MangaDex |
| `backend/tests/integration/test_book_progress_api.py` | 4 | Progresso de livro pela API |
| `backend/tests/integration/test_book_preferences.py` | 8 | Preferências de livro: `book_font_scale` e `book_theme` |
| `backend/tests/integration/test_book_series_enrichment.py` | 5 | Séries de livro enriquecidas como as demais (automática, por série, repositório, busca admin) e paridade CBZ, EPUB e pasta |
| `backend/tests/integration/test_progress_api.py` | 14 | API de progresso e preferências: cálculo no servidor, 422/404 genéricos, `DELETE` idempotente, `continue`, UTC, preferências, navegação fora do rate limit estrito |
| `backend/tests/integration/test_progress_repository.py` | 5 | Upsert e `get`, upserts concorrentes, cascata, `list_continue` por usuário, preferências só nas colunas dele |
| `backend/tests/integration/test_migrations.py` | 18 | Sobe e desce; ORM × schema; índices; pragmas; unicidade; checks; reversibilidade; `reading_progress`; colunas de livro (`0008`) |
| `backend/tests/integration/test_migrations_dir.py` | 5 | `MIGRATIONS_DIR`; Dockerfile define `MIGRATIONS_DIR` |
| `backend/tests/integration/test_docker_files.py` | 6 | Checagens estáticas: `entrypoint.sh` LF e estrito; `.gitattributes`; Dockerfile fixado e não-root; constraints; hardening do compose; `.dockerignore` |
| `backend/tests/integration/test_cli.py` | 8 | CLI ponta a ponta (migrate, create, list, reset, deactivate); senha sem eco; sem argumento de senha |
| `backend/tests/integration/test_health.py` | 1 | Health |
| `backend/tests/security/test_csrf.py` | 23 | CSRF: token, cookie, assinatura, Origin, Referer, Fetch Metadata, métodos |
| `backend/tests/security/test_spa.py` | 28 | Frontend servido: traversal, dotfiles, symlink, métodos, cache por tipo, `Range`, cabeçalhos, docs não expostas |
| `backend/tests/security/test_progress_authz.py` | 6 | Anônimo = 401; sem acesso ao progresso alheio; preferências por usuário; escrita exige CSRF; `no-store` sem caminhos |
| `backend/tests/security/test_items_api.py` | 32 | Autorização de itens e scan; IDs e páginas hostis; ETag/304; tipos de mídia; erros genéricos |
| `backend/tests/security/test_series_authz.py` | 4 | Séries exigem sessão; progresso mostrado é sempre o do usuário; séries não aceitam escrita; sem caminho na resposta |
| `backend/tests/security/test_metadata_api.py` | 27 | Gestão de metadados: anônimo, usuário e admin; CSRF; entradas estritas; erros genéricos; limite de 10/min por usuário; precedência da capa |
| `backend/tests/security/test_safe_gateway.py` | 33 | `SafeGateway`: allowlist, https e porta, IP público, sem redirecionamento, tipos de mídia, limites, espaçamento, sem socket (falso) |
| `backend/tests/security/test_safe_gateway_release.py` | 13 | Consulta de release: `api.github.com` é o 8º host e o único condicional; ETag, 304, limitação, redirecionamento recusado, URLs parecidas recusadas |
| `backend/tests/security/test_webhook_notifier.py` | 20 | Contrato do webhook (cabeçalhos, assinatura, destino, redirecionamento, tamanho); carrega o receptor real de `infra/deploy-hook` (pula se ausente) |
| `backend/tests/security/test_update_api.py` | 28 | API de atualização: `GET /version` por papel, check com limite, `POST /update` (202, 409, 502, 503) e erros genéricos |
| `backend/tests/security/test_update_config.py` | 16 | `UPDATE_*` e `APP_VERSION`: validações, par URL+segredo, http só em rede do operador, segredo mínimo |
| `backend/tests/security/test_cover_store.py` | 13 | Capas: nome só pelo UUID do servidor, extensões fixas, tamanho, symlink, escrita atômica, concorrência, leitura hostil |
| `backend/tests/security/test_login_bruteforce.py` | 15 | Bloqueio por par, conta e IP; resposta idêntica; progressivo; expiração; distribuído; hash só HMAC |
| `backend/tests/security/test_rate_limit_and_cors.py` | 19 | Rate limit (global, auth, IP normalizado, IPv6 /64); CORS exato; origens inválidas |
| `backend/tests/security/test_session_attacks.py` | 11 | JWT forjado, expirado, sem claims, sessão alheia, troca de senha, segredos fora de logs |
| `backend/tests/security/test_jwt_tokens.py` | 15 | HS256: `alg:none`, algoritmos trocados, assinatura, claims, tempo |
| `backend/tests/security/test_cookies_and_cache.py` | 11 | Atributos de cookies; `no-store` em toda rota `/api` |
| `backend/tests/security/test_cache_exception.py` | 9 | Exceção de cache de imagem: só GET 200/304 em página, capa de item e capa de série; marcador exato |
| `backend/tests/security/test_book_chapter_headers.py` | 12 | CSP do capítulo EPUB só para GET 200 do caminho exato; cache privado; marcador interno nunca sai |
| `backend/tests/security/test_book_api.py` | 27 | Rotas de livro: autenticação, IDs e números hostis, erros sem caminho |
| `backend/tests/security/test_epub_extractor.py` | 53 | Extrator EPUB com casos hostis (DRM, limites, imagens e fontes) |
| `backend/tests/security/test_security_headers.py` | 8 | Cabeçalhos (inclui 404), 500 genérico, reraise, `CancelledError`, desconexão, substituição de cabeçalhos da rota |
| `backend/tests/security/test_body_limit.py` | 11 | 413 por `Content-Length` e por corpo recebido; 400 para `Content-Length` inválido |
| `backend/tests/security/test_settings.py` | 22 | `SECRET_KEY`; limites; coerência do lockout; fórmula; metadados (`METADATA_*`, `DATA_DIR`) |
| `backend/tests/security/test_password_storage.py` | 3 | Senha só como Argon2id; fora de logs, erros e auditoria |
| `backend/tests/security/test_local_storage.py` | 10 | Caminhos hostis, links reais, pasta OneDrive, raiz inexistente |
| `backend/tests/security/test_cbz_extractor.py` | 16 | CBZ: ordem, zip-slip, symlink, zip bomb, limites, arquivo falso, criptografado, corrompido |
| `backend/tests/security/test_folder_extractor.py` | 5 | Pasta: ordem, extensão falsa, página gigante, excesso de arquivos |
| `backend/tests/regression/test_reg_001_secret_key_not_in_error.py` | 1 | REG-001 (M-1): valor de `SECRET_KEY` fora do erro de validação |
| `backend/tests/regression/test_reg_002_migrations_dir_after_install.py` | 2 | Migrações rodam fora do pacote instalado |
| `backend/tests/regression/test_reg_003_scan_uses_injected_clock.py` | 1 | `added_at` vem da porta `Clock` |
| `backend/tests/regression/test_reg_004_audit_log_retention.py` | 1 | Retenção da auditoria no login |
| `backend/tests/regression/test_reg_005_request_body_size_limit.py` | 1 | JSON acima do limite recebe 413 |
| `backend/tests/regression/test_reg_006_forwarded_allow_ips_defaults_consistent.py` | 7 | FIND-001: `FORWARDED_ALLOW_IPS` coerente em compose, Dockerfile e `.env.example` |
| `backend/tests/regression/test_reg_007_login_flood_does_not_starve_api.py` | 4 | FIND-002: limite de concorrência do hasher; 503 sem falha registrada |
| `backend/tests/regression/test_reg_008_page_read_does_not_scan_all_entries.py` | 4 | FIND-003: índice em cache; limite do gate |
| `backend/tests/regression/test_reg_009_lockout_concurrent_attempts.py` | 5 | FIND-004: reserva antes do hash; liberação; serviço único |
| `backend/tests/regression/test_reg_010_concurrent_refresh_grace_window.py` | 5 | FIND-005: janela de tolerância do refresh |
| `backend/tests/regression/test_reg_011_audit_log_not_flooded_by_locked_attempts.py` | 5 | FIND-006: `login.locked` deduplicado; purga isolada |
| `backend/tests/regression/test_reg_012_password_policy_username_and_denylist.py` | 3 | FIND-007: username contido e padrões fracos |
| `backend/tests/regression/test_reg_013_no_trailing_slash_redirect.py` | 2 | FIND-008: barra final sem `Location` |
| `backend/tests/regression/test_reg_015_hardening_bundle.py` | 5 | FIND-010: `--no-server-header`, limites do uvicorn, pins, `Origin` repetido |
| `backend/tests/regression/test_reg_016_folder_page_count_ignores_fake_images.py` | 3 | FIND-011: `page_count` de pasta com arquivo falso |
| `backend/tests/regression/test_reg_017_scan_empty_root_keeps_items.py` | 10 | FIND-012: raiz vazia, ilegível, erro de caminhada, erro de banco |
| `backend/tests/regression/test_reg_018_user_writes_do_not_lose_concurrent_changes.py` | 8 | Escritas de usuário por CAS (sem finding correspondente) |
| `backend/tests/regression/test_reg_019_auth_reads_do_not_use_strict_bucket.py` | 2 | `me` e `csrf` não consomem o balde estrito; login continua nele |
| `backend/tests/regression/test_reg_020_chapters_sort_naturally_by_number.py` | 1 | REG-020: capítulos em ordem numérica (sem finding) |
| `backend/tests/regression/test_reg_021_manual_metadata_wins_over_a_running_enrichment.py` | 1 | REG-021: edição manual vence enriquecimento em andamento (sem finding) |
| `backend/tests/regression/test_reg_022_orv_work_not_lost_to_editions.py` | 2 | REG-022: obra do MangaDex não perdida para edições (sem finding) |
| `backend/tests/regression/test_reg_023_translation_missing_space_after_sentence.py` | 4 | REG-023: espaço faltando após ponto final na tradução do MyMemory (sem finding) |
| `backend/tests/regression/test_reg_024_book_locator_is_read_by_item_type.py` | 3 | REG-024: o locator é lido conforme o tipo do item (sem finding) |
| `backend/tests/regression/test_reg_025_preferences_put_keeps_book_settings.py` | 1 | REG-025: `PUT` de preferências preserva os campos de livro (sem finding) |
| `backend/tests/regression/test_reg_026_enrichment_does_not_depend_on_format.py` | 1 | REG-026: série de EPUB é consultada e recebe capa e descrição (sem finding; decisão do dono, 2026-11-21) |
| `backend/tests/regression/test_reg_027_series_chapters_expose_type_and_kind.py` | 1 | REG-027: capítulos trazem `type` e a série traz `kind` (sem finding) |

Helpers (não são teste, fora da contagem): `backend/tests/conftest.py` (ambiente hermético, `SECRET_KEY` de teste), `fakes.py`, `auth_fakes.py`, `library_env.py` (`library_env`, `logged_in`, `add_item`, `metadata_env`), `metadata_fakes.py` (`FakeGateway` com a allowlist real, respostas canônicas, `fake_translation`), `epub_fixtures.py` (construtores de EPUB), `update_fakes.py` (falsos de atualização), `regression/README.md`, `unit/.gitkeep`.

## Infra e CI

| Arquivo | Funções | Cobre |
|---|---|---|
| `infra/deploy-hook/test_receiver.py` | 46 | Receptor de referência: verificações do `infra/deploy-hook/README.md` (assinatura, timestamp, nonce, repositório, tag, corpo). Sem rede e sem Docker (runner falso) |
| `.github/scripts/test_release_notes.py` | 13 | Validação da tag e extração da seção do `CHANGELOG.md` para as notas da release |

Rodam no job `infra-tests` do CI (`ci.yml`) e no `scripts/check`.

## Regressão: convenção

| Regra | Detalhe |
|---|---|
| Nome | `test_reg_<NNN>_<slug>.py` em `backend/tests/regression/`; docstring com bug e causa |
| Existentes | 001 a 013 e 015 a 027 |
| Reservado | `014` → FIND-2026-009 (aberto; só se houver mitigação aprovada) |
| Próximo livre | `028` (conferido em `backend/tests/regression/`) |
| Frontend | `frontend/tests/regression/`, numeração própria (`reg_NNN`), independente do backend (`test_reg_NNN`). `reg_001` (issue #7) não tem relação com `test_reg_001` (REG-001). `.gitkeep` mantido |
| Frontend: existentes e próximo livre | `reg_001` (zoom/pinça no EPUB, 19 blocos); próximo livre `reg_002` |

Mapeamento finding → teste: FIND-001 → reg_006; FIND-002 → reg_007; FIND-003 → reg_008; FIND-004 → reg_009; FIND-005 → reg_010; FIND-006 → reg_011; FIND-007 → reg_012; FIND-008 → reg_013; FIND-010 → reg_015; FIND-011 → reg_016; FIND-012 → reg_017. M-1 (REG-001) → reg_001. Sem finding correspondente: reg_018 a reg_027.

## Frontend (Vitest): arquivo → blocos → cobre

| Arquivo | Blocos | Cobre |
|---|---|---|
| `frontend/tests/unit/api-client.test.ts` | 17 | api-client: credenciais, CSRF, 429, 500, rede, 204, não-JSON, AbortError, 2xx vazio, junção de `baseUrl` |
| `frontend/tests/unit/api-client-session.test.ts` | 15 | Recuperação de sessão (401 → refresh compartilhado → retry uma vez); bootstrap de CSRF; `keepalive` sem `sendBeacon` |
| `frontend/tests/unit/architecture.test.ts` | 2 | dependency-cruiser em `src` e em fixtures negativas |
| `frontend/tests/unit/auth.test.tsx` | 12 | Guarda de rota; login (sucesso, retorno, erro genérico, 429 com contagem, 503); `safeRedirect` |
| `frontend/tests/unit/eslint-rules.test.ts` | 5 | ESLint: formas proibidas em feature (`it.each`); permissões por pasta |
| `frontend/tests/unit/library.test.tsx` | 11 | Biblioteca de séries: capas, busca com debounce, "carregar mais", "Continuar lendo" (falha não bloqueia) |
| `frontend/tests/unit/series.test.tsx` | 16 | Tela de série: capa, "continuar"/"começar a ler", capítulos em janela, "ir para o capítulo N", descrição (texto puro, badge de idioma, link https), vazio, 404 e erro com nova tentativa |
| `frontend/tests/unit/series-books.test.tsx` | 9 | Série de livros: rótulo "Livro" sem contagem de páginas, progresso em %, `kind` e `type` (com fallback para respostas antigas), "continuar" de livro e cartão na biblioteca |
| `frontend/tests/unit/metadata.test.tsx` | 32 | Painel admin (invisível para usuário comum, recolhido, busca só por clique, usar candidato, edição com limites, remoção com confirmação, 429); botão "Atualizar metadados"; origem e atribuição; links só https; `Cover` |
| `frontend/tests/unit/reader.test.tsx` | 28 | Leitor de mangá: retomada, modos RTL/LTR/vertical, zoom, pré-carregamento, salvamento (debounce, `pagehide`, aba oculta, saída, falha com aviso) |
| `frontend/tests/unit/reader-series.test.tsx` | 8 | Leitor com série: próximo e anterior no fim do capítulo, "voltar" para a série, sem série o leitor se comporta como antes |
| `frontend/tests/unit/reader-vertical.test.tsx` | 11 | Modo vertical sem regredir o progresso salvo; janela de páginas; memória limitada; região viva e teclado |
| `frontend/tests/unit/reader-navigation.test.ts` | 10 | Lógica pura: zonas de toque, deslize, teclas, `clampPage` |
| `frontend/tests/unit/reader-epub.test.tsx` | 49 | Leitor EPUB: capítulos, progresso, painéis e preferências do livro |
| `frontend/tests/unit/epub-locator.test.ts` | 17 | Locator de livro (`capítulo * 10000 + offset_bp`), lógica pura do leitor EPUB e sandbox de todos os iframes do leitor (página e tira) |
| `frontend/tests/unit/epub-strip.test.ts` | 7 | Tira vertical do EPUB: janela de capítulos, posição, altura e conversão de posição |
| `frontend/tests/unit/epub-pinch.test.ts` | 9 | `createPinchGuard` (multitoque, toque perdido, reset, expiração) e `createReflowHold` (só largura, rolagem do usuário, extensão) |
| `frontend/tests/unit/reader-epub-vertical.test.tsx` | 11 | Leitor EPUB em modo vertical: tira, janela montada, progresso e fim do livro; altura de capítulo com `html`/`body` 100%; barras em toque |
| `frontend/tests/unit/auto-hide-controls.test.ts` | 3 | `useAutoHideControls`: oculto por padrão só em toque, auto-ocultar após 4 s, `keepAlive` e `paused`, com mouse não oculta |
| `frontend/tests/unit/progress-saver.test.ts` | 8 | Debounce, um envio por vez, retry, `flush` com `keepalive`, `dispose` |
| `frontend/tests/unit/preferences.test.tsx` | 3 | Não sobrescreve o servidor com padrões; edição com GET pendente é mesclada; PUTs em série |
| `frontend/tests/unit/session-images.test.tsx` | 7 | Verificação de sessão na carga (só 401 = saiu); recuperação de imagem compartilhada, sem `/auth/me` |
| `frontend/tests/unit/settings.test.tsx` | 11 | Ajustes: tema, sentido de leitura, troca de senha, sair |
| `frontend/tests/unit/system-update.test.tsx` | 29 | Aviso de versão e atualização: quem vê (só admin), notas em texto puro, confirmação, polling limitado (5 s, até ~5 min), "Agora não", verificação manual e polling de versão de 30 min |
| `frontend/tests/unit/pwa-update.test.tsx` | 10 | Service worker em modo `prompt`: nunca recarrega sozinho; "Recarregar" faz flush do progresso antes; "Depois" só esconde; configuração sem `skipWaiting` |
| `frontend/tests/unit/theme-css.test.ts` | 3 | Tokens do tema: cada valor escuro uma vez; gatilhos escuros; tokens em `:root` |
| `frontend/tests/unit/theme.test.tsx` | 2 | Tema: sistema por padrão; troca explícita; sem localStorage |
| `frontend/tests/regression/reg_001_epub_zoom_no_page_change.test.tsx` | 19 | reg_001 (issue #7): zoom/pinça no EPUB não troca capítulo, não move a posição e não salva progresso; tira vertical e capítulo único |

Helpers (não são teste): `frontend/tests/setup.ts`, `frontend/tests/helpers/fake-api.ts`, `frontend/tests/helpers/render-app.tsx`, `frontend/tests/helpers/epub-frame.ts`. Fixtures de arquitetura: `frontend/tests/fixtures/arch-*/` (8 diretórios, uma violação cada).

## Lacunas

| Item | Pasta | Status |
|---|---|---|
| Regressão frontend | `frontend/tests/regression/` | só `reg_001` (issue #7); demais correções de frontend sem `reg_NNN` |
| E2E (login, mangá na página 5 e retomada, tema, offline, série, EPUB) | `frontend/tests/e2e/` | vazia; Playwright sem navegadores instalados |
| Service worker: instalação e registro real | — | não testados no navegador; há testes de configuração e do aviso (`pwa-update.test.tsx`) |
| Leitor PDF e CBR | — | sem código, sem teste |
| Progresso de PDF | — | sem código |
| Renderização real do EPUB em navegador (layout, rolagem, fontes) | — | só testes de lógica e de frame falso; sem EPUB real da biblioteca no repositório |
| Rede real das fontes de metadados e do GitHub | — | testes usam `FakeGateway` (sem socket) e respostas canônicas; Google Livros respondeu 429 na validação |
| Webhook contra receptor em execução | — | testado contra o receptor de `infra/deploy-hook` importado, sem rede nem Docker |
| Cota do MyMemory | — | não estourada nos testes; comportamento de cota coberto por resposta falsa |
| Arquivos corrompidos da biblioteca real (92 de 301 CBZ) | — | validado manualmente com a biblioteca do dono (relatado); sem teste automatizado com a biblioteca real |
| Build da imagem, compose e `migrate` na imagem | — | validados manualmente (2026-11-20 e 2026-11-21, relatado); `test_docker_files.py` faz só checagem estática |
| Escrita concorrente de scan e cancelamento | — | não existe cancelamento |
| Teste de módulo fora do CODEMAP | `backend/tests/architecture/` | planejado; não existe |
| Reverificação ao vivo de FIND-002 e reteste dos PoCs | `docs/security/poc/` | pendente (auditor) |
| Scan de segredos local | `scripts/` | só regex reduzida sem gitleaks; no CI, gitleaks roda |
| CI e release | `.github/workflows/` | existem (`ci.yml`, `release.yml`); não executados nesta entrega, validar no primeiro run |
