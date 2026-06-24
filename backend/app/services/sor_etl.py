"""SOR ETL — Import CSV rate data into PostgreSQL"""
import csv
import uuid
import logging
from pathlib import Path
from typing import Dict

from sqlalchemy import select, func, inspect
from sqlalchemy.orm import Session

from app.db.database import get_sync_engine
from app.models.sor_rate import SorRate, SorAgency

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent / "sor"


def _norm(code: str) -> str:
    """Normalize: remove spaces, hyphens, dots, &, lowercase"""
    return code.replace(' ', '').replace('-', '').replace('.', '').replace('&', '').lower()


def get_sor_count() -> int:
    """Return total SorRate records in PostgreSQL."""
    engine = get_sync_engine()
    inspector = inspect(engine)
    if "sor_rates" not in inspector.get_table_names():
        return 0
    with Session(engine) as session:
        return session.scalar(select(func.count(SorRate.id))) or 0


def import_sor_to_db(force: bool = False) -> Dict[str, int]:
    """Import all SOR CSV data into PostgreSQL. Skips if data exists unless force=True."""
    if not force:
        existing = get_sor_count()
        if existing > 0:
            logger.info("SOR ETL skipped: %d rates already in PostgreSQL", existing)
            return {"skipped": True, "existing_count": existing}

    engine = get_sync_engine()
    if force:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            conn.execute(sa_text("TRUNCATE TABLE sor_rates CASCADE"))
            conn.commit()
        logger.info("SOR ETL: truncated existing sor_rates table")
    agencies = ["BWDB", "PWD", "LGED"]
    total = 0
    results = {}

    with Session(engine) as session:
        for agency_name in agencies:
            csv_path = BASE_DIR / agency_name.lower() / "rates.csv"
            if not csv_path.exists():
                logger.warning("CSV not found for %s: %s", agency_name, csv_path)
                continue

            count = 0
            with open(str(csv_path), 'r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        code = row.get('code', '').strip()
                        if not code:
                            continue
                        rate = SorRate(
                            id=str(uuid.uuid4()),
                            agency=SorAgency(agency_name),
                            code=code,
                            normalized_code=_norm(code),
                            description=row.get('description', '').strip()[:500],
                            unit=row.get('unit', '').strip().lower()[:50],
                            zone_a=float(row.get('zone_a', 0) or 0),
                            zone_b=float(row.get('zone_b', 0) or 0),
                            zone_c=float(row.get('zone_c', 0) or 0),
                            zone_d=float(row.get('zone_d', 0) or 0),
                            is_active=True,
                            source_file=str(csv_path),
                        )
                        session.add(rate)
                        count += 1
                    except (ValueError, KeyError) as e:
                        logger.warning("Skipping row in %s: %s", csv_path, e)
                        continue

            session.commit()
            results[agency_name] = count
            total += count
            logger.info("SOR ETL: imported %d %s rates", count, agency_name)

    results["total"] = total
    logger.info("SOR ETL complete: %d total rates imported", total)
    return results


def load_all_from_db():
    """Load all SorRate records from PostgreSQL as list of dicts."""
    engine = get_sync_engine()
    inspector = inspect(engine)
    if "sor_rates" not in inspector.get_table_names():
        return {}

    from sqlalchemy.orm import Session
    with Session(engine) as session:
        rates = session.execute(
            select(SorRate).where(SorRate.is_active == True)
        ).scalars().all()

    data = {}
    for rate in rates:
        agency = rate.agency.value
        if agency not in data:
            data[agency] = []
        data[agency].append({
            "agency": agency,
            "code": rate.code,
            "description": rate.description,
            "unit": rate.unit,
            "zone_a": rate.zone_a,
            "zone_b": rate.zone_b,
            "zone_c": rate.zone_c,
            "zone_d": rate.zone_d,
            "normalized_code": rate.normalized_code,
        })
    return data
