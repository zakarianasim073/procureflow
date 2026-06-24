param([switch]$NoKill)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND = Join-Path $ROOT "backend"
$FRONTEND = Join-Path $ROOT "frontend"
$PYTHON = "C:\Program Files\Python310\python.exe"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  ProcureFlow -- Starting All Services" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

if (-not $NoKill) {
    Write-Host "[1/4] Killing previous processes..." -ForegroundColor Yellow
    foreach ($port in @(8000, 5173)) {
        Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep 2
    Write-Host "  Done`n"
}

Write-Host "[2/4] Starting backend (port 8000)..." -ForegroundColor Yellow
$env:PYTHONPATH = $BACKEND
Start-Process -WindowStyle Hidden -FilePath $PYTHON -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -WorkingDirectory $BACKEND

$ok = $false
for ($i = 0; $i -lt 8; $i++) {
    Start-Sleep 2
    try { $r = Invoke-WebRequest -Uri "http://localhost:8000/docs" -UseBasicParsing -TimeoutSec 2; $ok = $true; break } catch {}
}
if ($ok) { Write-Host "  Backend UP`n" -ForegroundColor Green } else { Write-Host "  Backend FAILED`n" -ForegroundColor Red }

Write-Host "[3/4] Starting frontend (port 5173)..." -ForegroundColor Yellow
if (Test-Path (Join-Path $FRONTEND "node_modules")) {
    Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory $FRONTEND

    $ok = $false
    for ($i = 0; $i -lt 8; $i++) {
        Start-Sleep 2
        try { $r = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 2; $ok = $true; break } catch {}
    }
    if ($ok) { Write-Host "  Frontend UP`n" -ForegroundColor Green } else { Write-Host "  Frontend FAILED`n" -ForegroundColor Red }
} else {
    Write-Host "  node_modules not found -- run 'cd frontend && npm install'`n" -ForegroundColor Red
}

Write-Host "[4/4] All services started!" -ForegroundColor Yellow
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Database: PostgreSQL (localhost:5432/procurementflow)" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Stop: taskkill /f /pid (process from netstat)" -ForegroundColor Gray
