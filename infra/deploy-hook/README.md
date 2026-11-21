# deploy-hook: receptor do webhook de atualização

> **Implementação de REFERÊNCIA.** O agente de deploy do dono pode adaptá-la ou substituí-la, desde que **preserve todas as verificações** descritas em "Verificações obrigatórias". O app nunca acessa o Docker: ele só avisa o admin e, quando o admin aprova, chama este webhook. Quem atualiza o servidor é este receptor, no host.

Roda **no host do servidor** (não no container do app). Só biblioteca padrão do Python 3.10+; sem dependências, sem shell.

## Contrato

O app faz:

```
POST <UPDATE_WEBHOOK_URL>            (o caminho do receptor é /update)
Content-Type: application/json
X-Update-Timestamp: <unix, segundos>
X-Update-Signature: sha256=<hex(HMAC_SHA256(secret, timestamp + "." + corpo_bruto))>

{"event":"update_requested","repository":"owner/name","tag":"v1.2.3",
 "image":"ghcr.io/owner/name:v1.2.3","requested_at":"<ISO8601 UTC>","nonce":"<32 hex>"}
```

- `corpo_bruto` são exatamente os bytes enviados; `timestamp` é o texto do cabeçalho. A assinatura é minúscula.
- `image` deve ser `ghcr.io/<repository em minúsculas>:<tag>`.
- Resposta: **202** (aceito; a atualização roda em segundo plano). Demais códigos: 400 (payload inválido, tag, imagem, nonce), 401 (assinatura ou timestamp), 403 (repositório diferente do configurado), 404, 405, 409 (`replay` ou `busy`), 411, 413, 415, 503 (armazém de nonces cheio). O corpo da resposta é só `{"error":"<codigo>"}` ou `{"status":"accepted"}`.

## Verificações obrigatórias

1. Assinatura HMAC-SHA256 comparada em tempo constante (`hmac.compare_digest`), ANTES de interpretar o JSON.
2. Janela de timestamp de 300 s (passado e futuro).
3. Nonce de 32 hex nunca reutilizado (arquivo com TTL de 600 s; só é gravado depois da assinatura válida).
4. `repository` igual ao configurado (`UPDATE_HOOK_REPOSITORY`).
5. `tag` por regex estrita `^v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$` (casamento total, só dígitos ASCII, até 64 caracteres) e `image` coerente com repositório e tag.
6. Corpo de no máximo 16 KiB (rejeitado pelo `Content-Length`, antes de ler); `Content-Type: application/json`; sem `Transfer-Encoding`.
7. Sem shell: `docker compose pull` e `docker compose up -d` são listas de argumentos. A tag nunca vai para a linha de comando: só entra no `.env` (gravação atômica), e só depois de validada.
8. Uma atualização por vez (lock); o 202 sai na hora e o trabalho segue em segundo plano.
9. Depois do `up -d`, espera o container ficar `healthy` (timeout de 180 s). Se falhar (pull, up ou healthcheck), **restaura o `.env` original** e sobe de novo a versão anterior.
10. Escuta só em `127.0.0.1` por padrão; o log não contém segredo, assinatura nem corpo.
11. O ambiente repassado ao `docker` não contém `UPDATE_HOOK_*` nem `APP_TAG` (um `APP_TAG` do ambiente venceria o do `.env`).

## Configuração (variáveis de ambiente)

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `UPDATE_HOOK_SECRET` | sim | - | Segredo compartilhado com o app (mínimo 32 bytes). Gere: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `UPDATE_HOOK_REPOSITORY` | sim | - | `owner/name` aceito (ex.: `Andre-Bueno/biblioteca-pwa`) |
| `UPDATE_HOOK_COMPOSE_FILE` | sim | - | Caminho ABSOLUTO do `compose.example.yml` (ou o seu) |
| `UPDATE_HOOK_ENV_FILE` | sim | - | Caminho ABSOLUTO do `.env` do compose (onde o `APP_TAG` é gravado) |
| `UPDATE_HOOK_PROJECT` | não | `livros` | Nome do projeto do compose (`-p`) |
| `UPDATE_HOOK_SERVICE` | não | `backend` | Serviço cuja saúde é verificada |
| `UPDATE_HOOK_BIND` / `UPDATE_HOOK_PORT` | não | `127.0.0.1` / `9110` | Endereço e porta do receptor |
| `UPDATE_HOOK_NONCE_FILE` | não | `~/.deploy-hook/nonces.json` | Armazém de nonces |
| `UPDATE_HOOK_HEALTH_TIMEOUT` | não | `180` | Segundos esperando o `healthy` (5 a 1800) |
| `UPDATE_HOOK_DOCKER` | não | `docker` | Binário do Docker |

O segredo não vai para o repositório: coloque em um arquivo só do dono (`chmod 600`) lido por `EnvironmentFile=`, ou no cofre de senhas.

## Rodar

```bash
UPDATE_HOOK_SECRET=... UPDATE_HOOK_REPOSITORY=Andre-Bueno/biblioteca-pwa \
UPDATE_HOOK_COMPOSE_FILE=/srv/livros/infra/compose.example.yml \
UPDATE_HOOK_ENV_FILE=/srv/livros/.env \
python3 infra/deploy-hook/receiver.py
```

Exemplo de unidade systemd (ajuste usuário e caminhos; o usuário precisa poder usar o Docker, o que equivale a root no host: por isso o receptor só escuta em loopback e valida tudo):

```ini
[Unit]
Description=Receptor do webhook de atualizacao (biblioteca-pwa)
After=docker.service

[Service]
User=deploy
EnvironmentFile=/etc/deploy-hook.env
ExecStart=/usr/bin/python3 /srv/livros/infra/deploy-hook/receiver.py
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
```

O app e o receptor precisam se enxergar: o mais simples é expor o receptor atrás do proxy HTTPS que já existe no servidor (`https://.../update` apontando para `127.0.0.1:9110`) e usar essa URL em `UPDATE_WEBHOOK_URL`. Se preferir falar direto do container ao host, use o IP do gateway da rede do projeto em `UPDATE_HOOK_BIND` e libere só esse caminho no firewall (rede e firewall são do servidor, fora do escopo do app).

## Testar a assinatura à mão

```bash
BODY='{"event":"update_requested","repository":"Andre-Bueno/biblioteca-pwa","tag":"v0.1.0","image":"ghcr.io/andre-bueno/biblioteca-pwa:v0.1.0","requested_at":"2026-11-21T12:00:00Z","nonce":"'$(python3 -c "import secrets;print(secrets.token_hex(16))")'"}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$UPDATE_HOOK_SECRET" -hex | sed 's/^.* //')
curl -i -X POST http://127.0.0.1:9110/update -H 'Content-Type: application/json' \
  -H "X-Update-Timestamp: $TS" -H "X-Update-Signature: sha256=$SIG" --data-binary "$BODY"
```

Isto de fato inicia a atualização para a tag informada; use uma tag que exista.

## Testes

```bash
python -I -m unittest discover -s infra/deploy-hook -p "test_*.py"
```

Sem rede e sem Docker (runner falso). Fazem parte do `scripts/check` e do CI.
