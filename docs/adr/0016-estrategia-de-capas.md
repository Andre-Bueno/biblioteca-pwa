# ADR 0016: Estratégia de capas (baixadas uma vez e servidas pelo app)

- **Status:** Aceito
- **Data:** 2026-11-21

## Contexto

- A capa de série pode vir de uma fonte pública (ADR 0015) ou, sem fonte, da primeira página legível de um capítulo.
- O frontend roda com `img-src 'self' data: blob:` (ADR 0012). Um `<img>` apontando para `uploads.mangadex.org` seria bloqueado, e a CSP não deve ser afrouxada.
- Hotlink de capa faria o navegador do usuário falar com a fonte e vazaria o acesso.

## Decisão

| Tema | Decisão |
|---|---|
| Download | Uma vez, no enriquecimento, pelo `SafeGateway` (imagem até 5 MiB; só JPEG, PNG ou WebP, pelos bytes mágicos) |
| Armazenamento | `DATA_DIR/covers/<uuid da série>.<extensão>`, com extensão jpg, png ou webp. Em `Settings`, `DATA_DIR` padrão `./data`; na imagem, `/data` (volume) |
| Nome | Só o UUID gerado pelo servidor e a extensão dos bytes. Nada da rede, do banco ou do cliente entra no caminho. Nome lido do banco é validado de novo |
| Escrita | Arquivo temporário com criação exclusiva e `fsync`; depois renomeação atômica. A capa só é confirmada depois que o banco aceita a mudança; falha remove o temporário |
| Leitura | `GET /api/v1/series/{id}/cover`: capa baixada se existir e for legível; senão, capa do primeiro capítulo legível (até 5 tentativas). Sem capa: 404 |
| Servidor | Sempre pelo próprio app, mesma origem. O navegador nunca recebe URL externa de imagem |
| Cache | Entra na exceção de cache privado de 1 h do ADR 0010, só GET 200/304 |
| CSP | Inalterada: `img-src 'self' data: blob:` |
| Substituição e remoção | Nova capa aceita apaga a anterior. `DELETE /metadata` apaga a capa baixada |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Guardar URL externa e usar em `<img>` | Exige afrouxar `img-src` e expõe o navegador à fonte |
| Proxy de imagem sem gravar | Repete o download a cada visita e aumenta a carga sobre a fonte |
| Guardar a capa no banco (BLOB) | Infla o SQLite e o backup; arquivo em disco é mais simples de inspecionar |
| Gerar miniatura própria | Não necessário agora; YAGNI |

## Consequências

- Positivas: CSP preservada; uma única saída de rede por capa; navegador não toca em fonte externa; capa funciona offline depois de baixada.
- Negativas:
  - Ocupa `DATA_DIR` (até 5 MiB por capa) e precisa entrar no backup de `/data` (`docs/DEPLOY.md` §6 copia só `app.db`; a capa não está nele).
  - Capa baixada não é atualizada sozinha; um reprocessamento com `force` (série em `matched`) pode substituí-la.
- Obrigações:
  - Mudar o formato ou o local das capas exige ADR novo.
  - Qualquer outra imagem externa precisa de novo ADR e de mudança de CSP com teste.

Complementa ADR 0010, ADR 0012 e ADR 0015. Não altera ADR 0001 a 0013.
