$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendPath = Join-Path $projectRoot 'frontend'
$logPath = Join-Path $projectRoot '.local'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment is missing. Follow the Local Windows setup in README.md.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules\vite\bin\vite.js'))) {
    throw 'Frontend dependencies are missing. Run npm --prefix frontend ci first.'
}
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $logPath -Force | Out-Null

& $pythonPath (Join-Path $PSScriptRoot 'local_db.py') start
if ($LASTEXITCODE -ne 0) { throw 'Project PostgreSQL could not start.' }

function Test-LocalListener([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::', '::1') })
}

if (-not (Test-LocalListener 8000)) {
    Start-Process -FilePath $pythonPath -ArgumentList @('-u', 'backend/manage.py', 'runserver', '127.0.0.1:8000', '--noreload') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logPath 'api.stdout.log') `
        -RedirectStandardError (Join-Path $logPath 'api.stderr.log') | Out-Null
}
if (-not (Test-LocalListener 5173)) {
    Start-Process -FilePath $nodePath -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort') `
        -WorkingDirectory $frontendPath -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logPath 'frontend.stdout.log') `
        -RedirectStandardError (Join-Path $logPath 'frontend.stderr.log') | Out-Null
}

$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:5173/api/health/' -TimeoutSec 2
        $page = Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2
        if ($health.status -eq 'ok' -and $health.database -eq 'postgresql' -and
            $page.StatusCode -eq 200 -and $page.Content -match '/src/main.tsx') {
            $ready = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    throw 'ERP did not become ready. Check .local/*.stderr.log and whether ports 8000/5173 belong to another app.'
}
Write-Output 'ERP is ready: http://127.0.0.1:5173/'
Write-Output 'Local development only. Logs: .local/*.log. This command does not reset data or change passwords.'
