# PLANO — Leitor de Mangás e Livros (PWA para iOS)

> Nome provisório: **Biblioteca**. Status: Fase 1, Fase 2 e leitor de mangá (MVP) entregues; Fase 3 parcial; agrupamento em séries e metadados de fontes públicas entregues (2026-11-21, ADR 0014 a 0016). Última atualização: 2026-11-21 (ver `docs/history/2026-11-21-series-e-metadados.md`).

## 1. Decisões já tomadas

| Tema | Decisão |
|---|---|
| Instalação iOS | **PWA** (Safari → "Adicionar à Tela de Início"). Sem Mac, sem conta Apple. |
| Formatos | Mangá: **CBZ, CBR, pasta de imagens**. Livros: **EPUB**. **PDF**. |
| Servidor | Criado do zero, **uso individual**, mas modelado para multiusuário depois. |
| Backend | **Python + FastAPI**. |
| Frontend | **React + TypeScript + Vite** (PWA). |
| Padrão | **Backend: Arquitetura Hexagonal (Ports & Adapters) leve. Frontend: por feature.** Ver §3 e ADR 0001. |
| Fontes externas (estilo extensões do Tachiyomi) | **Fora do escopo** por ora (risco legal e quebra constante). Deixar um ponto de extensão (`SourceProvider`). |

## 2. Requisitos

**Funcionais (MVP)**
1. Login do usuário.
2. Biblioteca: listar, buscar, filtrar por tipo (mangá/livro/PDF) e por status (lendo, concluído).
3. Escanear a pasta do servidor e catalogar o conteúdo (metadados, capa, contagem de páginas).
4. Leitores: mangá (página a página, RTL/LTR, modo webtoon vertical), EPUB (fonte, tamanho, tema) e PDF.
5. **Acompanhamento de leitura**: página/posição atual, percentual, última leitura, "continuar lendo".
6. **Modo claro / escuro / sistema**, persistido por usuário.
7. Instalável e com cache offline do que já foi aberto.

**Depois do MVP:** download offline explícito, coleções/tags, favoritos, estatísticas de leitura, multiusuário, OPDS, sincronização entre dispositivos com resolução de conflito, fontes externas.

**Não funcionais**
- **Segurança** (§6) · **Escalabilidade** (§7) · **Manutenibilidade e rastreabilidade** (§8).

## 3. Arquitetura

Decisão em `docs/adr/0001-arquitetura-hexagonal-e-frontend-por-feature.md`. MVC foi descartado: não encaixa numa API JSON e não permite trocar adaptadores nem incluir formatos novos sem tocar no núcleo.

**Backend: Arquitetura Hexagonal (Ports & Adapters) leve**

| Camada | Pasta | Responsabilidade |
|---|---|---|
| API (entrada) | `backend/app/api/` | Routers FastAPI, schemas HTTP (Pydantic), autenticação. Camada fina, **sem regra de negócio**. |
| Services (casos de uso) | `backend/app/services/` | Escanear biblioteca, salvar progresso, obter página. Usa `domain` e `ports`. |
| Domain (núcleo) | `backend/app/domain/` | Entidades e regras puras (Item, Progress, Locator). Sem framework. |
| Ports (interfaces) | `backend/app/ports/` | Contratos: repositório, storage, extrator de formato, fonte externa. |
| Adapters (saída) | `backend/app/adapters/{persistence,storage,extractors}/` | Implementam `ports`: banco (SQLAlchemy), disco, leitores CBZ/CBR/EPUB/PDF. |

Regra de dependência (sentido único, **dependências apontam para dentro**):
- `api → services → domain`
- `services → ports → domain`
- `adapters → ports` (adapters implementam ports; services nunca importam adapters)
- `domain` não importa nenhuma outra camada nem framework.

**Frontend: por feature**

