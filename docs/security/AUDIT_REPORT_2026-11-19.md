# Relatório de Auditoria de Segurança — 2026-11-19

ID da auditoria: AUDIT-2026-11-19. Auditor: Claude Code (Sonnet 5.5), auditor interno. Alvo: Fase 1 do backend (`backend/`, `infra/`, `.env.example`).

## 1. Escopo
Dentro: auth (`api/auth.py`, `csrf.py`, `rate_limit.py`, `body_limit.py`, `security_headers.py`, `errors.py`, `deps.py`, `services/auth_service.py`, `domain/lockout.py`, `domain/auth.py`, `adapters/security/*`, `adapters/persistence/*`), biblioteca (`api/items.py`, `library.py`, `services/scan*.py`, `catalog.py`, `pages.py`, `adapters/storage/local.py`, `adapters/extractors/*`), config/composição, CLI, migrações, Dockerfile/compose/`.env.example`.
Fora: rede, VPN, TLS, servidor, proxy reverso; frontend (apenas `scripts/check` do frontend foi executado); Docker não foi construído (daemon indisponível).

## 2. Método
1. `scripts/check` na base: verde (741 testes, 1 pulado; todos os passos OK; ver fila).
2. Revisão manual do código do escopo.
3. Pentest dinâmico contra instâncias locais próprias (uvicorn em 127.0.0.1:18701-18704; SQLite e biblioteca em pasta temporária; `SECRET_KEY` de teste de 48 caracteres; `COOKIE_SECURE=false` só no HTTP local): A = limites padrão, proxy não confiável; B = CORS com origem permitida, limites relaxados; C = modo mesma-origem, limites relaxados, `X-Forwarded-For` confiável (simula proxy); D = banco sem migração, `COOKIE_SECURE` padrão, biblioteca ausente. Usuários criados com `python -m app.cli` (getpass simulado). Cliente: `httpx` e sockets crus.
4. Biblioteca hostil sintética (20 itens: zip-slip, caminho absoluto e com `\`, symlink interno, bomba por razão, 10001 entradas, 9500 entradas, falso `.cbz`, vazio, extensão falsa, polyglot JPEG+HTML, página de 60 MiB, pasta com página de 70 MiB, título com bidi/zero-width/aspas/SQL, nome de 150+ caracteres, junction para fora).

## 3. Ferramentas e versões
Python 3.14.10 (venv do backend); fastapi 0.165.0, starlette 1.10.0, uvicorn 0.54.0 (h11 0.16.0), pydantic 2.14.3, SQLAlchemy 2.1.9, alembic 1.20.1, argon2-cffi 25.1.0, PyJWT 2.15.1; bandit 1.9.4 (sem achados); `ruff --select S` (sem achados); pip-audit 2.10.1 (sem vulnerabilidades conhecidas; `reader-backend` local não auditável); `npm audit --omit=dev` 0, completo 4 moderadas (vite-plugin-pwa/minimatch/glob, informativo); semgrep e gitleaks **não instalados** (não executados).

## 4. Resultado resumido por severidade

| Severidade | Qtde | Findings |
|---|---|---|
| critical | 0 | — |
| high | 1 | FIND-2026-001 |
| medium | 2 | FIND-2026-002, FIND-2026-003 |
| low | 7 | FIND-2026-004, 005, 006, 007, 008, 009, 012 |
| info | 2 | FIND-2026-010, FIND-2026-011 |

Total: 12 findings (1 high, 2 medium, 7 low, 2 info). Confiança: 001 *likely* (parte estática, Docker não executado), 012 *likely* (só leitura de código), demais *confirmed*.

## 5. O que foi testado e se manteve (comprovado, sem finding)
- **Enumeração de usuário:** existente, inexistente, inativo, caixa, espaços, unicode, Kelvin sign, NUL, malformado e curto retornam status, corpo e cabeçalhos idênticos (401 `Invalid credentials`) e mesmo tempo (mediana 46-51 ms em todos). Usernames de 128 caracteres OK; 129 -> 422 genérico; senha 1024 OK / 1025 -> 422. Usuário inexistente também é bloqueado após 5 falhas, igual ao existente.
- **Lockout:** correta senha não burla o bloqueio; variações de caixa/espaço compartilham contador; rotacionar IPv6 dentro do /64 não burla; /64 diferentes contam separado (esperado); spray de usernames bloqueia o IP após 20; sucesso do atacante em conta própria não zera o contador por IP; XFF malformado ou lixo não burla (IP cai em "unknown" ou no cliente real). XFF/`X-Real-IP`/`Forwarded` são ignorados quando o proxy não é confiável (instância A).
- **CSRF** (40+ casos): sem token, token forjado, token válido de outra sessão só no cabeçalho (403), `Origin` nulo/forjado/subdomínio/userinfo/esquema, `Referer` forjado/`@`/subdomínio, `Sec-Fetch-Site` cross-site/same-site, `text/plain`/form/sem Content-Type (422, nenhuma ação), override de método (sem efeito), `GET` em `/login` (405). Preflight CORS: apenas a origem exata permitida recebe ACAO; `null`, outra origem, subdomínio, caixa diferente, esquema diferente e `/` final -> 400 sem ACAO.
- **Cookies:** `access_token` HttpOnly Path=/api; `refresh_token` HttpOnly Path=/api/v1/auth; `csrf_token` legível Path=/; todos `SameSite=Strict`, sem `Domain` (host-only), `Secure` presente com `COOKIE_SECURE` padrão (instância D). Tokens nunca no corpo. Logout apaga ambos.
- **JWT:** `alg:none` (incl. variações de caixa), HS256 com a `SECRET_KEY` crua, HS384/HS512, payload adulterado, `kid` malicioso (ignorado), claims ausentes (exp, iat, nbf, sub, sid, jti), exp/nbf, tipos errados (string, float, bool), `sid`/`sub` inexistentes, `sub` de outro usuário com `sid` alheio, `iat` anterior à troca de senha, token > 2048 -> todos 401. `Authorization: Bearer` não é aceito. Troca de senha, `reset-password` do CLI e desativação invalidam acesso e refresh na hora.
- **Refresh:** rotação, reuso revoga a família (e o acesso), expiração e TTL absoluto aplicados (manipulando o banco temporário), logout idempotente por qualquer um dos tokens. Observação sobre corrida: FIND-2026-005.
- **Mass assignment:** campos extras e tipos errados em login/troca de senha -> 422 genérico (strict + `extra=forbid`); corpo do 422 não ecoa entrada. JSON com chave duplicada: último vence (padrão).
- **Cabeçalhos de segurança** presentes em 200, 401, 403, 404 (API e fora da API), 405, 413, 422, 429, 307, 500 e na resposta de preflight; `Cache-Control: no-store` + `Pragma` em todo `/api` (404/405/422/413/429/500 inclusive).
- **Cache de imagens:** só `GET` em `/api/v1/items/<uuid>/pages/<n>` e `/cover` com 200/304 recebem `private, max-age=3600`. Tentativas de ampliar: `/pages/0/..`, `/pages/0/../`, `%2f..`, `;a=b`, `%00`, `.png`, `//`, barra final (307 `no-store`), `HEAD`/`POST` (405 `no-store`), erro 404 (`no-store`), `Range`, maiúsculas do UUID, `?x=1` (query não muda o resultado) -> nada de sensível ganhou cache; `/items/<id>`, `/items`, `/auth/me` sempre `no-store`.
- **Autorização/IDOR:** anônimo -> 401 em todas as rotas de itens e scan; usuário comum -> 403 em `/library/scan` e `/library/scan/status`; admin -> 202; segundo scan simultâneo -> 409. Biblioteca é global por desenho (sem itens por usuário nesta fase; progresso e preferências não existem ainda). IDs inválidos (maiúsculas aceitas e canonizadas, sem hífen, chaves, `urn:`, espaços, NUL, SQL, traversal, dígitos Unicode) -> 404 genérico; `n` com sinal, float, hex, dígito Unicode, vazio, gigante -> 404.
- **Injeção em `q`:** `%`, `_`, `\`, `' OR 1=1 --`, `UNION`, NUL, `%00`, bytes inválidos, emoji, mais de 100 caracteres -> comportamento literal ou 422; nenhum 500. `limit`/`offset` inválidos -> 422; `limit` alto é limitado a 100.
- **Corpo e HTTP:** Content-Length acima do limite -> 413; chunked acima do limite -> 413; Content-Length inválido/duplicado/negativo/gigante -> 400; TE bogus/duplicado/espaço antes de `:` -> 400; `Host` duplicado/ausente (HTTP/1.1) -> 400; cabeçalho de 70 KB e cookie gigante -> 400; JSON aninhado 30 mil níveis -> 400, 60 mil -> 413, 1000 -> 422; sem crash. Variantes de caminho no login (`//`, `/./`, `%2e`, `%6c`, barra dupla, `;`, `\`, maiúsculas, absolute-URI) nunca contornam CSRF/limite: ou 403/429 ou 404; `//api/...` e `/API/...` dão 404 (nenhuma rota sem middleware).
- **Rate limit:** auth (burst 10) e global (burst 200) funcionam; XFF/IPv6/caminho não contornam; 429 idêntico ao do lockout.
- **Arquivos hostis (scan):** zip-slip, caminho absoluto, `\` e symlink interno -> `UnsafePath` (4); não-zip e vazio -> `CorruptArchive` (2); falso por extensão -> `UnsupportedFormat`; bomba por razão, 10001 entradas e página de 70 MiB em pasta -> `ArchiveLimitExceeded` (3); junction para fora da biblioteca ignorada (não indexada); erros só como contagem por classe (`errors_by_reason`), sem caminho. Polyglot JPEG+HTML é servido como `image/jpeg` com `nosniff` e CSP (inofensivo). Títulos: bidi/zero-width removidos, `<`/`>` -> espaço, truncados a 200; aspas e SQL permanecem como texto no JSON (`application/json`). Respostas de item nunca trazem caminho nem nome de arquivo.
- **Vazamento em logs/erros:** grep nos logs do servidor (3 instâncias) por senhas de teste, `SECRET_KEY`, `argon2`, `eyJ`, cookies, caminhos da máquina -> 0 ocorrências. Falha de configuração (SECRET_KEY curta) não ecoa o valor. Banco sem migração -> 500 genérico (`{"detail":"Internal Server Error"}`), com cabeçalhos; stack só no log, sem parâmetros SQL. Biblioteca ausente -> 503 genérico (por código). Banco: `login_attempts` guarda só HMAC; `audit_log` sem senha/token/IP bruto.
- **SQLite sob carga:** 200 logins simultâneos, flood de 120 clientes (1239 tentativas) e scan: nenhum `database is locked`, nenhum 5xx.
- **Configuração padrão:** compose publica em `127.0.0.1`, `read_only`, `cap_drop ALL`, `no-new-privileges`; Dockerfile roda como usuário não root (uid 10001); `.dockerignore` exclui `.env*`, docs e testes; `SECRET_KEY` obrigatória sem padrão; `COOKIE_SECURE` padrão true. Falhas: FIND-2026-001, 010.

## 6. O que NÃO foi testado (ou só em parte)
- **Docker/compose reais:** daemon indisponível; `docker compose config` mostra a rede implícita `infra_default`, mas o gateway real não foi medido (FIND-2026-001 é *likely*). Build da imagem e `migrate` dentro dela não validados.
- **TLS/proxy/HSTS e `Secure` atrás de HTTPS:** fora de escopo; `Secure` verificado só pelo `Set-Cookie`.
- **CBR e EPUB/PDF:** extratores não existem na Fase 1 (só CBZ e pasta).
- **Symlink de arquivo na biblioteca:** o Windows da auditoria exige privilégio; só junction foi testado (o teste `test_local_storage.py:136` também é pulado aqui). Casos Linux (permissões, FIFO, `/proc`) não testados.
- **Slowloris/timeouts de cabeçalho e exaustão de conexões abertas:** dependem do uvicorn/proxy; só registrados (FIND-2026-010).
- **Memória real sob páginas de 64 MiB em paralelo:** só tempo medido; o pico de RAM é cálculo (FIND-2026-003).
- **Semgrep, gitleaks, SBOM:** ferramentas ausentes.
- **Frontend/PWA:** nenhum teste dinâmico do service worker ou do cliente nesta rodada (somente `scripts/check` do frontend verde).
- **Expiração real do access token (15 min) e refresh (30 dias):** simulados via banco/claims, sem esperar.
- **Cadeia de smuggling com proxy:** só o servidor uvicorn/h11 foi testado.
- **Cobertura de regressão (item 7 do protocolo):** os testes existentes `test_reg_001..005`, `tests/security/*` cobrem os controles fortes (CSRF, JWT, lockout sequencial, cache, headers). Faltam testes de **concorrência** (lockout, refresh, flood de login) e de configuração de infra; os novos `test_reg_006..017` da fila cobrem isso.
- Observação: o pipelining de requisições malformadas gera `LocalProtocolError` no h11 do uvicorn (log de exceção ao responder 400 com conexão em `MUST_CLOSE`); é comportamento da biblioteca, sem efeito no app.

## 7. Conclusão
Os controles centrais da Fase 1 resistiram a um teste adversarial amplo: não há bypass de autenticação, CSRF, IDOR, traversal, zip-slip, injeção ou vazamento de informação comprovados, e a base passa em `scripts/check`. Os riscos reais são de **disponibilidade e configuração**: o padrão de proxy do compose provavelmente colapsa todos os clientes em um IP (FIND-2026-001, alto), o login derruba a latência de toda a API sob flood (002) e a leitura de página de CBZ grandes amplifica CPU (003). Há endurecimentos de baixo risco (corrida do lockout, corrida do refresh, inflação do audit_log, política de senha) e observações informativas. Recomenda-se seguir a ordem de `REMEDIATION_QUEUE.md` e reexecutar os PoCs de `docs/security/poc/` no reteste.

Arquivos: `docs/security/findings/FIND-2026-001.md` a `012.md`, `docs/security/REMEDIATION_QUEUE.md`, `docs/security/poc/`.
