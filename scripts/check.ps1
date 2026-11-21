<#
.SYNOPSIS
  Verificacao unica do projeto (backend + frontend + scan de segredos).
.PARAMETER Only
  backend | frontend : roda so essa parte (o scan de segredos roda sempre). Resultado PARCIAL.
.PARAMETER Fast
  Pula build e audits (pip-audit, npm audit). Resultado declarado como MODO RAPIDO.
.PARAMETER AllowOffline
  Converte em AVISO as auditorias (pip-audit, npm audit --omit=dev) que falharem por falta de rede.
  Sem esta flag, auditoria nao executada por falta de rede e FALHA.
.NOTES
  npm audit completo e AVISO nao bloqueante: ha 4 achados moderados conhecidos e
  aceitos, transitivos de vite-plugin-pwa -> workbox-build -> glob/minimatch, que
  existem so no build (nao vao para o runtime). Ver scripts/README.md.
  Etapas nao executadas NUNCA contam como OK silenciosamente: ou FALHA, ou AVISO declarado no resumo.
#>
param(
  [ValidateSet('backend', 'frontend')][string]$Only,
  [switch]$Fast,
  [switch]$AllowOffline
)
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$results = New-Object System.Collections.ArrayList
$script:fastSkipped = 0
$script:offlineWarned = 0

# Erros de rede ESPECIFICOS (nao casar palavras genericas como 'connection' ou 'timed out').
$PipNetRegex = 'ConnectionError|Max retries|getaddrinfo|NewConnectionError'
$NpmNetRegex = 'ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ETIMEDOUT|ECONNRESET|getaddrinfo|audit endpoint returned an error|FetchError'

function Add-Result($name, $status, $secs, $note) {
  [void]$results.Add([pscustomobject]@{ Name = $name; Status = $status; Secs = $secs; Note = $note })
}

function Invoke-Step {
  param([string]$Name, [scriptblock]$Cmd, [string]$Dir, [switch]$WarnOnly, [string]$NetRegex)
  Write-Host ""
  Write-Host "=== $Name ===" -ForegroundColor Cyan
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $pushed = $false
  $code = 1
  $text = ''
  try {
    Push-Location -LiteralPath $Dir -ErrorAction Stop
    $pushed = $true
  } catch {
    Write-Host "diretorio inexistente: $Dir" -ForegroundColor Red
    Add-Result $Name 'FALHA' 0 'diretorio inexistente'
    return
  }
  $global:LASTEXITCODE = 0
  try {
    if ($NetRegex) {
      $out = @(& $Cmd 2>&1 | ForEach-Object { $_.ToString() })
      $out | ForEach-Object { Write-Host $_ }
      $text = $out -join "`n"
    } else {
      & $Cmd
    }
    $code = $global:LASTEXITCODE
  } catch { Write-Host $_; $code = 1 }
  if ($pushed) { Pop-Location }
  $sw.Stop()
  $note = ''
  if ($code -eq 0) { $st = 'OK' }
  elseif ($NetRegex -and $text -match $NetRegex) {
    if ($AllowOffline) { $st = 'AVISO'; $note = 'nao executado: sem rede (-AllowOffline)'; $script:offlineWarned++ }
    else { $st = 'FALHA'; $note = 'sem rede: auditoria NAO executada (use -AllowOffline para aceitar como AVISO)' }
  }
  elseif ($WarnOnly) { $st = 'AVISO' }
  else { $st = 'FALHA' }
  Add-Result $Name $st $sw.Elapsed.TotalSeconds $note
}

function Skip-Step($Name, $Why) {
  Write-Host ""
  Write-Host "=== $Name === (nao executado: $Why)" -ForegroundColor Yellow
  Add-Result $Name 'AVISO' 0 "nao executado: $Why"
  if ($Why -eq '-Fast') { $script:fastSkipped++ }
}

$doBack = $Only -ne 'frontend'
$doFront = $Only -ne 'backend'

