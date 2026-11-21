# ADR 0011: FORWARDED_ALLOW_IPS obrigatória e IP real atrás de proxy

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- O app é público e roda atrás de um proxy que termina TLS (ADR 0002). Rate limit e lockout usam o IP do cliente.
- O padrão `172.17.0.1` do compose não era o gateway da rede do projeto (`infra_default`). Com proxy fora da lista, todos os clientes viravam um único IP, e 20 falhas de qualquer pessoa bloqueavam o login de todos (FIND-2026-001, severidade alta).
- Não é possível adivinhar o gateway de uma rede que o servidor define (rede e VPN são fora de escopo).

## Decisão

| Tema | Decisão |
|---|---|
| Fonte do IP real | Só uvicorn: `--proxy-headers --forwarded-allow-ips $FORWARDED_ALLOW_IPS`. O app usa `scope["client"]` e nunca lê `X-Forwarded-For`, `X-Real-IP` ou `Forwarded` |
| Padrão | Nenhum. Compose: `FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:?...}` (falha se vazio). Dockerfile: sem `ENV`; o `CMD` usa `${FORWARDED_ALLOW_IPS:?...}`. `.env.example`: campo vazio com instruções |
| Valor correto | IP ou CIDR do proxy que conecta ao container, como o container o vê. `*` só se a porta não for alcançável diretamente |
| Avisos | No startup, aviso genérico se vazio ou `*`. No primeiro login vindo de endereço privado ou loopback, aviso genérico (uma vez, sem endereço) |
| Normalização | IPv4-mapeado vira IPv4; IPv6 é agrupado por /64 (`normalize_client_ip`) |
| Lock por par sem sessão confiável | **Não implementado.** Contradiz ADR 0009 e o teste `test_ip_failures_are_not_reset_by_a_successful_login_of_another_account` |
| Teste | `backend/tests/regression/test_reg_006_forwarded_allow_ips_defaults_consistent.py` lê compose, Dockerfile e `.env.example` |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Fixar subnet e gateway no compose | Ainda depende da topologia do servidor (fora de escopo); pode divergir do proxy real |
| Middleware próprio que lê `X-Forwarded-For` | Confiança em cabeçalho forjável; o uvicorn já faz isso com lista explícita |
| `TRUSTED_PROXY_COUNT` | Removido: contava saltos, não endereços, e dependia da topologia |
| Padrão `127.0.0.1` na imagem | Proxy do host chega pelo gateway da bridge, nunca por loopback |

## Consequências

- Positivas: deploy sem a variável não sobe (falha explícita); o padrão enganoso deixou de existir; avisos apontam o erro de configuração.
- Negativas e **risco residual (raio do dano)**, registrado em FIND-2026-001:
  - Valor errado (proxy não listado) faz todos os clientes parecerem o proxy. O lock por IP (20 falhas, bloqueio de 300 a 3600 s) bloqueia todos os logins daquele endereço.
  - Os limites de `/api/v1/auth` (20/min, burst 10) e do `/api` (600/min, burst 200) passam a ser compartilhados por todos.
  - Lista ampla demais (`*` ou CIDR grande) permite forjar o IP e escapar do lock por IP.
  - O app apenas avisa; não corrige a configuração sozinho. A verificação é do operador (ver `.env.example`).
- Obrigações:
  - Não voltar a ler cabeçalhos de proxy no app.
  - Não restaurar padrão para a variável em compose, Dockerfile ou `.env.example` sem novo ADR.

Complementa ADR 0002 e ADR 0005 (proxy confiável). Não altera ADR 0001 a 0007.
