# Biblioteca (nome provisório)

PWA para ler mangás (CBZ, CBR, pasta de imagens), livros (EPUB) e PDF. Instalável no iPhone. O conteúdo fica no servidor; o app consome a API.

Stack: Python/FastAPI (backend) e React/TypeScript/Vite (frontend).

Status: planejamento e Fase 0 (fundação). Roteiro em [docs/PLANO.md](docs/PLANO.md).

## Organização

| Pasta | Conteúdo |
|---|---|
| `backend/` | API REST `/api/v1` em Hexagonal (Ports & Adapters) |
| `frontend/` | PWA organizada por feature |
| `docs/` | Plano, mapas, ADRs, histórico e segurança |
| `infra/` | Dockerfile e compose do app |
| `scripts/` | `check.ps1` e `check.sh`: lint, tipos, testes, auditoria de dependências e scan de segredos (ver `scripts/README.md`) |

## Por onde começar

1. [AGENTS.md](AGENTS.md): regras do projeto.
2. [docs/PLANO.md](docs/PLANO.md): o quê e por quê.
3. `AGENTS.md` do módulo em que for trabalhar (`backend/`, `frontend/`, `docs/`, `infra/`).

Histórico de versões: [CHANGELOG.md](CHANGELOG.md). Decisões: [docs/adr/](docs/adr/).
