# ADR 0010: Exceção de cache para imagens autenticadas

- **Status:** Aceito
- **Data:** 2026-11-19
- **Substitui:** a regra do ADR 0006 apenas no ponto de cache (ver "Relação com o ADR 0006"). O ADR 0006 não foi alterado e permanece como histórico.

## Contexto

- ADR 0002 exige `Cache-Control` em respostas autenticadas.
- O leitor de mangá precisa reutilizar páginas já vistas, sem baixar de novo a cada página. O PLANO §7 prevê ETag e cache.
- Toda resposta de `/api` é específica do usuário. Um cache compartilhado (proxy) não pode guardar nada.
- ADR 0006 manda o middleware sobrepor qualquer cabeçalho de segurança da rota. Não há relaxamento por rota.
- O service worker não guarda `/api` (`runtimeCaching: []`).

## Decisão

| Tema | Decisão |
|---|---|
| Regra geral | Toda resposta de `/api`: `Cache-Control: no-store` e `Pragma: no-cache` |
| Exceção | Somente `GET /api/v1/items/{uuid}/pages/{n}` e `GET /api/v1/items/{uuid}/cover` com status 200 ou 304 |
| Como a rota pede | A rota marca a resposta com o cabeçalho interno `x-internal-cache-class: private-image`. O middleware valida o caminho (regex fixa) e o método, remove o marcador da resposta final |
| Quem escreve o valor | Só o middleware: `Cache-Control: private, max-age=3600`, sem `Pragma`. Rota nunca escolhe o cabeçalho de cache |
| Erros | Nunca cacheáveis (qualquer status fora de 200/304) |
| Testes | `backend/tests/security/test_cache_exception.py`, `test_cookies_and_cache.py`, `test_items_api.py` |

### Relação com o ADR 0006

- Substitui o ADR 0006 no ponto de cache: a resposta de imagem recebe `Cache-Control` diferente de `no-store`, decidido pelo middleware e não pela rota.
- Não substitui o ADR 0006 nos cabeçalhos de segurança (CSP, `nosniff`, `Referrer-Policy`, `Permissions-Policy`): esses continuam sobrepostos e fixos.

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| `no-store` em tudo | Obriga a baixar cada página de novo; leitor lento |
| Rota escolhe `Cache-Control` | Uma rota esquecida passa a cachear dado privado |
| Cache por service worker | `/api` fica fora do SW por decisão de segurança (ADR 0002) |
| `public` | Permitiria cache compartilhado de conteúdo autenticado |

## Consequências

- Positivas: leitura de páginas sem refetch; a exceção é estreita (duas rotas, 200/304, GET) e testada.
- Negativas e **risco registrado**:
  - Imagens ficam no cache do navegador por até 1 hora **após o logout**. Em dispositivo compartilhado, quem abrir o navegador pode ver páginas já lidas (FIND-2026-010, item 7).
  - Não mitigado nesta entrega. Opções: `Clear-Site-Data: "cache"` no logout ou TTL menor. Decisão pendente.
  - Um 304 exige autenticação (testado): o ETag não vaza existência de item a anônimo.
- Obrigações:
  - Nova rota que queira cache precisa de novo ADR e entrada na regex fixa.
  - Mudar o TTL ou o escopo da exceção exige novo ADR.

Não altera ADR 0001 a 0007 (substitui 0006 só no ponto de cache, conforme acima).
