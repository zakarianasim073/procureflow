"""BOQ API routes"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from typing import Optional, Dict, Any, List
import uuid
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone

from app.db.base import get_async_session
from app.db.models import KnowledgeEntry
from app.models.boq import BOQComparison, BOQItem
from app.models.tender import Tender, TenderStatus
from app.models.user import User
from app.schemas.boq import BOQComparisonCreate, BOQComparisonRead
from app.core.config import settings
from app.core.security import get_optional_user, get_current_user

router = APIRouter(prefix="/boq", tags=["boq"])


async def _get_or_create_system_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == "system@procureflow.local"))
    system_user = result.scalar_one_or_none()
    if system_user:
        return system_user

    from app.core.security import hash_password

    system_user = User(
        id=str(uuid.uuid4()),
        email="system@procureflow.local",
        hashed_password=hash_password(settings.SYSTEM_USER_PASSWORD),
        full_name="System User",
        is_active=True,
        is_superuser=True,
    )
    db.add(system_user)
    await db.flush()
    return system_user


@router.post("/compare")
async def compare_boq(
    boq_file_id: str = Form(...),
    sor_agency: str = Form("BWDB"),
    zone: Optional[str] = Form(None),
    tender_info: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_session),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Compare BOQ against SOR rates. No auth required — saves results to database."""
    import json
    
    tender_info_dict = {}
    if tender_info:
        try:
            tender_info_dict = json.loads(tender_info)
        except Exception:
            pass

    # zone can be a plain string (e.g. "B") or a JSON dict keyed by agency
    zone_db_value = zone  # short string for DB column (VARCHAR(10))
    resolved_zone = zone
    if zone and zone.startswith("{"):
        try:
            resolved_zone = json.loads(zone)
            zone_db_value = ",".join(f"{k}={v}" for k, v in sorted(resolved_zone.items()))
        except:
            resolved_zone = zone
    
    upload_dir = Path(settings.BASE_DIR) / "uploads"
    boq_files = list(upload_dir.glob(f"{boq_file_id}.*"))
    if not boq_files:
        raise HTTPException(status_code=404, detail=f"BOQ file {boq_file_id} not found")
    
    boq_path = boq_files[0]
    
    # ── Lookup APP Estimated Cost by package number ──
    package_no = tender_info_dict.get("package_no", "")
    if not package_no and "title" in tender_info_dict:
        pkg_match = re.search(r"([A-Za-z]+-\d+[A-Za-z]?/[\d-]+)", tender_info_dict["title"])
        if pkg_match:
            package_no = pkg_match.group(1)
    estimated_cost_app = None
    if package_no:
        try:
            from app.models.intelligence import APPRecord as APPRec
            app_result = await db.execute(
                select(APPRec).where(APPRec.title.ilike(f"{package_no}%"))
                .order_by(APPRec.created_at.desc()).limit(1)
            )
            app_rec = app_result.scalar_one_or_none()
            if app_rec and app_rec.estimated_cost_bdt:
                estimated_cost_app = app_rec.estimated_cost_bdt
        except Exception:
            pass
    tender_info_dict["estimated_cost_app"] = estimated_cost_app

    # ── Extract TDS financial criteria if TDS PDF exists ──
    try:
        tender_id = tender_info_dict.get("tender_id", "")
        # Check both with and without /docs/ subdirectory
        tds_pdf = None
        for tds_dir_candidate in [
            upload_dir / str(tender_id) / "docs" / "Section2_Tender Data Sheet",
            upload_dir / str(tender_id) / "Section2_Tender Data Sheet",
        ]:
            if tds_dir_candidate.is_dir():
                for f in tds_dir_candidate.iterdir():
                    if f.suffix.lower() == ".pdf":
                        tds_pdf = f
                        break
            if tds_pdf:
                break

        if tds_pdf:
            import pdfplumber
            with pdfplumber.open(tds_pdf) as pdf:
                tds_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            import re as _re
            def _rx(p): return _re.search(p, tds_text, _re.I | _re.S)
            def _clean_val(v):
                """Extract numeric value from e-GP bracket format: [50,00,000] or [5500000] or 5500000"""
                v = v.strip().strip("[]()")
                v = v.replace(",", "")
                try:
                    return int(v)
                except ValueError:
                    return None

            criteria = {}
            # General Experience — e-GP format: "shall be [5] years"
            m = _rx(r"general experience.*?shall be\s*\[?(\d+)\]?\s*years?")
            if m: criteria["General Experience"] = f"{m.group(1)} years"

            # Specific Experience — e-GP format: "value of at least Tk. [50,00,000]"
            m = _rx(r"value of at least Tk\.?\s*\[?([\d,]+)\]?")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Specific Experience (min value)"] = f"Tk. {val:,}"

            # Avg Annual Turnover — e-GP format: "greater than Tk [55,00,000]"
            m = _rx(r"average annual construction turnover.*?greater than Tk\.?\s*\[?([\d,]+)\]?")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Avg Annual Turnover"] = f"Tk. {val:,}"

            # Liquid Assets / Working Capital — e-GP format: "shall be Tk [17,50,000"
            m = _rx(r"(?:financial resources|liquid asset|working capital|credit line).*?shall be Tk\.?\s*\[?([\d,]+)")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Liquid Assets / Credit Line"] = f"Tk. {val:,}"

            # Min Tender Capacity — e-GP format: "BDT [5500000]" or "minimum capacity shall be: BDT [5500000"
            m = _rx(r"(?:minimum tender capacity|minimum capacity shall be).*?(?:BDT|Tk)\.?\s*\[?([\d,]+)\]?")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Min Tender Capacity"] = f"BDT {val:,}"

            # Tender Security — e-GP format: "The amount of the Tender Security shall be as per tender notice"
            m = _rx(r"Tender Security.*?(?:amount.*?(?:Tk\.?\s*\[?([\d,]+)\]?|as per tender notice))")
            if m:
                if m.group(1):
                    val = _clean_val(m.group(1))
                    if val: criteria["Tender Security"] = f"Tk. {val:,}"
                else:
                    criteria["Tender Security"] = "As per tender notice"
            else:
                criteria["Tender Security"] = "As per tender notice"

            # Performance Security — e-GP format
            m = _rx(r"Performance Security shall(?:\s*not)?\s*be required")
            if m:
                criteria["Performance Security"] = "Not required"
            else:
                m = _rx(r"Performance Security.*?(?:rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent)")
                if m: criteria["Performance Security"] = f"{m.group(1)}% of contract price"

            # Retention Money — e-GP format
            m = _rx(r"retention.*?(?:(\d+)\s*%|at the rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent)")
            if m:
                pct = m.group(1) or m.group(2)
                if pct: criteria["Retention Money"] = f"{pct}% per certificate"

            financial_check = [
                {"criterion": k, "required": v, "our_figure": "", "remarks": "From TDS", "status": "PENDING"}
                for k, v in criteria.items()
            ]
            if financial_check:
                tender_info_dict["financial_check"] = financial_check
    except Exception:
        pass

    from app.services.boq_processor import BOQProcessor
    from app.sor.sor_service import sor_service
    processor = BOQProcessor()
    result = await processor.compare(
        boq_path=str(boq_path),
        sor_agency=sor_agency,
        zone=resolved_zone,
        sor_service=sor_service,
        tender_info=tender_info_dict,
    )
    
    result["comparison_id"] = boq_file_id
    result["sor_agency"] = "BWDB / PWD / LGED"
    result["zone"] = zone
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    
    # Resolve a stable owner for guest/demo mode so saved comparisons remain visible.
    user_id = user.get("id") if user and user.get("id") and user.get("id") != "guest" else None
    if user_id:
        existing_user = await db.get(User, user_id)
        if existing_user is None:
            user_id = None
    if not user_id:
        user_id = (await _get_or_create_system_user(db)).id

    tender_public_id = str(
        tender_info_dict.get("tender_id")
        or tender_info_dict.get("package_no")
        or boq_file_id
    ).strip()
    tender_title = str(
        tender_info_dict.get("title")
        or tender_info_dict.get("entity")
        or boq_path.stem
    ).strip() or f"BOQ Analysis {boq_file_id}"
    procuring_entity = str(tender_info_dict.get("entity") or sor_agency).strip() or sor_agency

    tender_result = await db.execute(select(Tender).where(Tender.tender_id == tender_public_id))
    tender = tender_result.scalar_one_or_none()
    if tender is None:
        tender = Tender(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            tender_id=tender_public_id,
            title=tender_title[:500],
            procuring_entity=procuring_entity[:255],
            status=TenderStatus.ACTIVE,
            sor_agency="BWDB / PWD / LGED",
            zone=zone_db_value,
            extracted_data=tender_info_dict,
            comparison_results=result,
        )
        db.add(tender)
        await db.flush()
    else:
        tender.owner_id = user_id
        tender.title = tender_title[:500]
        tender.procuring_entity = procuring_entity[:255]
        tender.status = TenderStatus.ACTIVE
        tender.sor_agency = "BWDB / PWD / LGED"
        tender.zone = zone_db_value
        tender.extracted_data = tender_info_dict
        tender.comparison_results = result
        await db.flush()

    await db.execute(delete(BOQItem).where(BOQItem.tender_id == tender.id))

    for item in result.get("data", []) or []:
        db.add(
            BOQItem(
                id=str(uuid.uuid4()),
                tender_id=tender.id,
                item_no=str(item.get("item_no") or "")[:50] or None,
                code=str(item.get("code") or "")[:100] or None,
                description=str(item.get("description") or item.get("desc") or "")[:1000] or "BOQ item",
                unit=str(item.get("unit") or "")[:50] or None,
                quantity=float(item.get("qty") or 0) if item.get("qty") not in (None, "") else None,
                quoted_rate=float(item.get("rate") or 0) if item.get("rate") not in (None, "") else None,
                sor_rate=float(item.get("sor_rate") or 0) if item.get("sor_rate") not in (None, "") else None,
                sor_code=str(item.get("sor_code") or item.get("code") or "")[:100] or None,
                diff=float(item.get("diff") or 0) if item.get("diff") not in (None, "") else None,
                pct_diff=float(item.get("pct_diff") or 0) if item.get("pct_diff") not in (None, "") else None,
                flag=str(item.get("flag") or "")[:50] or None,
                work_type=str(item.get("work_type") or "")[:100] or None,
                agency=str(item.get("agency") or "BWDB / PWD / LGED")[:20],
                attributes={
                    "raw_item": item,
                },
            )
        )

    # Save comparison to PostgreSQL database
    comparison = BOQComparison(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tender_id=tender.id,
        boq_file_id=boq_file_id,
        sor_agency="BWDB / PWD / LGED",
        zone=zone_db_value,
        total_items=result.get("total_items", 0),
        matches=result.get("matches", 0),
        variances=result.get("variances", 0),
        mismatches=result.get("mismatches", 0),
        below_sor=result.get("below_sor", 0),
        total_sor_amount=result.get("summary", {}).get("total_sor", 0.0),
        total_quoted_amount=result.get("summary", {}).get("total_quoted", 0.0),
        discount_pct=result.get("summary", {}).get("discount_pct", 0.0),
        summary_by_work_type=result.get("summary", {}).get("by_work_type", {}),
        excel_path=result.get("excel_path"),
        docx_path=result.get("docx_path"),
        tenderai_dir=result.get("tenderai_dir"),
    )
    db.add(comparison)
    await db.commit()
    
    return {
        **result,
        "financial_check": tender_info_dict.get("financial_check", []),
        "estimated_cost_app": tender_info_dict.get("estimated_cost_app"),
    }


