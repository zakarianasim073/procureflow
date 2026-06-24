# ProcureFlow BD — Project Checkpoint

## Last Updated: 2026-06-15

---

## Project Location
- **Build**: `/data/local/tmp/procureflow/`
- **Source**: `/sdcard/procurementflow-bd/`
- **Server**: `http://localhost:8000`

---

## Database (27 tables, ~200MB SQLite)
| Table | Records | Status |
|-------|---------|--------|
| `tenders` | 33,063 | ✅ Imported |
| `awards` | 54,360 | ✅ Imported |
| `contractors` | 12,630 | ✅ Imported |
| `npp_records` | 46,554 | ✅ Imported |
| `app_records` | 31,200 | ✅ Imported |
| `opening_reports` | 4 | ⚠️ Need e-GP crawl |
| `ppr_evaluations` | 0 | ⚠️ Need import |
| `rate_analysis` | 0 | ⚠️ Need import |
| `agent_thoughts` | 2 | ✅ Pending approval |
| `knowledge_entries` | 15 | ✅ System docs |

**New tables added**: `tender_data_pool`, `tender_documents`, `tender_reports`, `agent_thoughts`

---

## 35 Agents Registered
### Discovery (4)
- agent-001: Tender Radar ✓
- agent-002: Tender Acquisition ✓ (enhanced)
- agent-003: Corrigendum Watchdog ✓
- agent-029: Vision Intelligence ✓

### Intelligence (4)
- agent-005: BOQ Intelligence ✓
- agent-006: Spec Intelligence ✓
- agent-014: Award Intelligence ✓
- agent-019: Resource Capacity ✓

### Evaluation (5)
- agent-007: Eligibility Compliance ✓
- agent-008: Risk Intelligence ✓
- agent-009: PPR Evaluation ✓
- agent-010: PPR Compliance ✓
- agent-010: LERT Prediction ✓

### Pricing (5)
- agent-011: Rate Analysis ✓
- agent-012: Market Rate Intelligence ✓
- agent-020: EGP Rate Fill ✓
- agent-030: RA Bill Predictor ✓
- agent-033: VAT Tax Calculator ✓

### Competitor (5)
- agent-013: Competitor Intelligence ✓
- agent-015: Competitor Pricing Predictor ✓
- agent-016: Win Probability ✓
- agent-017: Bid Position Optimizer ✓
- agent-028: Syndicate Radar ✓

### Decision (3)
- agent-018: AI Bid Assistant ✓
- agent-021: Financial Intelligence ✓
- agent-022: Executive Decision ✓

### Acquisition (5)
- agent-004: Document AI ✓
- agent-024: Submission Validation ✓
- agent-031: Tender Preparation ✓
- agent-032: Document Preparation ✓
- agent-034: Tender Document ✓
-**agent-035: Tender Dashboard** ✅ **NEW**

### Knowledge & Learning (3)
- agent-023: Report Generation ✓
- agent-025: Knowledge Lake ✓
- agent-026: Learning Agent ✓

---

## Architecture Built

### ✅ Agent Brain (Message Bus)
- Pub/sub messaging between agents
- Knowledge store (shared facts)
- Query routing
- Workflow orchestration
- **Now started on server boot**

### ✅ Inter-Agent Communication
- TenderRadar → TenderAcquisition → BOQ/Spec agents
- WinProbability ← CompetitorIntelligence + MarketRate
- ExecutiveDecision ← WinProb + BidPosOptimizer + ResourceCapacity
- LearningAgent broadcasts to ALL agents

### ✅ Intelligence Pipeline
10-stage pipeline: Discovery → Intelligence → Decision
- Dependencies validated
- Each stage enriches context for next

### ✅ Knowledge Graph
- Contractor DNA profiles (awards, agencies, patterns)
- Agency Intelligence profiles (spending, top contractors)
- Syndicate pattern detection
- Tender Lifecycle (APP→Tender→Opening→Award)

### ✅ Thought Engine (Human-in-the-Loop)
- Agents propose insights/recommendations
- "Approve once, auto-execute forever" via signatures
- Pending → Approve/Reject flow
- Cached approval signatures for speed

### ✅ Tender Dashboard
- Full document extraction pipeline (Notice→TDS→BOQ→Report)
- Qualification criteria extraction (equipment, manpower, turnover, capacity)
- Readiness scoring
- Structured TenderDataPool

### ✅ SOR Module
- BWDB rates loaded (931 items, 4 zones)
- LGED/PWD stubs ready

---

## Running the System
```bash
cd /data/local/tmp/procureflow/backend
python3 -m uvicorn app.api.server:app --host 0.0.0.0 --port 8000
```

## Key API Endpoints
- `GET /api/v1/health` — System health
- `GET /api/v1/agents` — All 35 agents
- `GET /api/v1/stats` — Database stats
- `GET /api/v1/brain/status` — Brain message queue
- `GET /api/v1/thoughts/pending` — Pending approvals
- `POST /api/v1/thoughts/{id}/approve` — Approve once
- `GET /api/v1/dashboard/{tender_id}` — Full dashboard
- `POST /api/v1/dashboard/{id}/extract` — Run extraction
- `POST /api/v1/pipeline/run` — Full intelligence pipeline
- `GET /api/v1/knowledge-graph/contractor/{name}` — Contractor DNA
- `GET /api/v1/knowledge-graph/agency/{name}` — Agency profile

## Pending Tasks
1. **e-GP credentials**: info@handbl.com / infohandbl2018 — need cookie export from Chrome
2. **~700 opening reports**: Crawl from archived tenders
3. **Frontend connection**: React app at `/sdcard/procurementflow-bd/frontend/dist/`
4. **Import remaining PPR evaluations and rate analysis data**
5. **PostgreSQL migration** when moving to VPS

## Learned Lessons
- Server takes ~15s to start with 35 agents — be patient
- SQLite COUNT(*) queries on large tables are slow — use PRAGMA approach
- Database path must be absolute, not based on cwd
- `execute_raw()` doesn't exist in newer SQLAlchemy async — use `exec_driver_sql()`
- Agent files must use `from app.agents.core.base import` not `from .base import`
