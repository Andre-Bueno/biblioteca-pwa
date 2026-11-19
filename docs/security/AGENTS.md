# docs/security/AGENTS.md

Fluxo de segurança entre **auditor** (IA terceira) e **corretor** (agente que implementa).

## Arquivos
- `AUDIT_PROTOCOL.md`: escopo da auditoria, formato dos findings e da fila. **O auditor lê este primeiro.**
- `findings/FIND-AAAA-NNN.md`: um finding por arquivo.
- `REMEDIATION_QUEUE.md`: fila priorizada, gerada pelo auditor.
- `AUDIT_REPORT_<data>.md`: relatório de cada rodada.

## Auditor
- Não altera código de produção; escreve só nesta pasta.
- Testa apenas local/staging. Toda afirmação com evidência reproduzível; separar comprovado de suspeito.

## Corretor
Para cada item da fila, em ordem: reproduzir → escrever teste de regressão que falha → correção mínima → `scripts/check` verde → atualizar finding (`status: fixed`), mapas, `CHANGELOG` (Security) e `history/`.
Não marcar `verified` (é do auditor). Discordância: `status: disputed` com justificativa.

Status: `open → fixed → verified` (ou `disputed` / `accepted-risk`, este só com aprovação do dono).