@router.post("/brain-compare")
async def brain_compare_boq(
    tender_id: str = Form(...),
    sor_agency: str = Form("BWDB"),
    zone: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_session),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Compare BOQ against SOR rates using brain knowledge entries (no file upload needed)."""
    import json

    # ── Resolve zone ──
    zone_db_value = zone
    resolved_zone = zone
    if zone and zone.startswith("{"):
        try:
            resolved_zone = json.loads(zone)
            zone_db_value = ",".join(f"{k}={v}" for k, v in sorted(resolved_zone.items()))
        except:
            resolved_zone = zone

    # ── Query brain knowledge entries ──
    doc_entry = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.entry_type == "tender_document",
            KnowledgeEntry.tender_id == tender_id,
        ).order_by(KnowledgeEntry.created_at.desc()).limit(1)
    )
    doc_entry = doc_entry.scalar_one_or_none()
    if not doc_entry:
        raise HTTPException(status_code=404, detail=f"No tender_document knowledge found for tender {tender_id}")

    boq_entry = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.entry_type == "boq_text",
            KnowledgeEntry.tender_id == tender_id,
        ).order_by(KnowledgeEntry.created_at.desc()).limit(1)
    )
    boq_entry = boq_entry.scalar_one_or_none()

    tds_entry = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.entry_type == "tds_text",
            KnowledgeEntry.tender_id == tender_id,
        ).order_by(KnowledgeEntry.created_at.desc()).limit(1)
    )
    tds_entry = tds_entry.scalar_one_or_none()

    # ── Build tender_info from brain knowledge ──
    doc_data = doc_entry.data or {}
    tender_info = doc_data.get("tender_info", {})
    tender_info_dict = dict(tender_info) if tender_info else {}
    tender_info_dict.setdefault("tender_id", tender_id)
    tender_info_dict.setdefault("title", doc_data.get("title") or doc_entry.title or "")
    tender_info_dict.setdefault("entity", tender_info_dict.get("procuring_entity") or doc_data.get("procuring_entity", ""))
    package_no = tender_info_dict.get("package_no") or doc_data.get("package_no") or ""
    tender_info_dict["package_no"] = package_no

    # ── Find BOQ PDF from downloaded_files in brain knowledge ──
    downloaded_files = doc_data.get("downloaded_files", []) or []
    boq_pdf = None
    for f in downloaded_files:
        fp = f.get("path", "")
        kind = (f.get("kind") or f.get("doc_type") or "").lower()
        fname_lower = Path(fp).name.lower() + " " + str(fp).lower()
        if "boq" in kind or "bill" in kind or "quantity" in kind or "section6" in fname_lower:
            if Path(fp).exists():
                boq_pdf = fp
                break

    if not boq_pdf:
        storage_dir = doc_data.get("storage_dir") or doc_data.get("download_path") or ""
        if storage_dir and Path(storage_dir).is_dir():
            for f in Path(storage_dir).rglob("*.pdf"):
                fname = f.name.lower()
                if "boq" in fname or "bill" in fname or "quantity" in fname or "section6" in fname:
                    boq_pdf = str(f)
                    break

    if not boq_pdf:
        raise HTTPException(status_code=404, detail=f"BOQ PDF not found in brain knowledge for tender {tender_id}")

    # ── Lookup APP Estimated Cost by package number ──
    estimated_cost_app = None
    if package_no:
        try:
            from app.models.intelligence import APPRecord as APPRec
            app_result = await db.execute(
                select(APPRec).where(APPRec.title.ilike(f"{package_no}%"))
                .order_by(APPRec.created_at.desc()).limit(1)
            )
            app_rec = app_result.scalar_one_or_none()
            if app_rec and app_rec.estimated_cost_bdt:
                estimated_cost_app = app_rec.estimated_cost_bdt
        except Exception:
            pass
    tender_info_dict["estimated_cost_app"] = estimated_cost_app

    # ── Extract TDS financial criteria from brain knowledge ──
    tds_text = (tds_entry.data or {}).get("text", "") if tds_entry else ""
    if tds_text:
        try:
            import re as _re
            def _rx(p): return _re.search(p, tds_text, _re.I | _re.S)
            def _clean_val(v):
                v = v.strip().strip("[]()")
                v = v.replace(",", "")
                try:
                    return int(v)
                except ValueError:
                    return None

            criteria = {}
            m = _rx(r"general experience.*?shall be\s*\[?(\d+)\]?\s*years?")
            if m: criteria["General Experience"] = f"{m.group(1)} years"

            m = _rx(r"value of at least Tk\.?\s*\[?([\d,]+)\]?")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Specific Experience (min value)"] = f"Tk. {val:,}"

            m = _rx(r"average annual construction turnover.*?greater than Tk\.?\s*\[?([\d,]+)\]?")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Avg Annual Turnover"] = f"Tk. {val:,}"

            m = _rx(r"(?:financial resources|liquid asset|working capital|credit line).*?shall be Tk\.?\s*\[?([\d,]+)")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Liquid Assets / Credit Line"] = f"Tk. {val:,}"

            m = _rx(r"(?:minimum tender capacity|minimum capacity shall be).*?(?:BDT|Tk)\.?\s*\[?([\d,]+)\]?")
            if m:
                val = _clean_val(m.group(1))
                if val: criteria["Min Tender Capacity"] = f"BDT {val:,}"

            m = _rx(r"Tender Security.*?(?:amount.*?(?:Tk\.?\s*\[?([\d,]+)\]?|as per tender notice))")
            if m:
                if m.group(1):
                    val = _clean_val(m.group(1))
                    if val: criteria["Tender Security"] = f"Tk. {val:,}"
                else:
                    criteria["Tender Security"] = "As per tender notice"
            else:
                criteria["Tender Security"] = "As per tender notice"

            m = _rx(r"Performance Security shall(?:\s*not)?\s*be required")
            if m:
                criteria["Performance Security"] = "Not required"
            else:
                m = _rx(r"Performance Security.*?(?:rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent)")
                if m: criteria["Performance Security"] = f"{m.group(1)}% of contract price"

            m = _rx(r"retention.*?(?:(\d+)\s*%|at the rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent)")
            if m:
                pct = m.group(1) or m.group(2)
                if pct: criteria["Retention Money"] = f"{pct}% per certificate"

            financial_check = [
                {"criterion": k, "required": v, "our_figure": "", "remarks": "From TDS", "status": "PENDING"}
                for k, v in criteria.items()
            ]
            if financial_check:
                tender_info_dict["financial_check"] = financial_check
        except Exception:
            pass

    # ── Run BOQ comparison ──
    from app.services.boq_processor import BOQProcessor
    from app.sor.sor_service import sor_service
    processor = BOQProcessor()
    result = await processor.compare(
        boq_path=str(boq_pdf),
        sor_agency=sor_agency,
        zone=resolved_zone,
        sor_service=sor_service,
        tender_info=tender_info_dict,
    )

    result["comparison_id"] = f"brain-{tender_id}"
    result["sor_agency"] = "BWDB / PWD / LGED"
    result["zone"] = zone
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    result["source"] = "brain"

    # ── Resolve user ──
    user_id = user.get("id") if user and user.get("id") and user.get("id") != "guest" else None
    if user_id:
        existing_user = await db.get(User, user_id)
        if existing_user is None:
            user_id = None
    if not user_id:
        user_id = (await _get_or_create_system_user(db)).id

    tender_public_id = tender_id
    tender_title = str(
        tender_info_dict.get("title")
        or doc_data.get("title")
        or f"BOQ from brain {tender_id}"
    ).strip() or f"BOQ Analysis {tender_id}"
    procuring_entity = str(
        tender_info_dict.get("entity")
        or tender_info_dict.get("procuring_entity")
        or sor_agency
    ).strip() or sor_agency

    # ── Save tender ──
    tender_result = await db.execute(select(Tender).where(Tender.tender_id == tender_public_id))
    tender = tender_result.scalar_one_or_none()
    if tender is None:
        tender = Tender(
            id=str(uuid.uuid4()),
            owner_id=user_id,
            tender_id=tender_public_id,
            title=tender_title[:500],
            procuring_entity=procuring_entity[:255],
            status=TenderStatus.ACTIVE,
            sor_agency="BWDB / PWD / LGED",
            zone=zone_db_value,
            extracted_data=tender_info_dict,
            comparison_results=result,
        )
        db.add(tender)
        await db.flush()
    else:
        tender.owner_id = user_id
        tender.title = tender_title[:500]
        tender.procuring_entity = procuring_entity[:255]
        tender.status = TenderStatus.ACTIVE
        tender.sor_agency = "BWDB / PWD / LGED"
        tender.zone = zone_db_value
        tender.extracted_data = tender_info_dict
        tender.comparison_results = result
        await db.flush()

    # ── Save BOQ items ──
    await db.execute(delete(BOQItem).where(BOQItem.tender_id == tender.id))
    for item in result.get("data", []) or []:
        db.add(
            BOQItem(
                id=str(uuid.uuid4()),
                tender_id=tender.id,
                item_no=str(item.get("item_no") or "")[:50] or None,
                code=str(item.get("code") or "")[:100] or None,
                description=str(item.get("description") or item.get("desc") or "")[:1000] or "BOQ item",
                unit=str(item.get("unit") or "")[:50] or None,
                quantity=float(item.get("qty") or 0) if item.get("qty") not in (None, "") else None,
                quoted_rate=float(item.get("rate") or 0) if item.get("rate") not in (None, "") else None,
                sor_rate=float(item.get("sor_rate") or 0) if item.get("sor_rate") not in (None, "") else None,
                sor_code=str(item.get("sor_code") or item.get("code") or "")[:100] or None,
                diff=float(item.get("diff") or 0) if item.get("diff") not in (None, "") else None,
                pct_diff=float(item.get("pct_diff") or 0) if item.get("pct_diff") not in (None, "") else None,
                flag=str(item.get("flag") or "")[:50] or None,
                work_type=str(item.get("work_type") or "")[:100] or None,
                agency=str(item.get("agency") or "BWDB / PWD / LGED")[:20],
                attributes={"raw_item": item},
            )
        )

    # ── Save BOQ comparison ──
    comparison = BOQComparison(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tender_id=tender.id,
        boq_file_id=f"brain-{tender_id}",
        sor_agency="BWDB / PWD / LGED",
        zone=zone_db_value,
        total_items=result.get("total_items", 0),
        matches=result.get("matches", 0),
        variances=result.get("variances", 0),
        mismatches=result.get("mismatches", 0),
        below_sor=result.get("below_sor", 0),
        total_sor_amount=result.get("summary", {}).get("total_sor", 0.0),
        total_quoted_amount=result.get("summary", {}).get("total_quoted", 0.0),
        discount_pct=result.get("summary", {}).get("discount_pct", 0.0),
        summary_by_work_type=result.get("summary", {}).get("by_work_type", {}),
        excel_path=result.get("excel_path"),
        docx_path=result.get("docx_path"),
        tenderai_dir=result.get("tenderai_dir"),
    )
    db.add(comparison)
    await db.commit()

    return {
        **result,
        "financial_check": tender_info_dict.get("financial_check", []),
        "estimated_cost_app": tender_info_dict.get("estimated_cost_app"),
        "tender_notice": {
            "tender_id": tender_id,
            "title": tender_title,
            "procuring_entity": procuring_entity,
            "package_no": package_no,
            "downloaded_files": len(downloaded_files),
            "has_boq_text": boq_entry is not None,
            "has_tds_text": tds_entry is not None,
        },
    }


@router.post("/upload")
async def upload_boq(
    file: UploadFile = File(...),
    file_type: str = Form("boq"),
):
    """Upload BOQ file (PDF or Excel). No auth required."""
    try:
        ext = Path(file.filename).suffix.lower() if file.filename else ".xlsx"
        fid = str(uuid.uuid4())[:8]
        dest = Path(settings.BASE_DIR) / "uploads" / f"{fid}{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"success": True, "file_id": fid, "filename": file.filename, "file_type": ext[1:]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/export/{file_id}")
async def export_comparison(
    file_id: str,
    format: str = Query("xlsx", pattern="^(xlsx|docx)$"),
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Export comparison result as Excel or DOCX"""
    # Find the comparison in database
    from sqlalchemy import select
    stmt = select(BOQComparison).where(BOQComparison.boq_file_id == file_id)
    result = await db.execute(stmt)
    comparison = result.scalar_one_or_none()
    
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")
    
    file_path = comparison.excel_path if format == "xlsx" else comparison.docx_path
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"{format.upper()} file not found")
    
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" 
                   else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=Path(file_path).name
    )


