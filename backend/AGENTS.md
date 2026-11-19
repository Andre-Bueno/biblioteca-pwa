# backend/AGENTS.md

Python 3.12 · FastAPI · SQLAlchemy + Alembic · pydantic-settings. Arquitetura Hexagonal leve.

## Camadas e dependência

```
api  →  services  →  domain
          ↓
        ports  ←  adapters
```
- `domain/`: entidades e regras puras. **Não importa nada** de FastAPI, SQLAlchemy ou disco.
- `ports/`: interfaces (Protocol/ABC): `ItemRepository`, `ProgressRepository`, `StorageBackend`, `Extractor`, `SourceProvider`.
- `services/`: casos de uso. Dependem de `domain` e `ports`, nunca de `adapters`, HTTP nem `app.core`. Configuração entra por injeção (parâmetro), lida só na composição.
- `adapters/`: implementam os ports (SQLAlchemy, disco, extratores de formato).
- `api/`: routers, schemas Pydantic, dependências de auth. **Sem regra de negócio e sem SQL**; só valida, chama um service e devolve o schema.
- Montagem (injeção de dependência) apenas em `app/main.py`/`api/deps.py`.

Violação = `tests/architecture/test_layers.py` falha (executa import-linter de verdade; 6 contratos em `pyproject.toml`).

## Regras

- Tipado (`mypy --strict`), `ruff` para lint e formatação.
- Config por variável de ambiente; nunca commitar `.env` nem conteúdo real.
- Mudança de schema ⇒ nova migração Alembic; nunca editar migração aplicada.
- API versionada; mudança incompatível = nova versão + ADR.
- Novo endpoint ⇒ schema de entrada/saída, teste de autorização (IDOR) e linha no `docs/maps/API.md`.
- Novo formato de arquivo ⇒ novo `Extractor` em `adapters/`, sem alterar services.
- Logs sem senha, token ou dados pessoais.

## Segurança do app (serviço público)

Não implementar controles de rede/VPN/IP allowlist; o servidor já cuida disso. O app deve resistir a qualquer cliente anônimo:
- **Anti brute force:** limite por conta e por IP, atraso progressivo e bloqueio temporário, resposta e tempo idênticos para "usuário inexistente" e "senha errada", log de falhas. IP real só via cabeçalho de proxy confiável, decidido exclusivamente pelo uvicorn (`FORWARDED_ALLOW_IPS`); o app usa `request.client.host`.
- **Senhas:** Argon2id, política mínima; trocar senha revoga sessões.
- **Sessão:** access token curto; refresh rotativo em cookie `HttpOnly; Secure; SameSite`; reuso de refresh revoga a família; logout revoga.
- **CSRF:** token CSRF em toda requisição que altera estado + checagem de `Origin`/`Referer`; CORS por lista fixa (`ALLOWED_ORIGINS`), nunca `*` com credenciais.
- **Cadastro:** não existe cadastro público nem "esqueci a senha". Só o admin cria contas e redefine senhas (CLI `python -m app.cli create-user` ou endpoint exclusivo de admin, com autorização testada). Não criar rota pública de registro.
- **Rate limit** global e por rota (login, scan, páginas); limite de tamanho de corpo e de `Range`; paginação obrigatória; timeouts.
- **Cabeçalhos** emitidos pelo próprio app via middleware: CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store` em respostas autenticadas.
- **Validação:** schemas Pydantic estritos (`extra="forbid"`) com limites de tamanho.
- Todo controle acima precisa de teste em `tests/security/` (ex.: N falhas ⇒ bloqueio; POST sem CSRF ⇒ 403).

## Testes (`backend/tests/`)

`unit/` (services com adaptadores falsos) · `integration/` (API + banco) · `regression/` (`test_reg_NNN_*`) · `security/` (authz, traversal, zip bomb) · `architecture/` (import-linter).
Rode `scripts/check` antes de entregar.
