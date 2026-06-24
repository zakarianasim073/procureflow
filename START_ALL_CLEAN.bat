@echo off
setlocal EnableExtensions EnableDelayedExpansion

title ProcurementFlow Full Restart

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "PYTHON=C:\Program Files\Python310\python.exe"

echo ============================================================
echo  ProcurementFlow Full Restart
echo ============================================================
echo.

echo [1/4] Stopping existing listeners on 8000 and 5173...
call :KillPort 8000
call :KillPort 5173
timeout /t 2 /nobreak >nul
echo       Done.
echo.

echo [2/4] Starting backend on port 8000...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -WindowStyle Hidden -FilePath '%PYTHON%' -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000','--reload') -WorkingDirectory '%BACKEND%'"
if errorlevel 1 goto :fail
echo       Backend launch issued.
echo.

echo [3/4] Preparing frontend...
if not exist "%FRONTEND%\node_modules" (
    echo       node_modules not found, running npm install...
    pushd "%FRONTEND%"
    call npm install
    if errorlevel 1 (
        popd
        echo       Frontend install failed.
        goto :fail
    )
    popd
)
echo       Frontend ready.
echo.

echo [4/4] Starting frontend on port 5173...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList @('/c','npm','run','dev') -WorkingDirectory '%FRONTEND%'"
if errorlevel 1 goto :fail
echo       Frontend launch issued.
echo.

timeout /t 8 /nobreak >nul
start "" "http://localhost:5173"

echo ============================================================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo  Docs:     http://localhost:8000/docs
echo ============================================================
echo.
echo All services launched.
exit /b 0

:KillPort
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING"') do (
    if not "%%P"=="" taskkill /F /PID %%P >nul 2>&1
)
exit /b 0

:fail
echo.
echo Launch failed. Check the backend or frontend console output.
exit /b 1
