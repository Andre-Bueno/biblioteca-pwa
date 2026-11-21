# PoCs da auditoria 2026-11-19

Scripts de reproducao, **somente contra instancia local (127.0.0.1)**. Sem segredos reais: o `SECRET_KEY` e as senhas abaixo sao valores de teste descartaveis. Nada aqui altera `backend/`, `scripts/` ou `frontend/`.

## Instancia local usada na auditoria

PowerShell, a partir de qualquer pasta (use uma pasta temporaria fora do repositorio, `$T`):

```powershell
$T = "$env:TEMP\audit"; New-Item -ItemType Directory -Force "$T\data","$T\lib" | Out-Null
$py = "<repo>\backend\.venv\Scripts\python.exe"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:SECRET_KEY = "$([guid]::NewGuid().ToString('N'))$([guid]::NewGuid().ToString('N'))"   # descartavel, so para teste local
$env:DATABASE_URL = "sqlite:///" + ($T -replace '\\','/') + "/data/app.db"
$env:LIBRARY_PATH = "$T\lib"
$env:COOKIE_SECURE = "false"                       # so porque o teste e HTTP local
# Limites de taxa relaxados: os PoCs medem o efeito SEM o limitador por IP
$env:RATE_LIMIT_AUTH_PER_MINUTE = "100000"; $env:RATE_LIMIT_AUTH_BURST = "100000"
$env:RATE_LIMIT_API_PER_MINUTE = "1000000"; $env:RATE_LIMIT_API_BURST = "1000000"
# uvicorn confia em X-Forwarded-For de 127.0.0.1 (padrao): simula varios IPs de cliente atras de um proxy
& $py -m uvicorn app.main:app --app-dir <repo>\backend --host 127.0.0.1 --port 18703
```

Criar usuarios (senha por `getpass`, aqui simulada; nao use isto fora de teste):

```python
from unittest import mock; import app.cli as cli
for u, p, admin in [("admin1","Adm1n-Correct-Horse-42",True),("user1","Us3r-Correct-Horse-42",False),("victim","V1ctim-Correct-Horse-42",False)]:
    with mock.patch("getpass.getpass", return_value=p):
        cli.main(["create-user", u] + (["--admin"] if admin else []))
```
(antes: `cli.main(["migrate"])`; execute com `PYTHONPATH=<repo>\backend` e as mesmas variaveis de ambiente.)

## Scripts

| Script | Finding | O que mostra |
|---|---|---|
| `flood_login.py` | FIND-2026-002 | Latencia de `/auth/me` sobe de ~3 ms para ~2,5 s durante flood de logins de IPs distintos |
| `race_lockout.py` | FIND-2026-004, FIND-2026-005 | Tentativas concorrentes passam do limite do lockout; dois refresh simultaneos derrubam a sessao inteira |
| `page_cpu.py` | FIND-2026-003 | Custo por pagina de um CBZ com ~9500 entradas e efeito sob concorrencia |

Nota: os scripts foram condensados a partir dos executados durante a auditoria (os numeros citados nos findings vem das execucoes originais); a versao condensada nao foi reexecutada e pode precisar de ajuste (por exemplo, leitura de cookies com `Path`).

Uso: `python <script> http://127.0.0.1:18703` (precisa de `httpx`, presente no venv do backend).
