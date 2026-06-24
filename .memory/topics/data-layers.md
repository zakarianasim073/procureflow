# 6 Data Layers Found

- 2026-06-14 — [Identified 6 distinct data layers in the project:
  1. Raw JSON crawl files (runtime/knowledge/ — eexperience/, awards_batch/, econtracts/, app/, npp/)
  2. PostgreSQL tables (app_records, award_records_v2, procurement_lifecycle, eexperience_completed, ecms_ongoing, econtract_execution, contractors, contractor_dna)
  3. Derived intelligence (contractor_dna, rate_quoted_analysis, execution-lifecycle reconciliation)
  4. API/Service layer (intelligence.py, analytics.py, executive.py, predictions.py, ppr2025.py endpoints + IntelligenceDataService)
  5. Agent system (34 agents — 31 don't touch PostgreSQL)
  6. Frontend (React dashboards, 17 routes)
  Gap: Layers 2-3 invisible to 31 of 34 agents](dc://w/procurementflow/c/eexperience-crawl/m/all)
