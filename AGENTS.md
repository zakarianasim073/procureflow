# ProcureFlow Agent Knowledge

## Project Structure
- Backend: `backend/` — FastAPI Python app on port 8000
- Database: PostgreSQL 16.14, `procurementflow` DB, `postgres` user, password=`procurementflow`
- Python: 3.10 at `C:\Program Files\Python310\python.exe`
- Virtual env: `env/` (Python 3.10)
- Frontend: separate SPA (not in this repo)

## Key Domains

### SOR (Schedule of Rates)
- 3 agencies: BWDB (1024 rates), PWD (2018 rates), LGED (1503 rates)
- DB table: `sor_rates` with columns `agency`, `code`, `description`, `unit`, `zone_a/b/c/d`
- SOR service: `backend/app/sor/sor_service.py` — `find_rate(code, desc, agency, zone)`
- ETL: `backend/app/services/sor_etl.py` — CSV → PostgreSQL, supports `force=True` for re-import
- Extract scripts: `backend/scripts/extract_from_pdf_tables.py` (LGED/PWD), `extract_all_bwdb_pdfs.py`

### SOR Item Code Patterns (Agency Detection)
Each agency uses a distinct code format — patterns are perfectly disjoint (zero ambiguity):

| Agency | Pattern | Regex | Example | Count |
|--------|---------|-------|---------|-------|
| **BWDB** | `XX-XXX-XX` (dash-separated) | `^\d{2}-\d{3}-\d{2}` | `40-200-00`, `16-200-00` | 1024 |
| **PWD** | `XX.XX...` (dotted, 2-digit prefix) | `^\d{2}\.\d` | `26.50.1`, `12.1.1.1`, `32.7` | 2018 |
| **LGED** | `X.XX.XX...` (dotted, 1-digit prefix [2-9]) | `^[2-9]\.\d{2}` | `4.09.01.01`, `3.11.01`, `4.07.01.01` | 1503 |

**Edge cases** (verified: no cross-agency ambiguity):
- PWD has 7 dash codes (`02-1-2`, `04-3`, `15-1-1`, `16-1-1`) — these are old-format PWD items
- PWD has 16 EM codes (`EM3.1.2`, `EM07.13.01`, `EM-1.18.1.1.1`) — all PWD-specific
- PWD has 7 codes with `PWD ` prefix (`PWD 03.1`) — import artifacts
- LGED has 1 trivial code `1` (also exists in PWD — singleton edge case)
- LGED has 19 codes starting with `1.` (no PWD codes use single-digit `1.`; PWD uses `01.`)
- Detection in boq_processor: suffix first (`(PWD)/(LGED)/(BWDB)`), then pattern fallback

### Zone Mapping (Division → Agency Zone)
See main CLAUDE.md for full mapping. TL;DR: LGED swaps C↔D vs PWD/BWDB.
Zone can be passed as string ("B") or dict (`{"BWDB":"B","PWD":"B","LGED":"B"}`).

### BOQ Comparison Pipeline
- Upload → Compare → Excel report
- Legacy API: `POST /api/boq/upload` (multipart `file`), then `POST /api/boq/compare` with `boq_file_id`, `sor_agency`, `zone`, `tender_info`
- **Brain API (new)**: `POST /api/boq/brain-compare` with `tender_id`, `sor_agency`, `zone` — queries knowledge_entries for BOQ file paths + extracted text, no file upload needed
- BOQ Processor: `backend/app/services/boq_processor.py` — parses PDF via `pdf_parser.py`, matches items across all 3 SOR agencies
- PDF Parser: `backend/app/services/pdf_parser.py` — tries pdfplumber table extraction first, then format-detection text parsing
- Multi-agency matching: For each item, tries detected agency first (from code suffix), then all other agencies

### e-GP Tender Document Download
- Base URL: `https://www.eprocure.gov.bd`
- Demo credentials: hbsrjv@gmail.com / hbsrjv2017
- Client: `backend/app/agents/egp_client.py`
- Public tender search: POST `/TenderDetailsServlet` with `funName=AllTenders`, `viewType=Live|Archive|AllTenders|Cancel`, `pageNo`, `size`
- ZIP download all: `/TenderSecUploadServlet?tenderId={ID}&folderArchId=1&lotNo=Package&funName=zipdownload` (most reliable bulk method)
- Notice PDF: `/GeneratePdf?reqURL=http://www.eprocure.gov.bd/resources/common/ViewTender.jsp&reqQuery=id={ID}&folderName=TenderNotice&id={ID}`
  - Do NOT use the old URL: `/resources/common/GeneratePdf?reqURL=/resources/common/ViewTender.jsp%3Fid%3D{ID}` (returns 404)
