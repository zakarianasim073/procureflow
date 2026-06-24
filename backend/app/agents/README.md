# Procurement Flow Specialist BD — Agent Registry v1.0

A complete AI Tender Operating System with 27 specialized agents for end-to-end tender management.

## Architecture

```
                    ┌──────────────────────────────┐
                    │   Workflow Orchestrator (27)  │
                    │     Master Agent Controller   │
                    └──────────────────────────────┘
                                    │
         ┌──────────┬──────────┬────┴────┬──────────┬──────────┐
         ▼          ▼          ▼         ▼          ▼          ▼
    ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
    │DISCOVERY│ │INTELLIGE│ │EVALUATI│ │ PRICING│ │COMPETIT│ │DECISION│
    │ 1-3     │ │ 4-6     │ │ 7-10   │ │ 11-12  │ │ 13-17  │ │ 18-21  │
    └─────────┘ └─────────┘ └────────┘ └────────┘ └────────┘ └────────┘
                                                    │
                                           ┌────────┴────────┐
                                           ▼                 ▼
                                      ┌─────────┐       ┌─────────┐
                                      │EXECUTION│       │REPORTING│
                                      │ 22-23   │       │   24    │
                                      └─────────┘       └─────────┘
                                           │
                                           ▼
                                      ┌─────────┐
                                      │ LEARNING│
                                      │ 25-26   │
                                      └─────────┘
```

## All 27 Agents

### Phase 1: Discovery (Agents 1-3)
| # | Agent | Purpose |
|---|-------|---------|
| 1 | Tender Radar | Monitor eGP/BPPA portals for new tenders |
| 2 | Tender Acquisition | Download tender documents from Tender ID |
| 3 | Corrigendum Watchdog | Detect changes in published tenders |

### Phase 2: Intelligence (Agents 4-6)
| # | Agent | Purpose |
|---|-------|---------|
| 4 | Document AI | OCR, layout detection, section extraction |
| 5 | BOQ Intelligence | Parse and classify BOQ line items |
| 6 | Spec Intelligence | Extract technical specification requirements |

### Phase 3: Evaluation (Agents 7-10)
| # | Agent | Purpose |
|---|-------|---------|
| 7 | Eligibility & Compliance | Check qualification requirements |
| 8 | Risk Intelligence | Analyze contractual risks |
| 9 | PPR 2025 Evaluation | Simulate TEC evaluation |
| 10 | LERT Prediction | Predict Lowest Evaluated Responsive Tender |

### Phase 4: Pricing (Agents 11-12)
| # | Agent | Purpose |
|---|-------|---------|
| 11 | Rate Analysis | Generate item rates |
| 12 | Market Rate Intelligence | Market pricing database |

### Phase 5: Competitor (Agents 13-17)
| # | Agent | Purpose |
|---|-------|---------|
| 13 | Competitor Intelligence | Track competitor behavior |
| 14 | Award Intelligence | Build award history database |
| 15 | Competitor Pricing Predictor | Predict competitor bid prices |
| 16 | Win Probability | Predict chance of winning |
| 17 | Bid Position Optimizer | Recommend optimal bid amount |

### Phase 6: Decision (Agents 18-21)
| # | Agent | Purpose |
|---|-------|---------|
| 18 | AI Bid Assistant | Should We Bid? analysis |
| 19 | Resource Capacity | Check company readiness |
| 20 | Financial Intelligence | Financial planning & forecasting |
| 21 | Executive Decision | Final executive recommendation |

### Phase 7: Execution (Agents 22-23)
| # | Agent | Purpose |
|---|-------|---------|
| 22 | EGP Rate Fill | Prepare portal pricing data |
| 23 | Submission Validation | Verify submission integrity |

### Phase 8: Reporting (Agent 24)
| # | Agent | Purpose |
|---|-------|---------|
| 24 | Report Generation | Technical, Commercial, Executive reports |

### Phase 9: Learning (Agents 25-26)
| # | Agent | Purpose |
|---|-------|---------|
| 25 | Knowledge Lake | Central organizational memory |
| 26 | Learning Agent | Continuous improvement from outcomes |

### Master Control (Agent 27)
| # | Agent | Purpose |
|---|-------|---------|
| 27 | Workflow Orchestrator | Coordinate all agents across pipeline |

## Quick Start

```bash
# List all agents
python -m app.agents.runner list

# Show agent details
python -m app.agents.runner info agent-001-tender-radar

# Run a single agent
python -m app.agents.runner run agent-001-tender-radar --context '{"tender_id":"eGP-001"}'

# Run full pipeline
python -m app.agents.runner pipeline --mode full

# Run a specific phase
python -m app.agents.runner pipeline --mode phase --phase discovery

# Start the API server
python -m app.agents.server
```

## API Endpoints (server mode)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | App info |
| GET | `/api/health` | Health check |
| GET | `/api/agents` | List all agents |
| GET | `/api/agents/{id}` | Agent details |
| POST | `/api/agents/{id}/run` | Execute agent |
| POST | `/api/pipeline/run` | Run pipeline |
| GET | `/api/system/status` | System health |
| GET | `/api/pipeline/phases` | List phases |

## Build Priority

**Phase 1 (MVP):** Agents 1-11, 21, 24, 25, 27  
**Phase 2 (Advanced):** Agents 12-17 (needs data accumulation)  
**Phase 3 (ML):** Agents 15-17, 26 (needs 500+ outcome records)
