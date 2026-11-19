# backend/tests/AGENTS.md

- **Nomes:** bug ou finding corrigido => `regression/test_reg_NNN_<slug>.py` (docstring com bug e causa). Controles de segurança => `security/`. Os demais: `unit/`, `integration/`, `architecture/`.
- **Middleware de 500:** `SecurityHeadersMiddleware` converte exceções em 500 genérico, então o `TestClient` padrão ainda levanta a exceção do app (`raise_server_exceptions=True`). Para afirmar a resposta 500 use `TestClient(app, raise_server_exceptions=False)`; para afirmar o log use `caplog` (`caplog.at_level(..., logger="app.api.security_headers")`).
- **Segredos em teste:** nunca assertar com valor real; `tests/conftest.py` define uma `SECRET_KEY` só de teste. Erros de `Settings` não podem conter o valor.
- **Testes negativos de arquitetura:** em `architecture/test_layers.py`, adicione uma tupla `(fragmento do nome do contrato, módulo, código)` em `VIOLATIONS`; o teste monta um pacote `app` mínimo em `tmp_path` com esse import e exige `BROKEN`. Todo item de `forbidden_modules` em `pyproject.toml` precisa de um caso. Exceções (`ignore_imports`) ganham teste positivo e um negativo vizinho.
