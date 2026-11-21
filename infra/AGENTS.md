# infra/AGENTS.md

Só o empacotamento do app: `Dockerfile` (multi-stage: build do frontend + runtime), `entrypoint.sh`, `constraints.txt` (deps Python e setuptools/wheel fixados, gerado DENTRO de `python:3.12.8-slim` por `gen_constraints.sh`) e `compose.example.yml`. Um único container: o backend serve o frontend (`FRONTEND_DIST_DIR=/app/static`). Guia de operação: `docs/DEPLOY.md`. Contexto de build: raiz do repositório (`.dockerignore` na raiz).

**Fora de escopo:** rede, VPN/Tailscale, firewall, TLS, proxy e domínio. O servidor já está configurado e o app é público. Não criar regras de acesso por IP ou VPN.

Regras do app no container:
- Usuário sem root; imagem com versão fixada; sem segredos na imagem (tudo por variável de ambiente).
- Biblioteca montada como volume somente leitura.
- Porta publicada em loopback por padrão (`BIND_ADDRESS=127.0.0.1`).
- `FORWARDED_ALLOW_IPS` é obrigatória e não tem padrão (ADR 0011). Não voltar a colocar um valor-padrão em compose, Dockerfile ou `.env.example`.
- Mudança aqui ⇒ atualizar `docs/maps/ARCHITECTURE.md` e `docs/maps/CODEMAP.md`.

## Variáveis (modelo: `.env.example` na raiz)

Obrigatórias (sem padrão; o compose e o `entrypoint.sh` recusam subir sem elas):

| Variável | Uso |
|---|---|
| `SECRET_KEY` | ≥ 32 caracteres, ≥ 12 distintos, sem espaço nas pontas, sem bloco ≤ 8 repetido; sem ela o app não sobe |
| `FORWARDED_ALLOW_IPS` | IP ou CIDR do proxy que conecta ao container, como visto pelo container. Única fonte do IP real (uvicorn `--forwarded-allow-ips`). Errado: todos os clientes viram o proxy. `*` só se a porta não for alcançável diretamente |

Compose, com padrão:

