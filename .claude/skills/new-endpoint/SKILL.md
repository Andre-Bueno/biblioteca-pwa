---
name: new-endpoint
description: Checklist para criar ou alterar um endpoint da API (/api/v1) respeitando a arquitetura hexagonal, segurança e testes. Use ao adicionar rota, schema ou caso de uso no backend.
---

# Novo endpoint

Use como briefing para o `backend-dev`. Leia antes `backend/AGENTS.md`.

1. **Caso de uso** em `services/` (nome por ação: `SaveProgress`). Dependa só de `domain` e `ports`. Se precisar de dado/IO novo, defina a interface em `ports/` e a implementação em `adapters/`.
2. **Schemas** em `api/` (entrada e saída), `extra="forbid"`, com limites de tamanho. Nunca devolver o modelo do banco direto.
3. **Router** em `api/`: só autentica, valida, chama o service e devolve o schema. Sem regra de negócio nem SQL.
4. **Autorização:** o endpoint exige usuário autenticado e toda consulta filtra por `user_id`; IDs são opacos. Rotas que alteram estado exigem CSRF.
5. **Rate limit** se o endpoint for custoso ou sensível (login, scan, páginas); paginação obrigatória em listas.
6. **Testes:** unit do service (adaptadores falsos); integration da rota; **teste de autorização** (outro usuário e anônimo recebem 403/401/404); teste de segurança se tocar arquivo ou entrada complexa.
7. **Docs (docs-keeper):** `docs/maps/API.md`, `CODEMAP.md`, `TEST_MAP.md`, `SECURITY_MAP.md` se houver superfície nova, `CHANGELOG.md`.
8. Fechar com a skill `close-change`.
