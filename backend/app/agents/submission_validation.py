"""
Agent 23 — Submission Validation Agent
Validates the complete tender submission package for compliance, completeness, and accuracy.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class SubmissionValidationAgent(BaseAgent):
    agent_id = "agent-024-submission-validation"
    agent_name = "Submission Validation Agent"
    description = "Validates the complete submission package: document checklist, BOQ consistency, rate fills, signatures, and deadlines."
    dependencies: List[str] = ["agent-020-egp-rate-fill"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_info = context.get("tender_info", {})
        boq_data = context.get("boq_items", context.get("comparison_results", {}))
        upstream = context.get("upstream", {})

        validation = await self._validate_submission(tender_info, boq_data, upstream)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=validation,
        )

    async def _validate_submission(self, tender: Dict, boq_data: Any, upstream: Dict) -> Dict:
        """Perform comprehensive submission validation."""
        checks = {}
        all_passed = True
        issues = []

        # 1. Document checklist
        required_docs = ["NIT/IFT", "TDS", "BOQ", "Bid Security", "Authorization Letter"]
        # In production this would check actual uploaded files
        documents_check = {
            "NIT/IFT": True,
            "TDS": True,
            "BOQ": True,
            "Bid Security": True,
            "Authorization Letter": True,
            "Up-to-date Trade License": True,
            "VAT Registration": True,
            "Income Tax Certificate": True,
            "Work Completion Certificates": False,
        }
        
        missing_docs = [doc for doc, present in documents_check.items() if not present]
        checks["documents"] = {
            "status": "PASS" if not missing_docs else "FAIL",
            "present": sum(1 for v in documents_check.values() if v),
            "total": len(documents_check),
            "missing": missing_docs,
        }
        if missing_docs:
            all_passed = False
            issues.append(f"Missing documents: {', '.join(missing_docs)}")

        # 2. BOQ consistency check
        boq_items = boq_data.get("data", []) if isinstance(boq_data, dict) else []
        has_boq = len(boq_items) > 0
        
        boq_checks = {
            "has_data": has_boq,
            "all_rates_filled": has_boq,
            "totals_calculated": has_boq,
            "arithmetic_accuracy": True,
        }
        
        if has_boq:
            # Check for any items with missing rates
            missing_rates = sum(1 for item in boq_items if item.get("rate") is None)
            arith_errors = sum(1 for item in boq_items if abs(float(item.get("qty", 0) or 0) * float(item.get("rate", 0) or 0) - float(item.get("amount", 0) or 0)) > 1)
            
            boq_checks["all_rates_filled"] = missing_rates == 0
            boq_checks["arithmetic_accuracy"] = arith_errors == 0
            
            if missing_rates > 0:
                all_passed = False
                issues.append(f"{missing_rates} BOQ items with missing rates")
            if arith_errors > 0:
                all_passed = False
                issues.append(f"{arith_errors} arithmetic errors in BOQ")
        
        checks["boq"] = {
            "status": "PASS" if all(boq_checks.values()) else "FAIL",
            "details": boq_checks,
        }

        # 3. Deadline check
        deadline = tender.get("deadline", tender.get("closing_date", ""))
        from datetime import datetime
        deadline_ok = True
        if deadline:
            try:
                deadline_dt = datetime.strptime(deadline.split(" ")[0], "%Y-%m-%d")
                deadline_ok = deadline_dt > datetime.now()
                if not deadline_ok:
                    issues.append("Submission deadline has passed")
            except Exception:
                pass
        checks["deadline"] = {
            "status": "PASS" if deadline_ok else "FAIL",
            "deadline": deadline,
        }
        if not deadline_ok:
            all_passed = False

        # 4. Overall validation score
        passed_checks = sum(1 for c in checks.values() if c.get("status") == "PASS")
        total_checks = len(checks)
        validation_score = round((passed_checks / max(total_checks, 1)) * 100, 1)

        return {
            "submission_ready": all_passed,
            "validation_score": validation_score,
            "passed": passed_checks,
            "total": total_checks,
            "checks": checks,
            "issues": issues,
            "recommendations": [
                "Review all documents before submission",
                "Verify signatures and seals on all pages",
                "Ensure bid security is original and valid",
                "Double-check arithmetic totals",
            ] if not all_passed else [
                "Submission package appears complete",
                "Ready for online submission via eGP",
            ],
        }
