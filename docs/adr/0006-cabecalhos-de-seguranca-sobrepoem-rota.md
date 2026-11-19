# ADR 0006: Cabeçalhos de segurança do middleware sobrepõem os da rota

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- ADR 0002 exige que o app emita os cabeçalhos de segurança (CSP, nosniff, Referrer-Policy, Permissions-Policy).
- Uma rota poderia enviar cabeçalho fraco (ex.: CSP com `unsafe-inline`) e o valor da rota chegaria ao cliente.
- O leitor EPUB/PDF pode precisar de política diferente (iframe, `sandbox`). Isso ainda não existe.

## Decisão

| Tema | Decisão |
|---|---|
| Precedência | `SecurityHeadersMiddleware` remove do `http.response.start` qualquer cabeçalho de segurança da rota e aplica o padrão |
| CSP por rota | Não existe relaxamento por rota. A CSP é fixa e testada (`test_security_headers.py`) |
| Mudança futura | Override por rota só por novo ADR, com opt-in explícito e teste |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Rota pode sobrepor o cabeçalho (padrão `setdefault`) | Uma rota esquecida enfraquece a CSP sem aviso |
| Override por rota já agora | Sem caso de uso ainda (leitor EPUB/PDF é Fase 2–4); seria superfície sem teste |

## Consequências

- Positivas: nenhuma rota afrouxa cabeçalhos; a política é uma só e fica em teste.
- Negativas: o leitor EPUB/PDF pode não funcionar com a CSP atual sem uma decisão nova.
- Obrigações: ao implementar o leitor EPUB/PDF, decidir por novo ADR se haverá override por rota. Não alterar este ADR.

Complementa ADR 0002. Não altera ADR 0001, 0003, 0004 ou 0005.
