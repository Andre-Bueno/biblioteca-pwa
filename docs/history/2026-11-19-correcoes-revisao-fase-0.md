# 2026-11-19 — Correções da revisão da Fase 0

Esta entrega é só documentação. Testes e scripts foram rodados nesta revisão: backend `pytest` 64 passed; frontend `vitest` 67 passed; `scripts/check` OK com 1 aviso (npm audit completo: 4 moderadas). Uma primeira execução do check falhou por arquivo temporário de outro processo (`frontend/src/zz_secret_tmp.txt`), que já não existia na segunda execução.

## O que foi feito

| Área | Entrega | Onde |
|---|---|---|
| Backend | Teste de arquitetura executa import-linter; 25 casos negativos parametrizados e controle positivo (33 após a 2ª revisão) | `backend/tests/architecture/test_layers.py` |
| Backend | 6 contratos do import-linter; `domain` proíbe pydantic, starlette e httpx; `core` coberto | `backend/pyproject.toml` |
| Backend | `create_app()` carrega `Settings`, guarda em `app.state.settings`; falha sem `SECRET_KEY` válida | `backend/app/main.py`, `backend/app/core/config.py` |
| Backend | Testes de `SECRET_KEY` | `backend/tests/security/test_settings.py` |
| Backend | Exceção vira 500 JSON genérico com cabeçalhos e `Cache-Control: no-store`; CSP sem `'unsafe-inline'` (fixada em teste) | `backend/app/api/security_headers.py` |
| Infra | Dockerfile com HEALTHCHECK em Python; uvicorn com `--proxy-headers --forwarded-allow-ips` | `infra/Dockerfile` |
| Infra | Porta em `${BIND_ADDRESS:-127.0.0.1}:${HOST_PORT:-8000}`; `FORWARDED_ALLOW_IPS` | `infra/compose.example.yml` |
| Infra | `.dockerignore` e `.env.example` na raiz | `.dockerignore`, `.env.example` |
| Frontend | `tsconfig.json` só com referências; `tsconfig.app.json` (src) e `tsconfig.node.json`; `typecheck` nos dois; `build` = `vite build` | `frontend/tsconfig*.json`, `frontend/package.json` |
| Frontend | ESLint bloqueia `fetch`, `localStorage` e `sessionStorage` também via `window`, `globalThis` e `self` | `frontend/eslint.config.js` |
| Frontend | Testes de regras ESLint e de tokens CSS | `frontend/tests/unit/eslint-rules.test.ts`, `theme-css.test.ts` |
| Frontend | dependency-cruiser com `not-to-unresolvable`, `not-to-dev-dep` e `tsPreCompilationDeps`; 8 fixtures negativas | `frontend/.dependency-cruiser.cjs`, `frontend/tests/fixtures/arch-*/` |
| Frontend | api-client: `credentials` conforme `baseUrl`; corpo não-JSON vira `ApiError`; `AbortError` propagado | `frontend/src/shared/api-client/client.ts` |
| Frontend | Tema com tokens `--if-dark`/`--if-light`, sem duplicar a paleta | `frontend/src/shared/theme/theme.css` |
| Scripts | Sem rede = FALHA por padrão (`-AllowOffline` vira AVISO); regex de rede restrito; `-Fast` e `-Only` declarados; scan de segredos ampliado; `gitleaks.toml` | `scripts/check.ps1`, `scripts/check.sh`, `scripts/gitleaks.toml` |
| Docs | Mapas, CHANGELOG, ADR 0005 | `docs/maps/`, `docs/adr/`, `CHANGELOG.md` |

## Achados da revisão e status

| ID | Achado | Status | Onde |
|---|---|---|---|
| A1 | Teste de arquitetura não executava nada e sempre passava | Corrigido | `backend/tests/architecture/test_layers.py` |
| A2 | `check.sh` dava OK sem executar etapas | Corrigido | `scripts/check.sh`, `scripts/check.ps1` |
| M1 | Código de saída e resumo escondiam etapas não executadas | Corrigido (ver discrepâncias: `-Fast`/`-Only` saem com 0) | `scripts/` |
| M2 | Regex de rede amplo demais | Corrigido | `scripts/check.ps1`, `scripts/check.sh` |
| M3 | `SECRET_KEY` definida mas não validada no startup | Corrigido | `backend/app/main.py`, `backend/app/core/config.py` |
| M4 | Erro 500 sem cabeçalhos de segurança | Corrigido | `backend/app/api/security_headers.py` |
| M5 | Quem serve o HTML da SPA (e seus cabeçalhos) | **Aberto**: aguarda decisão do dono | — |
| M6 | CSP com `style-src 'unsafe-inline'` | Corrigido | `backend/app/api/security_headers.py` |
| M7 | Brechas nos contratos do import-linter | Corrigido (6 contratos) | `backend/pyproject.toml` |
| M8 | Sem lockfile do backend; Dockerfile sem hashes | **Pendente** | `infra/Dockerfile` |
| M9 | Sem `.dockerignore` | Corrigido | `.dockerignore` |
| B1–B8 | Frontend e scripts (IDs não informados; listados por tema na seção "O que foi feito") | Corrigidos | `frontend/`, `scripts/` |
| B9 | Tema não persiste (preferência só em memória) | **Dívida** | `frontend/src/shared/theme/ThemeProvider.tsx` |

