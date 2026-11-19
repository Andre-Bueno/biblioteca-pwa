# Protocolo de Auditoria de Segurança

Destinatário: **IA auditora (terceira)**. Leia primeiro `/AGENTS.md`, `docs/maps/SECURITY_MAP.md` e `docs/maps/CODEMAP.md`.

## 1. Regras do auditor

- Você **não altera código de produção**. Escreve apenas em `docs/security/`.
- Teste **somente** o ambiente local/staging indicado pelo dono. Nunca atacar produção ou terceiros.
- Não incluir segredos reais nos relatórios; mascare-os.
- Cada afirmação precisa de **evidência reproduzível** (comando, requisição, trecho de código com arquivo:linha).
- Distinga o que foi **comprovado** do que é **suspeita**. Informe o que não conseguiu testar.

## 2. Escopo mínimo da auditoria

1. **Executar** `scripts/check` e registrar o resultado.
2. **SAST**: `bandit`, `semgrep`, `ruff --select S`, ESLint security.
3. **Dependências e segredos**: `pip-audit`, `npm audit`, `gitleaks`.
4. **Revisão manual** de: auth/sessão, autorização (IDOR em todo endpoint), upload/leitura de arquivos, validação de entrada, CSRF, proteção anti brute force/rate limit, headers/CORS/CSP emitidos pelo app, logs. **Fora de escopo:** rede, VPN, TLS, firewall e configuração do servidor.
5. **Pentest dinâmico** (OWASP ASVS/Top 10 + API Top 10), incluindo os riscos próprios do projeto:
   - path traversal e zip-slip na leitura de CBZ/CBR/EPUB/pastas;
   - zip bomb / arquivos gigantes / muitos arquivos;
   - XSS via conteúdo de EPUB e metadados (título, nome de arquivo);
   - IDOR em `/items`, `/progress`, `/pages`;
   - brute force e enumeração em login; fixação/roubo de refresh token;
   - SSRF/ReDoS se existirem; abuso de `/library/scan`;
   - Range requests abusivos (DoS); cache poisoning de imagens.
6. **PWA/iOS**: service worker não pode cachear respostas autenticadas de outros usuários nem dados sensíveis sem controle; `manifest` e escopo corretos.
7. **Testes de regressão de segurança**: confirmar que `tests/security` e `tests/regression` cobrem cada finding antigo.

## 3. Formato obrigatório de cada finding

Arquivo: `docs/security/findings/FIND-<AAAA>-<NNN>.md`

```markdown
---
id: FIND-2026-001
title: <título curto>
severity: critical | high | medium | low | info
confidence: confirmed | likely | suspected
cwe: CWE-22
owasp: A01:2021
status: open
component: backend/app/api/items.py
affected: [arquivo:linha, ...]
found_by: <nome da IA/ferramenta>
date: 2026-11-19
---

## Resumo
Uma frase: o que é e qual o impacto.

## Como reproduzir
Passos exatos (comandos/requisições). Resultado esperado vs obtido.

## Evidência
Trechos, saídas, arquivo:linha.

## Impacto
Quem explora, o que ganha, pré-condições.

## Correção recomendada
O que mudar (sem alterar além do necessário). Referência de padrão seguro.

## Critérios de aceite
- [ ] Exploit original não funciona mais
- [ ] Teste de regressão `tests/regression/test_reg_<NNN>_<slug>.py` criado e verde
- [ ] `scripts/check` verde
- [ ] Mapas/CHANGELOG atualizados
```

Severidade: *critical* = execução remota/vazamento geral/bypass de auth · *high* = acesso indevido a dados de outro usuário, DoS fácil · *medium* = exige condições · *low* = endurecimento · *info* = observação.

## 4. Fila de remediação (entrada do agente corretor)

Após os findings, gere `docs/security/REMEDIATION_QUEUE.md`:

```markdown
# Fila de Remediação — <data>
Relatório de origem: <ID da auditoria>
Resultado de scripts/check na base auditada: <verde/vermelho + resumo>

| Ordem | ID | Severidade | Componente | Depende de | Esforço (P/M/G) |
|---|---|---|---|---|---|
| 1 | FIND-2026-001 | critical | backend/... | — | P |

## Observações para o corretor
- Agrupamentos seguros (corrigir juntos) e conflitos entre correções.
- O que NÃO mexer.
```

Também gere `docs/security/AUDIT_REPORT_<data>.md` com: escopo, método, ferramentas e versões, cobertura (o que ficou de fora), resumo por severidade e conclusão.

## 5. Protocolo do agente corretor

Para cada item da fila, na ordem:
1. Leia o finding e reproduza o problema.
2. Escreva o **teste de regressão que falha**.
3. Aplique a correção mínima, respeitando as camadas do `AGENTS.md`.
4. Rode `scripts/check` (tudo verde).
5. Atualize: status do finding (`status: fixed` + `fixed_in: <commit>`), `SECURITY_MAP.md`, `TEST_MAP.md`, `CODEMAP.md`, `CHANGELOG.md` (seção Security) e `docs/history/`.
6. Não feche como `verified`: isso é do auditor. Em discordância, marque `status: disputed` com justificativa.

Ciclo de status: `open → fixed → verified` (ou `disputed` / `accepted-risk` com aprovação do dono).

## 6. Reteste

O auditor reexecuta os exploits dos findings `fixed`, confirma o teste de regressão e marca `verified`. Findings novos seguem o mesmo fluxo.
