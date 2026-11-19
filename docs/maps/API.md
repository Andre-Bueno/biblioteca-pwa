# API

Base: `/api/v1`. Estado: 2026-11-19. Fonte: `backend/app/api/`.
OpenAPI e Swagger **desligados** (`backend/app/main.py`: `docs_url`, `redoc_url`, `openapi_url` = None). Este mapa é **manual**: não é gerado do OpenAPI.

## Existente

| Método | Caminho | Auth | Resposta | Arquivo |
|---|---|---|---|---|
| GET | `/api/v1/health` | não | 200 `{"status": "ok"}` | `backend/app/api/health.py` |

Cabeçalhos em todas as respostas HTTP: `Content-Security-Policy` (sem `unsafe-inline`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (`backend/app/api/security_headers.py`).

| Caso | Status | Corpo | Cabeçalhos extras |
|---|---|---|---|
| Rota inexistente | 404 | padrão do FastAPI | cabeçalhos de segurança |
| Exceção não tratada | 500 | `{"detail": "Internal Server Error"}` | `Cache-Control: no-store`, `Content-Type: application/json` |

## Planejado (PLANO §5, status: planejado)

| Método | Caminho | Função |
|---|---|---|
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/items` | Listar biblioteca |
| GET | `/api/v1/items/{id}` | Detalhe do item |
| GET | `/api/v1/items/{id}/pages/{n}` | Imagem da página |
| GET | `/api/v1/items/{id}/file` | EPUB/PDF com Range |
| PUT | `/api/v1/progress/{item_id}` | Salvar progresso |
| GET | `/api/v1/progress/continue` | Continuar lendo |
| POST | `/api/v1/library/scan` | Escanear biblioteca |
| GET | `/api/v1/me/preferences` | Ler preferências |
| PUT | `/api/v1/me/preferences` | Gravar preferências |

Planejado sem caminho definido: endpoint de criação de conta pelo admin (PLANO §6; sem cadastro público).

Pendente para toda rota autenticada: CSRF no servidor, `Cache-Control: no-store`, rate limit, CORS (ver `SECURITY_MAP.md`).
