from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import get_session_factory  # noqa: E402
from app.models.intelligence import APPRecord, AwardRecordV2, ProcurementTender  # noqa: E402
from app.services.intelligence_data_service import IntelligenceDataService  # noqa: E402
from sqlalchemy import select  # noqa: E402


EXPORT_DIR = ROOT / "runtime" / "canonical_exports"


def row_to_payload(row) -> dict:
    payload = {}
    for col in row.__table__.columns:
        value = getattr(row, col.name)
        if hasattr(value, "isoformat"):
            try:
                value = value.isoformat()
            except TypeError:
                pass
        payload[col.name] = value
    return payload


async def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    session_factory = get_session_factory()

    async with session_factory() as session:
        svc = IntelligenceDataService(session)

        app_rows = (
            await session.execute(
                select(ProcurementTender, APPRecord).join(APPRecord, APPRecord.procurement_tender_id == ProcurementTender.id)
            )
        ).all()
        app_payloads = []
        app_tender_ids = set()
        for tender, app_record in app_rows:
            app_tender_ids.add(tender.id)
            app_payloads.append(
                {
                    "procurement_tender_id": tender.id,
                    "package_no": tender.package_no,
                    "source_tender_id": app_record.source_tender_id,
                    "title": app_record.title or tender.title,
                    "estimated_cost_bdt": app_record.estimated_cost_bdt,
                    "status": app_record.status,
                    "published_date": app_record.published_date,
                    "deadline": app_record.deadline,
                    "financial_year": app_record.financial_year,
                    "app_code": app_record.app_code,
                    "category": app_record.category,
                    "agency_code": tender.agency_code,
                    "pe_office": tender.pe_office,
                    "procurement_method": tender.procurement_method,
                    "match_type": tender.match_type,
                }
            )

        raw_awards = (await session.execute(select(AwardRecordV2))).scalars().all()
        canonical_awards, dedup_stats = svc._deduplicate_awards(raw_awards, app_tender_ids)
        canonical_award_payloads = []
        canonical_match_summary = []
        app_by_tender_id = {tender.id: tender for tender, _ in app_rows}
        app_record_by_tender_id = {app_record.procurement_tender_id: app_record for _, app_record in app_rows}

        for award in canonical_awards:
            canonical_award_payloads.append(
                {
                    "procurement_tender_id": award.procurement_tender_id,
                    "source_tender_id": award.source_tender_id,
                    "package_no": award.package_no,
                    "title": award.title,
                    "contractor_name": award.contractor_name,
                    "amount_bdt": award.amount_bdt,
                    "procurement_method": award.procurement_method,
                    "award_date": award.award_date,
                    "detail_url": award.detail_url,
                    "agency_code": award.agency_code,
                    "district": award.district,
                    "pe_office": award.pe_office,
                }
            )

            tender = app_by_tender_id.get(award.procurement_tender_id)
            app_record = app_record_by_tender_id.get(award.procurement_tender_id)
            if tender and app_record:
                canonical_match_summary.append(
                    {
                        "award_ref": award.source_tender_id or award.package_no,
                        "award_package_no": award.package_no,
                        "award_source_tender_id": award.source_tender_id,
                        "app_ref": tender.package_no,
                        "app_package_no": tender.package_no,
                        "app_source_tender_id": app_record.source_tender_id,
                        "match_type": tender.match_type or "package_exact",
                    }
                )

        (EXPORT_DIR / "canonical_app_records.json").write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "canonical_app_records": app_payloads,
                    "count": len(app_payloads),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (EXPORT_DIR / "canonical_awards.json").write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "canonical_awards": canonical_award_payloads,
                    "count": len(canonical_award_payloads),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (EXPORT_DIR / "canonical_match_summary.json").write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "canonical_match_summary": canonical_match_summary,
                    "count": len(canonical_match_summary),
                    "metrics": dedup_stats,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "export_dir": str(EXPORT_DIR),
                "canonical_awards": len(canonical_award_payloads),
                "canonical_app_records": len(app_payloads),
                "canonical_match_summary": len(canonical_match_summary),
                "metrics": dedup_stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
