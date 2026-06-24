# ProcureFlow — Brain CLAUDE.md

## Goal
- Extract SOR items with zonal unit rates from PWD/BWDB/LGED PDFs to PostgreSQL, run BOQ comparison pipeline against SOR rates, generate 5-tab Excel analysis with APP estimate + TDS criteria + SOR NOT FOUND red-flagged items, and acquire tender documents via agent-002

## Constraints & Preferences
- PostgreSQL 16.14 at localhost:5432 — `procurementflow` database (60+ tables, 395K tenders, 207K app_records, 238K awards, 32K contractors)
- Password for postgres user: `procurementflow`
- Python 3.10 at `C:\Program Files\Python310\python.exe`
- **Keep ALL JSON files untouched** — do not delete or overwrite
- Real project is `D:\A1\procurementflow_final_v3\procurementflow` (NOT `bidbrain2025_latest`)
- e-GP credentials: `hbsrjv@gmail.com` / `hbsrjv2017` (demo account); httpx `verify=False`, session cookies auto-managed
- Server persistence: use `Start-Process -WindowStyle Hidden` (Start-Job dies when shell exits)

## Progress

### Done
- Extracted LGED SOR from PDF via pdfplumber table extraction — 1503 items
- Extracted PWD SOR from PDF via pdfplumber table extraction — 2018 items
- Extracted BWDB SOR from Excel + 9 split PDFs — 1024 items
- Total SOR database: 4,545 rates
- Verified SOR API: `GET /api/sor/agencies` shows BWDB 1024, PWD 2018, LGED 1503
- Downloaded ALL tender documents for tender 1290886 via `/tenderer/TenderDocView.jsp` → `all_documents.zip` (2.2MB), 13 files across Section1–Section11
- Fixed zone dict compare for VARCHAR storage
- Fixed BOQ column mapping — auto-detects 10-col vs 14-col format
- Added sub-item code extraction (dotted sub-items from raw PDF text)
- Fixed SOR prefix matching with `len(nc) >= 3` guard
- SOR NOT FOUND marking — red-bold Remarks column, not auto-filled
- Two-pass agency matching: PASS 1 exact, PASS 2 prefix/fuzzy
- Agency suffix restriction: `(PWD)/(LGED)/(BWDB)` in code
- Remarks column with red background + bold dark red text
- APP estimated cost lookup from `app_records` by package number
- TDS financial criteria extraction — 7 qualification criteria from Section2 PDF
- SOR code pattern analysis — perfectly disjoint across agencies
- Pattern-based agency detection in `_detect_agency()`
- Zone mapping for LGED/PWD/BWDB (C↔D swap between LGED and PWD/BWDB)
- Fixed agent-002 crawler — replaced Playwright with subprocess httpx downloader (`_sub_dl.py`) to bypass in-process WinError 10060
- Fixed Notice PDF URL — corrected from broken `/resources/common/GeneratePdf?reqURL=...%3Fid%3D{id}` to working `/GeneratePdf?reqURL=...&reqQuery=id={id}&folderName=TenderNotice&id={id}`
- Fixed TDS extraction — added path fallback + e-GP bracket regex for Indian numbering ("Lac")
- Added brain knowledge sharing — `TenderAcquisitionAgent` v1.4.0 extracts BOQ/TDS text from PDFs via pdfplumber and shares with brain via `share_knowledge("tender_document", ...)`, `share_knowledge("boq_text", ...)`, `share_knowledge("tds_text", ...)`
- Migrated `knowledge_entries` table — added 14 columns, dropped old `stored_at`, dropped FK constraints, made `checksum` nullable
- Built **`POST /api/boq/brain-compare`** — queries brain knowledge entries for BOQ comparison, no file upload needed
- Saved everything to CLAUDE.md and AGENTS.md

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- Used **pdfplumber** table extraction for BOQ PDFs — PyPDF2 breaks multi-cell codes
- **Auto-detect column layout**: check `cells[4]` for code pattern vs unit name
- **Exact match only for auto-fill** — prefix/fuzzy flagged SOR NOT FOUND
- **Two-pass agency matching**: PASS 1 exact (all agencies), PASS 2 prefix/fuzzy
- **Pattern-based agency fallback**: dashes→BWDB, `^\d{2}\.`→PWD, `^[1-9]\.\d{2}`→LGED (perfectly disjoint)
- **Agent-002 doc download**: subprocess `_sub_dl.py` (clean Python, bypasses WinError 10060)
- **Brain knowledge sharing**: 3 entry types — tender_document, boq_text, tds_text — persisted to memory + DB
- **Server persistence**: `Start-Process -WindowStyle Hidden`
- **Zone dict → DB shorthand**: `"BWDB=B,PWD=B,LGED=B"` for VARCHAR storage
- **Brain-based BOQ endpoint**: reads file paths + extracted text from knowledge_entries, no file upload needed

## Next Steps
1. Review SOR NOT FOUND items for tender 1290886 — group codes may need description-based matching
2. Build daily ETL scripts for APP/tenders/e-contracts/e-experience from e-GP
3. Add BD-RERA report generation for e-contracts
4. Handle BREB descriptive BOQs (no SOR codes) via description-based matching
5. Connect orchestrator so agent-002 runs with brain attached in production pipeline
6. Add `GET /api/boq/brain/{tender_id}` for cached brain results without re-comparing

