# ADR 0001: Arquitetura hexagonal no backend e frontend por feature

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- O plano inicial adotava MVC adaptado (models/views/controllers).
- MVC foi pensado para páginas renderizadas no servidor. Aqui o backend é uma API JSON e o frontend é uma SPA/PWA.
- Os formatos (CBZ, CBR, pasta, EPUB, PDF) e a infraestrutura (SQLite, disco, futuro Postgres/S3) vão mudar. Precisamos trocar adaptadores e incluir formatos sem tocar no núcleo.

## Decisão

| Tema | Decisão |
|---|---|
| Backend | Arquitetura Hexagonal (Ports & Adapters) leve |
| Camadas | `api` → `services` → `domain`; `services` → `ports`; `adapters` → `ports` |
| Adapters | `backend/app/adapters/{persistence,storage,extractors}` |
| Frontend | Organização por feature: `app/`, `features/<nome>/`, `shared/` |
| Regra entre features | Feature não importa feature |
| Imposição | Teste de arquitetura: `import-linter` (backend); dependency-cruiser ou eslint boundaries (frontend) |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| MVC adaptado | Controller e View não se aplicam a uma API JSON. Não isola formatos nem armazenamento. |
| Clean Architecture completa | Camadas e cerimônia (DTOs, use cases por classe, mapeamentos duplicados) excessivos para uso individual. |

## Consequências

- Positivas: formatos e armazenamento trocáveis por adaptador; núcleo testável sem framework; regra de dependência verificada por ferramenta.
- Negativas: mais pastas e interfaces (`ports`) do que um CRUD simples; exige disciplina de imports.
- Obrigações: nunca desativar o teste de arquitetura; corrigir o código quando ele falhar.
- Pendente: local do ponto de composição (ligação de ports a adapters) será definido na Fase 1.