- Document listing: `GET /tenderer/TenderDocView.jsp?tenderId={ID}` (authenticated)
- Individual section downloads via `funName=downloadTenderer` often return 0 bytes for demo accounts
- Document sections: Section1 (ITT), Section2 (TDS), Section3 (GCC), Section4 (PCC), Section5 (Forms), Section6 (BOQ), Section7-11 (Specs, Drawings, Appendix)
- Tender search awards (public): POST `/SearchNoaServlet` with `keyword`, `pageNo`, `size`

### Tender Acquisition Agent (agent-002) v1.4.0
- Subprocess-based download (`_sub_dl.py`) — clean Python process bypasses in-process WinError 10060
- Downloads:
  1. **Notice PDF** via `GeneratePdf?reqURL=...` — saved to `uploads/{tender_id}/notice.pdf`
  2. **All-documents ZIP** via `TenderSecUploadServlet?funName=zipdownload` — saved + extracted to `uploads/{tender_id}/`
  3. **TenderDocView.jsp** scrape — downloads individual section PDFs/DOCX
  4. All docs mirrored to `uploads/{tender_id}/` for BOQ pipeline access
- Extracts BOQ + TDS text via pdfplumber and shares with brain via `share_knowledge()`
- Uploaded docs stored at: `backend/uploads/{tender_id}/`
- Source file: `backend/app/agents/discovery/tender_acquisition.py`
- Subprocess script: `backend/app/agents/discovery/_sub_dl.py`

### Brain Knowledge Architecture
The brain stores 3 knowledge entry types per acquired tender:

| Entry Type | Content | Stored By |
|------------|---------|-----------|
| `tender_document` | Full acquisition metadata (file paths, status, tender info, downloaded_files list) | Agent-002 on completion |
| `boq_text` | Extracted BOQ PDF text (up to 50K chars) via pdfplumber | Agent-002 on completion |
| `tds_text` | Extracted TDS PDF text (up to 50K chars) via pdfplumber | Agent-002 on completion |

Storage: both brain memory cache AND PostgreSQL `knowledge_entries` table (21 columns including entry_type, tender_id, data JSON, summary, tags, source).

Query from code: `self.query_brain("boq_text", "1298004")` → gets BOQ text from brain.
Query from API: `POST /api/boq/brain-compare` uses brain knowledge to find BOQ PDF, extract TDS criteria, run comparison.

### TDS Financial Criteria Extraction
Parses Section2 PDF text via pdfplumber + regex for e-GP bracket format:
- Indian numbering: `[50,00,000]`, `[5500000]`, `[17,50,000` — commas removed, values parsed as integers
- Regex patterns target e-GP phrasing: "shall be [5] years", "value of at least Tk. [50,00,000]", "average annual construction turnover greater than Tk [55,00,000]"
- 7 criteria extracted: General Experience, Specific Experience, Avg Annual Turnover, Liquid Assets, Min Tender Capacity, Tender Security, Performance Security

### e-GP Opening Reports
- Tender opening reports were crawled from the authenticated tenderer area, not public tender pages.
- Known navigation pattern:
  1. `Tender -> My Tenders`
  2. move to archived tenders when required
  3. open the tender dashboard
  4. open the `Opening` tab
  5. select `TORR2` when that report variant is needed
- Preserve this route in agent logic when implementing tender opening report acquisition or brain/knowledge retrieval for opening-stage data.

### Tender Database
- 395K tenders, 207K app_records, 238K awards, 32K contractors
- Tables: `procurement_tenders`, `procurement_awards`, `procurement_lifecycle`, `app_records`, `contractors`
- Agent: `TenderAcquisitionAgent` in `backend/app/agents/discovery/tender_acquisition.py`

### Quick Commands
```powershell
# Start server
Start-Process -WindowStyle Hidden -FilePath "C:\Program Files\Python310\python.exe" -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory "D:\A1\procurementflow_final_v3\procurementflow\backend"

# Kill server
$p = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id $p.OwningProcess -Force }

# Brain-based BOQ comparison (no file upload needed)
curl -X POST http://localhost:8000/api/boq/brain-compare -F "tender_id=1298004" -F "sor_agency=BWDB" -F "zone=A"

# Legacy file-upload BOQ comparison
curl -X POST http://localhost:8000/api/boq/compare -F "boq_file_id=UUID" -F "sor_agency=BWDB" -F "zone=A"

# Check SOR counts
curl http://localhost:8000/api/sor/agencies

# Test endpoints
python scripts/upload_compare_v3.py
```
