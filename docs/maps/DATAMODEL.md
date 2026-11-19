# DATAMODEL

Estado: **nenhuma tabela existe no código**. `backend/migrations/` não existe. Abaixo, o modelo planejado (PLANO §4), marcado "planejado". Banco previsto: SQLite (WAL) via SQLAlchemy/Alembic; `DATABASE_URL` default `sqlite:///./data/app.db` (`backend/app/core/config.py`).

| Entidade | Campos | Status |
|---|---|---|
| User | id, email, password_hash, role, theme_pref, created_at | planejado |
| Item | id, type [manga\|book\|pdf], title, path_rel, format, page_count, cover, content_hash, added_at | planejado |
| Series | agrupa volumes/capítulos de mangá | planejado |
| Chapter | opcional, dentro de Series | planejado |
| ReadingProgress | user_id, item_id, locator, percent, device_id, updated_at, finished. Chave única (user_id, item_id) | planejado |
| Session / RefreshToken | revogáveis; família para detecção de reuso | planejado |
| AuditLog | login, falhas, troca de senha, scan | planejado |

## Regras planejadas

| Tema | Regra |
|---|---|
| locator | manga/PDF = índice da página; EPUB = CFI |
| Conflito entre dispositivos | vence o maior `updated_at`; servidor define o relógio |
| Isolamento | toda consulta de dados de usuário filtra por `user_id` (PLANO §6) |
| Caminho | `path_rel` relativo; caminho absoluto nunca vem do cliente |
