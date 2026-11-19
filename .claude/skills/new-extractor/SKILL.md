---
name: new-extractor
description: Passo a passo para adicionar suporte a um novo formato de arquivo (CBZ, CBR, EPUB, PDF, pasta, etc.) como Extractor, com limites de segurança e testes. Use ao criar ou alterar um leitor de formato no backend.
---

# Novo extractor de formato

Use como briefing para o `backend-dev`. Leia `backend/AGENTS.md` e `backend/app/adapters/AGENTS.md`.

1. **Port:** confirme que `ports/Extractor` cobre o necessário (listar páginas/capítulos, ler uma página, metadados, contagem). Estenda o port só se preciso, sem quebrar os extractors existentes.
2. **Adapter:** um arquivo em `adapters/extractors/<formato>.py`, registrado no registry de formatos. Services não mudam.
3. **Segurança obrigatória:**
   - limite de tamanho descompactado, nº de entradas e razão de compressão;
   - sem extração em disco com nome vindo do arquivo; rejeitar `..`, caminho absoluto e symlinks (zip-slip);
   - subprocesso externo só com lista de argumentos, timeout e limites, sem shell;
   - metadados e nomes são texto não confiável.
4. **Testes em `tests/security/`:** arquivo corrompido, zip bomb, entrada com `../`, arquivo gigante, muitas entradas. Mais testes unit com arquivos de fixture pequenos e gerados em teste (nunca conteúdo protegido real).
5. **Docs (docs-keeper):** `SECURITY_MAP.md`, `CODEMAP.md`, `TEST_MAP.md`, `CHANGELOG.md`.
6. Fechar com `close-change`. Entregas desta skill devem passar pelo `code-reviewer`.