# ---------------- Backend ----------------
if ($doBack) {
  $be = Join-Path $Root 'backend'
  $venv = Join-Path $be '.venv\Scripts'
  if (-not (Test-Path (Join-Path $venv 'python.exe'))) {
    Write-Host "backend/.venv nao existe. Crie com:" -ForegroundColor Red
    Write-Host "  cd backend; python -m venv .venv; .venv\Scripts\pip install -e '.[dev]'" -ForegroundColor Red
    foreach ($n in 'backend: ruff check','backend: ruff format --check','backend: mypy','backend: lint-imports','backend: pytest','backend: bandit','backend: pip-audit') {
      Add-Result $n 'FALHA' 0 'backend/.venv ausente'
    }
  } else {
    $py = Join-Path $venv 'python.exe'
    Invoke-Step 'backend: ruff check' { & $py -m ruff check . } $be
    Invoke-Step 'backend: ruff format --check' { & $py -m ruff format --check . } $be
    Invoke-Step 'backend: mypy' { & $py -m mypy } $be
    Invoke-Step 'backend: lint-imports' { & (Join-Path $venv 'lint-imports.exe') } $be
    Invoke-Step 'backend: pytest' { & $py -m pytest -q } $be
    Invoke-Step 'backend: bandit' { & $py -m bandit -q -r app } $be
    if ($Fast) {
      Skip-Step 'backend: pip-audit' '-Fast'
    } else {
      Invoke-Step 'backend: pip-audit' { & $py -m pip_audit } $be -NetRegex $PipNetRegex
    }
  }
}

# ---------------- Frontend ----------------
if ($doFront) {
  $fe = Join-Path $Root 'frontend'
  if (-not (Test-Path (Join-Path $fe 'node_modules'))) {
    Write-Host "frontend/node_modules ausente. Rode: cd frontend; npm ci" -ForegroundColor Red
    foreach ($n in 'frontend: lint','frontend: typecheck','frontend: test','frontend: arch','frontend: format:check') {
      Add-Result $n 'FALHA' 0 'node_modules ausente'
    }
    if (-not $Fast) { Add-Result 'frontend: build' 'FALHA' 0 'node_modules ausente'; Add-Result 'frontend: npm audit --omit=dev' 'FALHA' 0 'node_modules ausente' }
  } else {
    Invoke-Step 'frontend: lint' { npm run lint } $fe
    Invoke-Step 'frontend: typecheck' { npm run typecheck } $fe
    Invoke-Step 'frontend: test' { npm test } $fe
    Invoke-Step 'frontend: arch' { npm run arch } $fe
    Invoke-Step 'frontend: format:check' { npm run format:check } $fe
    if ($Fast) {
      Skip-Step 'frontend: build' '-Fast'
      Skip-Step 'frontend: npm audit --omit=dev' '-Fast'
      Skip-Step 'frontend: npm audit (completo, informativo)' '-Fast'
    } else {
      Invoke-Step 'frontend: build' { npm run build } $fe
      Invoke-Step 'frontend: npm audit --omit=dev' { npm audit --omit=dev } $fe -NetRegex $NpmNetRegex
      # Conhecido/aceito: 4 moderados transitivos de vite-plugin-pwa -> workbox-build -> glob/minimatch (so build).
      Invoke-Step 'frontend: npm audit (completo, informativo)' { npm audit } $fe -WarnOnly
    }
  }
}

# ---------------- Infra e CI (testes so com biblioteca padrao: sem rede, sem Docker) ----------------
# Roda sempre (como o scan de segredos): receptor do webhook de atualizacao e script de notas da release.
$infraPy = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $infraPy)) { $infraPy = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $infraPy) {
  Add-Result 'infra: deploy-hook tests' 'FALHA' 0 'python nao encontrado'
  Add-Result 'ci: release_notes tests' 'FALHA' 0 'python nao encontrado'
} else {
  Invoke-Step 'infra: deploy-hook tests' { & $infraPy -I -m unittest discover -s infra/deploy-hook -p 'test_*.py' } $Root
  Invoke-Step 'ci: release_notes tests' { & $infraPy -I -m unittest discover -s .github/scripts -p 'test_*.py' } $Root
}

