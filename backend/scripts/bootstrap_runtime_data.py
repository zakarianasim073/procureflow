"""One-time bootstrap for heavy runtime data imports.

Run this manually instead of doing it inside app startup:

    cd backend
    python scripts/bootstrap_runtime_data.py
"""

from __future__ import annotations

import asyncio
import logging

from app.db.base import init_db, get_session_factory
from app.services.intelligence_data_service import IntelligenceDataService, ImportProgress
from app.services.sor_etl import import_sor_to_db


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bootstrap_runtime_data")


async def main() -> None:
    logger.info("Initializing database...")
    await init_db()

    logger.info("Importing SOR data into PostgreSQL...")
    try:
        import_sor_to_db()
        logger.info("SOR import complete")
    except Exception as exc:
        logger.warning("SOR import skipped: %s", exc)

    logger.info("Running legacy JSON sync and regime backfill...")
    progress = ImportProgress()
    sf = get_session_factory()
    async with sf() as session:
        svc = IntelligenceDataService(session)
        existing = await svc.get_import_counts()
        if existing.get("app_records", 0) > 0 and existing.get("awards", 0) > 0:
            logger.info("Legacy data already present; only backfilling regimes.")
            summary = await svc.backfill_tender_regimes()
            logger.info("Regime backfill summary: %s", summary)
            return

        summary = await svc.import_existing_json_data(progress=progress)
        summary["regime_backfill"] = await svc.backfill_tender_regimes()
        logger.info("Bootstrap complete: %s", summary)


if __name__ == "__main__":
    asyncio.run(main())
