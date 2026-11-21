# Fila de Remediação — 2026-11-19
Relatório de origem: AUDIT-2026-11-19 (`docs/security/AUDIT_REPORT_2026-11-19.md`), Fase 1 do backend
Resultado de scripts/check na base auditada: **verde** (741 passed, 1 skipped por falta de privilégio de symlink no Windows; ruff, mypy, import-linter, bandit, pip-audit, ESLint, tsc, vitest, build OK; `npm audit` completo com 4 avisos moderados informativos; gitleaks ausente, checagem de segredos reduzida)

| Ordem | ID | Severidade | Componente | Depende de | Esforço (P/M/G) |
|---|---|---|---|---|---|
| 1 | FIND-2026-001 | high | infra/compose.example.yml, infra/Dockerfile, .env.example | — | P |
| 2 | FIND-2026-002 | medium | backend/app/adapters/security/argon2_hasher.py, api/auth.py | 001 (mesmo vetor de DoS por IP compartilhado) | M |
| 3 | FIND-2026-003 | medium | backend/app/adapters/extractors/cbz.py, folder.py | — | M |
| 4 | FIND-2026-004 | low | backend/app/services/auth_service.py | — | M |
| 5 | FIND-2026-005 | low | backend/app/services/auth_service.py, refresh_token_repository.py | — | M |
| 6 | FIND-2026-006 | low | backend/app/services/auth_service.py, adapters/persistence/audit_log.py | — | P |
| 7 | FIND-2026-008 | low | backend/app/main.py | — | P |
| 8 | FIND-2026-007 | low | backend/app/domain/password_policy.py | — | P |
| 9 | FIND-2026-012 | low | backend/app/services/scan.py | — | P |
| 10 | FIND-2026-009 | low | backend/app/services/auth_service.py | decisão do dono (accepted-risk ou mitigação) | P |
| 11 | FIND-2026-010 | info | infra/Dockerfile, api/csrf.py, api/security_headers.py (subitens) | — | M |
| 12 | FIND-2026-011 | info | backend/app/adapters/extractors/folder.py | 003 (mesmo arquivo/área) | P |

Próximo número livre de teste de regressão antes desta fila: 006. Atribuídos: 006 (FIND-001), 007 (002), 008 (003), 009 (004), 010 (005), 011 (006), 012 (007), 013 (008), 014 (009), 015 (010), 016 (011), 017 (012). Livre depois: 018.

## Observações para o corretor
- **Agrupamentos seguros (corrigir juntos):**
  - 004 + 005 + 006 + 002 mexem em `auth_service.py`/`argon2_hasher.py`: fazer em PRs separados e em sequência (002 -> 004 -> 005 -> 006) para não gerar conflito; 004 e 005 alteram o fluxo de login/refresh e seus testes de concorrência devem usar threads reais (não o `TestClient` sequencial).
  - 003 + 011 tocam extratores (`cbz.py`, `folder.py`): corrigir juntos se o índice de páginas for gerado no scan.
  - 001 é só infra/doc; pode ir antes de tudo e não conflita com o código.
- **Conflitos entre correções:** 002 (fail-fast no semáforo) muda o tempo/status do login sob carga; manter a resposta idêntica para usuário existente e inexistente (não criar oráculo). 004 (reservar tentativa antes do Argon2) altera quando a falha é registrada: manter o comportamento "falhas durante um lock não são registradas". 005 (janela de tolerância) deve manter `token.reuse_detected` para reuso fora da janela.
- **O que NÃO mexer:** middlewares CSRF, rate limit, body limit, security headers e a lógica de cache de imagens (testados, nenhum bypass encontrado); `LocalStorage`; validação de nomes/ZIP em `cbz.py` (`_validate`, `_check_member_name`); ordem dos middlewares em `main.py`; política de lock por IP/par (só a corrida). Não relaxar limites para "passar" testes.
- **Decisão do dono necessária:** FIND-2026-009 (risco residual do lock por conta; `accepted-risk` só com aprovação) e subitens de FIND-2026-010 que exijam dependência nova (denylist maior, HSTS).
- Os PoCs de `docs/security/poc/` usam limites de taxa relaxados e `X-Forwarded-For` confiável só na instância local; não usar em outro ambiente.

## Estado após correções

Atualizado em 2026-11-19 por leitura de cada `findings/FIND-2026-NNN.md`. Seção nova; a fila e o relatório acima são históricos e não foram alterados. Status: `open → fixed → verified` (só o auditor marca `verified`). Nenhum finding está `verified`.

| ID | Severidade | Status | Correção (resumo) | Teste | Pendência |
|---|---|---|---|---|---|
| FIND-2026-001 | high | fixed | Compose e imagem exigem `FORWARDED_ALLOW_IPS` sem padrão; avisos no startup e no primeiro login privado | `test_reg_006` | Imagem não construída; risco residual do raio do dano (ADR 0011) |
| FIND-2026-002 | medium | fixed | Argon2 com gate de 2 slots e 8 em espera; excedente → 503 sem registrar falha | `test_reg_007` | Reverificação ao vivo: p95 não demonstrado |
| FIND-2026-003 | medium | fixed | Índice de página em cache LRU; uma entrada por página; gate de 4 leitores | `test_reg_008` | Sem streaming; pico de memória 4 × 64 MiB |
| FIND-2026-004 | low | fixed | Reserva de tentativa antes do Argon2, sob trava de processo | `test_reg_009` | Atômico só por processo; reteste do PoC pendente |
| FIND-2026-005 | low | fixed | `rotate` atômico com janela de 10 s (`REFRESH_REUSE_GRACE_SECONDS`) | `test_reg_010` | Ladrão dentro da janela não detectado; reteste do PoC pendente |
| FIND-2026-006 | low | fixed | `login.locked` deduplicado por IP a cada 60 s; purga isolada e independente de login; comando `purge` | `test_reg_011` | — |
| FIND-2026-007 | low | fixed | Username contido ou invertido, repetição fraca e sequências recusados | `test_reg_012` | Denylist grande não feita (exige arquivo de dados) |
| FIND-2026-008 | low | fixed | `redirect_slashes=False` | `test_reg_013` | — |
| FIND-2026-009 | low | **open** | Nenhuma mitigação implementada; teste de comportamento mantido | reg_014 reservado | **Decisão do dono**: `accepted-risk` ou mitigação aprovada |
| FIND-2026-010 | info | fixed (parcial) | Adotados: `--no-server-header`, limites do uvicorn, `==` nas dependências, `Origin` repetido → 403 | `test_reg_015` | Pendentes: itens 4 (CSRF não amarrado à sessão), 6 (proxy), 7 (`Clear-Site-Data`), 8 (HEAD em `/health`), 9 (HSTS do proxy), 10 (entropia da chave), 11 (IP no audit), 12 (query nos logs), 13 (semgrep e gitleaks) |
| FIND-2026-011 | info | fixed | Índice de pasta valida bytes de todos os arquivos; `page_count` coincide com páginas legíveis | `test_reg_016` | — |
| FIND-2026-012 | low | fixed | Raiz vazia, ilegível ou com erro de caminhada não marca itens como ausentes | `test_reg_017` | Sem cancelamento de scan |

Contagem: 11 `fixed`, 1 `open`, 0 `verified`, 0 `disputed`, 0 `accepted-risk`.

Pendências fora dos findings (ver `docs/maps/SECURITY_MAP.md`, seção Pendências): build da imagem Docker, lockfile do backend com hashes (M8), CI inexistente, gitleaks e semgrep ausentes, `check.sh` não testado em Linux real, rate limit e lockout em memória (uma worker).
