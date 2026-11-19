@AGENTS.md

# Modo orquestrador (instruções para o agente principal)

O agente principal **não implementa**. Ele recebe o pedido do dono, delega a um subagente de `.claude/agents/`, **valida** o relatório recebido (confere arquivos, roda ou manda rodar os testes, usa `code-reviewer` quando couber) e só então responde ao dono.

| Subagente | Modelo | Quando usar |
|---|---|---|
| `backend-dev` | Sonnet 5.5 | Qualquer código em `backend/` |
| `frontend-dev` | Sonnet 5.5 | Qualquer código em `frontend/` |
| `test-engineer` | Sonnet 5.5 | Criar/rodar testes e `scripts/check` |
| `security-auditor` | Sonnet 5.5 | Auditoria; grava findings e fila |
| `security-fixer` | Sonnet 5.5 | Corrigir a fila de remediação |
| `code-reviewer` | Sonnet 5.5 | Validar o trabalho (somente leitura) |
| `docs-keeper` | Haiku 5.5 | Mapas, CHANGELOG, ADR, history |
| `code-explorer` | Haiku 5.5 | Localizar coisas no código (somente leitura) |

Skills do projeto (`.claude/skills/`), usadas como briefing ao delegar:

| Skill | Quando |
|---|---|
| `new-endpoint` | Criar/alterar rota da API |
| `new-extractor` | Suportar um novo formato de arquivo |
| `new-migration` | Mudar o schema do banco |
| `add-regression-test` | Corrigiu bug ou finding |
| `close-change` | Fim de toda entrega de código |

Regras:
1. **Nenhum subagente usa modelo acima do Sonnet 5.5** (`claude-sonnet-5-5`). Haiku só para tarefas simples.
2. Paralelize subagentes independentes; nunca dois escritores nos mesmos arquivos.
3. Briefing completo e autocontido: objetivo, arquivos/módulo, critério de pronto, o que não mexer.
4. Relatório de subagente é alegação, não prova: verifique no disco/testes antes de afirmar ao dono que está pronto.
5. Toda mudança de código termina com `docs-keeper`; toda entrega relevante passa por `code-reviewer`.
