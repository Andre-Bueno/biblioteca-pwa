# ADR 0005: Padrões fechados (fail-closed) na verificação e na exposição do app

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- A revisão da Fase 0 achou: teste de arquitetura que não executava nada (A1); `check.sh` que dava OK sem executar etapas (A2); código de saída e resumo que escondiam etapas não executadas (M1); regex de rede amplo demais (M2).
- ADR 0002 exige defesa dentro do app e exposição controlada. A porta publicada e a confiança em cabeçalho de proxy são configuráveis.

## Decisão

| Tema | Decisão |
|---|---|
| Auditoria sem rede | FALHA por padrão; vira AVISO só com `-AllowOffline` / `--allow-offline`, declarado no resumo |
| Etapa não executada | Nunca OK silencioso: FALHA, ou AVISO declarado |
| Modos `-Fast` e `-Only` | Resumo diz MODO RAPIDO / MODO PARCIAL; "RESULTADO: OK" limpo só sem avisos e sem esses modos |
| Teste de arquitetura | Executa import-linter de verdade; falha em violação |
| Configuração do app | Não sobe sem `SECRET_KEY` válida |
| Porta publicada | Loopback (`127.0.0.1`) por padrão; exposição exige `BIND_ADDRESS` explícito |
| Proxy confiável | uvicorn confia só em `FORWARDED_ALLOW_IPS`; nunca `*` com acesso direto |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| Auditoria sem rede como AVISO por padrão | Gera falso OK em ambiente sem rede |
| Pular etapa sem declarar | Falso OK |
| Padrão `0.0.0.0` na porta | Expõe o app sem proxy na frente (ADR 0002) |

## Consequências

- Positivas: "verde" significa que as etapas rodaram; expor o app exige ato explícito.
- Negativas: ambiente sem rede precisa de `-AllowOffline`; `-Fast` e `-Only` saem com código 0 e exigem leitura do resumo.
- Obrigações: não tornar AVISO o padrão de auditoria sem rede; manter a declaração de modo rápido e parcial.
- Pendente: `check.sh` não validado em Linux real; gitleaks não instalado.

Complementa ADR 0002. Não altera ADR 0001, 0003 ou 0004.
