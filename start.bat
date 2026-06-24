@echo off
title Procurement Flow Specialist BD
cd /d "%~dp0"
echo ============================================
echo  Procurement Flow Specialist BD
echo  Starting Backend + Frontend
echo ============================================
echo.

:: Start backend (uvicorn)
echo [1/2] Starting Backend (port 8000)...
start "Backend" cmd /c "cd /d backend && python -m app.main"

:: Wait a moment for backend to initialize
timeout /t 3 /nobreak >nul

:: Start frontend (vite dev server)
echo [2/2] Starting Frontend (port 5173)...
start "Frontend" cmd /c "cd /d frontend && npm run dev"

echo.
echo ============================================
echo  Backend:  http://127.0.0.1:8000
echo  Frontend: http://127.0.0.1:5173
echo  API Docs: http://127.0.0.1:8000/docs
echo ============================================
echo.
echo Close this window to stop both servers.
pause
