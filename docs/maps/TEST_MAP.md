# TEST_MAP

Estado: 2026-11-19. Funcionalidade → testes que existem no disco → lacunas. Contagens da última execução: backend `pytest` 64 passed; frontend `vitest` 67 passed.

## Backend (pytest): 64 casos

| Funcionalidade | Teste | Caso | Tipo |
|---|---|---|---|
| Health | `backend/tests/integration/test_health.py` | `test_health_ok` | integration |
| Cabeçalhos de segurança | `backend/tests/security/test_security_headers.py` | `test_security_headers_present`, `test_security_headers_on_404`, `test_preexisting_security_headers_are_replaced` | security |
| Erro 500 genérico com cabeçalhos | `backend/tests/security/test_security_headers.py` | `test_unhandled_exception_returns_generic_500_with_headers` | security |
| Erro após resposta iniciada | `backend/tests/security/test_security_headers.py` | `test_exception_after_response_started_is_reraised`, `test_real_error_after_start_is_logged_and_reraised`, `test_disconnect_after_start_is_reraised_without_error_log` (2 casos: `ClientDisconnect`, `BrokenPipeError`) | security |
| `CancelledError` não engolido | `backend/tests/security/test_security_headers.py` | `test_cancelled_error_is_not_swallowed` | security |
| `SECRET_KEY` obrigatória e forte | `backend/tests/security/test_settings.py` | `test_create_app_fails_without_secret_key`, `test_create_app_fails_with_short_secret_key`, `test_create_app_fails_with_low_entropy_secret_key` (7 casos), `test_create_app_rejects_secret_key_with_edge_whitespace` (3 casos), `test_create_app_accepts_strong_secret_key` | security |
| Valor de `SECRET_KEY` fora do erro (M-1) | `backend/tests/regression/test_reg_001_secret_key_not_in_error.py` | `test_reg_001_secret_key_not_in_error` (3 casos) | regression |
| Contratos de camadas | `backend/tests/architecture/test_layers.py` | `test_import_linter_contracts_hold`, `test_runner_passes_on_clean_minimal_package`, `test_contract_is_enforced` (33 casos: domain 11, ports 7, services 6, core 4, adapters 3, api 2), `test_api_deps_is_the_only_api_module_allowed_to_import_adapters`, `test_api_deps_may_import_adapter_submodules`, `test_other_api_modules_cannot_import_adapter_submodules` | architecture |
| Fixture de cliente | `backend/tests/conftest.py` | `client` | — |

Regra para testar o middleware de 500: `TestClient(app, raise_server_exceptions=False)` e `caplog` (ver `backend/tests/AGENTS.md`).

## Frontend (Vitest): 67 casos

| Funcionalidade | Teste | Casos | Tipo |
|---|---|---|---|
| api-client (credenciais, CSRF, 429, 500, rede, 204, não-JSON, AbortError, 2xx vazio, junção de `baseUrl`) | `frontend/tests/unit/api-client.test.ts` | 30 | unit |
| ESLint: fetch, storage, XHR/WebSocket/sendBeacon e indexedDB | `frontend/tests/unit/eslint-rules.test.ts` | 18 formas proibidas em feature (`it.each`) + 4 casos de permissão por pasta | unit |
| Arquitetura (dependency-cruiser) | `frontend/tests/unit/architecture.test.ts` | `src` sem violação; 8 fixtures `arch-*`, cada uma dispara sua regra | unit |
| Tokens de tema (CSS) | `frontend/tests/unit/theme-css.test.ts` | 3: cada valor escuro declarado uma vez; dois gatilhos escuros; todos os tokens em `:root` | unit |
| Tela inicial (status do servidor) | `frontend/tests/unit/home.test.tsx` | `shows the health status from the API` | unit |
| Tema (sistema, troca, sem localStorage) | `frontend/tests/unit/theme.test.tsx` | `follows the system preference by default`, `switches explicitly and does not touch localStorage` | unit |

## Convenção de regressão

| Regra | Detalhe |
|---|---|
| Achados da revisão já corrigidos | Cobertos por testes nomeados em `tests/architecture` e `tests/security` (listados acima). M-1 também tem `test_reg_001` |
| A partir de agora | Todo bug ou finding corrigido ganha `test_reg_NNN_<slug>` em `tests/regression/` (backend ou frontend) |
| Primeiro da série | `test_reg_001_secret_key_not_in_error` (REG-001, achado M-1) |
| Próximo número | `002`; nunca reutilizar |

## Lacunas

| Item | Pasta | Status |
|---|---|---|
| Regressão backend | `backend/tests/regression/` | 1 arquivo (`test_reg_001`) |
| Regressão frontend | `frontend/tests/regression/` | vazia (.gitkeep) |
| Unit backend | `backend/tests/unit/` | vazia (.gitkeep) |
| E2E (login, mangá, página 5, tema, offline) | `frontend/tests/e2e/` | vazia; Playwright sem navegadores instalados |
| Auth, biblioteca, progresso, leitores | — | sem código, sem teste |
| Segurança do PLANO §6 (login, CSRF servidor, rate limit, IDOR, traversal, zip bomb) | `backend/tests/security/` | só cabeçalhos, 500, desconexão, `SECRET_KEY` |
| `FORWARDED_ALLOW_IPS` (compose, Dockerfile, `.env.example`) | — | sem teste; inspeção |
| Build da imagem Docker e compose | — | não validado |
| Scan de segredos (`scripts/check`) | — | só regex reduzido; gitleaks não executado |
| Teste de módulo fora do CODEMAP | `backend/tests/architecture/` | planejado; não existe (exigido por `docs/AGENTS.md`) |
