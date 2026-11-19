---
name: new-migration
description: Fluxo seguro para mudar o schema do banco com Alembic e atualizar modelo de domínio, repositório e DATAMODEL. Use sempre que uma tabela ou coluna for criada, alterada ou removida.
---

# Nova migração de banco

Use como briefing para o `backend-dev`. Leia `backend/AGENTS.md`.

1. Altere a entidade em `domain/` (regra) e o modelo ORM em `adapters/persistence/`. O domínio não importa SQLAlchemy.
2. Gere uma **nova** migração Alembic. Nunca edite migração já aplicada.
3. A migração precisa ser **reversível** (`downgrade`) e segura para dados existentes: colunas novas com default ou nulas; mudanças destrutivas (drop, rename) em passos separados e com autorização do dono.
4. Atualize o repositório (`ports/` + `adapters/persistence/`) mantendo o filtro por `user_id` em dados de usuário.
5. **Testes:** migração sobe e desce num banco vazio; integration do repositório; se mudou dado de usuário, teste de isolamento entre usuários.
6. **Docs (docs-keeper):** `DATAMODEL.md`, `CODEMAP.md`, `CHANGELOG.md`; ADR se a mudança for estrutural.
7. Fechar com `close-change`.
