# ADR 0009: Modelo de bloqueio de login (lockout por IP, conta e par IP-conta)

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- ADR 0002 exige limite por conta e por IP, atraso progressivo, bloqueio temporário, resposta idêntica para conta inexistente e senha errada, e log de falhas.
- Limite só por conta permite negar acesso à vítima de qualquer lugar (DoS de conta). Limite só por IP não contém ataque distribuído contra uma conta.
- Sem CAPTCHA (serviço externo proibido sem autorização, ADR 0002).
- Auditoria de FIND-2026-004 (corrida: N tentativas simultâneas passavam do limite) e FIND-2026-006 (uma linha de auditoria por tentativa bloqueada).

## Decisão

| Escopo | Chave | Limite padrão | Aplica-se |
|---|---|---|---|
| `ip_account` (principal) | par (IP, conta) | 5 falhas (`LOGIN_MAX_FAILURES_ACCOUNT`) | sempre |
| `account` | conta, todos os IPs | 15 falhas (`LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS`) | só a IPs sem login bem-sucedido nessa conta nos últimos 30 dias (`LOGIN_TRUSTED_IP_WINDOW_SECONDS`) |
| `ip` | IP, qualquer conta | 20 falhas (`LOGIN_MAX_FAILURES_IP`) | sempre |

| Tema | Decisão |
|---|---|
| Janela e bloqueio | Janela 900 s; bloqueio inicial 300 s, dobra a cada bloqueio seguido, teto 3600 s (`LOGIN_LOCKOUT_*`) |
| Estado | Calculado das falhas gravadas desde o último sucesso do escopo (`login_attempts`, chaves em HMAC). Sobrevive a reinício |
| Sucesso | Zera `ip_account` e `account` da conta. Não zera `ip` (um atacante com conta própria não apaga o contador do IP) |
| Ordem | Verifica o bloqueio antes da senha. Bloqueado: sem hash, e senha correta não passa |
| Reserva | Verificação do bloqueio e registro da falha acontecem sob trava de processo ANTES do Argon2. Sucesso ou tentativa abortada (hasher ocupado, erro) libera a reserva |
| Resposta | Mesmo status, corpo e tempo para conta existente, inexistente ou inativa: hash dummy e falha registrada nos três escopos |
| Auditoria | `login.locked` no máximo uma vez por IP a cada 60 s (tabela limitada a 10 000 chaves). Sem IP nem usuário em claro |
| Fórmula | `max_failures_from_one_address()` calcula o máximo de falhas que um único IP consegue numa janela. `LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS` precisa ser maior que esse valor, senão a aplicação não sobe. Padrão: pior caso 10, limite 15 |
| Validadores | `ACCOUNT < ALL_IPS`; `ACCOUNT <= IP`; `LOCKOUT_MAX >= LOCKOUT` |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| CAPTCHA | Serviço externo; proibido sem autorização (ADR 0002) |
| Bloqueio só por conta | Permite negar acesso à vítima de qualquer IP |
| Bloqueio só por IP | Não contém ataque distribuído contra uma conta |
| Zerar contador do IP no sucesso | Atacante com conta própria apagaria o contador entre tentativas em outras contas |
| Contador em memória | Perde estado no reinício e não sobrevive a futura migração de processo |

## Consequências

- Positivas: um IP sozinho nunca bloqueia a conta para todos; corrida de tentativas limitada; resposta idêntica para conta existente e inexistente; trilha de auditoria sem volume explosivo.
- Negativas:
  - Ataque distribuído bloqueia a vítima em IP novo por até 3600 s. Os IPs já confiáveis para a conta continuam entrando. **Pendente de decisão do dono** (FIND-2026-009, `open`).
  - Muitos usuários atrás do mesmo IP (NAT, operadora, proxy mal configurado) compartilham o contador do IP (ver ADR 0011).
  - A reserva é atômica só dentro de um processo. Com mais de uma worker, o limite passaria a ser multiplicado.
- Obrigações:
  - Mudar só os números por variável de ambiente, desde que a fórmula continue válida. Mudar a regra de escopo ou de reserva exige novo ADR.
  - Qualquer novo caminho de login (ex.: troca de senha) passa pelo mesmo bloqueio.

Complementa ADR 0002 (anti brute force). Não altera ADR 0001 a 0007.
