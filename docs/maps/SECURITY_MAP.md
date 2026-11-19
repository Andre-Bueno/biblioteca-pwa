# SECURITY_MAP

Estado: 2026-11-19. Fonte de requisitos: `docs/PLANO.md` §6. Decisões: ADR 0002 (segurança no app), ADR 0005 (padrões fechados) e ADR 0006 (cabeçalhos do middleware sobrepõem a rota). Convenção de testes de regressão: `TEST_MAP.md`.

## Implementado

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Clickjacking, sniffing, vazamento de referrer, APIs do navegador | Middleware de cabeçalhos: CSP sem `unsafe-inline`, nosniff, Referrer-Policy, Permissions-Policy | `backend/app/api/security_headers.py` | `backend/tests/security/test_security_headers.py` (CSP exata fixada) | Implementado |
| Cabeçalho de segurança relaxado pela rota | Middleware sempre sobrepõe cabeçalhos de mesmo nome da rota (ADR 0006) | `backend/app/api/security_headers.py` | `test_security_headers.py` (`test_preexisting_security_headers_are_replaced`) | Implementado; revisitar no leitor EPUB/PDF |
| Erro interno vazar detalhe ou sem cabeçalhos | Exceção não tratada vira 500 JSON genérico com cabeçalhos de segurança e `Cache-Control: no-store` | `backend/app/api/security_headers.py` | `test_security_headers.py` (`test_unhandled_exception_returns_generic_500_with_headers`) | Implementado |
| Erro após resposta iniciada | Erro real: log e reraise; desconexão do cliente: só debug; `CancelledError` propaga | `backend/app/api/security_headers.py` | `test_security_headers.py` (`test_real_error_after_start_is_logged_and_reraised`, `test_disconnect_after_start_is_reraised_without_error_log`, `test_cancelled_error_is_not_swallowed`) | Implementado |
| Segredo fraco ou ausente | `SECRET_KEY` obrigatória: ≥32 caracteres, ≥12 distintos, sem espaços nas pontas, sem bloco de ≤8 repetido; `create_app()` falha sem ela | `backend/app/core/config.py`, `backend/app/main.py` | `backend/tests/security/test_settings.py` | Implementado |
| `SECRET_KEY` no log de erro de validação (M-1) | `hide_input_in_errors=True`: o valor não aparece em `str`/`repr` do `ValidationError` | `backend/app/core/config.py` | `backend/tests/regression/test_reg_001_secret_key_not_in_error.py` (REG-001) | Corrigido |
| Exposição de rede da porta do app | Compose publica em `${BIND_ADDRESS:-127.0.0.1}` (loopback por padrão) | `infra/compose.example.yml`, `.env.example` | inspeção (sem teste) | Implementado (infra) |
| Confiança em cabeçalho de proxy (IP real) | Única fonte: uvicorn `--proxy-headers --forwarded-allow-ips $FORWARDED_ALLOW_IPS`. Compose e `.env.example`: `172.17.0.1`. `TRUSTED_PROXY_COUNT` removido | `infra/compose.example.yml`, `.env.example`, `infra/Dockerfile` | inspeção (sem teste) | Implementado no compose; Dockerfile em aberto (ver Pendências) |
| Segredo no contexto/imagem de build | `.dockerignore` exclui `.env*` (exceto `.env.example`), docs, testes, bancos | `.dockerignore` | inspeção (sem teste) | Implementado |
| Token em localStorage/sessionStorage (XSS) | ESLint bloqueia `localStorage` e `sessionStorage`, inclusive via `window`/`globalThis`/`self` | `frontend/eslint.config.js` | `frontend/tests/unit/eslint-rules.test.ts`; `theme.test.tsx` (tema não grava) | Implementado; indiretos dependem de revisão |
| Fetch disperso (CSRF/erros) | ESLint: `fetch` cru (inclusive `window.fetch` etc.) só em `shared/api-client` | `frontend/eslint.config.js` | `eslint-rules.test.ts` | Implementado; indiretos dependem de revisão |
| Rede por canal alternativo | ESLint: `XMLHttpRequest`, `WebSocket`, `navigator.sendBeacon` só em `shared/api-client`; `indexedDB` só em `shared/offline` | `frontend/eslint.config.js` | `eslint-rules.test.ts` | Implementado; indiretos (alias, desestruturação, `window.navigator.sendBeacon`) não detectados |
| HTML injetado (XSS) | ESLint `react/no-danger`, `no-eval`, `no-implied-eval`, plugin `security` | `frontend/eslint.config.js` | lint (`scripts/check`) | Implementado |
| CSRF (cliente) | Envia cabeçalho em POST/PUT/PATCH/DELETE; `credentials` same-origin, `include` só com origem externa configurada | `frontend/src/shared/api-client/client.ts`, `csrf.ts` | `frontend/tests/unit/api-client.test.ts` | Implementado (cliente) |
| Enumeração e detalhe de erro (429, 500, não-JSON) | Mensagem genérica; `Retry-After` lido; corpo não-JSON vira `ApiError`; `AbortError` propagado | `frontend/src/shared/api-client/errors.ts`, `client.ts` | `api-client.test.ts` | Implementado (cliente) |
| Cache de dados autenticados no SW | `runtimeCaching: []`; precache só do shell; `/api` fora do fallback | `frontend/vite.config.ts` | inspeção | Implementado |
| Verificação com falso OK | `check` falha sem rede por padrão; etapas puladas/parciais são declaradas | `scripts/check.ps1`, `scripts/check.sh` | não há teste automatizado | Implementado; `check.sh` só testado com bash do Git no Windows |
| Acoplamento entre camadas | Teste executa import-linter; violação quebra o teste | `backend/tests/architecture/test_layers.py` | `test_layers.py` (33 casos) | Implementado |

