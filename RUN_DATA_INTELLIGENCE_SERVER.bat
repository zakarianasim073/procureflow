@echo off
title Procurement Flow — Data Intelligence Server
color 0B
cd /d "%~dp0backend"
echo ============================================================
echo   Procurement Flow Specialist BD
echo   Data Intelligence Server
echo ============================================================
echo.

:: Set environment
set "BOQ_BASE_DIR=%~dp0runtime"
set "EGP_EMAIL=hbsrjv@gmail.com"
set "EGP_PASSWORD=hbsrjv2017"

:: Check if already running
netstat -ano | findstr ":8000" >nul 2>nul
if not errorlevel 1 (
    echo [OK] Backend already running on port 8000
    goto :frontend
)

:: Start backend
echo [START] Starting backend API...
start "ProcureFlow Backend" /min cmd /k "%~dp0backend\.venv\Scripts\python.exe %~dp0backend\start_server.py"
timeout /t 8 /nobreak >nul

:: Verify
netstat -ano | findstr ":8000" >nul 2>nul
if errorlevel 1 (
    echo [WARN] Backend may not have started. Check for errors.
) else (
    echo [OK] Backend is running at http://127.0.0.1:8000
)

:frontend
:: Start frontend
echo [START] Starting frontend...
cd /d "%~dp0frontend"
start "ProcureFlow UI" /min cmd /k "npm run dev -- --host 127.0.0.1"
timeout /t 3 /nobreak >nul

echo [OK] Opening browser...
start "" "http://localhost:5173"

echo.
echo ============================================================
echo   System Running!
echo ============================================================
echo   Frontend UI:    http://localhost:5173
echo   Backend API:    http://127.0.0.1:8000
echo   API Docs:       http://127.0.0.1:8000/docs
echo   Data Intel:     http://localhost:5173/data-intelligence
echo   BWDB Monitor:   http://localhost:5173/bwdb-monitor
echo.
echo   Press any key to stop...
pause

:: Clean shutdown
echo [STOP] Shutting down...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000"') do taskkill /f /pid %%p >nul 2>nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173"') do taskkill /f /pid %%p >nul 2>nul
echo [OK] Stopped.