@router.get("/latest")
async def get_latest_comparison(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Return the latest saved comparison with BOQ item rows for dashboard/results recovery."""
    stmt = select(BOQComparison).order_by(BOQComparison.created_at.desc())
    if user and user.get("id") and user.get("id") != "guest":
        stmt = stmt.where(BOQComparison.user_id == user["id"])
    result = await db.execute(stmt.limit(1))
    comparison = result.scalar_one_or_none()
    if comparison is None:
        raise HTTPException(status_code=404, detail="No saved comparison found")

    item_rows: List[BOQItem] = []
    if comparison.tender_id:
        items_result = await db.execute(
            select(BOQItem)
            .where(BOQItem.tender_id == comparison.tender_id)
            .order_by(BOQItem.created_at.asc())
        )
        item_rows = list(items_result.scalars().all())

    # Get financial check and APP estimate from related tender
    financial_check = []
    estimated_cost_app = None
    if comparison.tender_id:
        tender_result = await db.execute(
            select(Tender).where(Tender.id == comparison.tender_id)
        )
        tender = tender_result.scalar_one_or_none()
        if tender and tender.extracted_data:
            financial_check = tender.extracted_data.get("financial_check", [])
            estimated_cost_app = tender.extracted_data.get("estimated_cost_app")

    return {
        "success": True,
        "comparison_id": comparison.id,
        "boq_file_id": comparison.boq_file_id,
        "sor_agency": comparison.sor_agency,
        "zone": comparison.zone,
        "data": [
            {
                "item_no": item.item_no or "",
                "code": item.code or "",
                "agency": item.agency or comparison.sor_agency,
                "work_type": item.work_type or "",
                "desc": item.description or "",
                "unit": item.unit or "",
                "qty": item.quantity,
                "rate": item.quoted_rate,
                "sor_rate": item.sor_rate,
                "sor_source": item.sor_code,
                "diff": item.diff,
                "pct_diff": item.pct_diff,
                "flag": item.flag or "",
                "section": item.section or "",
            }
            for item in item_rows
        ],
        "summary": {
            "by_work_type": comparison.summary_by_work_type or [],
            "total_sor": comparison.total_sor_amount or 0.0,
            "total_quoted": comparison.total_quoted_amount or 0.0,
            "discount_pct": comparison.discount_pct or 0.0,
        },
        "flagged": [],
        "total_items": comparison.total_items,
        "mismatches": comparison.mismatches,
        "variances": comparison.variances,
        "matches": comparison.matches,
        "below_sor": comparison.below_sor,
        "excel_path": comparison.excel_path,
        "docx_path": comparison.docx_path,
        "tenderai_dir": comparison.tenderai_dir,
        "created_at": comparison.created_at.isoformat(),
        "financial_check": financial_check,
        "estimated_cost_app": estimated_cost_app,
    }


@router.get("/history", response_model=List[BOQComparisonRead])
async def get_comparison_history(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Get user's BOQ comparison history"""
    from sqlalchemy import select, desc
    stmt = select(BOQComparison).where(BOQComparison.user_id == user["id"]).order_by(desc(BOQComparison.created_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{comparison_id}", response_model=BOQComparisonRead)
async def get_comparison(
    comparison_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Get specific comparison details"""
    from sqlalchemy import select
    stmt = select(BOQComparison).where(BOQComparison.id == comparison_id, BOQComparison.user_id == user["id"])
    result = await db.execute(stmt)
    comparison = result.scalar_one_or_none()
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comparison