| Pasta | Conteúdo |
|---|---|
| `frontend/src/app/` | Bootstrap, rotas, providers, shell da PWA. Compõe as features. |
| `frontend/src/features/<nome>/` | Feature completa: telas, hooks, estado e chamadas à API. Ex.: `auth`, `library`, `reader-manga`, `reader-epub`, `reader-pdf`, `progress` (só README; código em `shared/`), `theme` (na prática em `shared/theme`). |
| `frontend/src/shared/` | Cliente HTTP, componentes genéricos, utilitários, cache offline/service worker. |

Regra de dependência:
- **Feature não importa feature.** Código comum vai para `shared/`.
- `features/` e `shared/` nunca importam `app/`.

**Teste de arquitetura (impõe as regras)**

| Lado | Ferramenta | Regra checada |
|---|---|---|
| Backend | `import-linter` em `backend/tests/architecture/` | Direção de dependência acima; `services` e `api` não importam `adapters`. |
| Frontend | dependency-cruiser ou eslint boundaries (escolha pendente na Fase 0) | Feature não importa feature; `shared` não importa feature nem `app`. |
| Backend | teste em `backend/tests/architecture` (planejado; hoje conferência manual) | Módulo fora do `CODEMAP` falha o teste (`docs/AGENTS.md`). |

Nunca desativar o teste de arquitetura: corrigir o código.

### Estrutura de pastas

```
LIVROS/
├─ AGENTS.md                  # regras para qualquer agente de IA
├─ README.md
├─ CHANGELOG.md               # histórico de versões
├─ docs/
│  ├─ PLANO.md                # este arquivo
│  ├─ maps/                   # MAPAS: arquitetura, código, dados, API, rotas
│  ├─ adr/                    # decisões de arquitetura (0001-*.md)
│  ├─ history/                # diário por sessão/mudança relevante
│  └─ security/               # protocolo de auditoria + findings + remediação
├─ backend/
│  ├─ app/{api,services,domain,ports,adapters/{persistence,storage,extractors}}/
│  ├─ migrations/             # Alembic
│  └─ tests/{unit,integration,regression,security,architecture}/
├─ frontend/
│  ├─ src/{app,features,shared}/
│  └─ tests/{unit,e2e,regression}/
├─ infra/                     # apenas Dockerfile e compose do app (rede/TLS/VPN são do servidor)
└─ scripts/                   # check.ps1/sh: lint+tipos+testes+scan
```

## 4. Modelo de dados (inicial)

- `User` (id, email, password_hash, role, theme_pref, created_at)
  - **Nota (Fase 1A):** implementado com `username` no lugar de `email` (ADR 0007), e com `is_active`, `updated_at` e `password_changed_at`. Tabelas em `backend/migrations/versions/0001_users_and_auth.py`.
- `Item` (id, type[manga|book|pdf], title, path_rel, format, page_count, cover, content_hash, added_at)
  - **Nota (Fase 1):** tabela `items` na migração `0002` (`rel_path` único, `size`, `mtime_ns`, `page_count`, `missing`) e adaptador `SqlAlchemyItemRepository`. Sem coluna `cover`: a capa é a primeira página. API em `/api/v1/items`.
- `Series` (agrupa volumes/capítulos de um mangá) e `Chapter` (opcional). **Nota (2026-11-21):** implementado como série por pasta com capítulos em `items` (ADR 0014); metadados em `series` (migrações `0005` a `0007`).
- `ReadingProgress` (user_id, item_id, **locator**, percent, device_id, updated_at, finished) — chave única `(user_id, item_id)`
  - `locator`: manga/PDF = índice da página; EPUB = CFI.
  - Conflito entre dispositivos: vence o maior `updated_at`; o servidor define o relógio. **Nota (Fase 3):** implementado como último a gravar vence, sem comparar timestamps do cliente (ADR 0013). `percent` e `finished` são calculados no servidor.
  - **Nota (Fase 3):** tabela `reading_progress` na migração `0004` (e `users.reading_direction`).
- `Session` / `RefreshToken` (revogáveis): implementado como família de `refresh_tokens` (ADR 0008), sem tabela de sessão própria.
- `AuditLog` (login, falhas, troca de senha, conta): implementado; escaneamento ainda não gera evento.

