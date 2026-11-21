# backend/AGENTS.md

Python 3.12 · FastAPI · SQLAlchemy + Alembic · pydantic-settings · PyJWT · argon2-cffi. Arquitetura Hexagonal leve.

## Camadas e dependência

```
api  →  services  →  domain
          ↓
        ports  ←  adapters
```
- `domain/`: entidades e regras puras. Não importa FastAPI, SQLAlchemy, Pydantic, Starlette, HTTPX, PyJWT, Argon2 nem Alembic.
- `ports/`: interfaces (Protocol). Existem (20 arquivos em `ports/`, sem `__init__.py`): `user_repository`, `refresh_token_repository`, `login_attempt_store`, `token_service`, `password_hasher`, `audit_log`, `clock`, `rate_limiter`, `storage`, `extractor`, `book_reader`, `item_repository`, `progress_repository`, `preferences_repository`, `series_repository`, `cover_store`, `http_gateway`, `metadata_provider`, `translator`, `update_notifier`.
- `services/`: casos de uso. Dependem de `domain` e `ports`. Não importam adapters, HTTP, `app.core`, `app.composition` nem libs de infra. Configuração entra por injeção (`AuthConfig`), lida só na composição.
- `adapters/`: implementam os ports (SQLAlchemy, Argon2, PyJWT, disco, extratores).
- `api/`: routers, schemas, middlewares de borda e dependências de autenticação. Sem regra de negócio e sem SQL; chama um service e mapeia o erro para HTTP genérico.
- `cli.py`: entrada administrativa. Só alcança adapters via `composition`.
- `composition.py`: `Container` (lazy, sob trava) monta ports → adapters. Usado por `api/deps.py` (via `app.state.container`) e `cli.py`. `main.py` monta o app e os middlewares.

Libs proibidas por camada (import-linter, `pyproject.toml`):

| Camada | Não importa |
|---|---|
| domain | fastapi, sqlalchemy, pydantic, pydantic_settings, starlette, httpx, jwt, argon2, alembic, e as camadas `ports`, `services`, `adapters`, `api`, `core`, `main`, `composition` |
| ports | fastapi, starlette, sqlalchemy, pydantic, pydantic_settings, jwt, argon2, alembic, e `services`, `adapters`, `api`, `core`, `main`, `composition` |
| services | fastapi, starlette, sqlalchemy, pydantic, pydantic_settings, jwt, argon2, alembic, e `adapters`, `api`, `core`, `main`, `composition` |
| core | `api`, `services`, `adapters`, `main` |
| adapters | fastapi, starlette, `api`, `services`, `main`, `composition` (adapters podem usar jwt, argon2, alembic) |
| api | sqlalchemy, jwt, argon2, alembic, `adapters`, `composition` (exceção: `api.deps` → `composition`) |
| main | sqlalchemy, alembic, argon2, jwt, `adapters`, `services`, `ports`, `domain` (indireto via `composition` permitido) |
| cli | sqlalchemy, `adapters` (indireto via `composition` permitido) |

Violação = `tests/architecture/test_layers.py` falha (executa import-linter de verdade; 8 contratos em `pyproject.toml`). `unmatched_ignore_imports_alerting = "error"`: exceção que não casa com nenhum import também quebra.

## Regras

- Tipado (`mypy --strict`); `ruff` para lint e formatação.
- Config por variável de ambiente; nunca commitar `.env` nem conteúdo real.
- Mudança de schema ⇒ nova revisão Alembic; nunca editar migração aplicada.
- API versionada; mudança incompatível = nova versão + ADR.
- Novo endpoint ⇒ schema de entrada e saída, teste de autorização (IDOR), linha em `docs/maps/API.md`.
- Rota autenticada usa `get_current_user`; rota de admin usa `require_admin`. Não criar outra forma de autenticação.
- Escrita sob `/api` passa pelo CSRF automaticamente (middleware); não há exceção por rota.
- Toda resposta de `/api` sai com `no-store`, exceto a exceção de imagem (ADR 0010). Rota não escolhe `Cache-Control`.
- Novo formato de arquivo ⇒ novo `Extractor` em `adapters/extractors/`, registrado em `registry.py`, sem alterar services.
- Escrita de usuário é alvo específico (CAS), nunca "grava o objeto lido antes" (`UserRepository`).
- Logs sem senha, token ou dados pessoais.

## Segurança do app (serviço público)

Não implementar controles de rede, VPN ou allowlist de IP; o servidor cuida disso. O app resiste a qualquer cliente anônimo. Controles atuais (detalhes em `docs/maps/SECURITY_MAP.md`):

