# Deploy (Docker)

Guia para subir o app em um servidor. Um único container: o backend (FastAPI) serve a API em `/api` e o frontend (PWA) em `/`, com os mesmos cabeçalhos de segurança.

Todos os comandos abaixo rodam na raiz do repositório. Para encurtar, os exemplos usam a variável `DC` (bash) ou `$DC` (PowerShell):

```bash
# bash / sh
DC="docker compose -p livros -f infra/compose.example.yml --env-file .env"
```

```powershell
# PowerShell
function dc { docker compose -p livros -f infra/compose.example.yml --env-file .env @args }
```

(`-p livros` fixa o nome do projeto; sem ele o nome vem da pasta do compose, `infra`. Os nomes de rede e volume abaixo assumem `-p livros`: `livros_default` e `livros_app-data`.)

## O que NÃO é responsabilidade do app

TLS/HTTPS, proxy reverso, domínio, firewall, VPN e rede. O app só publica HTTP na porta 8000 do container (em `127.0.0.1:8000` do host por padrão). Quem faz HTTPS na frente é o servidor. O proxy deve:

- terminar TLS (os cookies são `Secure`);
- repassar o cabeçalho `Host` original (o CSRF compara `Origin` com o `Host` quando `ALLOWED_ORIGINS` está vazio);
- enviar `X-Forwarded-For` (o app só confia nele para os IPs listados em `FORWARDED_ALLOW_IPS`).

## Pré-requisitos

- Docker Engine com Compose v2 (`docker compose version`).
- Uma pasta no host com a biblioteca. **Hoje só funcionam arquivos `.cbz` e pastas de imagens** (jpeg, png, webp, gif, avif); CBR, EPUB e PDF ainda não são lidos (Fase 4) e são ignorados pelo scan. Cada `.cbz` e cada pasta que contém imagens diretamente vira um item; subpastas são percorridas (até 16 níveis). Um `.cbz` com estrutura ZIP danificada é recusado no scan (ver §4). O container só lê (`:ro`); o usuário do container (UID 10001) precisa conseguir ler: arquivos legíveis por "outros" (`chmod -R a+rX`).
- Acesso à internet no build (imagens `node:24.21.0-slim` e `python:3.12.8-slim`, pacotes npm e pip).
- Saída de rede do container em `https` (porta 443) APENAS para os 7 hosts da allowlist de metadados: `api.mangadex.org`, `uploads.mangadex.org`, `graphql.anilist.co`, `s4.anilist.co`, `pt.wikipedia.org`, `www.googleapis.com`, `api.mymemory.translated.net`. Sem essa saída, os metadados não funcionam (o resto do app funciona). Se a política de rede não permitir, use `METADATA_ENABLED=false`, que desliga toda saída. O app não aceita outros hosts: não há variável para isso.

## 1. Configurar

```bash
cp .env.example .env
chmod 600 .env        # contém a SECRET_KEY; só o dono lê
```