## 5. API (contrato)

REST versionada em `/api/v1`. Documentação da API: mapa manual em `docs/maps/API.md` por ora; OpenAPI/Swagger **desligados** no app (`docs_url`, `redoc_url`, `openapi_url` = None em `backend/app/main.py`). Pode ser reavaliado via export em build.
Principais: `POST /auth/login`, `GET /items`, `GET /items/{id}`, `GET /items/{id}/pages/{n}` (imagem), `GET /items/{id}/file` (EPUB/PDF com *Range*), `PUT /progress/{item_id}`, `GET /progress/continue`, `POST /library/scan`, `GET/PUT /me/preferences`.
Estado (2026-11-20): implementados todos, exceto `GET /items/{id}/file` (Fase 4). Lista completa em `docs/maps/API.md`.

## 6. Segurança (requisito de primeira classe)

Ameaças específicas deste projeto e controles:

**Premissa:** o app é um **serviço público na web**. O servidor (Docker, rede, VPN/Tailscale, TLS, firewall) já está configurado e **não é escopo deste projeto**. Não haverá bloqueio por VPN/IP. Toda a segurança é **dentro da aplicação**, que deve se defender sozinha de qualquer cliente anônimo da internet. A única suposição sobre o ambiente: o app roda atrás de um proxy que termina TLS (por isso cookies `Secure` e IP real via cabeçalho confiável configurável).

| Risco | Controle dentro do app |
|---|---|
| Brute force / credential stuffing no login | Limite por conta **e** por IP; atraso progressivo e bloqueio temporário após N falhas; resposta idêntica para usuário inexistente e senha errada (sem enumeração); tempo de resposta constante; log de tentativas; CAPTCHA opcional após limite (Turnstile/hCaptcha). |
| Senhas | Argon2id; política mínima de senha; checagem contra senhas vazadas (k-anonymity) opcional; troca de senha invalida sessões. |
| Sessão | Access token curto + refresh rotativo em cookie `HttpOnly; Secure; SameSite=Lax/Strict`; detecção de reuso do refresh (revoga a família); logout revoga. |
| **CSRF** | `SameSite` + token CSRF (double-submit ou sincronizado) em toda requisição que altera estado; checagem de `Origin`/`Referer`; CORS por lista fixa e sem `*` com credenciais. |
| Cadastro | **Não existe cadastro público.** Contas só são criadas pelo dono (admin), via CLI/script ou endpoint exclusivo de admin. Sem rota de "registrar" nem "esqueci a senha" aberta; reset de senha feito pelo admin. |
| Abuso / DoS na camada de aplicação | Rate limit global e por rota (login, scan, páginas); limite de tamanho de corpo e de Range; paginação obrigatória; timeouts. |
| Autorização / IDOR | Toda query filtrada por `user_id`; IDs opacos; testes dedicados por endpoint. |
| Path traversal ao servir arquivos | Caminho nunca vem do cliente; `resolve()` + checagem de raiz. |
| Zip bomb / arquivo malicioso (CBZ/CBR/EPUB) | Limite de tamanho descompactado, nº de entradas e razão de compressão; sem extração em disco; sem zip-slip. |
| XSS (inclusive via EPUB e metadados) | EPUB em iframe `sandbox` sem `allow-scripts`; saída escapada; CSP estrita emitida pelo app. |
| CBR (RAR) | Extrator externo com timeout/limites e sem shell, ou conversão para CBZ no scan. |
| Cabeçalhos de segurança | CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Cache-Control em respostas autenticadas — emitidos pelo próprio app. |
| Validação de entrada | Schemas Pydantic estritos em tudo; limites de tamanho; rejeitar campos extras. |
| Dependências / segredos | `pip-audit`, `npm audit` e `bandit` no `check`; scan de segredos (regex reduzida; `gitleaks` configurado, não instalado). Planejados: `semgrep`, SBOM. Segredos só por variável de ambiente. |
| Logs e auditoria | Sem dados sensíveis; trilha de auditoria de login, falhas, troca de senha, scan. |

