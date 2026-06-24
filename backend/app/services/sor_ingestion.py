"""
Procurement Flow Specialist BD — SOR Ingestion Service
Parses SOR PDFs/CSVs and stores rates in PostgreSQL for millisecond lookup.
"""

from __future__ import annotations

import csv
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from io import StringIO

from app.models.sor_rate import SorRate, SorAgency

logger = logging.getLogger("procureflow.sor_ingestion")


def _normalize_code(code: str) -> str:
    """Normalize SOR code for matching: remove spaces, hyphens, dots, lowercase."""
    return re.sub(r"[\s\-.&/]", "", code).lower()


class SORIngestionService:
    """Handles parsing and storing SOR rates from various file formats."""

    async def ingest_csv(self, db_session, agency: str, csv_content: str) -> Dict[str, Any]:
        """
        Parse CSV content and upsert into sor_rates table.
        Expected CSV columns: code, description, unit, zone_a, zone_b, zone_c, zone_d
        """
        from sqlalchemy import select
        
        reader = csv.DictReader(StringIO(csv_content))
        agency_enum = SorAgency(agency.upper())
        
        imported = 0
        updated = 0
        errors = 0
        
        for row in reader:
            try:
                code = row.get("code", "").strip()
                if not code:
                    continue
                
                normalized = _normalize_code(code)
                
                # Check if exists
                stmt = select(SorRate).where(
                    SorRate.agency == agency_enum,
                    SorRate.normalized_code == normalized,
                )
                result = await db_session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                data = {
                    "code": code,
                    "normalized_code": normalized,
                    "description": row.get("description", "").strip(),
                    "unit": row.get("unit", "").strip().lower(),
                    "zone_a": float(row.get("zone_a", 0) or 0),
                    "zone_b": float(row.get("zone_b", 0) or 0),
                    "zone_c": float(row.get("zone_c", 0) or 0),
                    "zone_d": float(row.get("zone_d", 0) or 0),
                    "is_active": True,
                }
                
                if existing:
                    for key, val in data.items():
                        setattr(existing, key, val)
                    updated += 1
                else:
                    sor = SorRate(agency=agency_enum, **data)
                    db_session.add(sor)
                    imported += 1
                    
            except Exception as e:
                logger.warning(f"SOR row error: {e}")
                errors += 1
        
        await db_session.commit()
        
        return {
            "agency": agency,
            "imported": imported,
            "updated": updated,
            "errors": errors,
            "total": imported + updated,
        }

    async def ingest_from_sor_service(self, db_session, agency: str) -> Dict[str, Any]:
        """
        Migrate rates from the legacy SOR service (JSON/CSV files) into PostgreSQL.
        """
        from app.sor.sor_service import sor_service
        from sqlalchemy import select
        
        # Ensure SOR data is loaded
        sor_service.load_all()
        
        agency_enum = SorAgency(agency.upper())
        rates = sor_service._rates.get(agency.upper(), [])
        
        imported = 0
        for rate in rates:
            try:
                normalized = _normalize_code(rate.code)
                
                stmt = select(SorRate).where(
                    SorRate.agency == agency_enum,
                    SorRate.normalized_code == normalized,
                )
                result = await db_session.execute(stmt)
                
                if not result.scalar_one_or_none():
                    sor = SorRate(
                        agency=agency_enum,
                        code=rate.code,
                        normalized_code=normalized,
                        description=rate.description,
                        unit=rate.unit,
                        zone_a=rate.zone_a,
                        zone_b=rate.zone_b,
                        zone_c=rate.zone_c,
                        zone_d=rate.zone_d,
                        is_active=True,
                    )
                    db_session.add(sor)
                    imported += 1
            except Exception as e:
                logger.warning(f"SOR migration error for {rate.code}: {e}")
        
        await db_session.commit()
        return {"agency": agency, "migrated": imported, "total": len(rates)}

    async def find_rate(self, db_session, code: str, agency: str = "BWDB",
                         zone: Optional[str] = None) -> Tuple[Optional[float], Optional[SorRate]]:
        """Fast PostgreSQL lookup of SOR rate by code and agency."""
        from sqlalchemy import select
        
        normalized = _normalize_code(code)
        agency_enum = SorAgency(agency.upper())
        
        # 1. Exact match
        stmt = select(SorRate).where(
            SorRate.agency == agency_enum,
            SorRate.normalized_code == normalized,
            SorRate.is_active == True,
        )
        result = await db_session.execute(stmt)
        rate = result.scalar_one_or_none()
        if rate:
            return rate.get_rate(zone), rate
        
        # 2. Prefix match (e.g., "40-300" matches "40-300-10")
        prefix = normalized.replace("-", "").replace(".", "")
        stmt = select(SorRate).where(
            SorRate.agency == agency_enum,
            SorRate.normalized_code.startswith(prefix),
            SorRate.is_active == True,
        ).order_by(SorRate.normalized_code).limit(1)
        result = await db_session.execute(stmt)
        rate = result.scalar_one_or_none()
        if rate:
            return rate.get_rate(zone), rate
        
        return None, None


sor_ingestion = SORIngestionService()