Edite `.env` (nunca vai para o git nem para a imagem). Todo comando `docker compose` precisa de `--env-file .env`, inclusive `exec` (o Compose valida as variáveis obrigatórias a cada chamada); por isso o `DC` acima.

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SECRET_KEY` | sim | 32+ caracteres, 12+ distintos. Gere: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Trocar a chave invalida as sessões |
| `FORWARDED_ALLOW_IPS` | sim | IP ou CIDR do proxy como o container o vê (única fonte do IP real; ADR 0011). Sem valor o container não sobe. Veja "Primeira subida" |
| `COOKIE_SECURE` | não (`true`) | `true` em produção (HTTPS). `false` SOMENTE para teste local em `http://localhost` (cookie `Secure` não é aceito em http) |
| `ALLOWED_ORIGINS` | não (vazio) | Vazio = mesma origem (o normal, o app serve o frontend). Lista JSON de origens exatas só se o frontend estiver em outro domínio |
| `BIND_ADDRESS` / `HOST_PORT` | não (`127.0.0.1` / `8000`) | Endereço e porta publicados no host. Mantenha em loopback atrás de proxy |
| `NETWORK_SUBNET` | não (`172.30.77.0/24`) | Sub-rede fixa da rede do projeto. Mude só se colidir com a sua rede |
| `STOP_GRACE_PERIOD` / `PIDS_LIMIT` / `MEMORY_LIMIT` | não (`30s` / `256` / `1g`) | Tempo para encerrar (maior que `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`, 20 s), limite de processos e de memória do container |
| `LIBRARY_HOST_PATH` | não (`../library` relativo a `infra/`) | Pasta da biblioteca no host (montada em `/library`, somente leitura). Use caminho absoluto |
| `DATA_DIR` | não configurar (fixo no compose e na imagem: `/data`) | Pasta gravável do app: `app.db` e a pasta `covers/` (capas baixadas) ficam em `/data`, no volume `app-data`. Não mude |
| `METADATA_ENABLED` | não (`true`) | `true` liga a busca de capa e descrição nas fontes públicas. `false` desliga TODA saída de rede de metadados; a edição manual continua funcionando |
| `METADATA_PROVIDERS` | não (`mangadex,anilist,wikipedia,googlebooks`) | Fontes, em ordem de preferência. Nomes fixos: `mangadex`, `anilist`, `wikipedia`, `googlebooks`. Obra: MangaDex e AniList (capa e descrição); Wikipédia e Google Livros: só descrição, com casamento forte |
| `METADATA_LANGUAGES` | não (`pt-br,pt,en`) | Idiomas de descrição, do melhor para o pior (até 6 códigos) |
| `METADATA_HTTP_TIMEOUT_SECONDS` | não (`15`) | Tempo máximo, em segundos, de cada requisição às fontes (1 a 60) |
| `METADATA_MAX_PER_RUN` | não (`25`) | Séries processadas por execução de enriquecimento (1 a 1000). Para cobrir a biblioteca, rode de novo |
| `METADATA_TRANSLATE_ENABLED` | não (`true`) | Tradução automática da sinopse do inglês, último recurso, sempre marcada como "tradução automática" |
| Demais (`LOGIN_*`, `RATE_LIMIT_*`, `*_TTL_SECONDS`, `UVICORN_*`, `AUDIT_RETENTION_DAYS`) | não | Padrões seguros; veja os comentários no `.env.example` |

As variáveis `METADATA_*` estão no `.env.example` (comentadas, com os padrões) e são repassadas pelo compose com esses mesmos padrões. Os nomes e padrões acima foram conferidos em `backend/app/core/config.py`, `infra/compose.example.yml` e `.env.example`.

### Primeira subida e `FORWARDED_ALLOW_IPS`

O compose recusa `up` sem `FORWARDED_ALLOW_IPS`. Faça em duas etapas:

1. Primeira subida SÓ para testar: `FORWARDED_ALLOW_IPS=*` e `BIND_ADDRESS=127.0.0.1` (a porta fica acessível apenas no próprio servidor; nunca exponha com `*`). O app registra um aviso no log; é esperado.
2. Descubra o IP/CIDR do proxy que fala com o container (abaixo), troque o valor no `.env` e recrie: `$DC up -d` (o Compose recria o container quando o ambiente muda).

Como descobrir o endereço do proxy:

- O compose fixa a rede do projeto em `NETWORK_SUBNET` (padrão `172.30.77.0/24`), então o gateway (`172.30.77.1`) não muda quando o `down` recria a rede. Proxy no próprio host, publicado em `127.0.0.1:HOST_PORT`: use `FORWARDED_ALLOW_IPS=172.30.77.0/24` (ou o CIDR que você definiu em `NETWORK_SUBNET`). Confira com `docker network inspect livros_default --format "{{(index .IPAM.Config 0).Subnet}}"`.
- Proxy em outro container na mesma rede: o IP dele ou o mesmo CIDR.
- Confirmação: nos logs (`$DC logs backend`), cada requisição mostra o IP do cliente. Se todas mostram o mesmo IP (o do proxy), ele ainda não está listado.
- `*` só se a porta NÃO for alcançável diretamente (bind em loopback atrás do proxy).

## 2. Construir e subir

```bash
$DC build
$DC up -d
$DC ps          # esperar "healthy"
```

A imagem aplica as migrações do banco a cada subida (entrypoint) e recusa subir sem `SECRET_KEY` ou `FORWARDED_ALLOW_IPS`.

| Caminho no container | Origem | Observação |
|---|---|---|
| `/data` | volume nomeado `app-data` | `app.db` (SQLite em WAL: também `app.db-wal` e `app.db-shm`) e a pasta `covers/` (capas baixadas). Sobrevive a `down`; `down -v` APAGA tudo |
| `/library` | `LIBRARY_HOST_PATH`, `:ro` | Só leitura |
| `/tmp` | tmpfs | O resto do sistema de arquivos é somente leitura |

O container roda como usuário sem root (UID 10001), `read_only`, `cap_drop: ALL`, `no-new-privileges`, com limites de processos e memória.

## 3. Primeiro admin

Não existe cadastro pela web. Crie a conta pela CLI, com terminal (`-it`; a senha é pedida, nunca vai em argumento; política: 12 a 128 caracteres):

