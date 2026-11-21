#!/usr/bin/env bash
# Verificacao unica do projeto (equivalente a scripts/check.ps1).
# Uso: scripts/check.sh [--only backend|frontend] [--fast] [--allow-offline]
# npm audit completo e AVISO nao bloqueante: 4 achados moderados conhecidos e aceitos,
# transitivos de vite-plugin-pwa -> workbox-build -> glob/minimatch (so no build).
# Etapas nao executadas NUNCA contam como OK silenciosamente: ou FALHA, ou AVISO declarado no resumo.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USAGE="uso: $0 [--only backend|frontend] [--fast] [--allow-offline]"
ONLY=""; FAST=0; ALLOW_OFFLINE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --only|-Only)
      if [ $# -lt 2 ] || [ -z "$2" ]; then echo "--only exige um argumento (backend|frontend)"; echo "$USAGE"; exit 2; fi
      ONLY="$2"; shift 2 ;;
    --fast|-Fast) FAST=1; shift ;;
    --allow-offline|-AllowOffline) ALLOW_OFFLINE=1; shift ;;
    *) echo "$USAGE"; exit 2 ;;
  esac
done
case "$ONLY" in ""|backend|frontend) ;; *) echo "--only deve ser backend ou frontend"; exit 2 ;; esac

# Erros de rede ESPECIFICOS (nao casar palavras genericas como 'connection' ou 'timed out').
PIP_NET='ConnectionError|Max retries|getaddrinfo|NewConnectionError'
NPM_NET='ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ETIMEDOUT|ECONNRESET|getaddrinfo|audit endpoint returned an error|FetchError'
FAST_SKIPPED=0; OFFLINE_WARNED=0

NAMES=(); STATUS=(); SECS=(); NOTES=()
add() { NAMES+=("$1"); STATUS+=("$2"); SECS+=("$3"); NOTES+=("${4:-}"); }

# step <nome> <dir> <warnonly 0|1> <net_regex ou ""> cmd...
step() {
  local name="$1" dir="$2" warn="$3" netre="$4"; shift 4
  echo; echo "=== $name ==="
  local t0=$SECONDS
  if [ ! -d "$dir" ]; then
    echo "diretorio inexistente: $dir"; add "$name" FALHA 0 "diretorio inexistente"; return
  fi
  local code out="" st=OK note=""
  if [ -n "$netre" ]; then
    out="$(cd "$dir" && "$@" 2>&1)"; code=$?; echo "$out"
  else
    ( cd "$dir" && "$@" ); code=$?
  fi
  if [ $code -ne 0 ]; then
    if [ -n "$netre" ] && printf '%s\n' "$out" | grep -Eq "$netre"; then
      if [ $ALLOW_OFFLINE = 1 ]; then st=AVISO; note="nao executado: sem rede (--allow-offline)"; OFFLINE_WARNED=$((OFFLINE_WARNED + 1))
      else st=FALHA; note="sem rede: auditoria NAO executada (use --allow-offline para aceitar como AVISO)"; fi
    elif [ "$warn" = 1 ]; then st=AVISO
    else st=FALHA; fi
  fi
  add "$name" "$st" "$((SECONDS - t0))" "$note"
}
skip() {
  echo; echo "=== $1 === (nao executado: $2)"; add "$1" AVISO 0 "nao executado: $2"
  [ "$2" = "--fast" ] && FAST_SKIPPED=$((FAST_SKIPPED + 1))
}

if [ "$ONLY" != "frontend" ]; then
  BE="$ROOT/backend"
  # venv POSIX (bin/) ou Windows (Scripts/*.exe, ex.: bash do Git for Windows)
  if [ -x "$BE/.venv/bin/python" ]; then VENV="$BE/.venv/bin"; PY="$VENV/python"; LI="$VENV/lint-imports"
  elif [ -f "$BE/.venv/Scripts/python.exe" ]; then VENV="$BE/.venv/Scripts"; PY="$VENV/python.exe"; LI="$VENV/lint-imports.exe"
  else VENV=""; fi
  if [ -z "$VENV" ]; then
    echo "backend/.venv nao existe. Crie com:"
    echo "  cd backend && python -m venv .venv && .venv/bin/pip install -e '.[dev]'"
    for n in "ruff check" "ruff format --check" mypy lint-imports pytest bandit pip-audit; do add "backend: $n" FALHA 0 "backend/.venv ausente"; done
  else
    step "backend: ruff check" "$BE" 0 "" "$PY" -m ruff check .
    step "backend: ruff format --check" "$BE" 0 "" "$PY" -m ruff format --check .
    step "backend: mypy" "$BE" 0 "" "$PY" -m mypy
    step "backend: lint-imports" "$BE" 0 "" "$LI"
    step "backend: pytest" "$BE" 0 "" "$PY" -m pytest -q
    step "backend: bandit" "$BE" 0 "" "$PY" -m bandit -q -r app
    if [ $FAST = 1 ]; then skip "backend: pip-audit" "--fast"
    else step "backend: pip-audit" "$BE" 0 "$PIP_NET" "$PY" -m pip_audit; fi
  fi
