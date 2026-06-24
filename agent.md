# Agent Reference

This file is the concise operational reference for the agent layer.

## Canonical stack

- `Agent Brain`: message routing, knowledge sharing, and agent execution coordination
- `Watchdog`: runtime health, error capture, and pipeline telemetry
- `Intelligence Engineer`: component map, root-cause analysis, and repair steps
- `Knowledge Graph`: contractor DNA and tender lifecycle lookup

## Key data products

- Contractor DNA
- Tender lifecycle
- Live tender search results
- PPR evaluation results
- Knowledge lake entries

## Current source-of-truth tables

- `procurement_tenders`
- `app_records`
- `live_tender_sources`
- `award_records_v2`
- `procurement_lifecycle`
- `contractors`
- `contractor_dna`
- `knowledge_entries`

## What changed in the repair pass

- Contractor DNA now resolves from the PostgreSQL intelligence tables instead of the old awards-only shortcut.
- Lifecycle now resolves across APP, live tender, opening, and award sources using the current schema.
- Watchdog now distinguishes healthy, degraded, and down agent states.
- The engineer references the current registry rather than a stale hardcoded count.

## Example use

```bash
curl http://localhost:8000/api/knowledge-graph/contractor/Techno%20Drugs%20Ltd.
curl http://localhost:8000/api/knowledge-graph/lifecycle/1239360
curl http://localhost:8000/api/watchdog/health
```

## Operating rule

When a route looks wrong, check the current database-backed service first. The repo still has legacy compatibility paths, but the current service layer should be treated as canonical.
