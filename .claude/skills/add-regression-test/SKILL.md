---
name: add-regression-test
description: Cria um teste de regressão numerado (reg_NNN) para um bug ou finding de segurança corrigido e o referencia no CHANGELOG, TEST_MAP e finding. Use ao corrigir qualquer bug.
---

# Teste de regressão

Use como briefing para o `test-engineer`.

1. **Número:** próximo `NNN` livre, olhando `backend/tests/regression/` (ou `frontend/tests/regression/`). Não reutilize números.
2. **Arquivo e nome:** `test_reg_<NNN>_<slug>.py` (front: `reg_<NNN>_<slug>.test.ts`). Docstring/comentário no topo com: o bug, a causa e o link (`FIND-AAAA-NNN` ou descrição).
3. **Ordem:** escreva o teste, **confirme que falha** no código com o bug e que passa após a correção. Informe a saída real das duas execuções.
4. O teste deve reproduzir o cenário original (a requisição ou entrada que explorava o bug), não só o caso feliz.
5. Nunca remova nem enfraqueça um teste de regressão existente.
6. **Referências:** `TEST_MAP.md` (feature → teste), `CHANGELOG.md` (Fixed/Security cita `reg_NNN`) e, se for finding, o campo de critérios de aceite do arquivo em `docs/security/findings/`. Peça ao `docs-keeper`.