fi

if [ "$ONLY" != "backend" ]; then
  FE="$ROOT/frontend"
  if [ ! -d "$FE/node_modules" ]; then
    echo "frontend/node_modules ausente. Rode: cd frontend && npm ci"
    for n in lint typecheck test arch format:check; do add "frontend: $n" FALHA 0 "node_modules ausente"; done
    if [ $FAST = 0 ]; then add "frontend: build" FALHA 0 "node_modules ausente"; add "frontend: npm audit --omit=dev" FALHA 0 "node_modules ausente"; fi
  else
    step "frontend: lint" "$FE" 0 "" npm run lint
    step "frontend: typecheck" "$FE" 0 "" npm run typecheck
    step "frontend: test" "$FE" 0 "" npm test
    step "frontend: arch" "$FE" 0 "" npm run arch
    step "frontend: format:check" "$FE" 0 "" npm run format:check
    if [ $FAST = 1 ]; then
      skip "frontend: build" "--fast"; skip "frontend: npm audit --omit=dev" "--fast"
      skip "frontend: npm audit (completo, informativo)" "--fast"
    else
      step "frontend: build" "$FE" 0 "" npm run build
      step "frontend: npm audit --omit=dev" "$FE" 0 "$NPM_NET" npm audit --omit=dev
      step "frontend: npm audit (completo, informativo)" "$FE" 1 "" npm audit
    fi
  fi
fi

# Infra e CI: testes so com biblioteca padrao (sem rede, sem Docker); rodam sempre, como o scan de segredos.
INFRA_PY="$(command -v python3 || command -v python || true)"
if [ -x "${PY:-}" ]; then INFRA_PY="$PY"; fi
if [ -z "$INFRA_PY" ]; then
  add "infra: deploy-hook tests" FALHA 0 "python nao encontrado"; add "ci: release_notes tests" FALHA 0 "python nao encontrado"
else
  step "infra: deploy-hook tests" "$ROOT" 0 "" "$INFRA_PY" -I -m unittest discover -s infra/deploy-hook -p 'test_*.py'
  step "ci: release_notes tests" "$ROOT" 0 "" "$INFRA_PY" -I -m unittest discover -s .github/scripts -p 'test_*.py'
fi

echo; echo "=== scan de segredos ==="; t0=$SECONDS
if command -v gitleaks >/dev/null 2>&1; then
  ( cd "$ROOT" && gitleaks detect --no-git --source . --redact --config "$ROOT/scripts/gitleaks.toml" ); code=$?
  st=OK; [ $code -ne 0 ] && st=FALHA
  add "secrets (gitleaks)" "$st" "$((SECONDS - t0))"