**Fluxo com a IA terceira (auditora) e o agente corretor** — detalhado em `docs/security/AUDIT_PROTOCOL.md`:

```
Auditor externo lê AGENTS.md + docs/security/AUDIT_PROTOCOL.md
   → roda testes, SAST, pentest em ambiente local/staging
   → grava findings em docs/security/findings/FIND-AAAA-NNN.md (formato fixo)
   → gera docs/security/REMEDIATION_QUEUE.md (fila priorizada)
Agente corretor (eu) lê a fila
   → corrige 1 finding por vez, com teste de regressão
   → atualiza status do finding, CHANGELOG e docs/history
Auditor re-testa e fecha
```

## 7. Escalabilidade

- Começar simples: **SQLite (WAL) + disco local**, mas com SQLAlchemy/Alembic e `storage/` por interface (`StorageBackend`), para trocar por Postgres e S3/MinIO sem tocar nos services.
- Backend sem estado (JWT) → réplicas atrás de proxy.
- Miniaturas e páginas pré-processadas em cache em disco (chave = `content_hash`).
- Escaneamento em tarefa de fundo, incremental (por hash/mtime), não bloqueia a API.
- Entrega de imagens com ETag/Cache-Control e Range para PDF/EPUB.
- Fontes externas entram por `SourceProvider` (plugin), sem alterar o núcleo.

## 8. Mapas, histórico e regressão

**Mapas (`docs/maps/`)** — fonte única para humanos e agentes localizarem tudo:
- `ARCHITECTURE.md` (diagrama de camadas e fluxo), `CODEMAP.md` (arquivo → responsabilidade), `DATAMODEL.md` (ER), `API.md` (manual; OpenAPI desligado), `ROUTES.md` (telas do front), `SECURITY_MAP.md` (superfícies de ataque e controles), `TEST_MAP.md` (feature → testes que a cobrem).
- Regra: **mudou código → atualiza o mapa na mesma entrega.** Planejado: teste em `tests/architecture` que falha se um módulo novo não estiver no `CODEMAP.md` (hoje, conferência manual).

**Histórico**
- `CHANGELOG.md` (Keep a Changelog + SemVer), `docs/adr/` (uma decisão por arquivo, imutável), `docs/history/AAAA-MM-DD-*.md` (o que foi feito, por quê, o que ficou pendente).

**Regressão**
- Todo bug corrigido ganha um teste em `tests/regression/` com ID (`test_reg_012_...`) referenciando o finding/issue.
- `scripts/check` roda: lint, tipos (mypy/tsc), testes (pytest, vitest), arquitetura (import-linter, dependency-cruiser), SAST (bandit), auditoria de dependências (pip-audit, npm audit) e scan de segredos. Nada entra sem passar, mas hoje o gate é manual: **CI (`.github/`) é planejado e não existe**. **semgrep é planejado e não está no `check`.**
- E2E (Playwright) cobrindo: login, abrir mangá, parar na página 5 e retomar, alternar tema, offline.

## 9. Roteiro por fases

| Fase | Entrega | Pronto quando |
|---|---|---|
| 0 | Fundação: repositório git, AGENTS.md, docs/maps, `scripts/check`, Docker (CI planejado) | `check` roda verde num projeto vazio |
| 1 | Backend núcleo: auth, modelos, migrações, scan de CBZ/pasta, API de itens e páginas | Testes + auditoria básica passam |
| 2 | Front base: PWA, login, biblioteca, tema claro/escuro | Instala no iPhone e lista a biblioteca |
| 3 | **Leitor de mangá + progresso** (parei na página 5) | Fecha, reabre e continua na mesma página, em 2 dispositivos |
| 4 | EPUB e PDF, CBR | Leitura e progresso nos 3 formatos |
| 5 | Offline e endurecimento de segurança | 1ª auditoria externa concluída; findings críticos/altos zerados |
| 6 | Multiusuário, coleções, estatísticas, OPDS | — |
| 7 | Avaliar fontes externas | Decisão registrada em ADR |