## Critical Context

### Zone Mapping (Division → Zone Letter)
| Division | LGED | PWD | BWDB |
|----------|------|-----|------|
| Dhaka, Mymensingh | A | A | A |
| Chattogram, Sylhet | B | B | B |
| Khulna, Barishal | **D** | **C** | **C** |
| Rajshahi, Rangpur | **C** | **D** | **D** |

LGED swaps C↔D relative to PWD/BWDB.

### SOR Code Patterns — Perfectly Disjoint
- **BWDB**: `^\d{2}-\d{3}-\d{2}` (dash-separated, e.g., `40-200-00`)
- **PWD**: `^\d{2}\.\d` (dotted, 2-digit prefix, e.g., `26.50.1`)
- **LGED**: `^[2-9]\.\d{2}` (dotted, 1-digit prefix, e.g., `4.09.01.01`)
- Edge cases: PWD has 7 dash codes (`02-1-2`), 16 EM codes, 7 `PWD ` prefix; LGED has 19 `1.xx` codes

### e-GP Document Download URLs
- **ZIP bulk**: `/TenderSecUploadServlet?tenderId={id}&folderArchId=1&lotNo=Package&funName=zipdownload`
- **Notice PDF**: `/GeneratePdf?reqURL=http://www.eprocure.gov.bd/resources/common/ViewTender.jsp&reqQuery=id={id}&folderName=TenderNotice&id={id}`
- **Individual section**: `/TenderSecUploadServlet?docName=...&funName=downloadTenderer` (often 0 bytes for demo account)

### Agent-002 v1.4.0
- Subprocess-based download (`_sub_dl.py`) — clean Python process bypasses in-process WinError 10060
- Downloads Notice PDF + all-docs ZIP + extracts to `runtime/tender_acquisition/` + `uploads/{tender_id}/`
- Extracts BOQ + TDS text via pdfplumber and shares with brain via `share_knowledge()`

### Brain Knowledge Architecture
- `share_knowledge("tender_document", ...)` → full acquisition metadata in KnowledgeEntry DB
- `share_knowledge("boq_text", ...)` → extracted BOQ PDF text (up to 50K chars)
- `share_knowledge("tds_text", ...)` → extracted TDS PDF text (up to 50K chars)
- Query from API/agents: `self.query_brain("boq_text", "1298004")` or direct SQL on `knowledge_entries` table
- **`POST /api/boq/brain-compare`**: form params `tender_id`, `sor_agency`, `zone` — queries brain knowledge entries, finds BOQ PDF from acquired file paths, extracts TDS criteria, runs comparison, saves to DB, returns results + tender_notice metadata

### Server Restart
Python caches imported modules; parser/processor changes require server restart:
```powershell
$p = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id $p.OwningProcess -Force }
Start-Process -WindowStyle Hidden -FilePath "C:\Program Files\Python310\python.exe" -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory "D:\A1\procurementflow_final_v3\procurementflow\backend"
```

## Relevant Files
- `backend/app/services/boq_processor.py`: `_detect_agency()`, `_norm_code()`, `_compare_with_sor()` — two-pass matching
- `backend/app/services/pdf_parser.py`: `_parse_bwdb_boq_tables()` — auto-detects 10/14-col format, sub-item extraction
- `backend/app/sor/sor_service.py`: `find_rate()` — prefix match with `len(nc) >= 3` guard
- `backend/app/core/excel_writer.py`: Remarks column with `sor_not_found_fmt` (`#fecaca` bg + `#b91c1c` text)
- `backend/app/api/v1/boq.py`: `compare_boq()` (file-upload) + `brain_compare_boq()` (brain knowledge) endpoints
- `backend/app/agents/discovery/tender_acquisition.py`: `TenderAcquisitionAgent` v1.4.0 — subprocess download, brain knowledge sharing
- `backend/app/agents/discovery/_sub_dl.py`: standalone httpx download script for subprocess execution
- `backend/app/agents/egp_client.py`: `eGPClient` — document download, `_build_direct_export_links()`
- `backend/app/agents/core/brain.py`: `AgentBrain` — `store_knowledge()` (memory + KnowledgeEntry DB), `query_knowledge()`
- `backend/app/db/models.py`: `KnowledgeEntry` (line 505) — 21 columns, indexes on tender_id, entry_type, embedding_id
- `backend/app/models/intelligence.py`: `KnowledgeEntry` (line 347) — basic model (entry_type, tender_id, data, stored_at, checksum)
- `backend/uploads/1298004/`: tender 1298004 docs — all_documents.zip, Section1–Section7 + 6 drawings
- `backend/uploads/1298004/docs/Section2_Tender Data Sheet/`: TDS PDF for 1298004
- `backend/scripts/download_all_docs.py`: reference for TenderDocView scraping
- `backend/scripts/end2end_test.py`: full pipeline test (zone dict, APP estimate, TDS criteria, Excel verification)
- `AGENTS.md`: SOR code patterns, zone mapping, BOQ pipeline, e-GP doc download, agent-002 docs