## Não corrigidos e pendentes

| Item | Motivo | Próximo passo |
|---|---|---|
| M5: quem serve o HTML da SPA | Decisão do dono | Registrar decisão; se mudar a arquitetura, novo ADR |
| M8: lockfile do backend e hashes no Dockerfile | Pendente | Fase 1, antes de publicar |
| CAPTCHA (Turnstile/hCaptcha) | Serviço externo | Depende de autorização do dono |
| Checagem de senha vazada | Serviço externo | Depende de autorização do dono |
| Teste que falha se houver módulo fora do CODEMAP | Planejado; não existe | Implementar em `backend/tests/architecture/` |
| Build da imagem Docker e `docker compose` | Não validados | Rodar build antes de publicar |
| gitleaks | Não instalado; `scripts/gitleaks.toml` nunca executado | Instalar e rodar no `check` |
| `scripts/check.sh` | Executado só com bash do Git/MinGit no Windows; não testado em Linux real | Testar em Linux ou CI |
| B9: tema não persiste | Preferência em memória (`ThemeProvider.tsx` diz "persistir no servidor depois") | Persistir com a feature `settings` |
| CSRF no servidor, login, rate limit, CORS, `Cache-Control: no-store` em respostas autenticadas | Fase 1 | Ver `docs/maps/SECURITY_MAP.md` |

## Questões abertas para o dono

| Tema | Pergunta |
|---|---|
| M5 | O HTML da SPA é servido pelo FastAPI ou pelo servidor/proxy? Afeta CSP e cabeçalhos do shell. |
| `-Fast` / `-Only` | Código 0 com MODO RAPIDO ou PARCIAL é aceito em CI, ou deve falhar? |

## Discrepâncias encontradas entre código e documentação

| Item | Detalhe |
|---|---|
| `TRUSTED_PROXY_COUNT` | Existe em `Settings` e no compose, mas não é usado. O proxy confiado de fato é `FORWARDED_ALLOW_IPS` (uvicorn). Os mapas citavam `TRUSTED_PROXY_COUNT` como mecanismo. Resolvido na 2ª revisão: removido. |
| Código de saída de `--only` | `scripts/README.md` cita código 2 para `--only` inválido; vale só para `check.sh`. O `check.ps1` usa `ValidateSet`, código não documentado. |
| Histórico Fase 0 | `docs/history/2026-11-19-fase-0-scaffold.md` tem pendências antigas (SECRET_KEY, `no-store`, teste do CODEMAP). É registro histórico e não foi editado. |
| Mapas anteriores | ARCHITECTURE dizia `credentials: include`; o padrão real é `same-origin` (baseUrl vazio). |

## Próximo passo

Fase 1: auth, CSRF no servidor, `Cache-Control: no-store` em respostas autenticadas, rate limit, CORS e migrações. Antes: decidir M5 e M8.

## Segunda revisão (mesma data)

Correções de segurança sobre a Fase 0, com achados novos. Sem endpoint novo.

### O que mudou no código

| Área | Entrega | Onde |
|---|---|---|
| Backend | `SECRET_KEY`: ≥12 caracteres distintos, sem espaços nas pontas, sem bloco de até 8 repetido | `backend/app/core/config.py` |
| Backend | `hide_input_in_errors=True`: valor da chave não aparece no erro de validação | `backend/app/core/config.py` |
| Backend | `TRUSTED_PROXY_COUNT` removido; `FORWARDED_ALLOW_IPS` é a única fonte do IP real | `backend/app/core/config.py`, `infra/compose.example.yml`, `.env.example` |
| Backend | Middleware: cabeçalhos sobrepõem a rota (ADR 0006); desconexão após início vai para debug; `CancelledError` propaga | `backend/app/api/security_headers.py` |
| Backend | 33 casos negativos de arquitetura (todo item de `forbidden_modules`); `ignore_imports` com `app.adapters.**` | `backend/tests/architecture/test_layers.py`, `backend/pyproject.toml` |
| Backend | Testes de `SECRET_KEY` (7 casos de baixa entropia, 3 de espaços) e de middleware (desconexão, `CancelledError`, erro real) | `backend/tests/security/` |
| Backend | Teste de regressão REG-001 | `backend/tests/regression/test_reg_001_secret_key_not_in_error.py` |
| Backend | Regras de teste (500 com `raise_server_exceptions=False`, `caplog`, casos negativos) | `backend/tests/AGENTS.md` |
| Infra | Compose monta `../library:/library:ro` (relativo a `infra/`) | `infra/compose.example.yml` |
| Frontend | api-client: `text()` + `JSON.parse`; 2xx vazio → `undefined`; `baseUrl` sem barra dupla | `frontend/src/shared/api-client/client.ts` |
| Frontend | ESLint: XHR, WebSocket e `sendBeacon` só no api-client; `indexedDB` só em `shared/offline` | `frontend/eslint.config.js` |
| Frontend | 67 testes: api-client 30, ESLint 22, arquitetura 9, tema CSS 3, home 1, tema 2 | `frontend/tests/unit/` |

