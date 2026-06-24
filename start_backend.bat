@echo off
title Backend - Procurement Flow
cd /d "%~dp0backend"
echo Starting backend on http://127.0.0.1:8000
python -m app.main
pause
