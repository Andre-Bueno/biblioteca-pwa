# ADR 0018: Oitavo host (checagem de release) e webhook de atualização

- **Status:** Proposto (aguarda aceite do dono; ver nota no fim)
- **Data:** 2026-11-21

## Contexto

- O admin precisa saber que há uma release nova e pedir a atualização sem que o app mexa no servidor.
- A regra 7 de `AGENTS.md` (raiz) só cobre metadados (ADR 0015). Acrescentar host ou canal de saída exige autorização do dono e ADR.
- O app roda com `read_only` e sem acesso ao Docker: atualizar a imagem é tarefa do host, não do container.

## Decisão

| Tema | Decisão |
|---|---|
| Oitavo host da allowlist | `api.github.com`, só para `GET /repos/<repo>/releases/latest` (`RELEASE_HOST`). Entra no `SafeGateway` como os outros: https, 443, sem redirecionamento, IP público, sem cookies |
| Repositório | `UPDATE_REPOSITORY` (`owner/name`); não é URL |
| Consulta | Preguiçosa: só quando um admin chama `/system/version` e o cache passou de `UPDATE_CHECK_INTERVAL_HOURS` (padrão 6 h). Sem thread em segundo plano. ETag (`If-None-Match`) |
| Desligar | `UPDATE_CHECK_ENABLED=false`; `APP_VERSION=dev` também desliga (não há release a comparar) |
| Única saída fora do `SafeGateway` | Webhook de atualização (`adapters/http/webhook_notifier.py`), destino só por `UPDATE_WEBHOOK_URL` (configuração; nunca vem do cliente) |
| Esquema do webhook | https sempre. http só com `UPDATE_WEBHOOK_ALLOW_HTTP=true` e só se **todo** endereço resolvido for loopback, privado (RFC 1918, ULA) ou CGNAT `100.64.0.0/10`. Link-local, não especificado, multicast e público recusados |
| Assinatura | `X-Update-Timestamp` e `X-Update-Signature: sha256=hex(HMAC_SHA256(secret, timestamp + "." + corpo))`. `UPDATE_WEBHOOK_SECRET` com ≥ 32 caracteres |
| Redirecionamento e tempo | Sem seguir redirecionamento (3xx é falha); 10 s no total; resposta lida até 4 KiB e ignorada |
| Aprovação | Só admin, por `POST /api/v1/system/update` com tag igual à última release conhecida; estado do pedido em memória |
| Receptor | Implementação de referência em `infra/deploy-hook/` (roda no host). O app nunca acessa o Docker |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Montar o socket do Docker no app | Dá root no host a qualquer falha do app; viola o isolamento do container |
| Atualização automática sem aprovação | Remove o controle do admin; release com erro iria ao ar sem decisão humana |
| Thread de verificação em segundo plano | Mais chamadas à fonte e mais estado; a consulta preguiçosa basta |
| Webhook para host público | Expõe o disparo de atualização; por isso só rede privada em http e https com assinatura |
| Watchtower ou outro atualizador de imagem | Atualiza sem aprovação do admin e fora da validação do app |

## Consequências

- Positivas: o app só ganha uma consulta de leitura e um disparo assinado; a execução fica no host, sob controle do dono; release inválida é barrada pelas verificações do receptor.
- Negativas e riscos conhecidos:
  - A allowlist passa de 7 para 8 hosts: a regra 7 da raiz e os mapas foram atualizados para refletir isso.
  - O webhook é a primeira saída que não passa pelo `SafeGateway`. A proteção é a configuração fixa, a checagem de rede e a assinatura; `docs/maps/SECURITY_MAP.md` lista o risco.
  - O estado do pedido em memória zera ao reiniciar o app.
  - Um receptor com política mais fraca do que a de referência reduz a proteção; a obrigação de preservar as verificações está em `infra/deploy-hook/README.md`.
- Obrigações:
  - Novo host ou nova saída fora do `SafeGateway` exige ADR novo e teste de allowlist ou de destino.
  - Mudar o contrato do webhook (cabeçalhos, corpo, assinatura) exige ADR novo e atualização do receptor.

Estende ADR 0015 (metadados e allowlist). Não altera ADR 0001 a 0017.

**Nota de status:** o registro da autorização do dono para o oitavo host foi informado pelo coordenador da entrega, não confirmado diretamente pelo dono. Este ADR só vira "Aceito" depois dessa confirmação; até lá, a regra 7 da raiz deve ser lida como pendente de confirmação.
