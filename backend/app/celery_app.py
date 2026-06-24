"""
Procurement Flow Specialist BD — Celery Background Worker Configuration
Offloads heavy agent processing (eGP scraping, PDF parsing, 27-agent pipeline)
to background workers so FastAPI stays responsive.

Includes Celery Beat schedule for automated tasks:
  - Tender Radar: every hour
  - Award Intelligence scraping: daily at 2 AM
  - Corrigendum Watchdog: every 6 hours
  - Tender cleanup: weekly
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "procureflow",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.workers.tasks.agent_tasks",
        "app.workers.tasks.boq_tasks",
        "app.workers.tasks.pipeline_tasks",
        "app.workers.tasks.notification_tasks",
        "app.workers.tasks.document_tasks",
        "app.workers.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Dhaka",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# ── Celery Beat Schedule (Automated Tasks) ────────────────────────────────

celery_app.conf.beat_schedule = {
    # 1. Tender Radar — scan every hour for new matching tenders
    "radar-scan-hourly": {
        "task": "pipeline_discovery",
        "schedule": crontab(minute=0),
        "kwargs": {"context": {"mode": "discovery", "source": "celery_beat"}},
    },
    # 2. Award Intelligence — scrape eGP awards nightly at 2:00 AM (build Data Moat)
    "scrape-awards-daily": {
        "task": "run_agent_task",
        "schedule": crontab(hour=2, minute=0),
        "kwargs": {"agent_id": "agent-014-award-intelligence", "context": {"limit": 100}},
    },
    # 3. Corrigendum Watchdog — check for amendments every 6 hours
    "corrigendum-check": {
        "task": "run_agent_task",
        "schedule": crontab(hour="*/6", minute=0),
        "kwargs": {"agent_id": "agent-003-corrigendum-watchdog", "context": {}},
    },
    # 4. Daily Bulk Collection — collect 1000+ tenders every night at 3:00 AM
    "bulk-collection-daily": {
        "task": "run_agent_task",
        "schedule": crontab(hour=3, minute=0),
        "kwargs": {
            "agent_id": "agent-014-award-intelligence",
            "context": {"bulk_mode": True, "target_count": 1000, "run_bwdb_monitor": True},
        },
    },
    # 5. BWDB Monitor Scan — check for high-value tenders every 6 hours
    "bwdb-monitor-scan": {
        "task": "run_agent_task",
        "schedule": crontab(hour="*/6", minute=30),
        "kwargs": {
            "agent_id": "agent-014-award-intelligence",
            "context": {"bulk_mode": False, "limit": 200, "run_bwdb_monitor": True},
        },
    },
    # 6. Data cleanup — purge old temp files weekly on Sunday midnight
    "cleanup-weekly": {
        "task": "run_agent_task",
        "schedule": crontab(hour=0, minute=0, day_of_week=0),
        "kwargs": {"agent_id": "agent-025-knowledge-lake", "context": {"action": "cleanup"}},
    },
}