| Variável | Padrão | Uso |
|---|---|---|
| `ALLOWED_ORIGINS` | `[]` (vazia = mesma origem) | Lista JSON de origens exatas (`https://host[:porta]`); sem `*`, caminho ou barra final. Deve ser JSON válido também para `compose exec` (por isso o padrão `[]`) |
| `NETWORK_SUBNET` | `172.30.77.0/24` | Sub-rede fixa da rede do projeto (o gateway não muda no `down`); base para `FORWARDED_ALLOW_IPS` de proxy no host |
| `STOP_GRACE_PERIOD` / `PIDS_LIMIT` / `MEMORY_LIMIT` | `30s` / `256` / `1g` | Encerramento (> `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`), processos e memória do container |
| `LIBRARY_HOST_PATH` | `../library` | Pasta da biblioteca no host, montada em `/library:ro` |
| `BIND_ADDRESS` / `HOST_PORT` | `127.0.0.1` / `8000` | Endereço e porta publicados no host |
| `COOKIE_SECURE` | `true` | Flag `Secure` de `access_token`, `refresh_token` e `csrf_token`; `false` só em HTTP local |
| `DATABASE_URL` | `sqlite:////data/app.db` | Banco no volume `app-data` (`/data`) |
| `LIBRARY_PATH` | `/library` | Montado de `../library` (relativo a `infra/`), `:ro` |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | Vida do access token |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000` | Vida do refresh token (30 dias), rotativo |
| `SESSION_ABSOLUTE_TTL_SECONDS` | `7776000` | Teto absoluto da sessão (90 dias), mesmo com rotação |
| `REFRESH_REUSE_GRACE_SECONDS` | `10` | Janela de tolerância para refresh reapresentado (0 a 60; 0 desliga) |
| `AUDIT_RETENTION_DAYS` | `180` | Eventos de auditoria mais antigos são apagados (login, refresh ou `purge`) |
| `LOGIN_MAX_FAILURES_ACCOUNT` | `5` | Falhas por par (IP, conta) |
| `LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS` | `15` | Falhas por conta em todos os IPs (sem login recente do IP) |
| `LOGIN_MAX_FAILURES_IP` | `20` | Falhas por IP, qualquer conta |
| `LOGIN_FAILURE_WINDOW_SECONDS` | `900` | Janela de contagem |
| `LOGIN_LOCKOUT_SECONDS` | `300` | Bloqueio inicial; dobra a cada bloqueio seguido |
| `LOGIN_LOCKOUT_MAX_SECONDS` | `3600` | Teto do bloqueio |
| `LOGIN_TRUSTED_IP_WINDOW_SECONDS` | `2592000` | Por quanto tempo um login bem-sucedido torna o IP confiável para aquela conta (30 dias) |
| `RATE_LIMIT_API_PER_MINUTE` / `RATE_LIMIT_API_BURST` | `600` / `200` | Limite global por IP em `/api` (balde em memória, por processo) |
| `RATE_LIMIT_AUTH_PER_MINUTE` / `RATE_LIMIT_AUTH_BURST` | `20` / `10` | Limite de `/api/v1/auth/*` (soma-se ao global) |
| `DATA_DIR` | `/data` (imagem e compose) | Pasta gravável do servidor; capas em `DATA_DIR/covers` (ADR 0016). Padrão do `Settings` fora da imagem: `./data` |
| `METADATA_ENABLED` | `true` | `false` desliga TODA saída de rede de metadados (gateway sem socket); edição manual continua |
| `METADATA_PROVIDERS` | `mangadex,anilist,wikipedia,googlebooks` | Fontes em ordem de preferência; nomes fixos (ADR 0015) |
| `METADATA_TRANSLATE_ENABLED` | `true` | Tradução automática da sinopse, último recurso e marcada |
| `METADATA_LANGUAGES` | `pt-br,pt,en` | Idiomas de descrição, do melhor para o pior (até 6 códigos) |
| `METADATA_HTTP_TIMEOUT_SECONDS` | `15` | Tempo total de cada requisição externa (1 a 60) |
| `METADATA_MAX_PER_RUN` | `25` | Séries processadas por execução de enriquecimento (1 a 1000) |
| `UVICORN_LIMIT_CONCURRENCY` | `100` | Conexões abertas antes de responder 503 (Dockerfile) |
| `UVICORN_TIMEOUT_KEEP_ALIVE` | `5` | Segundos de keep-alive ociosa (Dockerfile) |
| `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` | `20` | Segundos para encerrar com graça (Dockerfile) |

Fixas na imagem (não são variáveis de operador):

| Variável | Valor | Motivo |
|---|---|---|
| `FRONTEND_DIST_DIR` | `/app/static` | Frontend compilado servido pelo app (`api/spa.py`) |
| `DATABASE_URL` / `LIBRARY_PATH` | `sqlite:////data/app.db` / `/library` | Banco no volume e biblioteca montada |
| `MIGRATIONS_DIR` | `/app/migrations` | Localiza `env.py` do Alembic dentro do container (`pip install .` não deixa `migrations/` ao lado do pacote) |

Só com padrão no `Settings` (não passam pelo compose; podem ser definidas no `.env` ou no ambiente):

| Variável | Padrão | Uso |
|---|---|---|
| `MAX_BODY_BYTES` | `65536` | Corpo acima disso: 413 |
| `EXTRACTOR_MAX_ENTRIES` | `10000` | Entradas por CBZ ou pasta |
| `EXTRACTOR_MAX_TOTAL_UNCOMPRESSED_BYTES` | `4294967296` (4 GiB) | Total descompactado |
| `EXTRACTOR_MAX_PAGE_BYTES` | `67108864` (64 MiB) | Tamanho de uma página |
| `EXTRACTOR_MAX_COMPRESSION_RATIO` | `100` | Razão de compressão (entradas ≥ 64 KiB) |
| `MIGRATIONS_DIR` | repo `backend/migrations` | Usado só fora da imagem |
| `FRONTEND_DIST_DIR` | vazio (não serve nada) | Se definido e sem `index.html`, o app não sobe |
| `ALLOWED_ORIGINS` | vazia | Ver acima |

### Relações entre as variáveis (validadas no startup; falham sem subir)

| Regra | Motivo |
|---|---|
| `LOGIN_LOCKOUT_MAX_SECONDS` ≥ `LOGIN_LOCKOUT_SECONDS` | Bloqueio nunca diminui |
| `LOGIN_MAX_FAILURES_ACCOUNT` < `LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS` | A conta em todos os IPs exige mais falhas que o par |
| `LOGIN_MAX_FAILURES_ACCOUNT` ≤ `LOGIN_MAX_FAILURES_IP` | O limite por IP não pode ser menor que o por par |
| `LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS` > máximo de falhas que um único IP consegue numa janela | Um IP sozinho não pode bloquear a conta para todos. O máximo é calculado por `max_failures_from_one_address()` com `ACCOUNT`, `FAILURE_WINDOW`, `LOCKOUT` e `LOCKOUT_MAX` (ADR 0009) |
| `SESSION_ABSOLUTE_TTL_SECONDS` ≥ `REFRESH_TOKEN_TTL_SECONDS` | O refresh não pode viver além do teto da sessão |
| `REFRESH_REUSE_GRACE_SECONDS` ≤ 60 | Janela de tolerância limitada (ADR 0008) |
| `SECRET_KEY` sem bloco repetido e com ≥ 12 caracteres distintos | Ver acima |

## Arquivo `.env`

- `docker compose` lê `.env` do diretório do compose (`infra/`), não da raiz.
- Opções: `infra/.env` ao lado do compose, ou `docker compose --env-file ../.env`.
- `.env` nunca vai para o git nem para a imagem (`.gitignore` e `.dockerignore`).

## Primeiro admin (banco e contas)

Com o container no ar, nesta ordem (`-it`: o prompt de senha usa `getpass`, que exige terminal):

| Passo | Comando |
|---|---|
| 1. Criar o schema | `docker compose exec backend python -m app.cli migrate` |
| 2. Criar o admin | `docker compose exec -it backend python -m app.cli create-user <nome> --admin` |

Demais comandos: `create-user` (sem `--admin`), `reset-password`, `deactivate-user`, `list-users`, `scan` (varre `LIBRARY_PATH`) e `purge` (apaga tentativas, famílias mortas e auditoria antiga). Nenhum aceita senha em argumento.

## Estado

- Dockerfile em 3 estágios: `node:24.21.0-slim` (build do frontend com `npm ci`), `python:3.12.8-slim` como estágio de instalação (`pip install --prefix`, com `PIP_CONSTRAINT`) e `python:3.12.8-slim` como runtime (cópia única do pacote em site-packages, pip/setuptools/wheel removidos, usuário 10001). `ENTRYPOINT entrypoint.sh` valida `SECRET_KEY` e `FORWARDED_ALLOW_IPS`, roda `migrate` e faz `exec uvicorn --no-server-header --proxy-headers --forwarded-allow-ips` com os limites. HEALTHCHECK em Python. Sem `ENV FORWARDED_ALLOW_IPS`.
- Compose: `read_only`, `cap_drop: ALL`, `no-new-privileges`, `tmpfs /tmp`, `restart: unless-stopped`, porta em loopback, volume `app-data`, sub-rede fixa, `stop_grace_period`, `pids_limit` e `mem_limit`.
- Validado em 2026-11-20: build, `up`, healthy, `/`, `/assets/*`, fallback SPA, login (CSRF), scan e listagem, não-root, fs somente leitura.
- Validado em 2026-11-21 com a biblioteca real (relatado pelo dono): build com `ENV DATA_DIR=/data`, scan, séries, enriquecimento e capas gravadas em `/data/covers`. Falha de build por DNS: ver `docs/DEPLOY.md` (troubleshooting).
- Pendente: lockfile com hashes (M8); digest das imagens; CI inexistente (`.github/` não existe).
