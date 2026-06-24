"""Tender API routes"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List, Dict, Any
import uuid
import shutil
from pathlib import Path

from app.db.base import get_async_session
from app.models.tender import Tender, TenderDocument, DocumentType, TenderStatus
from app.models.user import User
from app.schemas.tender import TenderCreate, TenderRead, TenderUpdate, TenderDocumentRead
from app.core.config import settings
from app.core.security import get_optional_user
from app.api.v1.auth import ensure_owner_user

router = APIRouter(prefix="/tender", tags=["tenders"])


async def _resolve_owner_id(db: AsyncSession, user: Optional[dict]) -> str:
    if user and user.get("id") and user.get("id") != "guest":
        existing = await db.get(User, user["id"])
        if existing:
            return existing.id
    return (await ensure_owner_user(db)).id


async def _persist_bundle_result(
    db: AsyncSession,
    owner_id: str,
    tender_public_id: str,
    sor_agency: str,
    zone: Optional[str],
    result: Dict[str, Any],
) -> None:
    manifest = result.get("manifest") or {}
    tender_info = manifest.get("tender_info") or {}
    uploaded = result.get("uploaded") or {}

    stmt = select(Tender).where(Tender.tender_id == tender_public_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    title = str(
        tender_info.get("title")
        or tender_info.get("project_name")
        or tender_info.get("package_name")
        or f"Tender {tender_public_id}"
    )[:500]
    procuring_entity = str(
        tender_info.get("entity")
        or tender_info.get("procuring_entity")
        or tender_info.get("pe_office")
        or ""
    )[:255] or None

    comparison = manifest.get("comparison") or {}
    stored_payload = {
        "bundle_zip": result.get("bundle_zip"),
        "artifacts": result.get("artifacts", []),
        "uploaded": uploaded,
        "manifest": manifest,
        "comparison": comparison,
    }

    if existing is None:
        existing = Tender(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            tender_id=tender_public_id,
            title=title,
            procuring_entity=procuring_entity,
            estimated_cost=tender_info.get("estimated_cost"),
            tender_security=tender_info.get("tender_security"),
            status=TenderStatus.ACTIVE,
            sor_agency=sor_agency,
            zone=zone,
            extracted_data=tender_info,
            comparison_results=stored_payload,
        )
        db.add(existing)
        await db.flush()
    else:
        existing.owner_id = owner_id
        existing.title = title
        existing.procuring_entity = procuring_entity
        existing.estimated_cost = tender_info.get("estimated_cost")
        existing.tender_security = tender_info.get("tender_security")
        existing.status = TenderStatus.ACTIVE
        existing.sor_agency = sor_agency
        existing.zone = zone
        existing.extracted_data = tender_info
        existing.comparison_results = stored_payload
        await db.flush()

    existing_docs = (
        await db.execute(select(TenderDocument).where(TenderDocument.tender_id == existing.id))
    ).scalars().all()
    by_type = {doc.doc_type: doc for doc in existing_docs}

    doc_map = {
        "notice": DocumentType.NOTICE,
        "tds": DocumentType.TDS,
        "tds_2": DocumentType.TDS_2,
        "boq": DocumentType.BOQ,
        "sor": DocumentType.SOR,
    }
    for key, doc_type in doc_map.items():
        path = uploaded.get(key)
        if not path:
            continue
        file_path = Path(path)
        payload = {
            "filename": file_path.name,
            "file_path": str(file_path),
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "mime_type": None,
            "attributes": {"source": "bundle_upload"},
        }
        doc = by_type.get(doc_type)
        if doc is None:
            db.add(
                TenderDocument(
                    id=str(uuid.uuid4()),
                    tender_id=existing.id,
                    doc_type=doc_type,
                    **payload,
                )
            )
        else:
            doc.filename = payload["filename"]
            doc.file_path = payload["file_path"]
            doc.file_size = payload["file_size"]
            doc.mime_type = payload["mime_type"]
            doc.attributes = payload["attributes"]

    await db.commit()


@router.post("/upload", response_model=Dict[str, Any])
async def upload_tender_bundle(
    notice: Optional[UploadFile] = File(None),
    tds: Optional[UploadFile] = File(None),
    tds_2: Optional[UploadFile] = File(None),
    boq: Optional[UploadFile] = File(None),
    sor: Optional[UploadFile] = File(None),
    docx_templates: Optional[List[UploadFile]] = File(None),
    xlsx_templates: Optional[List[UploadFile]] = File(None),
    tender_id: Optional[str] = Query(None),
    sor_agency: str = Query("BWDB"),
    zone: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Process a full tender bundle and generate outputs in one call. No auth required."""
    from app.services.tender_bundle import tender_bundle_processor
    
    has_files = not all(v is None for v in [notice, tds, tds_2, boq, sor])
    has_templates = (docx_templates and len(docx_templates) > 0) or (xlsx_templates and len(xlsx_templates) > 0)
    if not has_files and not has_templates:
        raise HTTPException(status_code=400, detail="No files provided. Upload at least one document (notice, tds, boq, sor, or templates).")

    result = await tender_bundle_processor.process(
        notice=notice,
        tds=tds,
        tds_2=tds_2,
        boq=boq,
        sor=sor,
        docx_templates=docx_templates or [],
        xlsx_templates=xlsx_templates or [],
        tender_id=tender_id,
        sor_agency=sor_agency,
        zone=zone,
    )
    owner_id = await _resolve_owner_id(db, user)
    await _persist_bundle_result(
        db=db,
        owner_id=owner_id,
        tender_public_id=result["tender_id"],
        sor_agency=sor_agency,
        zone=zone,
        result=result,
    )
    return result


