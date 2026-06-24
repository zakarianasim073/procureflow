@echo off
title eGP Portal Explorer — Tender Document Discovery
color 0B
setlocal enabledelayedexpansion

echo ============================================================
echo   eGP Portal Structure Explorer
echo   Discovers all tender documents, forms, and mapped data
echo ============================================================
echo.

:: Check venv
if not exist "backend\.venv\Scripts\activate.bat" (
    echo [ERROR] Run setup.bat first
    pause
    exit /b 1
)

cd /d "%~dp0backend"
call .venv\Scripts\activate.bat

echo.
echo  Choose exploration mode:
echo    1) Full Portal Structure Scan
echo    2) Explore My Tender - Archived
echo    3) Explore Tender Documents (enter ID)
echo    4) Extract Tender Forms and Mappings
echo    5) Exit
echo.

set /p MODE="Enter 1-5: "

if "%MODE%"=="1" (
    echo.
    echo [RUN] Full Portal Structure Scan...
    python -m app.agents.portal_explorer explore
    goto done
)

if "%MODE%"=="2" (
    echo.
    echo [RUN] Exploring My Tender - Archived...
    python -m app.agents.portal_explorer archived
    goto done
)

if "%MODE%"=="3" (
    set /p TID="Enter Tender ID: "
    echo.
    echo [RUN] Exploring Documents for Tender !TID!...
    python -m app.agents.portal_explorer documents !TID!
    goto done
)

if "%MODE%"=="4" (
    set /p TID="Enter Tender ID: "
    echo.
    echo [RUN] Extracting Forms and Mappings for Tender !TID!...
    python -m app.agents.portal_explorer tender !TID!
    goto done
)

:done
echo.
if "%MODE%" NEQ "5" (
    echo ============================================================
    echo   Exploration complete! Check output above.
    echo ============================================================
)
pause
