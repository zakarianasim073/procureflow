# 🏗 Procurement Flow Specialist BD

**Bangladesh's Most Advanced AI-Powered Tender Processing Operating System**

Procurement Flow Specialist BD is an end-to-end tender processing platform that automates BOQ analysis, SOR rate comparison, e-GP tender monitoring, bid document preparation, and competitor intelligence — powered by a registry-backed AI pipeline.

## Documentation

- [Founders Technical Documentation](FOUNDERS_TECHNICAL_DOCUMENTATION.md)
- [Agent Reference](agent.md)
- [Operator Skillbook](skill.md)
- [Agent Registry README](backend/app/agents/README.md)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker + Docker Compose (for production)

### Local Development

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
cp .env.example .env  # Edit with your keys
uvicorn app.main:app --reload
# → http://localhost:8000/api/health

# 2. Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173

# 3. Workers (optional)
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

### Docker Deployment

```bash
docker-compose up -d --build
# → Backend: http://localhost:8000
# → Frontend: http://localhost:80
# → MinIO: http://localhost:9001
# → Flower: http://localhost:5555
```

---

## 🧠 27-Agent Pipeline

| Phase | Agents | Purpose |
|-------|--------|---------|
| 🔍 **Discovery** | 1-3 | Tender Radar, Acquisition, Corrigendum Watchdog |
| 📖 **Intelligence** | 4-6 | Document AI, BOQ Intelligence, Spec Intelligence |
| ✅ **Evaluation** | 7-10 | Eligibility, Risk, PPR 2025, LERT Prediction |
| 💰 **Pricing** | 11-12 | Rate Analysis, Market Rate Intelligence |
| 🏢 **Competitor** | 13-17 | Competitor Intel, Awards, Pricing Predictor, Win Probability, Bid Optimizer |
| 🎯 **Decision** | 18-21 | AI Bid Assistant, Resource Capacity, Financial Intel, Executive Decision |
| 📋 **Execution** | 22-23 | EGP Rate Fill, Submission Validation |
| 📊 **Reporting** | 24 | Report Generation |
| 🧠 **Learning** | 25-27 | Knowledge Lake, Learning, Orchestrator |

### CLI Usage
```bash
python -m app.agents.runner list           # List all agents
python -m app.agents.runner phases         # Show pipeline phases
python -m app.agents.runner pipeline --mode full   # Run full pipeline
```

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│              FRONTEND (Vite + React 18)                  │
│  Dashboard | Upload | BOQ Review | AI Chat | Settings    │
└─────────────────────┬───────────────────────────────────┘
                      │ JWT + REST
┌─────────────────────▼───────────────────────────────────┐
│              API GATEWAY (FastAPI)                       │
│  Auth | BOQ Compare | SOR Lookup | Agent Pipeline        │
└──┬──────────────┬───────────────┬────────────────────────┘
   │              │               │
┌──▼──┐      ┌───▼───┐      ┌────▼────┐
│PostgreSQL│  │ Redis  │      │ MinIO   │
│ Multi-   │  │ Queue  │      │ File    │
│ Tenant   │  │ Broker │      │ Storage  │
└─────┘      └───┬───┘      └─────────┘
                 │
    ┌────────────▼────────────┐
    │      CELERY WORKERS      │
    │  27-Agent Pipeline       │
    └─────────────────────────┘
