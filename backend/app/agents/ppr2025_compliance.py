"""
Agent 31 — PPR 2025 Compliance Agent
Validates vendor/contractor compliance with Bangladesh Public Procurement Rules 2025,
including Schedule 4/5/6 TEC evaluation, document checklist, and eligibility criteria.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# ── PPR 2025 Schedule Mappings ──────────────────────────────────────────

# Schedule 4: TEC for Goods — specification compliance, delivery, warranty
SCHEDULE_4_MARKS = {
    "specification_compliance": 40,
    "delivery_schedule": 25,
    "warranty": 15,
    "after_sales_service": 10,
    "past_performance": 10,
}

# Schedule 5: TEC for Works — experience, equipment, personnel, methodology
SCHEDULE_5_MARKS = {
    "general_experience": 15,
    "specific_experience": 25,
    "equipment": 15,
    "personnel": 20,
    "methodology": 15,
    "safety_compliance": 5,
    "environmental_compliance": 5,
}

# Schedule 6: TEC for Services — similar experience, team, approach
SCHEDULE_6_MARKS = {
    "similar_experience": 30,
    "team_qualifications": 20,
    "proposed_approach": 20,
    "local_knowledge": 15,
    "quality_assurance": 10,
    "resource_availability": 5,
}

# Minimum pass marks for each schedule (typically 70%)
TEC_MINIMUM_PASS_PCT = 0.70

# ── Required document categories per tender type ───────────────────────

REQUIRED_DOCS_BY_TYPE = {
    "goods": [
        "bid_security",
        "manufacturer_authorization",
        "catalogue_specifications",
        "bidder_declaration",
        "vat_tax_certificate",
        "trade_license",
    ],
    "works": [
        "bid_security",
        "trade_license",
        "vat_tax_certificate",
        "income_tax_certificate",
        "experience_certificate",
        "similar_contract_completion",
        "equipment_list",
        "key_personnel_cv",
        "work_methodology",
        "financial_capacity_statement",
        "bank_guarantee_form",
    ],
    "services": [
        "bid_security",
        "trade_license",
        "vat_tax_certificate",
        "income_tax_certificate",
        "company_profile",
        "team_cv",
        "similar_experience",
        "proposed_approach",
        "financial_capacity",
        "quality_certification",
    ],
}


@dataclass
class ComplianceCheck:
    """Individual compliance check result."""
    check_name: str
    passed: bool
    score: float = 0.0
    max_score: float = 0.0
    details: str = ""
    recommendation: str = ""


@dataclass
class ScheduleResult:
    """TEC Schedule evaluation result."""
    schedule_label: str  # "Schedule 4 (Goods)" | "Schedule 5 (Works)" | "Schedule 6 (Services)"
    criteria: List[ComplianceCheck] = field(default_factory=list)
    total_marks: float = 0.0
    max_marks: float = 0.0
    percentage: float = 0.0
    passed: bool = False


@dataclass
class PPR2025ComplianceReport:
    """Full compliance report output."""
    overall_score: float = 0.0
    overall_passed: bool = False
    schedule: Optional[ScheduleResult] = None
    document_checks: List[ComplianceCheck] = field(default_factory=list)
    document_passed: bool = False
    document_score: float = 0.0
    eligibility_checks: List[ComplianceCheck] = field(default_factory=list)
    eligibility_passed: bool = False
    eligibility_score: float = 0.0
    all_checks: List[ComplianceCheck] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    total_checks: int = 0
    recommendations: List[str] = field(default_factory=list)
    vendor_name: str = ""
    tender_id: str = ""
    tender_type: str = ""


class PPR2025ComplianceAgent(BaseAgent):
    agent_id = "agent-031-ppr2025-compliance"
    agent_name = "PPR 2025 Compliance Agent"
    description = "Validates vendor/contractor compliance with Bangladesh Public Procurement Rules 2025, including Schedule 4/5/6 TEC evaluation, document checklist, and eligibility criteria."
    dependencies: List[str] = ["agent-007-eligibility-compliance"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_info = context.get("tender_info", {})
        submitted_docs = context.get("submitted_docs", {})
        vendor_profile = context.get("vendor_profile", {})
        upstream = context.get("upstream", {})

        eligibility_upstream = upstream.get("agent-007-eligibility-compliance", {})

        report = await self._build_compliance_report(
            tender_info, submitted_docs, vendor_profile, eligibility_upstream,
        )

        output = {
            "overall_score": report.overall_score,
            "overall_passed": report.overall_passed,
            "vendor_name": report.vendor_name,
            "tender_id": report.tender_id,
            "tender_type": report.tender_type,
            "summary": {
                "total_checks": report.total_checks,
                "passed": report.passed_count,
                "failed": report.failed_count,
                "pass_rate": f"{report.overall_score:.1%}",
            },
            "schedule_evaluation": {
                "schedule_label": report.schedule.schedule_label if report.schedule else None,
                "criteria": [
                    {"name": c.check_name, "passed": c.passed, "score": c.score,
                     "max_score": c.max_score, "details": c.details}
                    for c in (report.schedule.criteria if report.schedule else [])
                ],
                "total_marks": report.schedule.total_marks if report.schedule else 0,
                "max_marks": report.schedule.max_marks if report.schedule else 0,
                "percentage": report.schedule.percentage if report.schedule else 0.0,
                "passed": report.schedule.passed if report.schedule else False,
            },
            "document_checks": [
                {"name": c.check_name, "passed": c.passed, "details": c.details,
                 "recommendation": c.recommendation}
                for c in report.document_checks
            ],
            "document_passed": report.document_passed,
            "document_score": report.document_score,
            "eligibility_checks": [
                {"name": c.check_name, "passed": c.passed, "details": c.details,
                 "recommendation": c.recommendation}
                for c in report.eligibility_checks
            ],
            "eligibility_passed": report.eligibility_passed,
            "eligibility_score": report.eligibility_score,
            "all_checks": [
                {"name": c.check_name, "passed": c.passed, "score": c.score,
                 "max_score": c.max_score, "details": c.details,
                 "recommendation": c.recommendation}
                for c in report.all_checks
            ],
            "recommendations": report.recommendations,
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _build_compliance_report(
        self,
        tender_info: Dict,
        submitted_docs: Dict,
        vendor_profile: Dict,
        eligibility_upstream: Dict,
    ) -> PPR2025ComplianceReport:
        report = PPR2025ComplianceReport()
        report.vendor_name = vendor_profile.get("name", vendor_profile.get("company_name", "Unknown"))
        report.tender_id = tender_info.get("tender_id", tender_info.get("id", ""))
        report.tender_type = self._detect_tender_type(tender_info)

        # 1. Schedule 4/5/6 TEC marks evaluation
        schedule = self._evaluate_schedule_tec(tender_info, vendor_profile, report.tender_type)
        report.schedule = schedule
        report.all_checks.extend(schedule.criteria)

        # 2. Document checklist completeness
        doc_checks, doc_passed, doc_score = self._check_document_completeness(
            submitted_docs, report.tender_type,
        )
        report.document_checks = doc_checks
        report.document_passed = doc_passed
        report.document_score = doc_score
        report.all_checks.extend(doc_checks)

        # 3. Eligibility criteria compliance (from upstream + vendor_profile)
        elig_checks, elig_passed, elig_score = self._check_eligibility_criteria(
            vendor_profile, eligibility_upstream,
        )
        report.eligibility_checks = elig_checks
        report.eligibility_passed = elig_passed
        report.eligibility_score = elig_score
        report.all_checks.extend(elig_checks)

        # 4. Aggregate
        report.passed_count = sum(1 for c in report.all_checks if c.passed)
        report.failed_count = sum(1 for c in report.all_checks if not c.passed)
        report.total_checks = len(report.all_checks)

        report.overall_score = (
            sum(c.score for c in report.all_checks) /
            max(sum(c.max_score for c in report.all_checks), 1)
        )
        report.overall_passed = report.overall_score >= TEC_MINIMUM_PASS_PCT

        # 5. Recommendations
        report.recommendations = self._generate_recommendations(report)

        return report

    def _detect_tender_type(self, tender_info: Dict) -> str:
        """Detect tender type from tender info — defaults to 'works'."""
        raw = str(tender_info.get("type", "") or tender_info.get("category", "") or "works")
        raw_lower = raw.lower()
        for t in ("goods", "works", "services"):
            if t in raw_lower:
                return t
        return "works"

    # ── Schedule 4/5/6 TEC Evaluation ──────────────────────────────────

    def _evaluate_schedule_tec(self, tender_info: Dict, vendor: Dict, tender_type: str) -> ScheduleResult:
        """Evaluate TEC marks allocation per PPR 2025 Schedule rules."""
        schedule_map = {
            "goods": ("Schedule 4 (Goods)", SCHEDULE_4_MARKS),
            "works": ("Schedule 5 (Works)", SCHEDULE_5_MARKS),
            "services": ("Schedule 6 (Services)", SCHEDULE_6_MARKS),
        }

        label, criteria_weights = schedule_map.get(tender_type, schedule_map["works"])

        if tender_type == "goods":
            criteria = self._eval_schedule_4(tender_info, vendor)
        elif tender_type == "services":
            criteria = self._eval_schedule_6(tender_info, vendor)
        else:
            criteria = self._eval_schedule_5(tender_info, vendor)

        total_marks = sum(c.score for c in criteria)
        max_marks = sum(c.max_score for c in criteria)
        percentage = total_marks / max(max_marks, 1)
        passed = percentage >= TEC_MINIMUM_PASS_PCT

        return ScheduleResult(
            schedule_label=label,
            criteria=criteria,
            total_marks=total_marks,
            max_marks=max_marks,
            percentage=percentage,
            passed=passed,
        )

    def _eval_schedule_4(self, tender_info: Dict, vendor: Dict) -> List[ComplianceCheck]:
        """Schedule 4: TEC for Goods."""
        spec_score = self._score_spec_compliance(tender_info, vendor)
        delivery_score = self._score_bool_field(vendor, "delivery_schedule_committed", "Delivery schedule committed")
        warranty_score = self._score_bool_field(vendor, "warranty_provided", "Warranty provided")
        after_sales_score = self._score_bool_field(vendor, "after_sales_service_committed", "After-sales service committed")
        perf_score = self._score_past_performance(vendor)

        return [
            ComplianceCheck("Specification Compliance", spec_score >= 30, spec_score, 40,
                            self._spec_detail(tender_info, vendor), "Ensure all technical specs are met per tender SOR"),
            ComplianceCheck("Delivery Schedule", delivery_score >= 20, delivery_score, 25,
                            "Delivery schedule commitment verified", "Confirm delivery lead time aligns with NIT"),
            ComplianceCheck("Warranty", warranty_score >= 12, warranty_score, 15,
                            "Warranty terms reviewed", "Verify warranty period meets minimum requirements"),
            ComplianceCheck("After-Sales Service", after_sales_score >= 8, after_sales_score, 10,
                            "Service support commitment reviewed", "Ensure service centre presence in project area"),
            ComplianceCheck("Past Performance", perf_score >= 8, perf_score, 10,
                            "Past performance history evaluated", "Provide reference letters from previous clients"),
        ]

    def _eval_schedule_5(self, tender_info: Dict, vendor: Dict) -> List[ComplianceCheck]:
        """Schedule 5: TEC for Works."""
        gen_exp = self._score_general_experience(vendor)
        spec_exp = self._score_specific_experience(tender_info, vendor)
        equipment = self._score_equipment(tender_info, vendor)
        personnel = self._score_personnel(vendor)
        methodology = self._score_methodology(vendor)
        safety = self._score_bool_field(vendor, "safety_plan_provided", "Safety plan provided", max_val=5)
        env = self._score_bool_field(vendor, "environmental_plan_provided", "Environmental plan provided", max_val=5)

        return [
            ComplianceCheck("General Experience", gen_exp >= 12, gen_exp, 15,
                            f"{vendor.get('years_experience', 0)} years in construction sector",
                            "Minimum 5 years general experience required"),
            ComplianceCheck("Specific Experience", spec_exp >= 18, spec_exp, 25,
                            f"{vendor.get('similar_contracts', 0)} similar contracts completed",
                            "At least 1 similar contract of comparable size required"),
            ComplianceCheck("Equipment", equipment >= 10, equipment, 15,
                            self._equipment_detail(vendor),
                            "Own or lease-commit key construction equipment"),
            ComplianceCheck("Personnel", personnel >= 15, personnel, 20,
                            f"{vendor.get('engineers_count', 0)} engineers available",
                            "Minimum 5 qualified engineers including Project Manager"),
            ComplianceCheck("Methodology", methodology >= 10, methodology, 15,
                            "Work methodology and execution plan reviewed",
                            "Submit detailed work methodology with bar chart / CPM schedule"),
            ComplianceCheck("Safety Compliance", safety >= 4, safety, 5,
                            "Safety plan reviewed" if vendor.get("safety_plan_provided") else "Safety plan not found",
                            "Submit OHS plan per Bangladesh Labor Law"),
            ComplianceCheck("Environmental Compliance", env >= 4, env, 5,
                            "Environmental plan reviewed" if vendor.get("environmental_plan_provided") else "Environmental plan not found",
                            "Submit environmental management plan per DoE guidelines"),
        ]

    def _eval_schedule_6(self, tender_info: Dict, vendor: Dict) -> List[ComplianceCheck]:
        """Schedule 6: TEC for Services."""
        sim_exp = self._score_similar_experience_services(vendor)
        team = self._score_team_qualifications(vendor)
        approach = self._score_methodology(vendor)
        local = self._score_bool_field(vendor, "local_knowledge_demonstrated", "Local knowledge demonstrated", max_val=15)
        qa = self._score_bool_field(vendor, "quality_certification", "Quality certification held", max_val=10)
        resource = self._score_bool_field(vendor, "resource_availability_confirmed", "Resource availability confirmed", max_val=5)

        return [
            ComplianceCheck("Similar Experience", sim_exp >= 22, sim_exp, 30,
                            f"{vendor.get('similar_contracts', 0)} similar service contracts",
                            "Minimum 2 similar service contracts required"),
            ComplianceCheck("Team Qualifications", team >= 15, team, 20,
                            f"Key personnel: {vendor.get('engineers_count', 0)} qualified staff",
                            "Team must include qualified professionals with relevant certifications"),
            ComplianceCheck("Proposed Approach", approach >= 10, approach, 20,
                            "Technical approach and methodology evaluated",
                            "Submit detailed approach, work plan, and quality control measures"),
            ComplianceCheck("Local Knowledge", local >= 10, local, 15,
                            "Local market knowledge assessed",
                            "Demonstrate understanding of local conditions and regulations"),
            ComplianceCheck("Quality Assurance", qa >= 7, qa, 10,
                            "QMS certification reviewed" if vendor.get("quality_certification") else "No quality certification found",
                            "ISO 9001 or equivalent quality certification preferred"),
            ComplianceCheck("Resource Availability", resource >= 4, resource, 5,
                            "Resource commitment confirmed" if vendor.get("resource_availability_confirmed") else "Resource availability not confirmed",
                            "Confirm staff and infrastructure availability for project duration"),
        ]

    # ── Scoring Helpers ────────────────────────────────────────────────

    def _score_spec_compliance(self, tender_info: Dict, vendor: Dict) -> float:
        """Score specification compliance out of 40."""
        submitted_specs = set(vendor.get("specifications_met", vendor.get("offered_specs", [])))
        required_specs = set(tender_info.get("required_specifications", tender_info.get("specifications", [])))
        if not required_specs:
            return 35  # default high score if no specs listed
        matched = len(submitted_specs & required_specs)
        total = len(required_specs)
        ratio = matched / max(total, 1)
        return round(ratio * 40, 1)

    def _score_delivery_schedule(self, vendor: Dict) -> float:
        """Score delivery schedule commitment out of 25."""
        if vendor.get("delivery_schedule_committed"):
            offered_days = vendor.get("delivery_days", 0)
            required_days = vendor.get("required_delivery_days", 0)
            if required_days and offered_days <= required_days:
                return 25
            elif offered_days <= required_days * 1.2:
                return 20
            return 15
        return 0

    def _score_general_experience(self, vendor: Dict) -> float:
        years = vendor.get("years_experience", 0)
        if years >= 15:
            return 15
        elif years >= 10:
            return 12
        elif years >= 5:
            return 10
        elif years >= 3:
            return 8
        return max(years * 1.5, 0)

    def _score_specific_experience(self, tender_info: Dict, vendor: Dict) -> float:
        similar = vendor.get("similar_contracts", 0)
        value_ratio = vendor.get("similar_contract_value_ratio", 0)
        score = min(similar * 8, 20)
        if value_ratio >= 0.8:
            score += 5
        elif value_ratio >= 0.5:
            score += 3
        return min(score, 25)

    def _score_equipment(self, tender_info: Dict, vendor: Dict) -> float:
        company_equipment = set(vendor.get("equipment", vendor.get("equipment_list", [])))
        required_equipment = set(tender_info.get("required_equipment", []))
        if not required_equipment:
            return 12  # default if no specific equipment listed
        matched = len(company_equipment & required_equipment)
        total = len(required_equipment)
        ratio = matched / max(total, 1)
        return round(ratio * 15, 1)

    def _score_personnel(self, vendor: Dict) -> float:
        engineers = vendor.get("engineers_count", 0)
        tech_staff = vendor.get("technical_staff_count", 0)
        score = min(engineers * 3, 12)
        score += min(tech_staff * 1.5, 8)
        return min(score, 20)

    def _score_methodology(self, vendor: Dict) -> float:
        if vendor.get("methodology_provided") or vendor.get("work_plan_provided") or vendor.get("approach_provided"):
            quality = vendor.get("methodology_quality", vendor.get("approach_quality", 0.7))
            return round(quality * 15, 1)
        return 0

    def _score_past_performance(self, vendor: Dict) -> float:
        rating = vendor.get("past_performance_rating", vendor.get("performance_rating", 0.8))
        return round(rating * 10, 1)

    def _score_similar_experience_services(self, vendor: Dict) -> float:
        similar = vendor.get("similar_contracts", 0)
        if similar >= 5:
            return 30
        elif similar >= 3:
            return 25
        elif similar >= 2:
            return 22
        elif similar >= 1:
            return 18
        return max(similar * 10, 0)

    def _score_team_qualifications(self, vendor: Dict) -> float:
        engineers = vendor.get("engineers_count", 0)
        certifications = len(vendor.get("certifications", vendor.get("professional_certifications", [])))
        score = min(engineers * 2, 10)
        score += min(certifications * 2, 10)
        return min(score, 20)

    def _score_bool_field(self, vendor: Dict, field: str, label: str, max_val: float = 0) -> float:
        """Score a boolean/flag field — returns max_val if true, 0 if false."""
        if max_val == 0:
            max_val = SCHEDULE_5_MARKS.get(field, 0) or SCHEDULE_4_MARKS.get(field, 0) or SCHEDULE_6_MARKS.get(field, 0) or 10
        return float(max_val) if vendor.get(field) else 0.0

    def _spec_detail(self, tender_info: Dict, vendor: Dict) -> str:
        submitted = vendor.get("specifications_met", vendor.get("offered_specs", []))
        required = tender_info.get("required_specifications", tender_info.get("specifications", []))
        if not required:
            return "All specifications accepted (none explicitly required in tender)"
        missing = set(required) - set(submitted)
        if not missing:
            return "All required specifications met"
        return f"Missing specifications: {', '.join(list(missing)[:5])}"

    def _equipment_detail(self, vendor: Dict) -> str:
        eq = vendor.get("equipment", vendor.get("equipment_list", []))
        return f"Equipment available: {', '.join(eq[:8])}" if eq else "No equipment list provided"

    # ── Document Checklist ─────────────────────────────────────────────

    def _check_document_completeness(
        self, submitted_docs: Dict, tender_type: str,
    ) -> Tuple[List[ComplianceCheck], bool, float]:
        required = REQUIRED_DOCS_BY_TYPE.get(tender_type, REQUIRED_DOCS_BY_TYPE["works"])
        checks: List[ComplianceCheck] = []
        passed = 0

        submitted_set = set(k.lower() for k in submitted_docs.keys())

        for doc in required:
            doc_lower = doc.lower()
            is_present = doc_lower in submitted_set
            submitted_entry = submitted_docs.get(doc, submitted_docs.get(doc_lower))
            is_valid = bool(submitted_entry) if isinstance(submitted_entry, (str, bytes)) else bool(submitted_entry)

            present_and_valid = is_present and is_valid
            if present_and_valid:
                passed += 1

            detail = self._doc_detail(doc, submitted_docs, present_and_valid)
            rec = self._doc_recommendation(doc, present_and_valid)

            checks.append(ComplianceCheck(
                check_name=f"Document: {doc.replace('_', ' ').title()}",
                passed=present_and_valid,
                score=1.0 if present_and_valid else 0.0,
                max_score=1.0,
                details=detail,
                recommendation=rec,
            ))

        total = len(required)
        doc_score = passed / max(total, 1)
        all_passed = passed == total

        return checks, all_passed, doc_score

    def _doc_detail(self, doc: str, submitted_docs: Dict, is_valid: bool) -> str:
        if not is_valid:
            return f"{doc.replace('_', ' ').title()} — not submitted or invalid"
        entry = submitted_docs.get(doc)
        if isinstance(entry, dict):
            return f"{doc.replace('_', ' ').title()} — submitted ({entry.get('filename', entry.get('name', 'available'))})"
        return f"{doc.replace('_', ' ').title()} — submitted"

    def _doc_recommendation(self, doc: str, present_and_valid: bool) -> str:
        if present_and_valid:
            return "OK"
        recs = {
            "bid_security": "Submit Bank Draft / Pay Order of required EMD amount",
            "trade_license": "Ensure valid trade license from City Corporation / Union Council",
            "vat_tax_certificate": "Submit VAT registration certificate from NBR",
            "income_tax_certificate": "Submit TIN certificate with last year's return",
            "experience_certificate": "Provide completion certificates from previous clients",
            "similar_contract_completion": "Attach work completion / experience certificate for similar works",
            "manufacturer_authorization": "Provide manufacturer's authorization letter if agent",
            "key_personnel_cv": "Submit CVs of proposed key personnel with experience certificates",
            "equipment_list": "Provide list of owned or lease-committed equipment",
            "financial_capacity_statement": "Submit bank solvency certificate or audited financial reports",
        }
        return recs.get(doc, f"Submit {doc.replace('_', ' ')} before deadline")

    # ── Eligibility Criteria ───────────────────────────────────────────

    def _check_eligibility_criteria(
        self, vendor: Dict, eligibility_upstream: Dict,
    ) -> Tuple[List[ComplianceCheck], bool, float]:
        checks: List[ComplianceCheck] = []
        passed = 0

        # Experience
        exp_check = self._check_experience(vendor)
        checks.append(exp_check)
        if exp_check.passed:
            passed += 1

        # Turnover
        turnover_check = self._check_turnover(vendor)
        checks.append(turnover_check)
        if turnover_check.passed:
            passed += 1

        # Licenses
        license_check = self._check_licenses(vendor)
        checks.append(license_check)
        if license_check.passed:
            passed += 1

        # Conflict of interest
        coi_check = self._check_conflict_of_interest(vendor)
        checks.append(coi_check)
        if coi_check.passed:
            passed += 1

        # Blacklist check
        blacklist_check = self._check_blacklist(vendor)
        checks.append(blacklist_check)
        if blacklist_check.passed:
            passed += 1

        # Incorporate upstream eligibility result if available
        if eligibility_upstream.get("compliant"):
            upstream_note = ComplianceCheck(
                "Upstream Eligibility Signal",
                True,
                score=1.0, max_score=1.0,
                details="Agent-007 confirmed eligibility",
                recommendation="OK",
            )
            checks.append(upstream_note)
            passed += 1
        elif eligibility_upstream:
            upstream_note = ComplianceCheck(
                "Upstream Eligibility Signal",
                False,
                score=0.0, max_score=1.0,
                details=eligibility_upstream.get("notes", "Eligibility not confirmed by upstream agent"),
                recommendation="Review disqualifying factors identified by Eligibility Agent",
            )
            checks.append(upstream_note)

        total = len(checks)
        score = passed / max(total, 1)
        all_passed = passed == total

        return checks, all_passed, score

    def _check_experience(self, vendor: Dict) -> ComplianceCheck:
        years = vendor.get("years_experience", 0)
        required = vendor.get("required_experience_years", vendor.get("min_experience_years", 5))
        passed = years >= required
        return ComplianceCheck(
            "Eligibility: Experience", passed,
            score=1.0 if passed else 0.0, max_score=1.0,
            details=f"{years} years experience (required: {required})",
            recommendation="OK" if passed else f"Vendor must have at least {required} years of relevant experience",
        )

    def _check_turnover(self, vendor: Dict) -> ComplianceCheck:
        turnover = vendor.get("annual_turnover", vendor.get("avg_turnover", 0))
        required = vendor.get("required_turnover", vendor.get("min_turnover", 0))
        passed = turnover >= required
        return ComplianceCheck(
            "Eligibility: Turnover", passed,
            score=1.0 if passed else 0.0, max_score=1.0,
            details=f"Annual turnover ৳{turnover:,.0f} (required: ৳{required:,.0f})" if required else f"Annual turnover ৳{turnover:,.0f} (no minimum specified)",
            recommendation="OK" if passed else f"Vendor turnover ৳{turnover:,.0f} is below required ৳{required:,.0f}",
        )

    def _check_licenses(self, vendor: Dict) -> ComplianceCheck:
        licenses = vendor.get("licenses", vendor.get("company_licenses", []))
        has_valid = len(licenses) >= 1
        details = f"Licenses held: {', '.join(licenses)}" if licenses else "No licenses found"
        return ComplianceCheck(
            "Eligibility: Licenses", has_valid,
            score=1.0 if has_valid else 0.0, max_score=1.0,
            details=details,
            recommendation="OK" if has_valid else "At least one valid trade / professional license required",
        )

    def _check_conflict_of_interest(self, vendor: Dict) -> ComplianceCheck:
        coi = vendor.get("conflict_of_interest", vendor.get("has_conflict", False))
        if coi:
            return ComplianceCheck(
                "Eligibility: Conflict of Interest", False,
                score=0.0, max_score=1.0,
                details="Conflict of interest detected per PPR 2025 Rule 17",
                recommendation="Vendor must disclose relationship with procuring entity",
            )
        return ComplianceCheck(
            "Eligibility: Conflict of Interest", True,
            score=1.0, max_score=1.0,
            details="No conflict of interest detected",
            recommendation="OK",
        )

    def _check_blacklist(self, vendor: Dict) -> ComplianceCheck:
        blacklisted = vendor.get("blacklisted", vendor.get("is_blacklisted", False))
        if blacklisted:
            return ComplianceCheck(
                "Eligibility: Blacklist Check", False,
                score=0.0, max_score=1.0,
                details="Vendor is blacklisted by CPTU / procuring entity",
                recommendation="Vendor is ineligible until delisted per PPR 2025 Rule 19",
            )
        return ComplianceCheck(
            "Eligibility: Blacklist Check", True,
            score=1.0, max_score=1.0,
            details="Vendor not blacklisted",
            recommendation="OK",
        )

    # ── Recommendations ────────────────────────────────────────────────

    def _generate_recommendations(self, report: PPR2025ComplianceReport) -> List[str]:
        recs: List[str] = []

        if report.overall_passed:
            recs.append(f"Vendor complies with PPR 2025 rules (overall score: {report.overall_score:.1%}).")
        else:
            recs.append(f"Vendor does NOT fully comply (overall score: {report.overall_score:.1%}, minimum required: {TEC_MINIMUM_PASS_PCT:.0%}).")

        if report.schedule and not report.schedule.passed:
            recs.append(
                f"TEC evaluation ({report.schedule.schedule_label}) failed: "
                f"{report.schedule.total_marks:.0f}/{report.schedule.max_marks:.0f} marks "
                f"({report.schedule.percentage:.1%}). Minimum {TEC_MINIMUM_PASS_PCT:.0%} required."
            )

        if not report.document_passed:
            failed_docs = [c.check_name for c in report.document_checks if not c.passed]
            recs.append(f"Missing documents: {', '.join(failed_docs)}. Submit before evaluation deadline.")

        if not report.eligibility_passed:
            failed_elig = [c.check_name for c in report.eligibility_checks if not c.passed]
            recs.append(f"Eligibility criteria not met: {', '.join(failed_elig)}.")

        if report.overall_passed:
            recs.append("Proceed with technical evaluation.")
        elif report.overall_score >= 0.50:
            recs.append("Consider requesting additional documents / clarifications before rejection.")
        else:
            recs.append("Recommend disqualification based on PPR 2025 compliance failure.")

        return recs