# ---------------- Scan de segredos ----------------
Write-Host ""
Write-Host "=== scan de segredos ===" -ForegroundColor Cyan
$sw = [Diagnostics.Stopwatch]::StartNew()
$gl = Get-Command gitleaks -ErrorAction SilentlyContinue
if ($gl) {
  Push-Location -LiteralPath $Root
  $glCfg = Join-Path $PSScriptRoot 'gitleaks.toml'
  & gitleaks detect --no-git --source . --redact --config $glCfg
  $code = $LASTEXITCODE
  Pop-Location
  $sw.Stop()
  if ($code -eq 0) { $st = 'OK' } else { $st = 'FALHA' }
  Add-Result 'secrets (gitleaks)' $st $sw.Elapsed.TotalSeconds ''
} else {
  Write-Host "gitleaks nao encontrado: usando checagem REDUZIDA por regex (chaves privadas, tokens, password/SECRET_KEY literais, URL com credencial)." -ForegroundColor Yellow
  # Diretorios podados ANTES de enumerar (nunca entra em node_modules etc.).
  $skipDirs = @('.venv','venv','node_modules','.git','dist','build','__pycache__','.mypy_cache','.ruff_cache','.pytest_cache','.import_linter_cache','.claude','coverage','htmlcov','playwright-report','test-results')
  # Fixtures conhecidas (caminhos relativos a raiz); o resto de tests/ E varrido.
  $fixtureDirs = @('backend\tests\fixtures', 'backend\tests\data', 'frontend\e2e\fixtures')
  $binExt = '\.(png|jpe?g|gif|webp|ico|woff2?|ttf|zip|cbz|cbr|pdf|epub|db|sqlite3?|pyc|lock|map)$'
  # Valores claramente placeholder (so para padroes frouxos).
  $ph = 'changeme|change-me|change_me|change-this|your[-_ ]|example|xxx|placeholder|dummy|<[^<>]+>|\$\{|\$\(|\{\{|os\.environ|getenv|process\.env|import\.meta\.env|:(password|pass|senha|secret)@'
  $patterns = @(
    @{ R = '-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY'; F = $false }
    @{ R = 'AKIA[0-9A-Z]{16}'; F = $false }
    @{ R = 'gh[pousr]_[A-Za-z0-9]{36,}'; F = $false }
    @{ R = 'xox[baprs]-[A-Za-z0-9-]{10,}'; F = $false }
    @{ R = 'AIza[0-9A-Za-z_-]{35}'; F = $false }
    @{ R = 'sk_live_[0-9A-Za-z]{16,}'; F = $false }
    @{ R = 'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'; F = $false }
    @{ R = '\bSECRET_KEY\s*[=:]\s*["'']?[^\s"'']{8,}'; F = $true }
    @{ R = '\b(password|passwd)\s*[=:]\s*["''][^"''\s]{4,}["'']'; F = $true }
    @{ R = '://[^/\s:@"'']+:[^/\s@"'']{3,}@'; F = $true }
  )
  $hits = New-Object System.Collections.ArrayList
  $unreadable = New-Object System.Collections.ArrayList
  $stack = New-Object System.Collections.Stack
  $stack.Push($Root)
  while ($stack.Count -gt 0) {
    $dir = $stack.Pop()
    $children = $null
    try { $children = @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop) } catch { [void]$unreadable.Add(($dir + ' (diretorio)')); continue }
    foreach ($e in $children) {
      $rel = $e.FullName.Substring($Root.Length + 1)
      if ($e.PSIsContainer) {
        # Pula so symlink/junction (LinkType). Nao usar o atributo ReparsePoint: o OneDrive o marca em TODA pasta
        # e o scan nunca descia dos arquivos da raiz (falso OK).
        if ($e.LinkType) { continue }
        if ($skipDirs -contains $e.Name -or $e.Name -like '*.egg-info') { continue }
        if ($fixtureDirs -contains $rel) { continue }
        $stack.Push($e.FullName)
      } else {
        if ($e.Name -match $binExt -or $e.Length -ge 1MB) { continue }
        if ($e.Name -match '^\.env($|\.(?!example$))') { continue }
        foreach ($p in $patterns) {
          # Erro de leitura NAO pode virar falso OK: conta como FALHA (paridade com check.sh).
          try {
            $m = Select-String -LiteralPath $e.FullName -Pattern $p.R -ErrorAction Stop
          } catch {
            [void]$unreadable.Add($rel)
            break
          }
          foreach ($x in $m) {
            # Marcador explicito na MESMA linha: ignora so essa linha (valores de teste ficticios).
            if ($x.Line -match 'secret-scan:allow') { continue }
            if ($p.F -and $x.Line -match $ph) { continue }
            [void]$hits.Add(("{0}:{1}" -f $rel, $x.LineNumber))
          }
        }
      }
    }
  }
  $sw.Stop()
  if ($unreadable.Count -gt 0) {
    Write-Host "Arquivos/diretorios ILEGIVEIS no scan de segredos (contam como FALHA):" -ForegroundColor Red
    $unreadable | Select-Object -Unique | ForEach-Object { Write-Host "  $_" }
  }
  if ($hits.Count -eq 0 -and $unreadable.Count -eq 0) { $st = 'OK' } elseif ($hits.Count -eq 0) { $st = 'FALHA' } else { $st = 'FALHA'; Write-Host "Possiveis segredos:" -ForegroundColor Red; $hits | Select-Object -Unique | ForEach-Object { Write-Host "  $_" } }
  Add-Result 'secrets (regex reduzido)' $st $sw.Elapsed.TotalSeconds 'checagem reduzida; sem gitleaks'
}

