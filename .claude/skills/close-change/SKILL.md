---
name: close-change
description: Fecha uma mudança de código com a definição de pronto do projeto - validação, testes, revisão, mapas, CHANGELOG, ADR e history. Use ao final de toda entrega de código antes de responder ao dono.
---

# Fechar uma mudança

Roteiro do orquestrador, na ordem:

1. **Verificar no disco** que os arquivos citados no relatório do implementador existem e fazem o que ele diz. O relatório é alegação, não prova.
2. **`test-engineer`:** rodar `scripts/check` (ou o que existir) e trazer a saída real. Falhou? Volta ao implementador; não relaxe teste.
3. **`code-reviewer`:** revisar o diff (camadas, segurança, testes, duplicação). Achados altos/médios voltam ao implementador.
4. **`docs-keeper`**, passando o resumo do que mudou: `CODEMAP`, `ARCHITECTURE`, `DATAMODEL`, `API`, `ROUTES`, `TEST_MAP`, `SECURITY_MAP` (os afetados), `CHANGELOG.md`, ADR se houve decisão, e `docs/history/AAAA-MM-DD-<slug>.md`.
5. Conferir que nada foi commitado com segredo, `.env` ou conteúdo real de livros.
6. **Resposta ao dono:** o que mudou, resultado real dos testes, o que não foi verificado e pendências. Sem afirmar "pronto" se algo não foi executado.
