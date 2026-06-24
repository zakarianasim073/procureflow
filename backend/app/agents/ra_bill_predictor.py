"""
Agent 29 — RA Bill & Cash Flow Predictor
Predicts RA Bill (Running Account Bill) payment delays based on historical XEN/SDE behavior.
Generates cash flow projections and flags expected payment bottlenecks.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# Bangladesh govt RA Bill payment norms
RA_BILL_NORMS = {
    "standard_days": 45,       # CPTU guideline: 45 days for RA Bill processing
    "PWD": {"avg_delay": 60, "risk": "medium"},
    "LGED": {"avg_delay": 75, "risk": "high"},
    "RHD": {"avg_delay": 50, "risk": "low"},
    "BWDB": {"avg_delay": 90, "risk": "critical"},
    "City_Corp": {"avg_delay": 120, "risk": "critical"},
}


class RABillPredictorAgent(BaseAgent):
    agent_id = "agent-030-ra-bill-predictor"
    agent_name = "RA Bill & Cash Flow Predictor"
    description = "Predicts Running Bill payment delays, generates cash flow schedules, and flags payment risks."
    dependencies: List[str] = []
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        project_data = context.get("project_data", {})
        historical_awards = context.get("awards", context.get("upstream", {}).get("agent-014-award-intelligence", {}).get("awards", []))
        entity = project_data.get("procuring_entity", "").upper()
        
        prediction = self._predict_payment_delays(entity, historical_awards)
        ra_bills = self._generate_ra_bill_schedule(project_data, prediction)
        cash_flow = self._generate_cash_flow(ra_bills)
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output={
                "entity_payment_profile": prediction,
                "ra_bill_schedule": ra_bills,
                "cash_flow_projection": cash_flow,
                "estimated_completion_days": project_data.get("contract_period_days", 365),
                "warnings": self._generate_warnings(prediction, cash_flow),
            },
        )

    def _predict_payment_delays(self, entity: str, historical: List[Dict]) -> Dict[str, Any]:
        """
        Predict payment delays based on:
        1. Entity-specific norms
        2. Historical payment patterns
        3. Seasonality (June/Dec bottlenecks)
        """
        # Base prediction from norms
        norm = RA_BILL_NORMS.get(entity, {"avg_delay": RA_BILL_NORMS["standard_days"], "risk": "medium"})
        predicted_delay = norm["avg_delay"]
        risk = norm["risk"]
        
        # Adjust based on historical data
        if historical:
            delays = []
            for a in historical:
                try:
                    awarded = datetime.fromisoformat(a.get("award_date", "").replace("Z", "+00:00"))
                    # Estimate payment delay from completion date
                    comp = a.get("work_completion_date", "")
                    if comp:
                        comp_date = datetime.fromisoformat(comp.replace("Z", "+00:00"))
                        delay_days = (comp_date - awarded).days - (a.get("contract_period_days", 365))
                        if delay_days > 0:
                            delays.append(delay_days)
                except (ValueError, TypeError):
                    continue
            
            if delays:
                avg_historical = statistics.mean(delays)
                predicted_delay = int((predicted_delay + avg_historical) / 2)
        
        # Seasonal adjustment (June = budget closing, Dec = new budget)
        now = datetime.utcnow()
        if now.month in [5, 6]:  # May-June: budget closing delays
            predicted_delay = int(predicted_delay * 1.3)
        elif now.month in [11, 12]:  # Nov-Dec: new budget cycle
            predicted_delay = int(predicted_delay * 1.15)
        
        return {
            "entity": entity,
            "predicted_avg_delay_days": predicted_delay,
            "risk_level": risk,
            "cptu_standard_days": RA_BILL_NORMS["standard_days"],
            "seasonal_adjustment_applied": now.month in [5, 6, 11, 12],
            "analysis": f"Expected ~{predicted_delay} days for RA Bill payment from {entity}",
        }

    def _generate_ra_bill_schedule(self, project: Dict, prediction: Dict) -> List[Dict]:
        """Generate 4 hypothetical RA Bills based on 25%, 50%, 75%, 100% completion."""
        contract_value = float(project.get("estimated_cost", 0) or project.get("awarded_amount", 0))
        period_days = project.get("contract_period_days", 365)
        delay = prediction.get("predicted_avg_delay_days", 60)
        
        milestones = [25, 50, 75, 100]
        schedule = []
        
        for pct in milestones:
            milestone_value = contract_value * pct / 100
            # Retention money: typically 5-10%
            retention = milestone_value * 0.075
            net_payable = milestone_value - retention
            
            # Calculate expected dates
            work_day = int(period_days * pct / 100)
            submission_date = datetime.utcnow() + timedelta(days=work_day)
            expected_payment = submission_date + timedelta(days=delay)
            
            schedule.append({
                "milestone": f"{pct}%",
                "work_progress": {
                    "from_pct": max(0, pct - 25),
                    "to_pct": pct,
                },
                "milestone_value_bdt": round(milestone_value, 2),
                "retention_7.5pct": round(retention, 2),
                "net_payable_bdt": round(net_payable, 2),
                "expected_submission_date": submission_date.strftime("%Y-%m-%d"),
                "expected_payment_date": expected_payment.strftime("%Y-%m-%d"),
                "expected_delay_days": delay,
            })
        
        return schedule

    def _generate_cash_flow(self, ra_bills: List[Dict]) -> Dict[str, Any]:
        """Generate cash flow projection from RA Bill schedule."""
        total_contract = 0
        total_payable = 0
        total_retention = 0
        
        for bill in ra_bills:
            total_contract += bill["milestone_value_bdt"]
            total_payable += bill["net_payable_bdt"]
            total_retention += bill["retention_7.5pct"]
        
        return {
            "total_contract_value_bdt": round(total_contract, 2),
            "total_net_payable_bdt": round(total_payable, 2),
            "total_retention_bdt": round(total_retention, 2),
            "total_retention_pct": 7.5,
            "effective_tax_deduction": round(total_payable * 0.10, 2),  # 10% AIT
            "estimated_bank_interest_loss": round(total_payable * 0.12 * 0.1, 2),  # 12% annual on delayed amounts
        }

    def _generate_warnings(self, prediction: Dict, cash_flow: Dict) -> List[str]:
        """Generate actionable warnings."""
        warnings = []
        
        if prediction["risk_level"] in ("high", "critical"):
            warnings.append(
                f"⚠️ {prediction['entity']} has {prediction['risk_level']} payment risk. "
                f"Expected {prediction['predicted_avg_delay_days']} days delay. "
                f"Plan working capital accordingly."
            )
        
        if cash_flow["total_retention_bdt"] > 0:
            warnings.append(
                f"💰 ৳{cash_flow['total_retention_bdt']:,.0f} retention money will be held. "
                f"Ensure defect liability period compliance."
            )
        
        if cash_flow["estimated_bank_interest_loss"] > 0:
            warnings.append(
                f"🏦 Estimated ৳{cash_flow['estimated_bank_interest_loss']:,.0f} in bank interest "
                f"cost due to delayed payments."
            )
        
        return warnings
