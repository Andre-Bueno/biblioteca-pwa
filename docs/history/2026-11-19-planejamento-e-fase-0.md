# 2026-11-19 — Planejamento e início da Fase 0

## Decisões tomadas

| Tema | Decisão | Registro |
|---|---|---|
| Instalação iOS | PWA, sem Mac e sem conta Apple | ADR 0003 |
| Formatos | CBZ, CBR, pasta de imagens, EPUB, PDF | PLANO §1 |
| Backend | Python + FastAPI | PLANO §1 |
| Frontend | React + TypeScript + Vite (PWA) | PLANO §1 |
| Arquitetura backend | Hexagonal (Ports & Adapters) leve | ADR 0001 |
| Arquitetura frontend | Por feature (`app/`, `features/`, `shared/`) | ADR 0001 |
| Imposição | import-linter (backend); dependency-cruiser ou eslint boundaries (frontend) | PLANO §3 |
| Segurança | Serviço público; segurança só dentro do app; rede/VPN/TLS fora de escopo | ADR 0002 |
| Cadastro | Sem cadastro público; só o dono cria contas | ADR 0002 |
| Fontes externas | Fora do escopo por ora; ponto de extensão `SourceProvider` | PLANO §1 |
| Agentes | Orquestrador + subagentes (Sonnet no máximo; Haiku para docs e exploração) | `CLAUDE.md`, `.claude/agents/` |
| Skills | `new-endpoint`, `new-extractor`, `new-migration`, `add-regression-test`, `close-change` | `.claude/skills/` |

## Estado no disco

| Item | Situação |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, `docs/AGENTS.md`, `docs/PLANO.md` | Existem |
| `.claude/agents/` (8 arquivos) e `.claude/skills/` (5 arquivos) | Existem |
| `backend/AGENTS.md`, `backend/app/adapters/AGENTS.md` | Existem; código do backend em criação por outro agente |
| `frontend/AGENTS.md` | Existe; código do frontend em criação por outro agente |
| `infra/AGENTS.md` | Existe; sem Dockerfile nem compose |
| `docs/security/AGENTS.md`, `AUDIT_PROTOCOL.md` | Existem |
| `docs/maps/` | Não existe |
| `docs/adr/` | Criado, com 0001, 0002 e 0003 |
| `docs/history/` | Criado, com esta entrada |
| `scripts/check` | Não existe |
| `CHANGELOG.md`, `README.md` | Criados |

## Pendências

1. Criar `docs/maps/` (ARCHITECTURE, CODEMAP, DATAMODEL, API, ROUTES, SECURITY_MAP, TEST_MAP) quando o código existir. CODEMAP só depois de `backend/` e `frontend/` estarem prontos.
2. Escolher entre dependency-cruiser e eslint boundaries para o frontend.
3. Criar `scripts/check` (lint, tipos, testes, SAST, auditoria de dependências) e CI.
4. Criar `infra/` (Dockerfile e compose do app).
5. Definir o local do ponto de composição (ligação de ports a adapters) na Fase 1.
6. Perguntas abertas do dono (PLANO §11): tamanho da biblioteca, preferência de leitura de mangá, metadados automáticos no MVP, idioma da interface, IA auditora e ambiente de testes.
7. Sem autorização do dono: CAPTCHA (Turnstile/hCaptcha), verificação de senha vazada e qualquer serviço externo.

## Próximo passo

Fase 0 até `scripts/check` verde num projeto vazio (PLANO §9).
