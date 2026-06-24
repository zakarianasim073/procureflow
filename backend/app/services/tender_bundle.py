"""End-to-end tender bundle processing."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from app.core import helpers
from app.core.config import settings
from .boq_processor import BOQProcessor
from .tender_manager import tender_manager
from .template_filler import (
    fill_docx_template,
    fill_workbook_template,
    create_basic_work_plan,
    build_tender_values,
    create_pdf_text_docx,
)
from app.sor.sor_service import sor_service


@dataclass
class BundleArtifact:
    kind: str
    path: str
    filename: str


class TenderBundleProcessor:
    def __init__(self):
        self.boq_processor = BOQProcessor()

    def _save_upload(self, tender_id: str, doc_type: str, upload: UploadFile) -> str:
        ext = Path(upload.filename).suffix.lower() or ".bin"
        tdir = Path(settings.BASE_DIR) / "uploads" / tender_id
        tdir.mkdir(parents=True, exist_ok=True)
        dest = tdir / f"{doc_type}{ext}"
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        return str(dest)

    def _copy_with_suffix(self, src: str, dst_dir: Path, tender_id: str) -> str:
        src_path = Path(src)
        dst = dst_dir / f"{src_path.stem}_{tender_id}{src_path.suffix}"
        shutil.copy2(src_path, dst)
        return str(dst)

    async def process(
        self,
        notice: Optional[UploadFile] = None,
        tds: Optional[UploadFile] = None,
        tds_2: Optional[UploadFile] = None,
        boq: Optional[UploadFile] = None,
        sor: Optional[UploadFile] = None,
        docx_templates: Optional[List[UploadFile]] = None,
        xlsx_templates: Optional[List[UploadFile]] = None,
        tender_id: Optional[str] = None,
        sor_agency: str = "BWDB",
        zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        uploaded_paths: Dict[str, str] = {}

        for doc_type, file in [("notice", notice), ("tds", tds), ("tds_2", tds_2), ("boq", boq), ("sor", sor)]:
            if file is None:
                continue
            uploaded_paths[doc_type] = self._save_upload(tender_id or "incoming", doc_type, file)
            if not tender_id:
                stem = Path(file.filename or "").stem
                import re
                m = re.search(r"[_-](\d{5,})", stem)
                if m:
                    tender_id = m.group(1)

        if not tender_id:
            tender_id = "TENDER_" + datetime.now().strftime("%H%M%S")

        for doc_type, path in uploaded_paths.items():
            if doc_type in {"notice", "tds", "tds_2", "boq"}:
                tender_manager.store_document(tender_id, doc_type, path)

        try:
            variables = tender_manager.extract_variables(tender_id) or {}
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Variable extraction failed: {e}")
            variables = {"tender_id": tender_id}
        tender_values = build_tender_values({**variables, "tender_id": tender_id})

        if sor:
            sor_path = uploaded_paths.get("sor")
            if sor_path:
                sor_service.load_from_pdf(sor_agency, sor_path, zone)

        boq_path = uploaded_paths.get("boq")
        comparison = None
        if boq_path:
            comparison = await self.boq_processor.compare(
                boq_path=boq_path,
                sor_agency=sor_agency,
                zone=zone,
                sor_service=sor_service,
                tender_info={**variables, "tender_id": tender_id},
            )

        tender_dir = Path(settings.BASE_DIR) / "tenders" / tender_id
        tender_dir.mkdir(parents=True, exist_ok=True)
        output_dir = Path(settings.BASE_DIR) / "outputs" / tender_id
        output_dir.mkdir(parents=True, exist_ok=True)

        artifacts: List[BundleArtifact] = []
        filled_fields = {}
        validation_reports = {}

        for doc_type in ["notice", "tds", "tds_2", "boq"]:
            source_path = uploaded_paths.get(doc_type)
            if not source_path:
                continue
            try:
                text_docx = output_dir / f"{doc_type.upper()}_TextExtract_{tender_id}.docx"
                create_pdf_text_docx(source_path, str(text_docx), f"{doc_type.upper()} text extraction - {tender_id}")
                artifacts.append(BundleArtifact("pdf_text_docx", str(text_docx), text_docx.name))
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"PDF text extraction failed for {doc_type}: {e}")

        if docx_templates:
            for index, upload in enumerate(docx_templates, start=1):
                try:
                    template_path = self._save_upload(tender_id, f"template_{Path(upload.filename or 'template').stem}", upload)
                    uploaded_paths[f"docx_template_{index}"] = template_path
                    out_path = output_dir / f"{Path(upload.filename or 'template').stem}_{tender_id}.docx"
                    financial = variables.get("financial", {}) if isinstance(variables.get("financial", {}), dict) else {}
                    credit_amount = (
                        financial.get("min_liquid_assets_lakh")
                        or financial.get("min_tender_capacity_lakh")
                        or variables.get("estimated_cost")
                        or ""
                    )
                    result = fill_docx_template(template_path, str(out_path), {**variables, **tender_values}, extra={
                        "credit_line_amount": credit_amount,
                    })
                    filled_fields[Path(upload.filename or 'template').name] = result["fields"]
                    validation_reports[Path(upload.filename or 'template').name] = result.get("report", {})
                    artifacts.append(BundleArtifact("docx", str(out_path), out_path.name))
                    if result.get("report_path"):
                        report_path = Path(result["report_path"])
                        artifacts.append(BundleArtifact("validation", str(report_path), report_path.name))
                except Exception as e:
                    logging.getLogger(__name__).warning(f"DOCX template #{index} failed: {e}")

        if xlsx_templates:
            for index, upload in enumerate(xlsx_templates, start=1):
                try:
                    template_path = self._save_upload(tender_id, f"template_{Path(upload.filename or 'template').stem}", upload)
                    uploaded_paths[f"xlsx_template_{index}"] = template_path
                    out_path = output_dir / f"{Path(upload.filename or 'template').stem}_{tender_id}.xlsx"
                    result = fill_workbook_template(
                        template_path,
                        str(out_path),
                        {**variables, **tender_values},
                        boq_items=(comparison or {}).get("data", []),
                        sor_service=sor_service,
                        agency=sor_agency,
                        zone=zone,
                    )
                    filled_fields[Path(upload.filename or 'template').name] = result["fields"]
                    artifacts.append(BundleArtifact("xlsx", str(out_path), out_path.name))
                except Exception as e:
                    logging.getLogger(__name__).warning(f"XLSX template #{index} failed: {e}")

        if comparison:
            for key in ["excel_path", "docx_path"]:
                if comparison.get(key):
                    path = Path(comparison[key])
                    artifacts.append(BundleArtifact(key.replace("_path", ""), str(path), path.name))

        if not any(a.kind == "xlsx" for a in artifacts) and boq_path:
            try:
                workplan_out = output_dir / f"WorkPlan_{tender_id}.xlsx"
                create_basic_work_plan(str(workplan_out), {**variables, "tender_id": tender_id})
                artifacts.append(BundleArtifact("workplan", str(workplan_out), workplan_out.name))
            except Exception as e:
                logging.getLogger(__name__).warning(f"Work plan creation failed: {e}")

        manifest = {
            "tender_id": tender_id,
            "tender_info": variables,
            "filled_fields": filled_fields,
            "validation_reports": validation_reports,
            "uploaded_files": uploaded_paths,
            "artifacts": [a.__dict__ for a in artifacts],
            "comparison": comparison,
        }
        helpers.write_json(tender_dir / "manifest.json", manifest)

        bundle_dir = tender_dir / "_bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        for art in artifacts:
            src = Path(art.path)
            if src.exists():
                shutil.copy2(src, bundle_dir / src.name)
        if uploaded_paths:
            raw_dir = bundle_dir / "source_uploads"
            raw_dir.mkdir(parents=True, exist_ok=True)
            for src in uploaded_paths.values():
                sp = Path(src)
                if sp.exists():
                    shutil.copy2(sp, raw_dir / sp.name)
        helpers.write_json(bundle_dir / "manifest.json", manifest)

        zip_path = helpers.zip_dir(bundle_dir, tender_dir / f"{tender_id}_bundle.zip")

        return {
            "success": True,
            "tender_id": tender_id,
            "manifest": manifest,
            "bundle_zip": str(zip_path),
            "artifacts": [a.__dict__ for a in artifacts],
            "uploaded": uploaded_paths,
        }


    async def process_from_paths(
        self,
        tender_id: str,
        file_paths: Dict[str, str],
        docx_templates: Optional[List[str]] = None,
        xlsx_templates: Optional[List[str]] = None,
        sor_agency: str = "BWDB",
        zone: Optional[str] = None,
        agent_outputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a tender bundle from stored file paths (instead of UploadFile objects).
        Used by the Celery task and agent pipeline bridge.

        Args:
            tender_id: The tender ID
            file_paths: Dict like {"notice": "/path/to/notice.pdf", "boq": "/path/to/boq.xlsx", ...}
            docx_templates: List of paths to DOCX template files
            xlsx_templates: List of paths to XLSX template files
            sor_agency: SOR agency (default: BWDB)
            zone: Zone for SOR rates
            agent_outputs: Optional dict of agent outputs to enrich templates
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Processing bundle from paths for tender {tender_id}")

        tender_dir = Path(settings.BASE_DIR) / "tenders" / tender_id
        tender_dir.mkdir(parents=True, exist_ok=True)
        output_dir = Path(settings.BASE_DIR) / "outputs" / tender_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Store documents
        for doc_type in ["notice", "tds", "tds_2", "boq"]:
            path = file_paths.get(doc_type)
            if path and Path(path).exists():
                tender_manager.store_document(tender_id, doc_type, path)

        # Extract variables
        try:
            variables = tender_manager.extract_variables(tender_id) or {}
        except Exception as e:
            logger.warning(f"Variable extraction failed: {e}")
            variables = {"tender_id": tender_id}

        # Merge agent outputs into variables
        if agent_outputs:
            for aid, a_output in agent_outputs.items():
                if isinstance(a_output, dict):
                    for k, v in a_output.items():
                        if k not in variables and not isinstance(v, (dict, list)):
                            variables[k] = v

        tender_values = build_tender_values({**variables, "tender_id": tender_id})

        # Load SOR if provided
        sor_path = file_paths.get("sor")
        if sor_path and Path(sor_path).exists():
            sor_service.load_from_pdf(sor_agency, sor_path, zone)

        # BOQ comparison
        boq_path = file_paths.get("boq")
        comparison = None
        if boq_path and Path(boq_path).exists():
            comparison = await self.boq_processor.compare(
                boq_path=boq_path,
                sor_agency=sor_agency,
                zone=zone,
                sor_service=sor_service,
                tender_info={**variables, "tender_id": tender_id},
            )

        artifacts: List[BundleArtifact] = []
        filled_fields = {}
        validation_reports = {}

        # PDF text extraction
        for doc_type in ["notice", "tds", "tds_2", "boq"]:
            source_path = file_paths.get(doc_type)
            if not source_path or not Path(source_path).exists():
                continue
            try:
                text_docx = output_dir / f"{doc_type.upper()}_TextExtract_{tender_id}.docx"
                create_pdf_text_docx(source_path, str(text_docx), f"{doc_type.upper()} text extraction - {tender_id}")
                artifacts.append(BundleArtifact("pdf_text_docx", str(text_docx), text_docx.name))
            except Exception as e:
                logger.warning(f"PDF text extraction failed for {doc_type}: {e}")

        # DOCX templates
        if docx_templates:
            for idx, template_path in enumerate(docx_templates, start=1):
                tp = Path(template_path)
                if not tp.exists():
                    continue
                try:
                    stem = tp.stem
                    out_path = output_dir / f"{stem}_{tender_id}.docx"
                    financial = variables.get("financial", {}) if isinstance(variables.get("financial", {}), dict) else {}
                    credit_amount = (
                        financial.get("min_liquid_assets_lakh")
                        or financial.get("min_tender_capacity_lakh")
                        or variables.get("estimated_cost")
                        or ""
                    )
                    result = fill_docx_template(
                        str(tp), str(out_path),
                        {**variables, **tender_values},
                        extra={"credit_line_amount": credit_amount},
                    )
                    filled_fields[tp.name] = result["fields"]
                    validation_reports[tp.name] = result.get("report", {})
                    artifacts.append(BundleArtifact("docx", str(out_path), out_path.name))
                    if result.get("report_path"):
                        rp = Path(result["report_path"])
                        artifacts.append(BundleArtifact("validation", str(rp), rp.name))
                except Exception as e:
                    logger.warning(f"DOCX template #{idx} ({tp.name}) failed: {e}")

        # XLSX templates
        if xlsx_templates:
            for idx, template_path in enumerate(xlsx_templates, start=1):
                tp = Path(template_path)
                if not tp.exists():
                    continue
                try:
                    stem = tp.stem
                    out_path = output_dir / f"{stem}_{tender_id}.xlsx"
                    result = fill_workbook_template(
                        str(tp), str(out_path),
                        {**variables, **tender_values},
                        boq_items=(comparison or {}).get("data", []),
                        sor_service=sor_service,
                        agency=sor_agency,
                        zone=zone,
                    )
                    filled_fields[tp.name] = result["fields"]
                    artifacts.append(BundleArtifact("xlsx", str(out_path), out_path.name))
                except Exception as e:
                    logger.warning(f"XLSX template #{idx} ({tp.name}) failed: {e}")

        # Work plan fallback
        if not any(a.kind == "xlsx" for a in artifacts) and boq_path and Path(boq_path).exists():
            try:
                workplan_out = output_dir / f"WorkPlan_{tender_id}.xlsx"
                create_basic_work_plan(str(workplan_out), {**variables, "tender_id": tender_id})
                artifacts.append(BundleArtifact("workplan", str(workplan_out), workplan_out.name))
            except Exception as e:
                logger.warning(f"Work plan creation failed: {e}")

        # Manifest
        manifest = {
            "tender_id": tender_id,
            "tender_info": variables,
            "filled_fields": filled_fields,
            "validation_reports": validation_reports,
            "uploaded_files": file_paths,
            "artifacts": [a.__dict__ for a in artifacts],
            "agent_outputs": agent_outputs,
            "comparison": comparison,
        }
        helpers.write_json(tender_dir / "manifest.json", manifest)

        # Bundle directory
        bundle_dir = tender_dir / "_bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        for art in artifacts:
            src = Path(art.path)
            if src.exists():
                shutil.copy2(src, bundle_dir / src.name)

        helpers.write_json(bundle_dir / "manifest.json", manifest)

        zip_path = helpers.zip_dir(bundle_dir, tender_dir / f"{tender_id}_bundle.zip")

        return {
            "success": True,
            "tender_id": tender_id,
            "manifest": manifest,
            "bundle_zip": str(zip_path),
            "artifacts": [a.__dict__ for a in artifacts],
            "uploaded": file_paths,
        }


tender_bundle_processor = TenderBundleProcessor()
