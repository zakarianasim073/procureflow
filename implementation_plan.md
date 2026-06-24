# Implementation Plan - Configuration and Build Fixes

This plan addresses several configuration, database connection, and docker-compose bugs to ensure the application starts and builds correctly in the local Windows environment and Docker.

## User Review Required

> [!IMPORTANT]
> The database setup defaults to SQLite (`sqlite+aiosqlite`) for local development on Windows (via `setup.bat` and `start.bat`) and uses PostgreSQL when running inside Docker. We will keep this structure, but we will fix the environment variable loading so that the SQLite database is consistently picked up when running the backend locally.

## Proposed Changes

### Configuration and Environment Loading

#### [MODIFY] [config.py](file:///d:/A1/procurementflow_final_v3/procurementflow/backend/app/core/config.py)
- Import `load_dotenv` from `dotenv` at the top of the file.
- Resolve the project root path dynamically and load `.env` from the project root if it exists. This ensures that even if running from the `backend/` directory, the customized root `.env` (configured for SQLite) is loaded into `os.environ` before Pydantic Settings is initialized.

#### [MODIFY] [base.py](file:///d:/A1/procurementflow_final_v3/procurementflow/backend/app/db/base.py)
- Update `get_database_url` to use `settings.DATABASE_URL` from `app.core.config` instead of calling `os.getenv("DATABASE_URL")` directly. This ensures the database connection logic benefits from Pydantic Settings' custom `.env` parsing.

#### [MODIFY] [env.py](file:///d:/A1/procurementflow_final_v3/procurementflow/backend/alembic/env.py)
- Import `load_dotenv` and load the root `.env` file explicitly when Alembic runs database migrations, so migrations are performed against the correct database.

---

### Docker Infrastructure

#### [MODIFY] [docker-compose.yml](file:///d:/A1/procurementflow_final_v3/procurementflow/docker-compose.yml)
- Change the database user and password in `DATABASE_URL` for `backend` and `worker` services from `procureflow` to `procurementflow` to match the PostgreSQL environment settings.
- Update the `postgres` healthcheck command to query as the correct user `procurementflow` instead of `procureflow`.

---

### Redundant Code Consolidation

- `backend/app/main.py` is the unified server entry point (run by `backend/run.py`). The file `backend/app/agents/server.py` is a legacy agent-only FastAPI server. We will leave `backend/app/agents/server.py` as is (or document it as legacy) since it is not used in the default startup flow (`start.bat`).

---

## Verification Plan

### Automated Tests
- Activate the virtual environment and run the FastAPI server locally:
  ```powershell
  cd backend
  .venv\Scripts\activate
  python run.py
  ```
- Verify the server health endpoint returns a healthy status:
  ```powershell
  curl http://127.0.0.1:8000/api/health
  ```
- Run the project startup script `start.bat` to verify backend and frontend start up concurrently.

### Manual Verification
- Verify that the SQLite database file is created at `runtime/db/procureflow.db` and matches the schema when starting the backend locally.
- Validate that the dashboard loads correctly in the browser at `http://localhost:5173`.
