# ADR 0008: Modelo de autenticação e sessão (cookies HttpOnly, CSRF assinado, JWT curto e refresh rotativo)

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- ADR 0002 exige: sessão com access curto, refresh rotativo em cookie `HttpOnly; Secure; SameSite`, detecção de reuso (revoga a família), logout que revoga, CSRF com token e checagem de `Origin`/`Referer`.
- O frontend (ESLint) proíbe `localStorage`/`sessionStorage`: o token não pode ficar em JavaScript.
- Duas abas ou um retry após resposta perdida enviam o mesmo refresh duas vezes (FIND-2026-005).
- O app é público na web e atrás de proxy que termina TLS. Em desenvolvimento local o HTTP não tem `Secure`.

## Decisão

| Tema | Decisão |
|---|---|
| Access token | JWT HS256 (algoritmo fixo, nunca lido do cabeçalho), TTL `ACCESS_TOKEN_TTL_SECONDS` (900 s). Claims `sub`, `sid`, `jti`, `iat`, `nbf`, `exp`. Cookie `access_token`: HttpOnly, `Path=/api`, `SameSite=Strict`, `Secure` por `COOKIE_SECURE` |
| Validação do access | A cada requisição autenticada: usuário existe e está ativo, família (`sid`) não revogada, `iat` não anterior à última troca de senha. Revogação vale na hora |
| Refresh token | Opaco (`token_urlsafe(32)`), guardado só como SHA-256. Cookie `refresh_token`: HttpOnly, `Path=/api/v1/auth`, `SameSite=Strict`. Rotação a cada uso (consumo e sucessor na mesma transação). TTL 30 dias, teto absoluto da sessão 90 dias |
| Reuso | Reuso fora de `REFRESH_REUSE_GRACE_SECONDS` (padrão 10 s, máximo 60, 0 desliga) revoga a família e audita `token.reuse_detected`. Dentro da janela, emite sessão irmã sem revogar nada |
| CSRF | Cookie `csrf_token`: legível por JS (por desenho, double-submit), `Path=/`, `SameSite=Strict`, `Secure` por `COOKIE_SECURE`. Valor = nonce + HMAC-SHA256 com subchave. Toda escrita sob `/api` exige cabeçalho `X-CSRF-Token` igual ao cookie e com assinatura válida, além de `Origin` (ou `Sec-Fetch-Site` / `Referer`) de origem permitida. `Origin` repetido: 403 |
| Chaves | Uma subchave por finalidade, derivada por HKDF-SHA256 de `SECRET_KEY` (rótulos `access-jwt`, `csrf-token`, `login-attempts`). A chave crua nunca assina nada |
| Respostas | Login e refresh nunca devolvem token no corpo |
| Troca de senha | Revoga todas as famílias do usuário e abre uma sessão nova |
| Logout | Revoga a família identificada pelo refresh ou pelo access; idempotente; apaga `access_token` e `refresh_token` |
| Sem prefixo `__Host-` | `__Host-` exige `Path=/`, o que anularia o escopo estreito do refresh (`/api/v1/auth`). O nome `csrf_token` é contrato do cliente. `__Host-` exige `Secure`, que o HTTP de desenvolvimento não tem. Cookies host-only (sem `Domain`) + `SameSite=Strict` + `Path` + CSRF assinado cobrem as mesmas ameaças (cookie plantado por subdomínio irmão não forja token assinado) |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Token em `localStorage` | XSS lê o token; proibido pelo lint do frontend e pelo ADR 0002 |
| Access longo sem checagem no banco | Revogação de sessão só valeria após o TTL |
| Refresh como JWT sem estado | Não há como revogar nem detectar reuso |
| `__Host-` nos três cookies | Ver tabela (Path, nome do contrato, `Secure` obrigatório) |
| Double-submit sem assinatura | Cookie plantado por irmão de subdomínio ou rede passaria a checagem |

## Consequências

- Positivas: token nunca em JavaScript; revogação imediata; reuso de refresh detectado; CSRF não depende só de `SameSite`.
- Negativas:
  - Cada requisição autenticada lê o banco (usuário, família). Custo aceito para SQLite local.
  - Um ladrão que reapresenta o refresh dentro de 10 s não é detectado (janela de tolerância, FIND-2026-005).
  - Revogação e controle de lock dependem de estado do processo e do banco; o limitador de taxa é em memória (uma worker).
  - O token CSRF não é amarrado à sessão (FIND-2026-010, item 4): a defesa efetiva é a checagem de origem.
- Obrigações:
  - Rota autenticada usa `get_current_user` (ou `require_admin`). Não criar outra forma de autenticação.
  - Mudar algoritmo, cookies, janela de reuso ou o modelo de revogação exige novo ADR.

Complementa ADR 0002 (cookies, CSRF, sessão). Não altera ADR 0001 a 0007.
