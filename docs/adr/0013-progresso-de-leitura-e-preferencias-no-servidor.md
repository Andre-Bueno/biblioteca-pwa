# ADR 0013: Progresso de leitura e preferências no servidor

- **Status:** Aceito
- **Data:** 2026-11-20

## Contexto

- PLANO §2 exige posição de leitura, percentual, "continuar lendo" e tema persistido por usuário.
- PLANO §10: o Safari pode apagar o armazenamento do site. O servidor precisa ser a fonte da verdade.
- ADR 0002 e ADR 0008: nada sensível em `localStorage` ou `sessionStorage`. ESLint bloqueia esses acessos e `indexedDB` só existe em `shared/offline`.
- Fase 3 (PLANO §9): "fecha, reabre e continua na mesma página, em 2 dispositivos".

## Decisão

| Tema | Decisão |
|---|---|
| Fonte da verdade | Servidor. O frontend não guarda progresso nem preferência em web storage |
| Chave | Uma linha por `(user_id, item_id)` em `reading_progress` (migração `0004`). Toda consulta filtra pelo `user_id` do token |
| Escrita | Upsert atômico (`INSERT ... ON CONFLICT DO UPDATE`); não há duplicata nem erro por corrida |
| Conflito | Last-write-wins: a última gravação no banco vence. O cliente não envia timestamp |
| Relógio | `updated_at` em UTC, pelo relógio do servidor (porta `Clock`) |
| Derivados | `percent = (locator + 1) / page_count * 100` e `finished = locator == page_count - 1`, calculados no servidor. O cliente não envia nenhum dos dois |
| Validação | `locator` fora de `0..page_count-1` do item: 422 genérico. Item ausente ou marcado como ausente: 404 |
| Preferências | Duas colunas em `users` (`theme_pref`, `reading_direction`), por UPDATE dirigido. O `PUT` envia o objeto completo |
| Cliente | Não envia `PUT` a partir de valores padrão. Enquanto o `GET` não responde, guarda a alteração e a envia depois, sobre os dados do servidor |
| Envio | Um salvamento por vez, em ordem; ao sair ou ocultar a página, envio com `keepalive` pelo `api-client` |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| `localStorage` ou IndexedDB como fonte | Proibido (ADR 0002, ESLint); o iOS pode apagar o armazenamento |
| `max(updated_at)` com timestamp do cliente | Depende do relógio do aparelho. Adiado até haver conflito real entre dispositivos |
| Tabela própria de preferências | Duas colunas simples bastam. A migração `0004` usou `ALTER TABLE ADD COLUMN` para não apagar sessões em cascata |
| `PATCH` parcial | Mais regras; o `PUT` completo evita sobrescrever o servidor com padrões |

## Consequências

- Positivas: progresso e tema seguem o usuário entre aparelhos; o navegador não guarda dado de leitura.
- Negativas:
  - Last-write-wins descarta uma das duas escritas concorrentes de dois aparelhos.
  - A ordem de gravação pode diferir da ordem do relógio em milissegundos de corrida, porque o relógio é lido antes do upsert.
  - Reabrir um item concluído começa na última página (não há "reler do início").
- Obrigações:
  - Mudar a regra de conflito exige ADR novo.
  - O EPUB usará CFI no `locator`: ADR novo se o tipo do campo mudar.
  - A regra "vence o maior `updated_at`" do PLANO §4 e do `DATAMODEL.md` não é a implementada; este ADR é a referência.

Complementa ADR 0002 e ADR 0008. Não altera ADR 0001 a 0011.