### Fase 0: estado (2026-11-19)

| Item | Estado |
|---|---|
| `AGENTS.md`, `docs/AGENTS.md`, `docs/maps/`, ADRs 0001-0005, `CHANGELOG.md` | Entregue |
| Scaffold backend (FastAPI, `create_app()`, `GET /api/v1/health`) e frontend (PWA Vite/React/TS) | Entregue |
| Import-linter (backend) e dependency-cruiser (frontend) com teste de arquitetura | Entregue |
| `SECRET_KEY` validada no startup; cabeçalhos de segurança no erro 500 | Entregue |
| `scripts/check.ps1` e `scripts/check.sh` com `gitleaks.toml` | Entregue (gitleaks não instalado: regex reduzida) |
| `infra/Dockerfile` e `infra/compose.example.yml` | Entregue, build da imagem **não validado** |
| Lockfile do frontend (`package-lock.json`) | Entregue |
| Lockfile do backend e hashes no Dockerfile (M8) | **Sobra** (Fase 1, antes de publicar) |
| Repositório git | **Sobra** (não inicializado nesta pasta) |
| CI (`.github/`) | **Sobra** (planejado) |
| `semgrep` no `check` | **Sobra** (planejado) |
| Instalar e rodar `gitleaks` no `check` | **Sobra** |
| Teste de módulo fora do `CODEMAP` (`tests/architecture`) | **Sobra** (planejado) |
| Decisão M5: quem serve o HTML da SPA (FastAPI ou proxy) | **Sobra**: aguarda decisão do dono; se mudar a arquitetura, novo ADR |
| Validar `check.sh` em Linux real | **Sobra** |

### Fase 1: estado (2026-11-19)

Status: **concluída (backend)**, com pendências abaixo. Frontend não iniciou a Fase 2.

| Item | Estado |
|---|---|
| 1A: banco e usuários (domínio, `UserService`, SQLite WAL, migração `0001`, CLI admin, Argon2id, política de senha) | Entregue (ADR 0007) |
| 1B: biblioteca, núcleo (domínio, portas, scan incremental, `LocalStorage`, extratores CBZ e pasta) | Entregue |
| Autenticação e sessão (`/api/v1/auth`, cookies, JWT, refresh rotativo, CSRF, CORS, rate limit, lockout, limite de corpo, `no-store`) | Entregue (ADR 0008, 0009, 0010) |
| Persistência de `Item`, API de itens e páginas, scan por API e CLI | Entregue (migrações `0002`, `0003`) |
| `FORWARDED_ALLOW_IPS` obrigatória (M-3) | Entregue (ADR 0011) |
| Auditoria de 2026-11-19 (12 findings) e correções | Corrigido; todos `fixed` (nenhum `verified`); FIND-2026-009 `open` (decisão do dono) |
| `ComicInfo.xml` | Ignorado; parser pendente (biblioteca segura a decidir) |
| Extratores CBR, EPUB e PDF | Fase 4 (não iniciados) |
| Lockfile do backend e hashes no Dockerfile (M8) | Pendente (versões fixas em `pyproject.toml`) |
| Build da imagem e `migrate` dentro dela | Não validado |
| Reverificação ao vivo do FIND-2026-002 e reteste dos PoCs | Pendente (auditor) |
| Decisão do dono sobre FIND-2026-009 (lock por conta em IP novo) | Pendente |
| Quem serve o HTML da SPA (M5) | Resolvido em 2026-11-20 (ADR 0012) |

### Fase 2: estado (2026-11-20)

