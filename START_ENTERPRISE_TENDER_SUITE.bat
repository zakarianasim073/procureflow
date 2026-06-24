@echo off
setlocal enabledelayedexpansion
title Enterprise Tender Processing Suite
color 0B

set "ROOT=%~dp0"

echo ============================================================
echo   Enterprise Tender Processing Suite
echo   BWDB / LGED / PWD e-GP Tender Automation
echo ============================================================
echo.
echo   Choose an option:
echo     1) Full Setup + Start (first time)
echo     2) Start only (if already set up)
echo     3) Exit
echo.
set /p CHOICE="Enter 1, 2, or 3: "

if "%CHOICE%"=="1" (
    echo.
    echo [RUN] Running full setup...
    call "%ROOT%setup.bat"
    echo.
    echo [RUN] Starting system...
    call "%ROOT%start.bat"
) else if "%CHOICE%"=="2" (
    echo.
    echo [RUN] Starting system...
    call "%ROOT%start.bat"
) else (
    echo.
    echo Exiting.
    timeout /t 2 /nobreak >nul
    exit /b 0
)