```bash
$DC exec -it backend python -m app.cli create-user <nome> --admin
```

Outros comandos: `create-user` (sem `--admin`), `reset-password <nome>`, `deactivate-user <nome>`, `list-users`, `migrate`, `purge`, `scan`.

## 4. Escanear a biblioteca e buscar metadados

Ordem recomendada: primeiro o `scan` (cria séries e capítulos), depois o `enrich` (busca capa e descrição). Pela CLI (síncrono, imprime contagens):

```bash
$DC exec backend python -m app.cli scan
$DC exec backend python -m app.cli enrich
```

Saída do `scan`: `scan finished: added=… updated=… unchanged=… removed=… skipped=… errors=N`, seguida de uma linha por motivo de erro (`CorruptArchive: N`, por exemplo). Código de saída 0 só se a varredura terminou.

Como ler os números:

| Campo | Significado |
|---|---|
| `errors` / motivo | Arquivos que falharam nesta varredura. O motivo é o nome da classe de erro, nunca o caminho. `CorruptArchive` = CBZ com estrutura ZIP danificada na origem |
| `skipped` | Arquivos que nenhum leitor atende hoje (CBR, EPUB e PDF ainda não são lidos) |
| `removed` | Itens que sumiram da pasta. Se a pasta ou o banco tiveram erro durante a varredura, nenhum item é marcado como ausente nessa rodada |

Um CBZ corrompido é recusado de propósito: o app não exibe capítulo quebrado. Um arquivo novo com erro não entra no catálogo. Um arquivo que já estava cadastrado e passou a falhar mantém o registro anterior até ser corrigido. Corrija ou substitua o arquivo na origem e rode o `scan` de novo. Na biblioteca do dono, 92 de 301 CBZ foram recusados por isso (relato do dono; a biblioteca não está no repositório). Os capítulos que faltam aparecem como lacunas na numeração.

### Metadados (capas e descrições)

O `enrich` busca capa e descrição nas fontes públicas da allowlist (ver §1). Ele:

- roda em uma execução por vez; cada execução cuida de até `METADATA_MAX_PER_RUN` séries (padrão 25). Para uma biblioteca grande, repita o comando;
- consulta, nesta ordem, MangaDex e AniList (capa e descrição da obra); depois Wikipédia pt e Google Livros, só com casamento forte de título; por último a tradução automática da sinopse;
- respeita as cotas públicas: a tradução (MyMemory) tem cota anônima pequena, cerca de 5 000 caracteres por dia por IP. Ao estourar, o tradutor fica quieto por 6 h e a sinopse fica em inglês. O Google Livros pode responder 429 (limite de uso); o app trata a fonte como indisponível e segue para a próxima;
- nunca sobrescreve série editada à mão (estado `manual`), nem com `--force`.

Comandos do `enrich`:

```bash
$DC exec backend python -m app.cli enrich                       # séries sem metadado e não encontradas há mais de 7 dias
$DC exec backend python -m app.cli enrich --series <id-da-serie> # uma série; o id é o UUID em /serie/<id> no app
$DC exec backend python -m app.cli enrich --force                # reconsulta também as já encontradas (nunca as manuais)
```

Saída: `enrich finished: matched=… not_found=… skipped=… errors=…`. Código de saída 0 só se terminou; 1 se os metadados estão desligados (`METADATA_ENABLED=false`), se a série não existe ou se já há uma execução em andamento.

Pelo app: o admin logado abre a biblioteca e toca em "Atualizar metadados". A execução roda em segundo plano (uma por vez; se já houver uma, o app informa). Para devolver uma série à automação, o admin usa "remover" no painel de metadados da série; a série volta ao estado sem metadado.

Pela API (admin logado; `POST /api/v1/library/scan` responde 202 e roda em segundo plano; acompanhe em `GET /api/v1/library/scan/status`). Como é uma escrita em `/api`, exige o token CSRF (`GET /api/v1/auth/csrf`, depois o cabeçalho `X-CSRF-Token` igual ao cookie `csrf_token`, e `Origin` da própria origem).

## 5. Atualizar

```bash
git pull
$DC build
$DC up -d
```

O `up -d` recria o container com a imagem nova; o volume `/data` é mantido e as migrações rodam sozinhas. Faça backup antes (seção 6). Os usuários podem precisar recarregar o PWA para pegar o novo service worker.

## 6. Backup e restauração de `/data` (SQLite em modo WAL)

Não copie `app.db` com o app rodando: em WAL parte dos dados está em `app.db-wal`. Use o backup online do SQLite (consistente, sem parar o app). O arquivo gerado contém hashes de senha e o log de auditoria: guarde fora do servidor e trate como sensível.

