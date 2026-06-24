# Operator Skillbook

This file captures the practical operating steps for the repository.

## Start the backend

```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Smoke test the important endpoints

```bash
curl http://localhost:8000/api/watchdog/health
curl http://localhost:8000/api/knowledge-graph/stats
curl http://localhost:8000/api/intel/lifecycle/stats
curl http://localhost:8000/api/intel/contractors/stats
```

## Check contractor DNA

```bash
curl http://localhost:8000/api/knowledge-graph/contractor/Techno%20Drugs%20Ltd.
```

## Check lifecycle

```bash
curl http://localhost:8000/api/knowledge-graph/lifecycle/1239360
```

## Repository hygiene

- Keep runtime artifacts inside `runtime/`
- Archive temporary exports under `runtime/archive/`
- Avoid leaving generated logs, PDFs, or spreadsheets in the repository root
- Keep source files, docs, and scripts separate from temporary outputs

## Debugging order

1. Watchdog health
2. Engineer diagnosis
3. Knowledge graph lookup
4. Direct database query
5. Route smoke test

## Practical rule

If the UI is wrong, verify the API payload first. If the API is wrong, verify the SQL-backed service before changing frontend code.
