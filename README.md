# Biblioteca (nome provisório)

PWA para ler mangás (CBZ, CBR, pasta de imagens), livros (EPUB) e PDF. Instalável no iPhone. O conteúdo fica no servidor; o app consome a API.

Stack: Python/FastAPI (backend) e React/TypeScript/Vite (frontend).

Status (2026-11-21): Fase 1 (backend) e Fase 2 (login, biblioteca e tema) entregues; leitor de mangá com progresso (MVP) entregue; agrupamento em séries por pasta e metadados de fontes públicas (capa e descrição) entregues (ADR 0014 a 0016); Fase 3 parcial. Um único container serve API e PWA (ver [docs/DEPLOY.md](docs/DEPLOY.md)). Pendências em [docs/PLANO.md](docs/PLANO.md) §9 e [docs/maps/SECURITY_MAP.md](docs/maps/SECURITY_MAP.md). Roteiro em [docs/PLANO.md](docs/PLANO.md).

## Organização

| Pasta | Conteúdo |
|---|---|
| `backend/` | API REST `/api/v1` em Hexagonal (Ports & Adapters) |
| `frontend/` | PWA organizada por feature (login, biblioteca, séries, leitor de mangá, ajustes) |
| `docs/` | Plano, mapas, ADRs, histórico, segurança e guia de deploy (`docs/DEPLOY.md`) |
| `infra/` | Dockerfile, entrypoint e compose do app |
| `scripts/` | `check.ps1` e `check.sh`: lint, tipos, testes, auditoria de dependências e scan de segredos (ver `scripts/README.md`) |

## Por onde começar

1. [AGENTS.md](AGENTS.md): regras do projeto.
2. [docs/PLANO.md](docs/PLANO.md): o quê e por quê.
3. `AGENTS.md` do módulo em que for trabalhar (`backend/`, `frontend/`, `docs/`, `infra/`).
4. Para subir o app num servidor: [docs/DEPLOY.md](docs/DEPLOY.md).

Histórico de versões: [CHANGELOG.md](CHANGELOG.md). Decisões: [docs/adr/](docs/adr/).