## Planejado (PLANO §6)

| Superfície / ameaça | Controle | Onde | Teste | Status |
|---|---|---|---|---|
| Brute force no login | Limite por conta e IP, atraso, bloqueio, resposta e tempo idênticos, log | `backend/app/api/`, `services/` | `tests/security/` | planejado |
| Senhas | Argon2id; política mínima; troca invalida sessões | `adapters/`, `services/` | — | planejado |
| Sessão | Access curto; refresh rotativo em cookie HttpOnly/Secure/SameSite; detecção de reuso; logout revoga | `api/`, `adapters/persistence/` | — | planejado |
| CSRF (servidor) | Token em toda escrita; checagem de Origin/Referer | `backend/app/api/` | `tests/security/` | planejado |
| CORS | Lista fixa (`ALLOWED_ORIGINS`), sem `*` com credenciais | `backend/app/main.py` (middleware não existe) | — | planejado (setting existe, sem middleware) |
| Cadastro público | Não existe; conta só pelo dono (CLI/endpoint admin) | — | — | planejado |
| Rate limit | Global e por rota (login, scan, páginas) | `backend/app/api/` | — | planejado |
| IP real para rate limit | Usar `request.client.host` após uvicorn; fonte única é `FORWARDED_ALLOW_IPS` | `infra/`, `backend/app/api/` | — | planejado |
| Cookies | `COOKIE_SECURE` (setting existe, sem uso) | `backend/app/core/config.py` | — | planejado |
| IDOR | Toda query filtrada por `user_id`; IDs opacos | `services/`, `adapters/persistence/` | `tests/security/` | planejado |
| Path traversal | Caminho nunca vem do cliente; `resolve()` + checagem de raiz | `adapters/storage/` | `tests/security/` | planejado |
| Zip bomb / zip-slip (CBZ/CBR/EPUB) | Limites de tamanho, entradas e razão; sem extração em disco | `adapters/extractors/` | `tests/security/` | planejado |
| XSS via EPUB | iframe `sandbox` sem `allow-scripts` | `frontend/src/features/reader-epub/` | e2e | planejado |
| CBR | Extrator externo com timeout, sem shell | `adapters/extractors/` | — | planejado |
| Entrada inválida | Pydantic estrito (`extra="forbid"`), limites | `backend/app/api/` | — | planejado |
| Corpo e Range grandes | Limite de tamanho; paginação obrigatória; timeouts | `backend/app/api/` | — | planejado |
| Cache de respostas autenticadas | `Cache-Control: no-store` em respostas autenticadas (hoje só no 500) | `backend/app/api/security_headers.py` | — | **pendente** |
| Dependências e segredos | pip-audit, bandit e npm audit no `check`; scan de segredos por regex; gitleaks configurado | `scripts/check.ps1`, `scripts/check.sh`, `scripts/gitleaks.toml` | — | parcial: gitleaks não instalado (nunca executado); semgrep e SBOM não existem |
| Logs e auditoria | Trilha de login, falhas, troca de senha, scan; sem dados sensíveis | `services/`, `AuditLog` | — | planejado |

## Pendências

| Item | Motivo | Ação |
|---|---|---|
| Quem serve o HTML da SPA (M5) | Afeta CSP e cabeçalhos do shell | Aguarda decisão do dono; questão aberta |
| Lockfile do backend e hashes no Dockerfile (M8) | Dockerfile instala por `pyproject.toml` | Fase 1 ou antes da publicação |
| **`FORWARDED_ALLOW_IPS` diverge entre Dockerfile e compose (M-3)** | `infra/Dockerfile` define `ENV FORWARDED_ALLOW_IPS=127.0.0.1`; compose e `.env.example` usam `172.17.0.1`. Rodar a imagem sem compose não confia no proxy do host (o proxy chega pelo gateway da bridge, nunca por 127.0.0.1) | Alinhar o padrão do Dockerfile ao compose ou remover o `ENV`; até lá, a imagem sem compose não aceita o proxy do host |
| Checagem de senha vazada (k-anonymity) | Exige serviço externo | Depende de autorização do dono |
| CAPTCHA (Turnstile/hCaptcha) | Exige serviço externo | Depende de autorização do dono |
| `Cache-Control: no-store` em respostas autenticadas | Não implementado (só no 500) | Implementar na Fase 1 |
| Contrato CSRF | Cliente usa cookie `csrf_token` e cabeçalho `X-CSRF-Token` (`VITE_CSRF_COOKIE_NAME`, `VITE_CSRF_HEADER_NAME`); backend ainda não emite o cookie nem valida o cabeçalho | Alinhar cliente e backend na Fase 1 |
| CSP da rota não pode ser relaxada | ADR 0006: middleware sobrepõe a rota | Revisitar no leitor EPUB/PDF (iframe, `sandbox`) e decidir override por rota (novo ADR) |
| `npm audit` completo: 4 vulnerabilidades moderadas | Via `vite-plugin-pwa` / `minimatch` (aviso em `scripts/check`, não bloqueia) | Avaliar atualização do `vite-plugin-pwa`; `--omit=dev` está OK |
| Build da imagem Docker | Não validado | Rodar build antes de publicar |
| gitleaks | Não instalado; `gitleaks.toml` nunca executado | Instalar e rodar no `check` |
