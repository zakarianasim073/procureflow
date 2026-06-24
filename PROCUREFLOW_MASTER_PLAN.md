# 🏗 Procurement Flow Specialist BD — Master Plan Review
**Date:** June 5, 2026  
**Target MVP:** August 31, 2026  
**Status:** Pre-Build Architecture Review

---

## SECTION 1 — HONEST ASSESSMENT OF CURRENT STATE

### What You Actually Have (Procurement Flow Specialist BD)
| Module | Status | Quality |
|--------|--------|---------|
| BOQ parsing (XLSX + PDF) | ✅ Working | Solid, handles fallback |
| SOR matching (code + desc) | ✅ Working | SequenceMatcher, 0.8 threshold |
| Zone mapping (A–D) | ✅ Working | Hardcoded, needs DB |
| Export (DOCX, CSV, XLSX, PDF) | ✅ Working | Functional, basic formatting |
| JWT auth | ⚠️ Present but broken | Imported but not wired to routes |
| GPT chat | ⚠️ Skeleton only | OpenAI key not validated |
| Frontend Dashboard | ❌ Broken | Calls /api/boq/diff (doesn't exist) |
| AdminDashboard | ❌ Placeholder | Static list, no data |
| Docker | ⚠️ Exists | Paths mismatched, won't build |
| PostgreSQL | ❌ Missing | Still using JSON file cache |
| Redis | ❌ Missing | No queue system |
| MinIO | ❌ Missing | Files stored locally |

### Critical Bugs to Fix Before Building Forward
```
BUG 1: main.py is duplicated 3× in the project (lines 11, 15, 34 in docs)
        → Single source of truth needed

BUG 2: Frontend calls /api/boq/diff — endpoint does not exist
        → Causes blank dashboard on load

BUG 3: security.py imports from .config (relative) but project runs flat
        → ImportError on startup

BUG 4: boq_parser.py imports from app.models.boq_schema — missing entirely
        → Crashes on BOQ Excel upload

BUG 5: extraction_service.py imports app.parsers.pdf_parser — wrong path
        → Crashes on PDF extract

BUG 6: JWT auth is never applied to any route (no Depends in endpoints)
        → Every API is publicly accessible

BUG 7: config.py JWT_SECRET is hardcoded "super-secret-boq-ai-token-2024"
        → Security vulnerability in production

BUG 8: docker-compose.yml references ./backend and ./frontend 
        → Flat project structure doesn't match; containers won't start

BUG 9: requirements.txt missing: xlsxwriter, difflib (stdlib), pydantic-settings
        → pip install will fail

BUG 10: gpt_client.py uses os.getenv but no .env loading; 
         sync openai client called with async await
         → Runtime crash on chat endpoint
```

---

## SECTION 2 — PLAN REVIEW & SCORING

### Agent Plan Review (16 Agents)

| # | Agent | Verdict | Priority | Comment |
|---|-------|---------|----------|---------|
| 1 | Tender Fetch Agent | ✅ Build | Sprint 2 | eGP scraper — high value, high complexity |
| 2 | Document AI Agent | ✅ Build | Sprint 2 | Core of the product |
| 3 | BOQ Extraction Agent | ✅ Already 60% done | Sprint 1 fix | Refactor existing code |
| 4 | Rate Analysis Agent | ✅ Build | Sprint 3 | SOR comparison already working |
| 5 | Rate Fill Agent | ✅ Build | Sprint 3 | Auto-fill from SOR — killer feature |
| 6 | Validation Agent | ✅ Already 40% done | Sprint 1 fix | validation_service.py exists |
| 7 | Executive Report Agent | ✅ Build | Sprint 4 | PDF/DOCX export already partly working |
| 8 | AI Bid Assistant | ⚠️ Defer | Sprint 5 | GPT skeleton exists; needs stable base first |
| 9 | PPR 2025 Evaluation | ✅ Build | Sprint 4 | HIGH VALUE — unique in market |
| 10 | LERT/Win Probability | ✅ Build | Sprint 5 | Needs award data first |
| 11 | Competitor Intelligence | ✅ Build | Sprint 5 | Needs Award Intelligence data first |
| 12 | Competitor Price Predictor | ⚠️ Sprint 6 | Sprint 6 | ML model — needs 500+ records |
| 13 | Margin Optimizer | ⚠️ Sprint 6 | Sprint 6 | Needs Agent 10 + 12 first |
| 14 | Executive Decision Agent | ⚠️ Sprint 6 | Sprint 6 | Aggregates all agents |
| 15 | Learning Agent | ⚠️ Post-MVP | Post-v1 | Needs 12 months of outcome data |
| 16 | Bid Position Optimizer | ⚠️ Post-MVP | Post-v1 | Same — data-dependent |
| **17** | **Award Intelligence Agent** | ✅ Build EARLY | Sprint 2 | **Critical data feeder for 9, 10, 11** |

### 3 Added Features Review

| Feature | Verdict | Comment |
|---------|---------|---------|
| Tender Radar (daily monitor) | ✅ Must-have | SaaS retention driver — build in Sprint 3 |
| Corrigendum Watchdog | ✅ Must-have | Solves real pain — build in Sprint 3 |
| Bid Knowledge Graph | ✅ Build after data | Sprint 6 — needs 6 months of Award data |

---

## SECTION 3 — REVISED ARCHITECTURE

```
┌─────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js 14)                │
│  Dashboard | BOQ Review | Tender Monitor | Reports | Admin│
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS + JWT
┌─────────────────────▼───────────────────────────────────┐
│                  API GATEWAY (FastAPI)                    │
│  Auth | Rate Limiting | Audit Log | CORS                 │
└──┬──────────────┬───────────────┬────────────────────────┘
   │              │               │
┌──▼──┐      ┌───▼───┐      ┌────▼────┐
│PostgreSQL│  │ Redis  │      │ MinIO   │
│ Main DB  │  │ Queue  │      │ Files   │
└─────┘      └───┬───┘      └─────────┘
                 │
    ┌────────────▼────────────┐
    │     WORKER POOL          │
    │  ┌──────────────────┐   │
    │  │ Document AI       │   │
    │  │ BOQ Extractor     │   │
    │  │ Rate Analyzer     │   │
    │  │ Award Crawler     │   │
    │  │ Report Generator  │   │
    │  └──────────────────┘   │
    └─────────────────────────┘
                 │
    ┌────────────▼────────────┐
    │     AI LAYER             │
    │  Claude API (Primary)    │
    │  OpenAI (Fallback)       │
    │  Local OCR (Tesseract)   │
    └─────────────────────────┘
```

### Key Architecture Decisions

**1. Switch AI Provider**
Your current code uses OpenAI GPT-4-turbo. Switch primary to Claude (claude-sonnet-4-6) for:
- Better structured JSON output (critical for BOQ parsing)
- Longer context window (full tender docs)
- Better instruction following for Bengali tenders
Keep OpenAI as fallback.

**2. Database Schema (Core Tables)**
```sql
tenants           -- Multi-tenant SaaS
users             -- Auth + plan
tenders           -- Fetched/uploaded tenders  
tender_documents  -- MinIO file refs
boq_items         -- Parsed BOQ rows
sor_rates         -- SOR reference data by zone
comparisons       -- BOQ vs SOR results
contract_awards   -- eGP scraped awards (Agent 17)
contractors       -- Company profiles
bid_history       -- Your own bid outcomes
audit_logs        -- Full audit trail
```

**3. Replace JSON Cache with PostgreSQL**
Current `SESSION_CACHE` dict and JSON files → lose data on restart.
Every comparison result must persist to DB.

---

## SECTION 4 — SPRINT PLAN (Revised)

### Sprint 0 — Fix Existing Bugs (Week 1)
**Goal: Make existing code actually run**

```
[ ] Consolidate 3× duplicate main.py into single backend/app/main.py
[ ] Fix all import paths (relative → absolute)
[ ] Add missing requirements: xlsxwriter, pydantic-settings
[ ] Fix docker-compose.yml structure
[ ] Fix Frontend Dashboard to call correct endpoints
[ ] Add .env.example with all required keys
[ ] Wire JWT auth to protected routes
[ ] Fix async/sync mismatch in gpt_client.py
[ ] Add boq_schema.py model (missing)
[ ] Basic health endpoint /api/health
```

**Deliverable:** App starts, BOQ upload works, dashboard loads

### Sprint 1 — Core Infrastructure (Week 2)
**Goal: Production-grade foundation**

```
[ ] PostgreSQL setup + SQLAlchemy models
[ ] Alembic migrations
[ ] MinIO file storage (replace local uploads/)
[ ] Redis connection + Celery worker setup
[ ] Multi-tenant schema (tenant_id on all tables)
[ ] User auth: register, login, JWT refresh
[ ] Role-based access: admin, analyst, viewer
[ ] Centralized error handling middleware
[ ] Structured logging (structlog)
[ ] Docker compose: api + frontend + postgres + redis + minio
```

**Deliverable:** Stable multi-tenant base, clean Docker build

### Sprint 2 — Tender Intelligence (Week 3–4)
**Goal: Data acquisition pipeline**

```
[ ] Agent 1: eGP Tender Fetch (scraper + scheduler)
[ ] Agent 17: Award Intelligence Crawler (contract awards)
[ ] Document upload pipeline (PDF, XLSX, DOCX → MinIO)
[ ] Agent 2: Document AI (Claude API for extraction)
[ ] BOQ Extraction refactor (Agent 3) — move to worker
[ ] Tender Radar: daily matching against company profile
[ ] Corrigendum Watchdog: diff old vs new tender docs
[ ] Notification system (email alerts)
```

**Deliverable:** Auto-fetches new tenders, sends alerts

### Sprint 3 — BOQ + Rate Engine (Week 5–6)
**Goal: Core product value**

```
[ ] Agent 4: Rate Analysis — SOR matching refactored + persisted
[ ] Agent 5: Rate Fill — auto-populate rates from SOR
[ ] Agent 6: Validation Engine — completeness + compliance
[ ] SOR database (upload + zone management UI)
[ ] BOQ comparison UI (replaces current dashboard)
[ ] Inline editing of BOQ items
[ ] Export engine: PDF report, Excel diff, DOCX review sheet
[ ] Work type classification improvement
```

**Deliverable:** Full BOQ upload → SOR compare → export workflow

### Sprint 4 — PPR 2025 Engine (Week 7–8)
**Goal: Regulatory compliance + LERT**

```
[ ] Agent 9: PPR 2025 Rules Engine
    - SLT detection (Abnormally Low Tender)
    - NPPI calculation
    - Weighted average + std deviation
    - Responsive tender filter
[ ] Agent 10: LERT Predictor v1 (rule-based, pre-ML)
[ ] Agent 7: Executive Report (full submission readiness)
[ ] Tender Evaluation worksheet generator
[ ] SLT calculation UI
```

**Deliverable:** PPR 2025 compliant evaluation — unique market feature

### Sprint 5 — Competitor Intelligence (Week 9–10)
**Goal: Market intelligence**

```
[ ] Agent 11: Competitor Intelligence
    - Award history lookup per contractor
    - Win rate by agency/district/method
    - Average winning discount
[ ] Agent 8: AI Bid Assistant (Claude-powered Q&A on tender docs)
[ ] Agent 13: Margin Optimizer v1
[ ] Bid Knowledge Graph (visual)
[ ] Geographic Heat Map
[ ] Contractor DNA profiles
```

**Deliverable:** Real competitor insights from award data

### Sprint 6 — SaaS + ML (Week 11–12)
**Goal: Production-ready SaaS**

```
[ ] Multi-tenant subscription plans
[ ] Stripe payment integration
[ ] Agent 12: Competitor Price Predictor (ML — needs 500+ awards)
[ ] Agent 14: Executive Decision Agent
[ ] Usage metering + quota enforcement
[ ] Staging environment
[ ] CI/CD pipeline (GitHub Actions)
[ ] Load testing
[ ] Security audit
```

**Deliverable:** Billable SaaS product

---

## SECTION 5 — WHAT TO BUILD vs WHAT TO SKIP

### Build Immediately (High ROI)
1. **BOQ + SOR comparison** — already 60% done, fix and ship
2. **PPR 2025 SLT Engine** — nobody else has this, pure moat
3. **Award Intelligence crawler** — feeds everything downstream
4. **Tender Radar alerts** — creates daily active user habit
5. **Corrigendum Watchdog** — solves painful real problem

### Build After Data Exists (ML Dependent)
- Agent 12: Competitor Price Predictor → needs 500+ award records
- Agent 15: Learning Agent → needs 12 months of outcome data
- Agent 16: Bid Position Optimizer → same
- Bid Knowledge Graph → needs 6 months of award data

### Remove or Deprioritize
- ~~16 agents launched simultaneously~~ → Focus on 7 core agents first
- ~~GPT-4-turbo as primary~~ → Switch to Claude, cheaper + better for structured BOQ
- ~~Local JSON cache~~ → PostgreSQL only

---

## SECTION 6 — TECHNOLOGY STACK (FINAL)

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | Next.js 14 + Tailwind | Better SSR than Vite/React for reports |
| Backend | FastAPI + Python 3.12 | Keep existing, solid choice |
| Database | PostgreSQL 16 + SQLAlchemy | Multi-tenant, JSONB for flexible BOQ |
| Queue | Redis + Celery | Async OCR + AI jobs |
| File Storage | MinIO | S3-compatible, self-hosted |
| AI Primary | Claude claude-sonnet-4-6 | Better JSON, longer context |
| AI Fallback | OpenAI GPT-4o | Backup |
| OCR | Tesseract + pdfplumber | Scanned BOQ support |
| Auth | FastAPI-Users + JWT | Proper multi-tenant auth |
| Deployment | Docker Compose → K8s | Start simple, scale later |
| Monitoring | Grafana + Prometheus | Production observability |
| CI/CD | GitHub Actions | Automated testing + deploy |

---

## SECTION 7 — RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| eGP blocks scraper | High | High | Use official API if available; respectful rate limits; Cloudflare-aware headers |
| Bengali PDF OCR quality | High | High | Tesseract Bangla model + GPT-4 Vision fallback |
| 16 agents scope creep | High | High | **Build 7 agents for MVP, add rest post-revenue** |
| No award data initially | Medium | High | Seed with manually collected historical data |
| PPR 2025 rule changes | Medium | Medium | Rules engine as config, not hardcode |
| Single developer bandwidth | High | High | Strict sprint discipline, no feature additions mid-sprint |

---

## SECTION 8 — MILESTONE DATES

| Milestone | Date | Confidence |
|-----------|------|-----------|
| Sprint 0: Bugs fixed, app runs | June 15, 2026 | High |
| Sprint 1: Infrastructure done | June 22, 2026 | High |
| Sprint 2: Tender data pipeline | July 6, 2026 | Medium |
| Sprint 3: BOQ engine production-ready | July 20, 2026 | Medium |
| Sprint 4: PPR 2025 engine live | August 3, 2026 | Medium |
| Sprint 5: Competitor intelligence | August 17, 2026 | Low-Medium |
| **Sprint 6: SaaS MVP LIVE** | **August 31, 2026** | Low-Medium |
| First paying customer | September 30, 2026 | — |
| 100 tenders processed | October 31, 2026 | — |
| ML models trained (500+ awards) | December 31, 2026 | — |

---

## SECTION 9 — MY TOP 5 RECOMMENDATIONS

### #1 — Fix Before Build
Do Sprint 0 this week. The current codebase has broken imports, a non-functional frontend, and a duplicated main.py. Nothing new should be written until the base runs cleanly.

### #2 — Drop to 7 Agents for MVP
Agents 1, 2, 3, 4, 5, 6, 7 + Agent 17 (Award Intelligence). Ship these well. Agents 8–16 need data, time, or both. Quality over quantity.

### #3 — PPR 2025 Engine is Your Moat
No other platform in Bangladesh has a proper PPR 2025 SLT/LERT engine. This is your competitive moat. Build it in Sprint 4 and market it aggressively.

### #4 — Award Intelligence is Your Data Moat
Start crawling eGP contract awards from Day 1 of Sprint 2. Every week you delay is a week less competitive data. After 6 months you'll have something competitors cannot buy.

### #5 — Switch to Claude as Primary AI
Your current BOQ extraction needs structured JSON output from long PDFs. Claude handles this better than GPT-4-turbo and costs less. The API is right there (you're building in Claude now).

---

## SECTION 10 — IMMEDIATE NEXT ACTIONS

```
TODAY (June 5):
  1. Create proper project folder structure (backend/ frontend/ workers/)
  2. Consolidate duplicate main.py
  3. Fix all broken imports

THIS WEEK (Sprint 0):
  4. Fix 10 critical bugs listed in Section 1
  5. Create .env.example
  6. Fix Docker build
  7. Verify: BOQ upload → compare → export works end-to-end

NEXT WEEK (Sprint 1):
  8. Set up PostgreSQL with migrations
  9. Set up MinIO + Redis
  10. Wire auth properly

WEEK 3-4 (Sprint 2):
  11. Build Award Intelligence crawler (Agent 17) — START DATA COLLECTION
  12. eGP Tender Fetch Agent
  13. Tender Radar alerts
```

---

**Bottom line:** The plan is sound. The vision is excellent. The current code needs 1 week of cleanup before any new features. The highest-ROI move is fixing what's broken, wiring up PostgreSQL, and starting the Award Intelligence crawler immediately — because that data takes time to accumulate and is your long-term competitive moat.

*Target: Procurement Flow Specialist BD v1 — August 31, 2026*