### Achados da segunda revisão

| ID | Achado | Status | Onde |
|---|---|---|---|
| M-1 | `SECRET_KEY` inválida aparecia no erro de validação (log) | Corrigido (REG-001) | `backend/app/core/config.py`, `test_reg_001_secret_key_not_in_error.py` |
| M-2 | `TestClient` padrão re-levanta a exceção do middleware de 500; o teste precisa de `raise_server_exceptions=False` e o log, de `caplog` | Corrigido: teste ajustado; regra documentada | `backend/tests/security/test_security_headers.py`, `backend/tests/AGENTS.md` |
| M-3 | `ENV FORWARDED_ALLOW_IPS=127.0.0.1` no Dockerfile diverge de `172.17.0.1` no compose. Rodar a imagem sem compose não confia no proxy do host | Parcial: compose e `.env.example` corrigidos. Dockerfile **pendente** | `infra/Dockerfile` (linha 19) |
| M-4 | Regressão | **Não determinado**: descrição não informada ao docs-keeper e não encontrada no disco | — |
| B-1 a B-10 | Itens não informados ao docs-keeper e não encontrados no disco | **Não determinado**: lista e status do dono necessários | — |

### Decisões

| Decisão | Registro |
|---|---|
| `FORWARDED_ALLOW_IPS` é a única fonte do IP real; `TRUSTED_PROXY_COUNT` removido | Já previsto em ADR 0005; sem ADR novo |
| Cabeçalhos da rota não enfraquecem a política de segurança | ADR 0006 |
| Todo bug ou finding corrigido ganha `test_reg_NNN`; achados já corrigidos ficam cobertos por testes nomeados em `tests/architecture` e `tests/security` | `docs/maps/TEST_MAP.md` (convenção de regressão) |

### Verificação

| Verificação | Resultado |
|---|---|
| Backend `pytest` | 64 passed |
| Frontend `vitest` | 67 passed |
| `scripts/check` | OK com 1 aviso (npm audit completo: 4 moderadas via `vite-plugin-pwa`/`minimatch`); gitleaks não instalado |
| Primeira execução do `scripts/check` | FALHA por `frontend/src/zz_secret_tmp.txt` (arquivo temporário de outro processo, ausente na segunda execução) |

### Discrepâncias corrigidas nos mapas

| Onde | Antes | Agora |
|---|---|---|
| CODEMAP, SECURITY_MAP, CHANGELOG | `SECRET_KEY` "≥8 distintos" | ≥12 distintos |
| CODEMAP, SECURITY_MAP | `TRUSTED_PROXY_COUNT` como setting e como mecanismo | Removido; `FORWARDED_ALLOW_IPS` |
| ARCHITECTURE, TEST_MAP, CODEMAP | 25 casos de arquitetura | 33 |
| TEST_MAP, CODEMAP | ESLint "11 formas" | 18 formas proibidas + 4 permissões |
| TEST_MAP, CODEMAP | Regressão backend vazia | `test_reg_001` |
| CODEMAP | "`test_reg_*` ainda não existe" | Existe |
| frontend/AGENTS.md | Sem regra de XHR, WebSocket, `sendBeacon`, `indexedDB` | Regra adicionada |

Busca por "testes frontend 48", "≥8 distintos" e `TRUSTED_PROXY_COUNT` em `docs/` e `AGENTS.md`: após esta entrega, as únicas ocorrências são registros históricos ("antes") e a indicação de remoção.

### Pendências novas

| Item | Próximo passo |
|---|---|
| M-3: `ENV` do Dockerfile | Alinhar ao compose ou remover o `ENV` |
| `npm audit`: 4 moderadas | Avaliar atualização de `vite-plugin-pwa` |
| CSP por rota (EPUB/PDF) | Novo ADR se houver override |
| Acessos indiretos no ESLint | Revisão de código |
| M-4 e B-1 a B-10 | Dono informar descrição e status |
