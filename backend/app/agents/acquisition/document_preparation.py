"""
Document Preparation Agent — Tender Document Preparation & Contract Signing.
Automates the tender preparation workflow:

1. Extract required forms from "Contract Signing" tab
2. Map documents to form fields
3. Identify missing documents that could cause disqualification
4. Validate document completeness
5. Generate document preparation checklist
6. Feed data to Knowledge Lake for organizational memory

Key Features:
- Form extraction from e-GP document tabs
- Document-to-form-field mapping
- Completeness validation with critical/optional flags
- Missing document alerts
- Contract signing preparation
- Integration with Agent Brain
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# ── Standard forms required for Bangladesh e-GP tender submission ───────

TENDER_FORM_TEMPLATES = {
    "works": {
        "forms": [
            {"name": "notice_of_tender", "label": "Notice of Tender (NIT)", "critical": True},
            {"name": "tds_1", "label": "Tender Data Sheet (TDS-1)", "critical": True},
            {"name": "tds_2", "label": "Tender Data Sheet (TDS-2)", "critical": True},
            {"name": "boq", "label": "Bill of Quantities (BOQ)", "critical": True},
            {"name": "drawings", "label": "Drawings", "critical": True},
            {"name": "specifications", "label": "Technical Specifications", "critical": True},
            {"name": "bid_security_form", "label": "Bid Security Form", "critical": True},
            {"name": "bank_guarantee_form", "label": "Bank Guarantee Form", "critical": True},
            {"name": "contract_agreement", "label": "Contract Agreement Draft", "critical": True},
            {"name": "evaluation_criteria", "label": "Evaluation Criteria", "critical": False},
            {"name": "eligibility_criteria", "label": "Eligibility Criteria", "critical": True},
            {"name": "work_methodology", "label": "Work Methodology", "critical": False},
            {"name": "equipment_list", "label": "Equipment List Form", "critical": True},
            {"name": "personnel_schedule", "label": "Key Personnel Schedule", "critical": True},
            {"name": "price_schedule", "label": "Price Schedule", "critical": True},
        ],
        "contract_signing": {
            "forms": [
                {"name": "contract_signing_form", "label": "Contract Signing Form", "critical": True},
                {"name": "performance_guarantee", "label": "Performance Guarantee (BG)", "critical": True},
                {"name": "advance_payment_guarantee", "label": "Advance Payment Guarantee", "critical": True},
                {"name": "insurance_certificate", "label": "Insurance Certificate", "critical": True},
                {"name": "tax_clearance", "label": "Tax Clearance Certificate", "critical": True},
                {"name": "work_program", "label": "Work Program/Schedule", "critical": True},
                {"name": "mobilization_schedule", "label": "Mobilization Schedule", "critical": False},
                {"name": "safety_plan", "label": "Safety Plan", "critical": False},
            ],
        },
    },
    "goods": {
        "forms": [
            {"name": "notice_of_tender", "label": "Notice of Tender (NIT)", "critical": True},
            {"name": "tds_1", "label": "Tender Data Sheet (TDS-1)", "critical": True},
            {"name": "specifications", "label": "Technical Specifications", "critical": True},
            {"name": "bid_security_form", "label": "Bid Security Form", "critical": True},
            {"name": "manufacturer_auth", "label": "Manufacturer Authorization", "critical": True},
            {"name": "catalogue", "label": "Catalogue", "critical": False},
            {"name": "warranty_statement", "label": "Warranty Statement", "critical": True},
            {"name": "after_sales_service", "label": "After-Sales Service Commitment", "critical": False},
            {"name": "price_schedule", "label": "Price Schedule", "critical": True},
        ],
        "contract_signing": {
            "forms": [
                {"name": "contract_agreement", "label": "Contract Agreement", "critical": True},
                {"name": "performance_guarantee", "label": "Performance Guarantee", "critical": True},
                {"name": "insurance", "label": "Insurance", "critical": False},
            ],
        },
    },
    "services": {
        "forms": [
            {"name": "notice_of_tender", "label": "Notice of Tender (NIT)", "critical": True},
            {"name": "tds_1", "label": "Tender Data Sheet (TDS-1)", "critical": True},
            {"name": "specifications", "label": "Terms of Reference", "critical": True},
            {"name": "bid_security_form", "label": "Bid Security Form", "critical": True},
            {"name": "proposed_approach", "label": "Proposed Approach/Methodology", "critical": True},
            {"name": "team_cv", "label": "Team CVs", "critical": True},
            {"name": "similar_experience", "label": "Similar Experience Records", "critical": True},
            {"name": "quality_assurance", "label": "Quality Assurance Plan", "critical": False},
            {"name": "financial_capacity", "label": "Financial Capacity Statement", "critical": True},
        ],
        "contract_signing": {
            "forms": [
                {"name": "service_agreement", "label": "Service Agreement", "critical": True},
                {"name": "performance_guarantee", "label": "Performance Guarantee", "critical": True},
            ],
        },
    },
}


@dataclass
class DocumentMapping:
    """Mapping between form fields and source documents."""
    form_field: str = ""
    form_label: str = ""
    source_document: str = ""  # Document name in the tender docs
    source_doc_type: str = ""  # nit, tds, boq, drawing, etc.
    mapping_type: str = ""  # direct_extraction, manual_entry, ocr, calculation
    field_value: Any = None
    is_mapped: bool = False
    confidence: float = 0.0


@dataclass
class FormStatus:
    """Status of a single form."""
    form_name: str = ""
    form_label: str = ""
    is_completed: bool = False
    is_critical: bool = False
    mapping_status: str = "not_started"  # not_started, in_progress, completed, missing
    completeness_pct: float = 0.0
    fields_mapped: int = 0
    fields_total: int = 0
    missing_documents: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class TenderPreparationStatus:
    """Complete tender preparation status."""
    tender_id: str = ""
    tender_type: str = "works"
    
    # Forms tracking
    forms_required: List[FormStatus] = field(default_factory=list)
    forms_for_contract_signing: List[FormStatus] = field(default_factory=list)
    
    # Aggregated
    overall_completeness_pct: float = 0.0
    critical_forms_completed: int = 0
    critical_forms_total: int = 0
    missing_critical: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    
    # Document mappings
    document_mappings: List[DocumentMapping] = field(default_factory=list)
    
    # Preparation workflow
    preparation_status: str = "not_started"  # not_started, in_progress, completed
    contract_signing_status: str = "not_started"
    
    # Recommendations
    next_actions: List[str] = field(default_factory=list)
    critical_alerts: List[str] = field(default_factory=list)


class DocumentPreparationAgent(BaseAgent):
    agent_id = "agent-032-document-preparation"
    agent_name = "Document Preparation Agent"
    description = "Tender document preparation & contract signing workflow: form extraction, document mapping, completeness validation."
    dependencies: List[str] = ["agent-004-document-ai", "agent-002-tender-acquisition"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "")
        tender_info = context.get("tender_info", context.get("tender_data", {}))
        tender_type = tender_info.get("tender_type", tender_info.get("procurement_type", "works"))
        raw_docs = context.get("submitted_documents", context.get("documents", {}))
        submitted_documents = raw_docs if isinstance(raw_docs, dict) else {d: {} for d in raw_docs} if isinstance(raw_docs, list) else {}
        contract_signing_tab = context.get("contract_signing_data", context.get("contract_signing", {}))
        
        status = await self._prepare_tender(
            tender_id=tender_id,
            tender_type=tender_type,
            submitted_documents=submitted_documents,
            contract_signing_data=contract_signing_tab,
        )
        
        output = {
            "tender_id": status.tender_id,
            "overall_completeness_pct": status.overall_completeness_pct,
            "preparation_status": status.preparation_status,
            "contract_signing_status": status.contract_signing_status,
            "forms_required": [
                {
                    "name": f.form_name,
                    "label": f.form_label,
                    "completed": f.is_completed,
                    "critical": f.is_critical,
                    "completeness_pct": f.completeness_pct,
                    "missing_documents": f.missing_documents,
                }
                for f in status.forms_required
            ],
            "forms_contract_signing": [
                {
                    "name": f.form_name,
                    "label": f.form_label,
                    "completed": f.is_completed,
                    "critical": f.is_critical,
                }
                for f in status.forms_for_contract_signing
            ],
            "critical_forms": {
                "completed": status.critical_forms_completed,
                "total": status.critical_forms_total,
            },
            "missing_critical_documents": status.missing_critical,
            "missing_optional_documents": status.missing_optional,
            "document_mappings": [
                {
                    "form_field": m.form_field,
                    "source_document": m.source_document,
                    "is_mapped": m.is_mapped,
                    "confidence": m.confidence,
                }
                for m in status.document_mappings
            ],
            "next_actions": status.next_actions,
            "critical_alerts": status.critical_alerts,
        }
        
        # Share preparation status with Agent Brain
        await self.share_knowledge(
            entry_type="tender_preparation",
            tender_id=tender_id,
            data=output,
            summary=f"Preparation: {status.overall_completeness_pct:.0%} complete ({status.critical_forms_completed}/{status.critical_forms_total} critical forms)",
            tags=["preparation", "document", status.preparation_status],
        )
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _prepare_tender(
        self,
        tender_id: str,
        tender_type: str,
        submitted_documents: Dict[str, Any],
        contract_signing_data: Dict[str, Any],
    ) -> TenderPreparationStatus:
        """Full tender preparation workflow."""
        status = TenderPreparationStatus(
            tender_id=tender_id,
            tender_type=tender_type,
        )
        
        # Get templates for this type
        templates = TENDER_FORM_TEMPLATES.get(tender_type, TENDER_FORM_TEMPLATES["works"])
        
        # ── 1. Evaluate required forms ──
        for form_def in templates["forms"]:
            form_name = form_def["name"]
            form_doc = submitted_documents.get(form_name, {})
            
            # Check if document exists
            doc_exists = False
            if isinstance(submitted_documents, dict):
                if form_name in submitted_documents:
                    val = submitted_documents[form_name]
                    if isinstance(val, dict):
                        doc_exists = bool(val)
                    elif isinstance(val, bool):
                        doc_exists = val
                    elif isinstance(val, str):
                        doc_exists = bool(val.strip())
                    else:
                        doc_exists = val is not None
            
            f_status = FormStatus(
                form_name=form_name,
                form_label=form_def["label"],
                is_completed=doc_exists,
                is_critical=form_def["critical"],
                mapping_status="completed" if doc_exists else "missing",
                completeness_pct=100.0 if doc_exists else 0.0,
            )
            status.forms_required.append(f_status)
        
        # ── 2. Evaluate contract signing forms ──
        contract_signing_forms = templates.get("contract_signing", {}).get("forms", []) if isinstance(templates.get("contract_signing"), dict) else templates.get("contract_signing", [])
        for form_def in contract_signing_forms:
            form_name = form_def["name"]
            doc_exists = form_name in (contract_signing_data or {}) if isinstance(contract_signing_data, dict) else False
            
            f_status = FormStatus(
                form_name=form_name,
                form_label=form_def["label"],
                is_completed=doc_exists,
                is_critical=form_def["critical"],
                mapping_status="completed" if doc_exists else "missing",
            )
            status.forms_for_contract_signing.append(f_status)
        
        # ── 3. Calculate completeness ──
        all_forms = status.forms_required + status.forms_for_contract_signing
        completed = sum(1 for f in all_forms if f.is_completed)
        total = max(len(all_forms), 1)
        status.overall_completeness_pct = completed / total
        
        # Critical forms
        critical = [f for f in all_forms if f.is_critical]
        status.critical_forms_total = len(critical)
        status.critical_forms_completed = sum(1 for f in critical if f.is_completed)
        
        # Missing documents
        status.missing_critical = [
            f.form_label for f in status.forms_required
            if not f.is_completed and f.is_critical
        ]
        status.missing_optional = [
            f.form_label for f in status.forms_required
            if not f.is_completed and not f.is_critical
        ]
        
        # ── 4. Generate document mappings ──
        for form_def in templates["forms"]:
            dm = DocumentMapping(
                form_field=form_def["name"],
                form_label=form_def["label"],
                source_document=form_def["label"],
                is_mapped=form_def["name"] in (submitted_documents or {}),
                mapping_type="direct_extraction",
            )
            status.document_mappings.append(dm)
        
        # ── 5. Determine preparation status ──
        if status.critical_forms_completed == status.critical_forms_total and total == completed:
            status.preparation_status = "completed"
        elif status.critical_forms_completed > 0:
            status.preparation_status = "in_progress"
        else:
            status.preparation_status = "not_started"
        
        # Contract signing
        if status.forms_for_contract_signing:
            cs_completed = sum(1 for f in status.forms_for_contract_signing if f.is_completed)
            cs_total = len(status.forms_for_contract_signing)
            if cs_completed == cs_total:
                status.contract_signing_status = "completed"
            elif cs_completed > 0:
                status.contract_signing_status = "in_progress"
        
        # ── 6. Generate next actions and alerts ──
        if status.missing_critical:
            status.critical_alerts.append(
                f"MISSING CRITICAL DOCUMENTS: {', '.join(status.missing_critical)}. "
                "Submission may be disqualified."
            )
            status.next_actions.append(
                f"Submit missing critical documents: {', '.join(status.missing_critical)}"
            )
        
        if status.missing_optional:
            status.next_actions.append(
                f"Consider submitting optional documents: {', '.join(status.missing_optional)}"
            )
        
        if status.preparation_status == "completed":
            status.next_actions.append("All forms completed. Ready for submission.")
            if status.forms_for_contract_signing:
                missing_cs = [
                    f.form_label for f in status.forms_for_contract_signing
                    if not f.is_completed
                ]
                if missing_cs:
                    status.next_actions.append(
                        f"Prepare contract signing documents: {', '.join(missing_cs)}"
                    )
        
        if status.critical_forms_completed < status.critical_forms_total:
            pct = status.critical_forms_completed / max(status.critical_forms_total, 1) * 100
            status.next_actions.insert(
                0,
                f"Complete {status.critical_forms_total - status.critical_forms_completed} "
                f"missing critical forms ({pct:.0f}% complete)"
            )
        
        return status
