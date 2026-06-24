@echo off
title ProcureFlow — Backend
color 0B
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "PYTHON=C:\Program Files\Python310\python.exe"

:: Kill anything on port 8000
echo Killing existing process on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /f /pid %%a >nul 2>&1
timeout /t 2 /nobreak >nul

:: Start server
set "PYTHONPATH=%ROOT%"
start "ProcureFlow-Backend" /B "%PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
timeout /t 5 /nobreak >nul

:: Verify
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do set "PID=%%a"
if defined PID (
    echo Backend started on http://localhost:8000 ^(PID %PID%^)
) else (
    echo [WARNING] Backend may not have started.
)
