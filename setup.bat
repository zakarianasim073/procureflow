@echo off
title Procurement Flow Specialist BD — Windows 11 Setup
color 0B
setlocal enabledelayedexpansion

echo ============================================================
echo   Procurement Flow Specialist BD
echo   Windows 11 Complete Setup
echo   BWDB / LGED / PWD e-GP Tender Automation System
echo ============================================================
echo.
echo [INFO] Setting up in: %~dp0
echo.

:: ── 1. Check Python ────────────────────────────────────────────
echo [1/7] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10+ is required.
    echo   Download: https://www.python.org/downloads/
    echo   *Make sure to tick "Add Python to PATH" during install*
    pause
    exit /b 1
)
python --version
echo [OK] Python found

:: ── 2. Check Node.js ───────────────────────────────────────────
echo.
echo [2/7] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js 18+ is required.
    echo   Download: https://nodejs.org/
    pause
    exit /b 1
)
node --version
echo [OK] Node.js found

:: ── 3. Create Storage Directories ──────────────────────────────
echo.
echo [3/7] Creating storage directories...
set "ROOT=%~dp0"
set "RUNTIME_DIR=%ROOT%runtime"
set "TENDERAI_DIR=%USERPROFILE%\Documents\tenderai"
set "SOR_DIR=%ROOT%backend\app\sor"
set "UPLOAD_DIR=%RUNTIME_DIR%\uploads"
set "DATA_DIR=%ROOT%data"
set "DB_DIR=%RUNTIME_DIR%\db"
set "LOGS_DIR=%RUNTIME_DIR%\logs"

mkdir "%RUNTIME_DIR%" 2>nul
mkdir "%TENDERAI_DIR%" 2>nul
mkdir "%UPLOAD_DIR%" 2>nul
mkdir "%DATA_DIR%" 2>nul
mkdir "%DB_DIR%" 2>nul
mkdir "%LOGS_DIR%" 2>nul

if not exist "%SOR_DIR%\bwdb" mkdir "%SOR_DIR%\bwdb"
if not exist "%SOR_DIR%\lged" mkdir "%SOR_DIR%\lged"
if not exist "%SOR_DIR%\pwd" mkdir "%SOR_DIR%\pwd"

echo [OK] Storage directories created

:: ── 4. Create .env File ──────────────────────────────────────
echo.
echo [4/7] Creating .env configuration...
if not exist "%ROOT%.env" (
    (
        echo # Procurement Flow Specialist BD — Windows Configuration
        echo APP_NAME=Procurement Flow Specialist BD
        echo ENVIRONMENT=development
        echo DEBUG=true
        echo HOST=127.0.0.1
        echo PORT=8000
        echo ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:8000
        echo FRONTEND_URL=http://localhost:5173
        echo.
        echo # Windows: Uses SQLite by default ^(no PostgreSQL needed^)
        echo DATABASE_URL=sqlite+aiosqlite:///%RUNTIME_DIR:\=/%/db/procureflow.db
        echo.
        echo # Storage Paths
        echo BASE_DIR=%RUNTIME_DIR:\=/%
        echo TENDERAI_DIR=%TENDERAI_DIR:\=/%
        echo.
        echo # JWT
        echo JWT_SECRET=procurement-flow-windows-dev-key-2026
        echo JWT_ALGORITHM=HS256
        echo JWT_EXPIRE_HOURS=24
        echo.
        echo # AI — set your keys below ^(or leave blank for demo^)
        echo OPENAI_API_KEY=
        echo ANTHROPIC_API_KEY=
        echo.
        echo # eGP Portal Credentials — Set these for authenticated features
        echo # Without these, the system works in PUBLIC-ONLY mode ^(NOA, APP, etc.^)
        echo EGP_EMAIL=
        echo EGP_PASSWORD=
        echo EGP_PORTAL_URL=https://www.eprocure.gov.bd
        echo.
        echo # eGP Scraper
        echo EGP_BASE_URL=https://www.eprocure.gov.bd
        echo EGP_ENABLE_SCRAPER=true
        echo ENABLE_TENDER_RADAR=true
        echo ENABLE_DEMO_MODE=true
    ) > "%ROOT%.env"
    echo [OK] .env file created
) else (
    echo [SKIP] .env already exists
)

:: ── 5. Python Virtual Environment ─────────────────────────────
echo.
echo [5/7] Setting up Python virtual environment...
if not exist "%ROOT%backend\.venv" (
    cd /d "%ROOT%backend"
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [SKIP] Virtual environment already exists
)

:: ── 6. Install Backend Dependencies ────────────────────────────
echo.
echo [6/7] Installing Python packages...
cd /d "%ROOT%backend"
call .venv\Scripts\activate.bat

:: Install core deps first
pip install --upgrade pip setuptools wheel 2>nul

pip install fastapi uvicorn[standard] pydantic pydantic-settings python-multipart ^
    sqlalchemy aiosqlite alembic ^
    python-jose[cryptography] passlib[bcrypt] bcrypt ^
    email-validator python-dotenv httpx openpyxl pypdf python-docx ^
    python-dateutil pytesseract pdfplumber Pillow ^
    openai langchain langchain-openai ^
    celery redis ^
    pytest pytest-asyncio httpx 2>&1 | findstr /V "already satisfied"

echo [OK] Backend packages installed

:: ── 7. Install Frontend Dependencies ──────────────────────────
echo.
echo [7/7] Installing frontend packages...
cd /d "%ROOT%frontend"
if not exist node_modules (
    call npm install 2>&1
    if !errorlevel! neq 0 (
        echo [WARN] npm install had issues
    ) else (
        echo [OK] Frontend packages installed
    )
) else (
    echo [SKIP] Frontend packages already installed
)

:: ── Verify SOR Data ────────────────────────────────────────────
echo.
echo ------------------------------------------
echo Verifying SOR rate data...
cd /d "%ROOT%backend"
call .venv\Scripts\activate.bat
python -c "from app.sor.sor_service import sor_service; sor_service.load_all(); print('SOR data: OK')" 2>&1

:: ── Done ──────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo   Start the system with:    start.bat
echo   Or manually:              cd backend ^&^& .venv\Scripts\activate ^&^& python run.py
echo                            cd frontend ^&^& npm run dev
echo.
echo   Reports saved to:         %%USERPROFILE%%\Documents\tenderai\
echo   Runtime data:             backend\runtime\
echo.
echo   SQLite database:          backend\runtime\db\procureflow.db
echo                            ^(No PostgreSQL needed for development^)
echo.
pause
