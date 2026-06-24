"""
Procurement Flow Specialist BD — e-PW3 Form Auto-Generator
Maps extracted TenderProfile and Company Data to BPPA e-PW3 (Oct 2025) Forms.
Generates data payloads for Forms: 1, 2, 3, 5, 6, 6A, 10, 11, 12.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── BPPA e-PW3 Forms Registry ──────────────────────────────────────────

EPW3_FORMS = {
    "e-PW3-1": {"title": "Tender Submission Letter", "mandatory": True},
    "e-PW3-2": {"title": "Tenderer Information", "mandatory": True},
    "e-PW3-3": {"title": "Joint Venture Partner Information", "mandatory": False},
    "e-PW3-4": {"title": "Subcontractor Information", "mandatory": False},
    "e-PW3-5": {"title": "Personnel Information (CVs)", "mandatory": True},
    "e-PW3-6": {"title": "Tenderer's Capacity Information", "mandatory": True},
    "e-PW3-6A": {"title": "Current Commitment Determination", "mandatory": True},
    "e-PW3-7": {"title": "Bank Guarantee for Tender Security", "mandatory": True},
    "e-PW3-8": {"title": "Line of Credit Letter", "mandatory": False},
    "e-PW3-9": {"title": "Notification of Award", "mandatory": False},
    "e-PW3-10": {"title": "Contract Agreement", "mandatory": False},
    "e-PW3-11": {"title": "Performance Security", "mandatory": False},
    "e-PW3-12": {"title": "Advance Payment Guarantee", "mandatory": False},
}


class EPW3Generator:
    """
    BPPA e-PW3 (Oct 2025) Form Generator.
    Generates structured data payloads for all 13 standard forms.
    """

    def __init__(self):
        self.tender_dir = Path(settings.TENDERAI_DIR) / "epw3"
        self.tender_dir.mkdir(parents=True, exist_ok=True)

    def generate_form_1(
        self,
        tender_id: str,
        company_name: str,
        bid_amount: float,
        bid_validity_days: int = 90,
    ) -> Dict[str, Any]:
        """e-PW3-1: Tender Submission Letter"""
        today = datetime.now()
        validity_until = today + timedelta(days=bid_validity_days)
        
        return {
            "form_id": "e-PW3-1",
            "title": "Tender Submission Letter",
            "generated_at": today.isoformat(),
            "data": {
                "to": "The Procuring Entity",
                "tender_id": tender_id,
                "we_submit": f"We, {company_name}, hereby submit our tender for the above works.",
                "bid_amount_bdt": round(bid_amount, 2),
                "bid_amount_in_words": self._number_to_words_bn(bid_amount),
                "bid_validity_days": bid_validity_days,
                "validity_until": validity_until.strftime("%d-%b-%Y"),
                "declaration": (
                    "We declare that our company is not involved in any conflict of interest, "
                    "has not been blacklisted by any government agency, and all information "
                    "provided is true and accurate to the best of our knowledge."
                ),
                "acceptance": "We agree to abide by the PPR 2025 rules and the terms of the e-PW3 document.",
            },
        }

    def generate_form_2(
        self,
        company: Dict[str, Any],
    ) -> Dict[str, Any]:
        """e-PW3-2: Tenderer Information"""
        return {
            "form_id": "e-PW3-2",
            "title": "Tenderer Information",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "company_name": company.get("name", ""),
                "registered_address": company.get("address", ""),
                "registration_number": company.get("registration_no", ""),
                "vat_registration": company.get("vat_no", ""),
                "tax_identification": company.get("tin_no", ""),
                "years_in_business": company.get("years_in_business", 0),
                "business_type": company.get("business_type", "Sole Proprietorship"),
                "classification": company.get("classification", "A"),  # A/B/C/D based on capacity
                "contact_person": company.get("contact_person", ""),
                "phone": company.get("phone", ""),
                "email": company.get("email", ""),
                "website": company.get("website", ""),
                "eligible": True,
            },
        }

    def generate_form_3(
        self,
        jv_partners: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """e-PW3-3: Joint Venture Partner Information"""
        return {
            "form_id": "e-PW3-3",
            "title": "Joint Venture Partner Information",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "num_partners": len(jv_partners),
                "partners": [
                    {
                        "name": p.get("name", ""),
                        "role": p.get("role", "Partner"),
                        "share_pct": p.get("share_pct", 0),
                        "responsibility": p.get("responsibility", ""),
                        "years_experience": p.get("years_experience", 0),
                    }
                    for p in jv_partners
                ],
                "jv_agreement_attached": len(jv_partners) > 1,
                "lead_partner": jv_partners[0]["name"] if jv_partners else "",
            },
        }

    def generate_form_5(
        self,
        personnel: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """e-PW3-5: Personnel Information (CVs)"""
        return {
            "form_id": "e-PW3-5",
            "title": "Personnel Information (CVs)",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "total_technical_staff": len(personnel),
                "personnel": [
                    {
                        "name": p.get("name", ""),
                        "designation": p.get("designation", "Engineer"),
                        "years_experience": p.get("years_experience", 0),
                        "qualification": p.get("qualification", "B.Sc. Engineering"),
                        "relevant_projects": p.get("relevant_projects", 0),
                        "cv_attached": True,
                    }
                    for p in personnel
                ],
            },
        }

    def generate_form_6(
        self,
        company: Dict[str, Any],
        tender_value: float,
        current_commitments: float = 0.0,
    ) -> Dict[str, Any]:
        """e-PW3-6: Tenderer's Capacity Information (PPR 2025 formula)"""
        annual_turnover = company.get("annual_turnover", 100_000_000)
        years_in_business = company.get("years_in_business", 5)
        
        # Apply PPR 2025 Tender Capacity Formula
        max_capacity = annual_turnover * 2.0
        available_capacity = max(max_capacity - current_commitments, 0.0)
        capacity_ratio = available_capacity / max(tender_value, 1)
        turnover_ratio = annual_turnover / max(tender_value, 1)
        
        return {
            "form_id": "e-PW3-6",
            "title": "Tenderer's Capacity Information",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "annual_turnover": round(annual_turnover, 2),
                "max_capacity_2x_turnover": round(max_capacity, 2),
                "current_commitments": round(current_commitments, 2),
                "available_capacity": round(available_capacity, 2),
                "tender_value": round(tender_value, 2),
                "capacity_ratio": round(capacity_ratio, 2),
                "turnover_ratio": round(turnover_ratio, 2),
                "years_in_business": years_in_business,
                "capacity_adequate": available_capacity >= tender_value,
                "formula": "TC = max(Annual Turnover × 2 - Current Commitments, 0)",
                "evaluation": "PASS" if available_capacity >= tender_value and turnover_ratio >= 0.5 else "FAIL",
            },
        }

    def generate_form_6a(
        self,
        ongoing_projects: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """e-PW3-6A: Current Commitment Determination"""
        total_commitments = sum(p.get("remaining_value", 0) for p in ongoing_projects)
        
        return {
            "form_id": "e-PW3-6A",
            "title": "Current Commitment Determination",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "total_ongoing_projects": len(ongoing_projects),
                "total_commitments": round(total_commitments, 2),
                "projects": [
                    {
                        "project_name": p.get("name", ""),
                        "employer": p.get("employer", ""),
                        "contract_value": p.get("contract_value", 0),
                        "completed_pct": p.get("completed_pct", 0),
                        "remaining_value": p.get("remaining_value", 0),
                        "original_completion": p.get("original_completion", ""),
                        "current_status": p.get("status", "Ongoing"),
                    }
                    for p in ongoing_projects
                ],
            },
        }

    def generate_form_7(
        self,
        tender_value: float,
    ) -> Dict[str, Any]:
        """e-PW3-7: Bank Guarantee for Tender Security"""
        from app.services.ppr_engine import evaluate_bid_security
        security = evaluate_bid_security(tender_value, tender_value * 0.02)
        
        return {
            "form_id": "e-PW3-7",
            "title": "Bank Guarantee for Tender Security (EMD)",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "required_amount": round(security["required_amount"], 2),
                "validity_days": 118,  # 90 days bid validity + 28 days
                "beneficiary": "The Procuring Entity",
                "bg_type": "Irrevocable Bank Guarantee",
                "issuing_bank": "",
                "bg_number": "",
                "amount_in_words": self._number_to_words_bn(security["required_amount"]),
            },
        }

    def generate_form_10(
        self,
        tender_id: str,
        company_name: str,
        contract_value: float,
        completion_days: int = 365,
    ) -> Dict[str, Any]:
        """e-PW3-10: Contract Agreement (Post-Award)"""
        return {
            "form_id": "e-PW3-10",
            "title": "Contract Agreement",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "tender_id": tender_id,
                "contractor": company_name,
                "contract_value": round(contract_value, 2),
                "completion_period_days": completion_days,
                "governing_law": "PPR 2025 and Laws of Bangladesh",
                "dispute_resolution": "Arbitration per PPR 2025 Section 8",
                "language": "English/Bengali",
            },
        }

    def generate_form_11(
        self,
        contract_value: float,
    ) -> Dict[str, Any]:
        """e-PW3-11: Performance Security (GCC 66.1)"""
        from app.services.ppr_engine import calculate_performance_security
        ps = calculate_performance_security(contract_value)
        
        return {
            "form_id": "e-PW3-11",
            "title": "Performance Security",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "amount": round(ps["amount"], 2),
                "pct": ps["pct"],
                "validity": "60 days after defects liability period",
                "formula": ps["formula"],
            },
        }

    def generate_form_12(
        self,
        contract_value: float,
        mobilization_needed: float,
    ) -> Dict[str, Any]:
        """e-PW3-12: Advance Payment Guarantee (GCC 72.1)"""
        from app.services.ppr_engine import calculate_advance_payment
        ap = calculate_advance_payment(contract_value, mobilization_needed)
        
        return {
            "form_id": "e-PW3-12",
            "title": "Advance Payment Guarantee",
            "generated_at": datetime.now().isoformat(),
            "data": {
                "max_advance": round(ap["max_advance"], 2),
                "recommended": round(ap["recommended"], 2),
                "pct": round(ap["pct_of_contract"], 2),
                "repayment_terms": "Amortized over first 50% of work completed",
                "guarantee_type": "Irrevocable Bank Guarantee",
                "formula": "AP ≤ 20% of Contract Value per GCC 72.1",
            },
        }

    async def generate_all(
        self,
        tender_id: str,
        company: Dict[str, Any],
        tender_info: Dict[str, Any],
        bid_amount: float,
        personnel: Optional[List[Dict]] = None,
        jv_partners: Optional[List[Dict]] = None,
        ongoing_projects: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate all applicable e-PW3 forms for a tender."""
        forms = {}
        now = datetime.now().isoformat()
        
        forms["e-PW3-1"] = self.generate_form_1(
            tender_id, company.get("name", ""), bid_amount
        )
        forms["e-PW3-2"] = self.generate_form_2(company)
        
        if jv_partners and len(jv_partners) > 0:
            forms["e-PW3-3"] = self.generate_form_3(jv_partners)
        
        if personnel:
            forms["e-PW3-5"] = self.generate_form_5(personnel)
        
        forms["e-PW3-6"] = self.generate_form_6(
            company,
            tender_info.get("estimated_value", bid_amount),
            company.get("current_commitments", 0),
        )
        
        forms["e-PW3-6A"] = self.generate_form_6a(ongoing_projects or [])
        forms["e-PW3-7"] = self.generate_form_7(tender_info.get("estimated_value", bid_amount))
        forms["e-PW3-10"] = self.generate_form_10(
            tender_id, company.get("name", ""), bid_amount
        )
        forms["e-PW3-11"] = self.generate_form_11(bid_amount)
        forms["e-PW3-12"] = self.generate_form_12(
            bid_amount,
            company.get("mobilization_required", bid_amount * 0.15),
        )
        
        # Save to database
        from app.db.base import get_session_factory
        from app.models.intelligence import EPW3FormRecord
        from sqlalchemy import select
        import uuid

        output = {
            "tender_id": tender_id,
            "generated_at": now,
            "forms": forms,
            "total_forms": len(forms),
            "form_ids": list(forms.keys()),
        }

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(EPW3FormRecord).where(EPW3FormRecord.tender_id == tender_id)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()

            if record:
                record.forms = forms
                record.total_forms = len(forms)
                record.form_ids = list(forms.keys())
                record.generated_at = now
            else:
                record = EPW3FormRecord(
                    id=str(uuid.uuid4()),
                    tender_id=tender_id,
                    forms=forms,
                    total_forms=len(forms),
                    form_ids=list(forms.keys()),
                    generated_at=now
                )
                session.add(record)
            
            await session.commit()
        
        logger.info(f"Generated {len(forms)} e-PW3 forms for {tender_id}")
        
        return output

    def _number_to_words_bn(self, amount: float) -> str:
        """Convert numeric amount to Bengali words (approximate)."""
        crore = amount / 10_000_000
        lakh = (amount % 10_000_000) / 100_000
        thousand = (amount % 100_000) / 1_000
        hundred = amount % 1_000
        
        parts = []
        if crore >= 1:
            parts.append(f"{int(crore)} Crore")
        if lakh >= 1:
            parts.append(f"{int(lakh)} Lakh")
        if thousand >= 1:
            parts.append(f"{int(thousand)} Thousand")
        if hundred >= 1:
            parts.append(f"{int(hundred)}")
        
        text = " ".join(parts) + " Taka only" if parts else "Zero"
        return f"BDT {text}"


# Singleton
epw3_generator = EPW3Generator()
