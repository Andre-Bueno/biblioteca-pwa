# infra/AGENTS.md

Só o empacotamento do app: `Dockerfile` e `compose.example.yml`. Contexto de build: raiz do repositório (`.dockerignore` na raiz).

**Fora de escopo:** rede, VPN/Tailscale, firewall, TLS, proxy e domínio. O servidor já está configurado e o app é público. Não criar regras de acesso por IP/VPN.

Regras do app no container:
- Rodar como usuário sem root; imagem com versão fixada; sem segredos na imagem (tudo por variável de ambiente).
- Biblioteca montada como volume somente leitura.
- Porta publicada em loopback por padrão (`BIND_ADDRESS=127.0.0.1`).
- Mudança aqui ⇒ atualizar `docs/maps/ARCHITECTURE.md`.

## Variáveis (modelo: `.env.example` na raiz)

| Variável | Padrão | Uso |
|---|---|---|
| `SECRET_KEY` | obrigatória | ≥32 caracteres, ≥12 distintos, sem espaços nas pontas, não pode ser bloco ≤8 repetido; sem ela o app não sobe |
| `ALLOWED_ORIGINS` | obrigatória no compose | Lista JSON de origens exatas; sem `*` |
| `BIND_ADDRESS` | `127.0.0.1` | Endereço do host onde a porta é publicada; `0.0.0.0` só sem proxy na frente |
| `HOST_PORT` | `8000` | Porta publicada no host |
| `FORWARDED_ALLOW_IPS` | `172.17.0.1` (compose) | Única fonte do IP real: IPs/CIDRs do proxy confiável (uvicorn `--forwarded-allow-ips`). Proxy no host chega pelo gateway da bridge (ex.: `172.17.0.1`, `172.16.0.0/12`), nunca `127.0.0.1`; `*` só se a porta não for acessível diretamente |
| `COOKIE_SECURE` | `true` | Sem uso no código ainda (cookies chegam na Fase 1) |

## Arquivo `.env`

- `docker compose` lê `.env` do diretório do compose (`infra/`), não da raiz.
- Opções: `infra/.env` ao lado do compose, ou `docker compose --env-file ../.env`.
- `.env` nunca vai para o git nem para a imagem (`.gitignore` e `.dockerignore`).

## Estado

- Dockerfile: `python:3.12.8-slim`, HEALTHCHECK em Python, `uvicorn --proxy-headers --forwarded-allow-ips`.
- Compose: `read_only`, `cap_drop: ALL`, `no-new-privileges`, `tmpfs /tmp`.
- Pendente: build da imagem não validado; sem lockfile do backend e sem hashes (M8).
