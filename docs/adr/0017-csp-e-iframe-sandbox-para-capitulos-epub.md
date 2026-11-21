# ADR 0017: CSP e iframe sandbox para capítulos de EPUB

- **Status:** Proposto (aguarda aceite do dono; ver nota no fim)
- **Data:** 2026-11-21

## Contexto

- O leitor de EPUB precisa mostrar HTML de capítulo, que é conteúdo não confiável (ADR 0002; `backend/AGENTS.md`, saída de conteúdo de livro).
- ADR 0006 proíbe relaxar cabeçalhos de segurança por rota. ADR 0012 fixa a CSP global sem `unsafe-inline` nem `unsafe-eval`.
- A CSP global (`default-src 'self'`, `frame-ancestors 'none'`) impede o capítulo de rodar dentro do próprio app como frame, e `style-src 'self'` bloqueia o CSS de estilo embutido que o adapter gera.
- O SECURITY_MAP (Pendências) já apontava "CSP por rota (EPUB/PDF, iframe)" e "XSS via EPUB" como decisão a tomar por novo ADR.

## Decisão

| Tema | Decisão |
|---|---|
| Entrega do capítulo | `GET /api/v1/items/{id}/book/chapters/{n}` devolve HTML já saneado (`text/html; charset=utf-8`) |
| Quem aplica a CSP | O middleware (`api/security_headers.py`), não a rota. Só para GET com status 200, no caminho exato `/api/v1/items/<uuid>/book/chapters/<n>` e com marcador interno da rota |
| CSP do capítulo | `default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'` (`BOOK_CHAPTER_CSP`). Sem `script-src`, então sem script |
| Cache do capítulo | Mesma exceção privada de 1 h do ADR 0010 (GET 200 ou 304), mais `ETag` |
| Frame no app | `<iframe sandbox="allow-same-origin">`. Sem `allow-scripts`, `allow-forms`, `allow-popups` nem `allow-top-navigation` |
| Sanitização | Por allowlist de tags e atributos (`adapters/extractors/_epub_html.py`); CSS filtrado por allowlist de propriedades e valores (`_epub_css.py`); estilos gerados a partir de valores validados |
| Imagens | Só por `GET /api/v1/items/{id}/book/res/{rid}`, com `rid` numérico (posição na lista de imagens do manifesto); o HTML nunca traz caminho interno |
| Não servidos | Fontes e SVG nunca; DRM (`META-INF/rights.xml` ou criptografia que não seja ofuscação de fonte) recusado |
| Locator | Livro = `capítulo * 10000 + offset_bp` (pontos-base dentro do capítulo); concluído = último capítulo com offset ≥ 9000 |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Afrouxar a CSP global para o app inteiro | Viola ADR 0006 e ADR 0012 em todas as telas |
| Renderizar o HTML no DOM do app (sem iframe) | Conteúdo do livro ganharia acesso ao contexto da SPA; XSS viraria XSS da aplicação |
| `allow-scripts` no iframe | Desnecessário para leitura; abriria script de livro dentro da origem |
| Converter EPUB em imagens | Perde texto, seleção e ajuste de fonte; custo alto de armazenamento |
| Servir o EPUB inteiro e deixar o leitor abrir | Expõe arquivos internos e fontes; maior superfície |

## Consequências

- Positivas: a CSP do resto do app não muda; o capítulo não executa script (sem `script-src` e sem `allow-scripts`); imagens e links ficam dentro da origem do app.
- Negativas e riscos conhecidos:
  - `style-src 'unsafe-inline'` vale só para a resposta do capítulo. Injeção de CSS continua possível dentro do frame; é aceita porque CSS sem script não executa código.
  - `allow-same-origin` deixa o app ler o DOM do iframe (posição de rolagem e cliques). Se algum dia houver script dentro do frame, ele teria a origem do app: por isso a ausência de `allow-scripts` é obrigatória e testada.
  - Ver `docs/maps/SECURITY_MAP.md` (EPUB) para os testes que cobrem sanitização, CSP e cabeçalhos.
- Obrigações:
  - Mudar a CSP do capítulo, adicionar `allow-scripts` ou servir outra fonte exige ADR novo e teste.
  - Novo tipo de conteúdo de livro passa por sanitizador e teste de segurança antes de ser servido.

Complementa ADR 0006, ADR 0010 e ADR 0012. Não altera ADR 0001 a 0016.

**Nota de status:** o texto foi redigido pelo agente de documentação a partir do código entregue. Só vira "Aceito" com a confirmação do dono; até lá, não usar como regra definitiva.