# ---------------- Resumo ----------------
Write-Host ""
Write-Host "================ RESUMO ================" -ForegroundColor Cyan
Write-Host ("{0,-46} {1,-7} {2,8}" -f 'Etapa', 'Status', 'Tempo')
foreach ($r in $results) {
  $color = switch ($r.Status) { 'OK' { 'Green' } 'FALHA' { 'Red' } default { 'Yellow' } }
  $line = "{0,-46} {1,-7} {2,7:N1}s" -f $r.Name, $r.Status, $r.Secs
  if ($r.Note) { $line += "  ($($r.Note))" }
  Write-Host $line -ForegroundColor $color
}
$fail = @($results | Where-Object { $_.Status -eq 'FALHA' }).Count
$warn = @($results | Where-Object { $_.Status -eq 'AVISO' }).Count
Write-Host ""
if ($fail -gt 0) { Write-Host "RESULTADO: FALHA ($fail etapa(s) com falha, $warn aviso(s))" -ForegroundColor Red; exit 1 }
if ($Fast) { Write-Host "MODO RAPIDO: etapas puladas, NAO equivale a verificacao completa" -ForegroundColor Yellow }
if ($Only) { Write-Host "MODO PARCIAL (-Only $Only): a outra parte NAO foi verificada, NAO equivale a verificacao completa" -ForegroundColor Yellow }
if ($script:offlineWarned -gt 0) { Write-Host "OFFLINE (-AllowOffline): $($script:offlineWarned) auditoria(s) nao executada(s) por falta de rede" -ForegroundColor Yellow }
if ($warn -gt 0 -or $Fast -or $Only) { Write-Host "RESULTADO: OK com $warn aviso(s) (avisos NAO sao sucesso completo)" -ForegroundColor Yellow; exit 0 }
Write-Host "RESULTADO: OK" -ForegroundColor Green
exit 0