```

---

## ✨ Key Features

### BOQ/SOR Analysis Engine
- Parse BOQ from PDF and XLSX
- Compare against BWDB, PWD, LGED SOR rates
- Zone-based rate adjustment (A-D)
- Export to XLSX, DOCX, PDF

### PPR 2025 Compliance Engine
- Seriously Low Tender (SLT) detection
- Abnormally Low Tender (ALT) analysis
- Arithmetic error checking
- Qualification compliance

### eGP Integration
- Tender radar with hourly monitoring
- Award intelligence scraping
- Corrigendum watchdog
- Rate auto-fill for eGP submission

### Competitor Intelligence
- Win probability prediction
- Market rate analysis
- Bid position optimization
- Financial capacity assessment

### Multi-Tenant SaaS
- JWT authentication with role-based access
- Free/Pro/Enterprise pricing tiers
- Stripe payment integration
- Audit logging

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vite + React 18 + TypeScript + Tailwind CSS |
| Backend | FastAPI + Python 3.12 + SQLAlchemy (async) |
| Database | PostgreSQL 16 + Alembic migrations |
| Queue | Redis + Celery + Celery Beat |
| Storage | MinIO (S3-compatible) |
| AI | OpenAI GPT-4 / Claude Sonnet / Ollama (local) |
| Auth | JWT with password hashing |
| Monitoring | Flower (Celery) |
| Payments | Stripe |

---

## 📁 Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── agents/        # 27 AI agents + orchestrator
│   │   ├── api/v1/        # REST API routes
│   │   ├── core/          # Config, security, helpers
│   │   ├── db/            # Database engine & session
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic
│   │   ├── sor/           # SOR rate data (BWDB/PWD/LGED)
│   │   └── workers/       # Celery background tasks
│   ├── alembic/           # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # Reusable components
│   │   ├── pages/         # Route pages
│   │   ├── store/         # Zustand state management
│   │   └── api/           # API client
│   └── package.json
├── deploy/                # Docker Compose (prod)
├── desktop/               # Electron desktop app
├── extension/             # Chrome extension
├── docker-compose.yml     # Docker Compose (dev)
└── verify_local.sh        # Verification script
```

---

## 📄 License & Terms
- [Terms of Service](https://procurementflow.com.bd/terms)
- [Privacy Policy](https://procurementflow.com.bd/privacy)

---

*Built with ❤️ for Bangladeshi Contractors • Target MVP: August 31, 2026*

## 🪟 Windows 11 Quick Start

### Prerequisites
- **Python 3.10+** — [Download](https://www.python.org/downloads/) (check "Add Python to PATH")
- **Node.js 18+** — [Download](https://nodejs.org/)
- **Git** — [Download](https://git-scm.com/downloads) (optional, for cloning)

### Setup (One-Time)

**Option A — Double-click (Recommended)**
1. Extract the project to a folder (e.g. `C:\TenderSuite`)
2. Double-click `START_ALL_CLEAN.bat` for a clean restart, or `START_ENTERPRISE_TENDER_SUITE.bat` for the legacy all-in-one flow
3. Choose option **1** for full setup
4. Wait for all dependencies to install
5. The system starts automatically

**Option B — Manual**
```cmd
cd C:\TenderSuite
setup.bat
start.bat
```

### What Gets Installed
| Component | Technology | Notes |
|-----------|-----------|-------|
| Backend API | FastAPI (Python) | Port 8000 |
| Frontend UI | React + Vite | Port 5173 |
| Database | SQLite | No PostgreSQL needed |
| SOR Data | CSV files | BWDB / LGED / PWD rates |
| Storage | `runtime/` | Uploads, logs, DB |

### Data Storage (Windows)
```
%USERPROFILE%\Documents\tenderai\    → Generated reports & exports
backend\runtime\                     → Database, uploads, logs
backend\runtime\db\procureflow.db    → SQLite database
backend\app\sor\                     → SOR rate data (BWDB/LGED/PWD)
```

### Troubleshooting
- **"Python not found"** → Reinstall Python, tick "Add Python to PATH"
- **"pip not recognized"** → Run `python -m ensurepip --upgrade`
- **Port conflict** → Close other apps using port 8000 or 5173
- **OpenAI errors** → Set your API key in `.env` or use demo mode
- **Database errors** → Delete `runtime\db\procureflow.db` and restart

### Environment Variables (`.env`)
Copy `.env.example` to `.env` and configure:
- `OPENAI_API_KEY` — Your OpenAI key (optional, demo works without)
- `DATABASE_URL` — Defaults to SQLite; set PostgreSQL URL for production
- `JWT_SECRET` — Change for production