O backup cobre DUAS coisas em `/data`: o banco `app.db` e a pasta `covers/` (capas baixadas). Ambas entram nos comandos abaixo. Se `covers/` faltar no backup, o app não quebra: volta a mostrar a capa do primeiro capítulo legível; e o `enrich --force` (seção 4) baixa as capas de novo, porque sem `--force` as séries já `matched` não são reconsultadas.

**Backup, bash/sh:**

```bash
$DC exec backend python -c "import sqlite3; s=sqlite3.connect('/data/app.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close(); s.close()"
$DC cp backend:/data/backup.db "./backup-$(date +%F).db"
$DC exec backend python -c "import os; os.remove('/data/backup.db')"
$DC exec backend python -c "import os; os.makedirs('/data/covers', exist_ok=True)"
$DC cp backend:/data/covers "./backup-$(date +%F)-covers"
```

**Backup, PowerShell:**

```powershell
dc exec backend python -c "import sqlite3; s=sqlite3.connect('/data/app.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close(); s.close()"
dc cp backend:/data/backup.db ("./backup-" + (Get-Date -Format yyyy-MM-dd) + ".db")
dc exec backend python -c "import os; os.remove('/data/backup.db')"
dc exec backend python -c "import os; os.makedirs('/data/covers', exist_ok=True)"
dc cp backend:/data/covers ("./backup-" + (Get-Date -Format yyyy-MM-dd) + "-covers")
```

`docker cp` cria a pasta de destino com o conteúdo de `covers/`. Se o nome já existir (dois backups no mesmo dia), use outro nome: ele copiaria para dentro da pasta existente.

**Restauração** (com o app parado). Um container temporário monta o volume `/data` e a pasta de backup (`$PWD`, somente leitura). Ele restaura o banco (removendo `-wal` e `-shm` antigos), restaura `covers/` e devolve o dono `10001:10001` ao banco e às capas, com permissão restrita no banco. Se a pasta de capas do backup não existir, as capas são apenas removidas (o app usa a capa do primeiro capítulo). O mesmo comando serve em bash e PowerShell (troque `$PWD` por `${PWD}` no PowerShell):

```bash
$DC stop backend
docker run --rm -v livros_app-data:/data -v "$PWD":/backup:ro python:3.12.8-slim python -c "import glob, os, shutil; [os.remove(p) for p in glob.glob('/data/app.db-*')]; shutil.copyfile('/backup/backup-AAAA-MM-DD.db', '/data/app.db'); os.chown('/data/app.db', 10001, 10001); os.chmod('/data/app.db', 0o600); src='/backup/backup-AAAA-MM-DD-covers'; shutil.rmtree('/data/covers', ignore_errors=True); os.path.isdir(src) and shutil.copytree(src, '/data/covers'); [os.chown(p, 10001, 10001) for r, ds, fs in os.walk('/data/covers') for p in [r] + [os.path.join(r, n) for n in ds + fs]]"
$DC up -d
```

(Os `-wal`/`-shm` antigos precisam sair: pertenceriam ao banco anterior.) Confira com `$DC exec backend python -m app.cli list-users` e, se houve capas, abra uma série na biblioteca.

Estado destes comandos: **não executados** nesta revisão (só conferidos contra `backend/app/cli.py`, `infra/compose.example.yml` e `infra/entrypoint.sh`). Valide com um backup e uma restauração de teste antes de depender deles.

## 7. Logs e saúde

```bash
$DC logs -f backend
$DC ps
curl -s http://127.0.0.1:8000/api/v1/health      # {"status":"ok"}
```

O healthcheck chama `/api/v1/health` a cada 30 s. Os logs não contêm senhas nem tokens.

## 8. Teste local sem HTTPS (só desenvolvimento)

Para abrir em `http://localhost:8000` sem proxy: `COOKIE_SECURE=false`, `FORWARDED_ALLOW_IPS=*` (a porta fica só em loopback) e `BIND_ADDRESS=127.0.0.1`. Nunca use `COOKIE_SECURE=false` em produção.

