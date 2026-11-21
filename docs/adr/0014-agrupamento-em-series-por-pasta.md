# ADR 0014: Agrupamento em séries por pasta

- **Status:** Aceito
- **Data:** 2026-11-21

## Contexto

- A biblioteca real tem uma pasta por obra, com um arquivo por capítulo (`Capitulo - N.cbz`). Listar capítulos como itens soltos ordenados por título não serve: "Capitulo - 10" vem antes de "Capitulo - 2" (REG-020).
- PLANO §4 prevê `Series` e `Chapter`. O `DATAMODEL.md` as marcava como planejadas.
- A tabela `items` tem `reading_progress` em cascata (ADR 0013). Recriar `items` com foreign keys ligadas apagaria o progresso.

## Decisão

| Tema | Decisão |
|---|---|
| Série | Uma linha em `series` por pasta pai do item (`folder_rel_path`, único, relativo, só no servidor). Arquivo solto na raiz da biblioteca vira série própria, com `folder_rel_path` nulo |
| Capítulo | `items.series_id` (FK, `ON DELETE SET NULL`, indexada) e `items.chapter_number` (número lido do nome, `FLOAT`). Pasta que é item de imagens é capítulo da série da pasta pai |
| Número | Decidido por `domain/series.py` (`group_entry`, `parse_chapter_number`). Sem número: capítulo vai para o fim, ordenado pelo nome |
| Ordem de série | `sort_title` com dígitos preenchidos com zeros até 12 posições (`_PAD = 12`), em minúsculas. A listagem ordena por `(sort_title, id)` no SQL |
| Ordem de capítulo | Número primeiro; depois ordem natural do nome; depois id (`sort_chapters`) |
| Migração | `0005` com `ALTER TABLE ADD COLUMN` (`items.series_id`, `items.chapter_number`) e `CREATE TABLE series`. Sem recriar `items` nem `users`. Backfill idempotente |
| Continuar | Campo `continue` (atributo `resume`) do detalhe da série: capítulo não concluído mais recente; senão, o primeiro capítulo sem progresso depois do último concluído. Não é rota própria |
| Limitação aceita | Renomear a pasta cria uma série nova (a chave é o caminho da pasta). O progresso dos capítulos fica no item; a série antiga some na próxima varredura |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Agrupar só no frontend, pelo nome | Sem chave estável; não funciona com paginação nem com metadados |
| Tabela própria de capítulos e mover `items` | Obriga a recriar `items` (cascata no progresso) ou migrar dados em duas etapas arriscadas |
| Chave por nome da série (sem pasta) | Duas pastas com o mesmo nome colidiriam |
| Renomeação detectada por `content_hash` | Custo de hash em toda varredura; caso raro para a biblioteca do dono |

## Consequências

- Positivas: séries e capítulos na ordem certa; progresso preservado nas migrações; metadados (ADR 0015) têm onde ancorar.
- Negativas:
  - Renomear pasta cria série nova e perde os metadados associados à série antiga.
  - `chapter_number` vem do nome do arquivo: nome sem número cai no fim.
- Obrigações:
  - Mudar a chave de série (pasta) ou a regra de número exige ADR novo.
  - A migração `0005` não é editada depois de aplicada (regra de `backend/AGENTS.md`).

Complementa ADR 0013. Não altera ADR 0001 a 0013.