- **Login:** bloqueio por par (IP, conta), por conta em todos os IPs e por IP, com reserva atômica antes do hash (ADR 0009). Resposta idêntica para conta inexistente e senha errada. Falhas registradas com HMAC.
- **IP real:** só uvicorn com `FORWARDED_ALLOW_IPS` (obrigatória). O app lê `scope["client"]` via `api/http_utils.client_ip` e nunca cabeçalhos de proxy (ADR 0011).
- **Senhas:** Argon2id; política de 12–128 com username, repetição, sequência e lista curta. Troca de senha revoga todas as sessões.
- **Sessão:** access JWT HS256 (15 min), validado no banco a cada requisição; refresh opaco rotativo em cookie `HttpOnly` com janela de tolerância de 10 s; reuso fora dela revoga a família; logout revoga (ADR 0008).
- **CSRF:** cookie `csrf_token` assinado + cabeçalho `X-CSRF-Token` + `Origin`/`Sec-Fetch-Site`/`Referer`. CORS só com lista exata (`ALLOWED_ORIGINS`), nunca `*` com credenciais.
- **Cadastro:** não existe. Conta só pela CLI (`create-user`). Não criar rota pública de registro nem de recuperação de senha.
- **Saída de rede (metadados):** única exceção autorizada à regra 7 da raiz (ADR 0015). Só `adapters/http/safe_gateway.py` abre conexão de conteúdo; lista fixa de 8 hosts (`api.mangadex.org`, `uploads.mangadex.org`, `graphql.anilist.co`, `s4.anilist.co`, `pt.wikipedia.org`, `www.googleapis.com`, `api.mymemory.translated.net`, e `api.github.com` só para a checagem de release, ADR 0018 proposto); https/443; sem redirecionamento; IP público verificado e conexão fixada a ele; sem cookies; User-Agent genérico. Só título limpo e sinopse pública saem. `METADATA_ENABLED=false` troca o gateway por um que não abre socket.
- **Webhook de atualização:** única saída fora do `SafeGateway` (ADR 0018, proposto). `adapters/http/webhook_notifier.py` envia POST assinado (HMAC-SHA256) para `UPDATE_WEBHOOK_URL`, que só vem da configuração. http só em rede de loopback, privada ou CGNAT, e só com `UPDATE_WEBHOOK_ALLOW_HTTP`; link-local é sempre recusado. O app nunca acessa o Docker.
- **Livros (EPUB):** capítulo sanitizado por allowlist, servido com CSP própria só para a rota do capítulo (pelo middleware, ADR 0017); o frame do leitor não tem `allow-scripts`. Fontes e SVG nunca são servidos; DRM é recusado.
- **Metadados e capas:** casamento forte obrigatório para fontes só de descrição; tradução é último recurso e marcada; capa gravada só com UUID da série (`DATA_DIR/covers`, ADR 0016); descrição sanitizada no domínio e exibida como texto puro pelo frontend. Busca ao vivo de candidatos (`GET .../metadata/candidates`): 10 por minuto por usuário, verificada antes de qualquer saída de rede.
- **Limites:** rate limit por IP em memória, só em `/api`: global, e mais estrito só em `/api/v1/auth/login`, `refresh`, `logout` e `change-password` (`me` e `csrf` ficam só no global; `test_reg_019`); corpo máximo 64 KiB (413); concorrência limitada no Argon2 (2 slots) e na leitura de páginas (4 slots), com 503 + `Retry-After`. Rate limit por rota (scan, páginas) não existe.
- **Cabeçalhos:** CSP explícita (ADR 0012), `nosniff`, `Referrer-Policy`, `Permissions-Policy` sobrepostos pelo middleware (ADR 0006); `no-store` em `/api`; exceção de cache só para página e capa autenticadas (ADR 0010).
- **Progresso e preferências:** toda consulta filtra pelo `user_id` do token; `percent`, `finished` e `updated_at` são do servidor; upsert atômico, último a gravar vence (ADR 0013). Cliente não envia esses campos (`extra=forbid`).
- **Frontend servido:** `api/spa.py` serve `FRONTEND_DIST_DIR` só fora de `/api` (GET/HEAD); caminho validado e sem symlink; ADR 0012. `Range` existe só para esses arquivos estáticos (`FileResponse`); não há rota de arquivo para EPUB/PDF ainda.
- **Validação:** schemas Pydantic `strict` e `extra=forbid`; erro de validação genérico (422 sem eco).
- **Entrada:** `rel_path` nunca sai da API; caminho só resolvido em `LocalStorage`; ID opaco UUID; `redirect_slashes=False`.
- Todo controle novo precisa de teste em `tests/security/` (ex.: N falhas ⇒ bloqueio; POST sem CSRF ⇒ 403).

## Versão e atualização (`APP_VERSION`, `UPDATE_*`)

Variáveis lidas em `core/config.py` (ADR 0018). A checagem só roda numa imagem de release (`APP_VERSION` diferente de `dev`); o padrão do compose é `UPDATE_CHECK_ENABLED=true`.

| Variável | Padrão | Uso |
|---|---|---|
| `APP_VERSION` | `dev` | Versão em execução (vem do build da imagem). `dev` desliga a checagem |
| `UPDATE_CHECK_ENABLED` | `true` | Liga a consulta à última release |
| `UPDATE_REPOSITORY` | `Andre-Bueno/biblioteca-pwa` | `owner/name` consultado em `api.github.com` |
| `UPDATE_CHECK_INTERVAL_HOURS` | `6` | Intervalo do cache da consulta (1 a 168) |
| `UPDATE_WEBHOOK_URL` | vazio | Destino do webhook (https; http só com `ALLOW_HTTP` e rede do operador). Par obrigatório com o segredo |
| `UPDATE_WEBHOOK_SECRET` | vazio | Segredo HMAC; ≥ 32 caracteres, sem espaço nas pontas. Igual ao `UPDATE_HOOK_SECRET` do receptor |
| `UPDATE_WEBHOOK_ALLOW_HTTP` | `false` | Permite http só se todo endereço resolvido for loopback, privado ou CGNAT |

Regras: `GET /system/version` só devolve detalhe ao admin; nenhuma rota lê ou mostra a URL ou o segredo; o aviso no frontend é texto puro com link https.

## Testes (`backend/tests/`)

`unit/` (services com falsos) · `integration/` (API e banco) · `regression/` (`test_reg_NNN_*`) · `security/` (authz, traversal, zip bomb, cookies, cache, lockout) · `architecture/` (import-linter). Auxiliares: `conftest.py`, `fakes.py`, `auth_fakes.py`, `library_env.py`. Regras em `tests/AGENTS.md`.

Rode `scripts/check` antes de entregar. Se não rodou, diga que não rodou.
