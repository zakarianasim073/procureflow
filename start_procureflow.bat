@echo off
REM ============================================================
REM ProcureFlow BD — Start Server and Verify Endpoints
REM ============================================================
setlocal enabledelayedexpansion

set PYTHON=C:\Users\znasi\AppData\Local\Programs\Python\Python311\python.exe
set BACKEND=D:\A1\procurementflow_final_v3\procurementflow\backend
set FRONTEND=D:\A1\procurementflow_final_v3\procurementflow\frontend
set PORT=8000

echo [1/5] Killing existing server on port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% "') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)
echo       Done

echo [2/5] Building frontend...
cd /d "%FRONTEND%"
call npm run build >nul 2>&1
if !errorlevel! neq 0 (
    echo       Frontend build FAILED — using existing static files
) else (
    echo       Frontend build OK
)

echo [3/5] Copying frontend dist to backend static...
xcopy /E /Y /Q "%FRONTEND%\dist\*" "%BACKEND%\app\static\" >nul 2>&1
echo       Done

echo [4/5] Starting backend server on port %PORT%...
cd /d "%BACKEND%"
start "ProcureFlow" "%PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT% --log-level warning
echo       Server starting... (wait 10s)
timeout /t 10 /nobreak >nul

echo [5/5] Verifying server health...
"%PYTHON%" -c "import requests; r=requests.get('http://127.0.0.1:%PORT%/api/health', timeout=5); print('Health:', r.status_code, r.json().get('status',''))" 2>nul
if !errorlevel! neq 0 (
    echo       WARNING: Health check failed — retrying in 5s...
    timeout /t 5 /nobreak >nul
    "%PYTHON%" -c "import requests; r=requests.get('http://127.0.0.1:%PORT%/api/health', timeout=5); print('Health:', r.status_code, r.json().get('status',''))" 2>nul
)

echo.
echo ============================================================
echo  ProcureFlow BD is running!
echo  API:      http://localhost:%PORT%/docs
echo  Frontend: http://localhost:%PORT%/
echo ============================================================

REM Open browser
start http://localhost:%PORT%/

endlocal