else
  echo "gitleaks nao encontrado: usando checagem REDUZIDA por regex (chaves privadas, tokens, password/SECRET_KEY literais, URL com credencial)."
  Q="'"; DQ='"'
  # Diretorios podados ANTES de enumerar; fixtures conhecidas (o resto de tests/ E varrido).
  PRUNE=( -mindepth 1 \( )
  first=1
  for d in .venv venv node_modules .git dist build __pycache__ .mypy_cache .ruff_cache .pytest_cache .import_linter_cache .claude coverage htmlcov playwright-report test-results '*.egg-info'; do
    [ $first = 1 ] || PRUNE+=( -o ); first=0; PRUNE+=( -name "$d" )
  done
  for f in backend/tests/fixtures backend/tests/data frontend/e2e/fixtures; do PRUNE+=( -o -path "$ROOT/$f" ); done
  PRUNE+=( \) -prune -o -type f -size -1024k )
  for e in png jpg jpeg gif webp ico woff woff2 ttf zip cbz cbr pdf epub db sqlite sqlite3 pyc lock map; do PRUNE+=( ! -iname "*.$e" ); done
  # .env reais ficam fora; .env.example e varrido.
  PRUNE+=( \( -name '.env.example' -o \( ! -name '.env' ! -name '.env.*' \) \) -print0 )
  FILES=()
  while IFS= read -r -d '' f; do FILES+=("$f"); done < <(find "$ROOT" "${PRUNE[@]}")

  PH='changeme|change-me|change_me|change-this|your[-_ ]|example|xxx|placeholder|dummy|<[^<>]+>|\$\{|\$\(|\{\{|os\.environ|getenv|process\.env|import\.meta\.env|:(password|pass|senha|secret)@'
  # "nome|filtra_placeholder(1/0)|regex"
  PATS=(
    "-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY"
    "AKIA[0-9A-Z]{16}"
    "gh[pousr]_[A-Za-z0-9]{36,}"
    "xox[baprs]-[A-Za-z0-9-]{10,}"
    "AIza[0-9A-Za-z_-]{35}"
    "sk_live_[0-9A-Za-z]{16,}"
    "eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
  )
  LOOSE=(
    "\bSECRET_KEY[[:space:]]*[=:][[:space:]]*[${DQ}${Q}]?[^[:space:]${DQ}${Q}]{8,}"
    "\b(password|passwd)[[:space:]]*[=:][[:space:]]*[${DQ}${Q}][^${DQ}${Q}[:space:]]{4,}[${DQ}${Q}]"
    "://[^/[:space:]:@${DQ}${Q}]+:[^/[:space:]@${DQ}${Q}]{3,}@"
  )
  hits=""; scan_err=0
  if [ ${#FILES[@]} -gt 0 ]; then
    for kind in strict loose; do
      if [ $kind = strict ]; then list=("${PATS[@]}"); else list=("${LOOSE[@]}"); fi
      for PAT in "${list[@]}"; do
        res="$(grep -HIEin -e "$PAT" -- "${FILES[@]}")"; rc=$?
        if [ $rc -ge 2 ]; then echo "ERRO: grep falhou (status $rc) no padrao: $PAT"; scan_err=1
        elif [ $rc -eq 0 ]; then
          # Marcador explicito na MESMA linha (apos "arquivo:linha:"): ignora so essa linha.
          res="$(printf '%s\n' "$res" | grep -Ev '^.*:[0-9]+:.*secret-scan:allow')"
          if [ $kind = loose ]; then res="$(printf '%s\n' "$res" | grep -Eiv "^.*:[0-9]+:.*($PH)")"; fi
          [ -n "$res" ] && hits="$hits$res"$'\n'
        fi
      done
    done
  fi
  if [ $scan_err = 1 ]; then
    add "secrets (regex reduzido)" FALHA "$((SECONDS - t0))" "erro ao executar grep (scan incompleto)"
  elif [ -z "$hits" ]; then add "secrets (regex reduzido)" OK "$((SECONDS - t0))" "checagem reduzida; sem gitleaks"
  else echo "Possiveis segredos:"; printf '%s' "$hits" | sort -u | sed 's/^/  /'; add "secrets (regex reduzido)" FALHA "$((SECONDS - t0))" "checagem reduzida; sem gitleaks"; fi
fi

echo; echo "================ RESUMO ================"
printf '%-46s %-7s %8s\n' Etapa Status Tempo
fail=0; warn=0
for i in "${!NAMES[@]}"; do
  printf '%-46s %-7s %7ss' "${NAMES[$i]}" "${STATUS[$i]}" "${SECS[$i]}"
  [ -n "${NOTES[$i]}" ] && printf '  (%s)' "${NOTES[$i]}"
  echo
  [ "${STATUS[$i]}" = FALHA ] && fail=$((fail + 1))
  [ "${STATUS[$i]}" = AVISO ] && warn=$((warn + 1))
done
echo
if [ $fail -gt 0 ]; then echo "RESULTADO: FALHA ($fail etapa(s) com falha, $warn aviso(s))"; exit 1; fi
[ $FAST = 1 ] && echo "MODO RAPIDO: etapas puladas, NAO equivale a verificacao completa"
[ -n "$ONLY" ] && echo "MODO PARCIAL (--only $ONLY): a outra parte NAO foi verificada, NAO equivale a verificacao completa"
[ $OFFLINE_WARNED -gt 0 ] && echo "OFFLINE (--allow-offline): $OFFLINE_WARNED auditoria(s) nao executada(s) por falta de rede"
if [ $warn -gt 0 ] || [ $FAST = 1 ] || [ -n "$ONLY" ]; then echo "RESULTADO: OK com $warn aviso(s) (avisos NAO sao sucesso completo)"; exit 0; fi
echo "RESULTADO: OK"; exit 0
