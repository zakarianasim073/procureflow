@echo off
REM ProcureFlow PostgreSQL Startup Script
setlocal

set PYTHONIOENCODING=utf-8
set DATABASE_URL=postgresql+asyncpg://procurementflow:procurementflow@localhost:5432/procurementflow
set SYNC_DATABASE_URL=postgresql+psycopg2://procurementflow:procurementflow@localhost:5432/procurementflow

cd /d "%~dp0backend"

echo Starting ProcureFlow on PostgreSQL...
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
