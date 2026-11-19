# ADR 0004: dependency-cruiser para fronteiras do frontend e versões travadas

- **Status:** Aceito
- **Data:** 2026-11-19

## Contexto

- `docs/PLANO.md` §3 deixou em aberto: dependency-cruiser ou eslint boundaries para o frontend.
- O frontend precisa de ferramentas de lint e tipos cujas versões sejam compatíveis com os plugins.

## Decisão

| Tema | Decisão |
|---|---|
| Fronteiras do frontend | dependency-cruiser (`frontend/.dependency-cruiser.cjs`, script `arch`) |
| Teste da regra | `frontend/tests/unit/architecture.test.ts` |
| Lint de segurança | ESLint 9 com plugin `security` e regras de bloqueio (`frontend/eslint.config.js`) |
| TypeScript | 6.0.3, versão exata |
| ESLint | 9.39.5, versão exata (`save-exact=true` em `frontend/.npmrc`) |

## Alternativas consideradas

| Alternativa | Motivo de descarte |
|---|---|
| eslint boundaries | Não adotada. Motivo não registrado na Fase 0; dependency-cruiser já cobre as regras e a checagem de ciclo |
| Versões flutuantes (`^`) | Quebra de compatibilidade com plugins de lint e tipos |

## Consequências

- Positivas: regra de fronteira verificada por teste e script; versões reproduzíveis.
- Negativas: atualizar TypeScript ou ESLint exige checar os plugins antes.
- Obrigações: não relaxar as regras de fronteira; corrigir o código quando falhar.
- Pendente: revisar as versões fixadas quando os plugins suportarem versões mais novas.