## Troubleshooting

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Compose: `set FORWARDED_ALLOW_IPS ...` ou `set SECRET_KEY` | Variável ausente/vazia, ou faltou `--env-file .env` | Preencha o `.env` e use sempre o `DC` |
| Container sai logo com `entrypoint: ERROR ...` | Validação de `SECRET_KEY`/`FORWARDED_ALLOW_IPS` | Leia a mensagem em `$DC logs backend` |
| 429 ou bloqueio de login para todo mundo de uma vez | `FORWARDED_ALLOW_IPS` errado: todos os clientes parecem o proxy | Liste o IP/CIDR certo do proxy (seção "Primeira subida") |
| Login "funciona" mas a sessão não persiste / 403 após o login | Cookies `Secure` em http; ou o proxy não repassa `Host`/`Origin` | Use HTTPS no proxy; em teste local `COOKIE_SECURE=false`; garanta o `Host` original, ou liste a origem em `ALLOWED_ORIGINS` |
| 403 em POST (login, scan) | CSRF: sem cookie/cabeçalho `X-CSRF-Token`, ou `Origin` diferente do `Host` | O frontend faz isso sozinho; ao usar curl, siga a seção 4 |
| Biblioteca vazia depois do scan | Volume não montado ou ilegível para o UID 10001 | `$DC exec backend ls -la /library`; ajuste `LIBRARY_HOST_PATH` e permissões (`chmod -R a+rX`); com SELinux use `:ro,z` |
| `unable to open database file` / banco somente leitura após restaurar | `app.db` com dono errado | `chown 10001:10001` e `chmod 600` (seção 6) |
| `error: ... did you run migrate` na CLI | Banco ainda sem schema | `$DC exec backend python -m app.cli migrate` (o entrypoint já faz isso ao subir) |
| `SettingsError ... ALLOWED_ORIGINS` | Valor que não é JSON (ex.: `https://x`) | Use lista JSON: `["https://reader.exemplo.com"]` ou deixe vazio |
| `Pool overlaps with other one on this address space` | `NETWORK_SUBNET` colide com outra rede | Defina outro `NETWORK_SUBNET` no `.env` e ajuste `FORWARDED_ALLOW_IPS` |
| `/api/docs` não existe | Proposital: docs da API desligadas | — |
| Série sem capa depois de restaurar | `covers/` não estava no backup | O app mostra a capa do primeiro capítulo; para baixar de novo: `$DC exec backend python -m app.cli enrich --force` |
| `scan` com `errors` e motivo `CorruptArchive` | CBZ com estrutura ZIP danificada na origem | Corrija ou substitua o arquivo e rode `scan` de novo (seção 4) |
| `enrich`: saída com "disabled" ou código 1 e erro de metadados desligados | `METADATA_ENABLED=false` | Proposital; para buscar metadados, defina `true` no `.env` e recrie com `$DC up -d` |
| `enrich` com `errors` altos, ou metadados nunca chegam | Sem saída https para os 7 hosts da allowlist (política de firewall ou DNS) | Confira a saída do container (seção 1, "Pré-requisitos") ou desligue com `METADATA_ENABLED=false` |
| Tradução ficou em inglês | Cota anônima do MyMemory estourada (cerca de 5 000 caracteres por dia por IP) | Espere a cota voltar; as sinopses restantes ficam em inglês até lá |
| Página antiga depois de atualizar | Service worker em cache | Recarregar duas vezes ou fechar o PWA; `sw.js` e `index.html` sempre revalidam |

### Build falha com `SSL: UNEXPECTED_EOF_WHILE_READING` (DNS local)

Sintoma: `docker compose build` para ao baixar pacotes de `files.pythonhosted.org` com `SSL: UNEXPECTED_EOF_WHILE_READING`.

Causa observada: o DNS local resolveu `files.pythonhosted.org` para um IP interno (`100.127.127.77`, típico de filtro de DNS ou roteador), e a conexão TLS não chega ao PyPI.

Diagnóstico:

```bash
nslookup files.pythonhosted.org
```

Resposta esperada: endereços públicos (por exemplo `151.101.x.x`). Se aparecer um IP interno, o problema é o DNS.

Correção, em ordem de preferência:

1. Corrigir o DNS da rede ou do roteador para que o host resolva para o endereço público.
2. Configurar o DNS do Docker com o campo `dns` do `daemon.json` (Docker Desktop: Settings > Docker Engine), e reiniciar o Docker.
3. Só como contorno de build local, fixar o host no build (o IP deve ser o público correto, conferido com `nslookup`):

```bash
docker build --add-host files.pythonhosted.org:<ip correto> -f infra/Dockerfile -t <imagem> .
```

O contorno não muda a imagem nem o runtime; não use em servidor.

## Reprodutibilidade

As dependências Python da imagem são fixadas em `infra/constraints.txt`, gerado DENTRO de `python:3.12.8-slim` por `infra/gen_constraints.sh` (instruções no cabeçalho do script); o frontend usa `npm ci` com o `package-lock.json`. Ainda não há hashes nem digest das imagens base (pendência M8).
