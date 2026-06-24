@echo off
cd /d "%~dp0backend"
set TENDERAI_DIR=./runtime
set PROCUREFLOW_PORT=8000
echo Starting backend on port 8000 > backend\runtime\logs\backend_hidden.log
python -m app.main >> backend\runtime\logs\backend_hidden.log 2>&1
