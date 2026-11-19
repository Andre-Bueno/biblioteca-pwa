# scripts/

## check: verificacao unica

    # Windows (PowerShell)
    scripts\check.ps1                 # tudo
    scripts\check.ps1 -Fast           # pula build e audits (MODO RAPIDO)
    scripts\check.ps1 -Only backend   # ou frontend (resultado PARCIAL)
    scripts\check.ps1 -AllowOffline   # auditorias sem rede viram AVISO

    # Linux/CI
    scripts/check.sh [--fast] [--only backend|frontend] [--allow-offline]

Nao para na primeira falha: roda tudo, imprime tabela `etapa | OK/FALHA/AVISO | tempo` e sai com codigo 1 se alguma etapa obrigatoria falhar.

## Regras de saida (nenhum falso OK)

Etapa nao executada nunca e OK silencioso:

- **Sem rede** (pip-audit, `npm audit --omit=dev`): FALHA por padrao. Com `-AllowOffline` / `--allow-offline` vira AVISO e o resumo declara "OFFLINE: auditoria(s) nao executada(s)". Deteccao de rede restrita a erros especificos: pip-audit (`ConnectionError`, `Max retries`, `getaddrinfo`, `NewConnectionError`) e npm (`ENOTFOUND`, `EAI_AGAIN`, `ECONNREFUSED`, `ETIMEDOUT`, `ECONNRESET`, `getaddrinfo`, `audit endpoint returned an error`, `FetchError`). Outras falhas continuam FALHA.
- **`-Fast` / `--fast`**: pula build e audits (AVISO por etapa). Sai com codigo 0 somente se nada falhou, e o resumo diz "MODO RAPIDO: etapas puladas, NAO equivale a verificacao completa".
- **`-Only` / `--only`**: o resumo diz "MODO PARCIAL: a outra parte NAO foi verificada". Argumento invalido: no `check.sh`, `--only` sem argumento ou com valor invalido sai com codigo 2. No `check.ps1` o parametro usa `ValidateSet` (aceita so `backend` ou `frontend`) e o PowerShell recusa o valor antes de rodar; o codigo 2 nao se aplica a ele.
- **Codigo 0 com `-Fast` ou `-Only` NAO e gate**: nao usar como gate de CI ou de merge. Para gate, rodar a execucao completa (sem `-Fast` e sem `-Only`) e exigir `RESULTADO: OK` limpo.
- **`npm audit` completo**: informativo; exit 0 com AVISO (ver "Aviso conhecido").
- venv/node_modules ausentes, diretorio de etapa inexistente: FALHA.
- Codigo 0 com avisos imprime "OK com N aviso(s) (avisos NAO sao sucesso completo)". "RESULTADO: OK" limpo so aparece sem nenhum aviso, sem `-Fast` e sem `-Only`.

## Etapas

Backend (`backend/.venv`; se faltar: `cd backend; python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"`; o check.sh aceita `.venv/bin` ou `.venv/Scripts`):
`ruff check`, `ruff format --check`, `mypy`, `lint-imports` (arquitetura), `pytest` (unit, integration, regression, security, architecture), `bandit -q -r app`, `pip-audit`.

Frontend (`npm ci` antes): `lint`, `typecheck`, `test`, `arch`, `format:check`, `build`, `npm audit --omit=dev` (obrigatorio, deve ficar limpo).

## Scan de segredos

Usa `gitleaks` se estiver no PATH, com `scripts/gitleaks.toml` (`--config`: estende as regras padrao e ignora `.venv`, `venv`, `node_modules`, `dist`, `.git`). Senao faz checagem **reduzida** por regex, sem diferenciar maiusculas de minusculas, igual em .ps1 e .sh:

- Padroes fortes: chave privada PEM, `AKIA...`, tokens GitHub (`gh[pousr]_`), Slack (`xox`), Google (`AIza`), Stripe live, JWT (tres segmentos `eyJ...`).
- Padroes frouxos (ignoram valores placeholder claros: `changeme`, `your-...`, `example`, `xxx`, `<...>`, `${...}`, `os.environ`, `getenv`, `process.env`, `user:password@`): `SECRET_KEY=` com qualquer valor nao-espaco/aspas de 8+ caracteres, `password=`/`passwd=` com literal entre aspas, URL com credencial `://usuario:senha@`.
- `.env.example` e varrido (placeholders ignorados); outros `.env*` ficam de fora.
- Diretorios sao podados ANTES de enumerar: `.venv`, `venv`, `node_modules`, `.git`, `dist`, `build`, caches, `*.egg-info`, `.claude`. `tests/` e varrido; so ficam de fora fixtures conhecidas (`backend/tests/fixtures`, `backend/tests/data`, `frontend/e2e/fixtures`); se precisar de outra, adicione a lista `fixtureDirs` no .ps1 e o loop equivalente no .sh.
- Erro de leitura e FALHA, nunca falso OK: no check.sh, `grep` com status >= 2; no check.ps1, falha de `Select-String` (arquivo travado/sem permissao) ou de listagem de diretorio. Os caminhos ilegiveis sao listados. Binarios/extensoes ignoradas, arquivos >= 1MB e diretorios podados continuam fora (ignorados de forma explicita). stderr nao e descartado.

Nao substitui o gitleaks.

## Aviso conhecido e aceito

`npm audit` completo (informativo, nao bloqueante) reporta 4 achados moderados transitivos de `vite-plugin-pwa -> workbox-build -> glob/minimatch`. Existem so no build, nao vao para o runtime (`--omit=dev` esta limpo). A correcao exige upgrade major do vite-plugin-pwa; reavaliar periodicamente.
