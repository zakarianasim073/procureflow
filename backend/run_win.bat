@echo off
title Procurement Flow Specialist BD — Backend
color 0B
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "RUNTIME_DIR=%ROOT%runtime"
set "TENDERAI_DIR=%USERPROFILE%\Documents\tenderai"

:: Runtime db dir not needed for PostgreSQL — kept for uploads/temp files
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%RUNTIME_DIR%\uploads" mkdir "%RUNTIME_DIR%\uploads"
if not exist "%TENDERAI_DIR%" mkdir "%TENDERAI_DIR%"

:: Activate venv if available
if exist "%ROOT%.venv\Scripts\activate.bat" (
    call "%ROOT%.venv\Scripts\activate.bat"
)

:: Set environment
set "BOQ_BASE_DIR=%RUNTIME_DIR%"
set "TENDERAI_DIR=%TENDERAI_DIR%"
set "PYTHONPATH=%ROOT%"

echo Starting Procurement Flow Specialist BD Backend...
echo.
echo   Runtime:  %RUNTIME_DIR%
echo   Reports:  %TENDERAI_DIR%
echo   Database: PostgreSQL (localhost:5432/procurementflow)
echo.

:: Run from app directory
cd /d "%ROOT%app"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backend failed to start.
    pause
)