| Item | Estado |
|---|---|
| PWA base (Vite, React, TypeScript), manifest, meta tags de iOS, `skipWaiting` desligado, sem cache de `/api` | Entregue |
| Login (`/login`) e guarda de rota com 4 estados | Entregue |
| Biblioteca: listar, buscar, filtrar por tipo, "continuar lendo", "carregar mais" | Entregue |
| Tema claro, escuro e sistema, salvo no servidor | Entregue (ADR 0013) |
| Servir o frontend pelo backend (M5) | Resolvido (ADR 0012) |
| Filtro por status (lendo, concluído) | **Pendente** |
| Instala no iPhone e lista a biblioteca | **Não validado** (iOS real e service worker não provados) |

### Fase 3: estado (2026-11-20)

Status: **parcial**.

| Item | Estado |
|---|---|
| Leitor de mangá: RTL, LTR e vertical; toque, deslize, teclado; zoom; pré-carregamento limitado | Entregue (MVP) |
| Progresso: API (`/progress/*`), salvamento com debounce e `keepalive`, retomada, "continuar lendo" | Entregue (ADR 0013) |
| Sentido de leitura salvo no servidor (`/me/preferences`) | Entregue |
| Fecha, reabre e continua na mesma página | Validado no navegador (relato do dev) |
| Mesma leitura em 2 dispositivos | **Não validado** |
| Reinício de item concluído ("reler do início") | Pendente (decisão do dono) |
| E2E: login, página 5 e retomada, tema, offline | **Pendente** (`frontend/tests/e2e/` vazio) |

### Pós-MVP: estado (2026-11-21)

| Item | Estado |
|---|---|
| Agrupamento em séries por pasta; capítulos com número e ordem natural; migração `0005` | Entregue (ADR 0014) |
| Série em `/serie/:id`; próximo e anterior capítulo no leitor; "continuar" no detalhe | Entregue |
| Metadados de fontes públicas: capa e descrição em pt-BR (MangaDex, AniList, Wikipédia, Google Livros, tradução MyMemory marcada) | Entregue (ADR 0015); Google Livros respondeu 429 na validação |
| Capas em `DATA_DIR/covers`, servidas pelo app | Entregue (ADR 0016) |
| Gestão de metadados pelo admin (busca, escolher, editar, remover; CLI `enrich`) | Entregue |
| Validação com a biblioteca real (série do dono) | Relatada pelo dono; ver histórico |
| Filtro por status na biblioteca (lendo, concluído) | Pendente |
| Arquivos corrompidos (92 de 301 CBZ, relatado): recuperação opcional | Pendente (decisão do dono) |
| Reinício de série concluída; mesma série em dois dispositivos | Pendente |
| iOS real, service worker e instalação do PWA | Não validados |
| Proxy e HTTPS reais | Não validados (fora de escopo do app) |
| Cota pública do MyMemory e 429 do Google Livros | Riscos conhecidos (ADR 0015) |
| Renomear pasta cria série nova | Limitação aceita (ADR 0014) |

## 10. Riscos específicos do iOS/PWA

- O Safari pode **apagar o armazenamento** de sites pouco usados; instalado na Tela de Início fica mais protegido, mas o servidor é a fonte da verdade do progresso.
- Sem download em segundo plano e com cota de armazenamento limitada: offline é "melhor esforço".
- Push e alguns recursos exigem iOS 16.4+ com o app instalado.
- Se um dia precisar de algo nativo, o front React migra para Capacitor sem reescrever.

## 11. Perguntas ainda abertas

1. ~~Política de cadastro~~ — decidido: só o dono cria contas (sem cadastro público).
2. Tamanho aproximado da biblioteca (nº de itens e GB)?
3. Mangá: preferência padrão de leitura (direita→esquerda ou webtoon)?
4. ~~Metadados automáticos~~ — decidido (2026-11-20, ADR 0015): capas e sinopse de fontes públicas por lista fixa de hosts. `ComicInfo.xml` continua ignorado; OpenLibrary não entrou.
5. Idioma da interface (pt-BR apenas?).
6. Qual IA fará a auditoria e em que ambiente ela roda os testes (local, staging)?
