"""
Procurement Flow Specialist BD — BOQ Processing Celery Tasks
Background wrappers for BOQ comparison and export generation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional
from pathlib import Path

from app.celery_app import celery_app
from app.services.boq_processor import BOQProcessor
from app.sor.sor_service import sor_service

logger = logging.getLogger("procureflow.tasks.boq")


@celery_app.task(bind=True, max_retries=3, name="process_boq_comparison_task")
def process_boq_comparison_task(self, boq_path: str, sor_agency: str = "BWDB",
                                  zone: Optional[str] = None,
                                  tender_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Process BOQ comparison in the background.
    Returns the full comparison result with all items, summary, and flagged items.
    """
    if tender_info is None:
        tender_info = {}
    
    try:
        processor = BOQProcessor()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                processor.compare(
                    boq_path=boq_path,
                    sor_agency=sor_agency,
                    zone=zone,
                    sor_service=sor_service,
                    tender_info=tender_info,
                )
            )
            return result
        finally:
            loop.close()
            
    except Exception as exc:
        logger.error(f"BOQ comparison task failed: {exc}")
        self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, max_retries=2, name="generate_export_task")
def generate_export_task(self, comparison_id: str, format: str = "xlsx",
                          output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate Excel or DOCX export from comparison results.
    """
    try:
        from app.db.base import get_session_factory
        from app.models.boq import BOQComparison
        from sqlalchemy import select
        
        # Fetch comparison from DB
        factory = get_session_factory()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            async def _fetch_and_export():
                async with factory() as session:
                    stmt = select(BOQComparison).where(BOQComparison.id == comparison_id)
                    result = await session.execute(stmt)
                    comparison = result.scalar_one_or_none()
                    
                    if not comparison:
                        return {"error": "Comparison not found", "status": "failed"}
                    
                    if format == "xlsx" and comparison.excel_path:
                        return {
                            "status": "success",
                            "format": format,
                            "path": comparison.excel_path,
                        }
                    elif format == "docx" and comparison.docx_path:
                        return {
                            "status": "success",
                            "format": format,
                            "path": comparison.docx_path,
                        }
                    
                    return {
                        "status": "success",
                        "format": format,
                        "path": None,
                        "message": "Export file not yet generated",
                    }
            
            return loop.run_until_complete(_fetch_and_export())
        finally:
            loop.close()
            
    except Exception as exc:
        logger.error(f"Export task failed: {exc}")
        self.retry(exc=exc, countdown=10)
