# docs/AGENTS.md

Documentação viva: mapas, decisões e histórico. Serve a humanos e agentes.

## Conteúdo
- `PLANO.md`: o quê e por quê (roteiro).
- `maps/`: `CODEMAP` (arquivo → responsabilidade), `ARCHITECTURE`, `DATAMODEL`, `API` (manual; OpenAPI/Swagger desligados em `backend/app/main.py`), `ROUTES` (telas), `SECURITY_MAP` (superfícies e controles), `TEST_MAP` (feature → testes).
- `adr/`: uma decisão por arquivo `NNNN-titulo.md` (contexto, decisão, consequências). Aceito = imutável; mudar = novo ADR que o substitui.
- `history/`: `AAAA-MM-DD-slug.md` (o que foi feito, por quê, pendências).
- `security/`: ver `security/AGENTS.md`.

## Definição de pronto (toda mudança de código)
- [ ] `CODEMAP` reflete arquivos novos, movidos e removidos.
- [ ] `DATAMODEL`, `API`, `ROUTES`, `TEST_MAP` e `SECURITY_MAP` atualizados, se afetados.
- [ ] `CHANGELOG.md` (Added/Changed/Fixed/Security).
- [ ] ADR, se houve decisão relevante.
- [ ] Entrada em `history/`.

Planejado, ainda não existe: teste em `backend/tests/architecture` que falha se houver módulo fora do `CODEMAP`. Até existir, conferir o `CODEMAP` à mão.
Mantenha os mapas curtos: tabelas e listas, sem prosa.