@router.get("/list")
async def list_tenders(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """List all tenders with document status."""
    from app.services.tender_manager import tender_manager
    tenders = tender_manager.list_tenders()
    return {"success": True, "tenders": tenders}


@router.get("/{tender_id}")
async def get_tender(
    tender_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get tender details including extracted variables."""
    from app.services.tender_manager import tender_manager
    variables = tender_manager.get_variables(tender_id)
    docs = {}
    for doc_type in ['notice', 'tds', 'tds_2', 'boq']:
        path = tender_manager.get_document_path(tender_id, doc_type)
        if path:
            docs[doc_type] = Path(path).name
    
    return {
        "success": True,
        "tender_id": tender_id,
        "documents": docs,
        "variables": variables,
    }


@router.post("/{tender_id}/extract")
async def extract_tender(
    tender_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """(Re)extract variable data from tender documents."""
    from app.services.tender_manager import tender_manager
    variables = tender_manager.extract_variables(tender_id)
    return {"success": True, "tender_id": tender_id, "extracted": variables}


@router.delete("/{tender_id}")
async def delete_tender(
    tender_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Delete a tender and all its documents."""
    from app.services.tender_manager import tender_manager
    ok = tender_manager.delete_tender(tender_id)
    return {"success": ok}


@router.get("/{tender_id}/document/{doc_type}")
async def get_tender_document(
    tender_id: str,
    doc_type: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Download a specific tender document."""
    from app.services.tender_manager import tender_manager
    path = tender_manager.get_document_path(tender_id, doc_type)
    if not path:
        raise HTTPException(status_code=404, detail=f"Document {doc_type} not found")
    return FileResponse(path, filename=Path(path).name)


@router.post("/scan-uploads")
async def scan_uploads(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Scan uploads folder for tender documents and organize them."""
    from app.services.tender_manager import tender_manager
    result = tender_manager.create_from_upload(f"{settings.BASE_DIR}/uploads")
    return {"success": True, **result}


@router.get("/{tender_id}/bundle")
async def download_tender_bundle(
    tender_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    base = (Path(settings.BASE_DIR) / "tenders").resolve()
    tender_dir = (base / tender_id).resolve()
    if not str(tender_dir).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid tender_id")
    zip_path = tender_dir / f"{tender_id}_bundle.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Bundle ZIP not found")
    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )


# DB-based endpoints
@router.post("/db", response_model=TenderRead)
async def create_tender_db(
    tender: TenderCreate,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Create a new tender in database"""
    db_tender = Tender(
        owner_id=user["id"],
        **tender.model_dump()
    )
    db.add(db_tender)
    await db.commit()
    await db.refresh(db_tender)
    return db_tender


@router.get("/db", response_model=List[TenderRead])
async def list_tenders_db(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """List tenders from database"""
    stmt = select(Tender).where(Tender.owner_id == user["id"]).order_by(desc(Tender.created_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/db/{tender_id}", response_model=TenderRead)
async def get_tender_db(
    tender_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get tender from database"""
    stmt = select(Tender).where(Tender.id == tender_id, Tender.owner_id == user["id"])
    result = await db.execute(stmt)
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    return tender
