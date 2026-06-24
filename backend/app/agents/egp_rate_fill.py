"""
Agent 22 — EGP Rate Fill Agent
Fills BOQ with SOR zone-based unit rates, prepares portal-ready pricing data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

try:
    from app.sor import get_rate, get_rate_info
    SOR_AVAILABLE = True
except ImportError:
    SOR_AVAILABLE = False


class EGPRateFillAgent(BaseAgent):
    agent_id = "agent-020-egp-rate-fill"
    agent_name = "EGP Rate Fill Agent"
    description = "Maps BOQ items to SOR zone-based rates, prepares ready-to-fill pricing for eGP portal."
    dependencies: List[str] = ["agent-005-boq-intelligence", "agent-011-rate-analysis"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        upstream = context.get("upstream", {})
        boq_data = upstream.get("agent-005-boq-intelligence", {})
        rate_data = upstream.get("agent-011-rate-analysis", {})

        boq_items = boq_data.get("items", context.get("boq_items", []))
        analyzed_rates = rate_data.get("rates", [])
        
        zone = context.get("zone", context.get("sor_zone", "A")).upper()
        if zone not in ("A", "B", "C", "D"):
            zone = "A"

        fill_data = self._prepare_fill(boq_items, analyzed_rates, zone)

        output = {
            "ready_for_fill": fill_data["ready"],
            "total_items": fill_data["total"],
            "matched_items": fill_data["matched"],
            "unmatched_items": fill_data["unmatched"],
            "zone": zone,
            "items": fill_data["items"],
            "summary": fill_data["summary"],
            "notes": fill_data["notes"],
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    def _prepare_fill(self, boq_items: List[Dict], analyzed_rates: List[Dict], zone: str) -> Dict:
        rate_lookup = {r.get("item_no"): r for r in analyzed_rates}
        fill_items = []
        matched = 0
        unmatched = 0

        for item in boq_items:
            item_no = item.get("item_no")
            qty = item.get("quantity", 0)
            unit = item.get("unit", "")
            desc = item.get("description", "")
            sor_code = item.get("sor_code", "")

            ra = rate_lookup.get(item_no, {})
            rate = ra.get("recommended_rate", 0) or ra.get("sor_rate", 0)

            if not rate and SOR_AVAILABLE:
                sor_info = get_rate_info(sor_code, zone)
                if sor_info and sor_info.get("rate"):
                    rate = sor_info["rate"]

            amount = round(qty * rate, 2) if rate else 0

            fill_items.append({
                "item_no": item_no,
                "sor_code": sor_code,
                "description": desc,
                "unit": unit,
                "quantity": qty,
                "sor_rate": round(rate, 2),
                "amount": amount,
            })

            if rate and rate > 0:
                matched += 1
            else:
                unmatched += 1

        total_amount = sum(i.get("amount", 0) for i in fill_items)

        return {
            "ready": unmatched == 0,
            "total": len(fill_items),
            "matched": matched,
            "unmatched": unmatched,
            "items": fill_items,
            "summary": {
                "total_items": len(fill_items),
                "total_amount_bdt": round(total_amount, 2),
                "total_amount_formatted": f"\u09F3{total_amount:,.2f}",
                "matched_rate_items": matched,
                "unmatched_items": unmatched,
            },
            "notes": "Ready for eGP fill" if unmatched == 0
                     else f"{unmatched} items without SOR rates need manual entry",
        }
