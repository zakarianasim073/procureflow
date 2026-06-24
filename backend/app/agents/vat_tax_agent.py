"""
Agent 32 — VAT/Tax Calculator Agent
Calculates all applicable Bangladeshi taxes (VAT, AIT, SD, IT) for construction tender bids.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class VatTaxCalculatorAgent(BaseAgent):
    agent_id = "agent-033-vat-tax-calculator"
    agent_name = "VAT/Tax Calculator Agent"
    description = "Calculates all applicable Bangladeshi taxes (VAT, AIT, SD, IT) for construction tender bids, including net amount after deductions."
    dependencies: List[str] = ["agent-021-financial-intelligence"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        contract_value = context.get("contract_value", context.get("bid_amount", 50_000_000))
        contract_type = context.get("contract_type", "construction")
        company_tax_rate = context.get("company_tax_rate", 22.5)
        vat_rate = context.get("vat_rate", 5.0)
        ait_rate = context.get("ait_rate", self._default_ait_rate(contract_type))
        sd_rate = context.get("sd_rate", self._default_sd_rate(contract_type))

        calculation = await self._calculate_taxes(
            contract_value, contract_type, company_tax_rate, vat_rate, ait_rate, sd_rate
        )

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=calculation,
        )

    async def _calculate_taxes(
        self, contract_value: float, contract_type: str,
        company_tax_rate: float, vat_rate: float,
        ait_rate: float, sd_rate: float
    ) -> Dict:
        vat_amount = contract_value * (vat_rate / 100)
        ait_amount = contract_value * (ait_rate / 100)
        sd_amount = contract_value * (sd_rate / 100)
        it_amount = contract_value * (company_tax_rate / 100)

        total_tax_amount = vat_amount + ait_amount + sd_amount + it_amount
        net_amount = contract_value - total_tax_amount
        effective_tax_rate = (total_tax_amount / contract_value) * 100 if contract_value else 0

        return {
            "gross_amount": round(contract_value, 2),
            "contract_type": contract_type,
            "breakdown": {
                "vat": {
                    "rate_pct": vat_rate,
                    "amount": round(vat_amount, 2),
                    "label": "VAT (মূল্য সংযোজন কর)",
                },
                "ait": {
                    "rate_pct": ait_rate,
                    "amount": round(ait_amount, 2),
                    "label": "AIT (অগ্রিম আয়কর)",
                },
                "sd": {
                    "rate_pct": sd_rate,
                    "amount": round(sd_amount, 2),
                    "label": "SD (উৎসে কর)",
                },
                "it": {
                    "rate_pct": company_tax_rate,
                    "amount": round(it_amount, 2),
                    "label": "IT (আয়কর)",
                },
            },
            "total_tax": {
                "amount": round(total_tax_amount, 2),
                "effective_rate_pct": round(effective_tax_rate, 2),
            },
            "net_amount": round(net_amount, 2),
            "explanation_bn": (
                f"চুক্তির মূল্য: ৳{contract_value:,.2f}\n"
                f"ভ্যাট ({vat_rate}%): ৳{vat_amount:,.2f}\n"
                f"অগ্রিম আয়কর ({ait_rate}%): ৳{ait_amount:,.2f}\n"
                f"উৎসে কর ({sd_rate}%): ৳{sd_amount:,.2f}\n"
                f"আয়কর ({company_tax_rate}%): ৳{it_amount:,.2f}\n"
                f"মোট কর: ৳{total_tax_amount:,.2f} (কার্যকর হার {effective_tax_rate:.1f}%)\n"
                f"সর্বমোট প্রাপ্য (কর後): ৳{net_amount:,.2f}"
            ),
            "factors_considered": [
                "Contract value",
                "Contract type (construction, supply, service)",
                "Standard VAT rate for construction (5%)",
                "AIT rate based on contract type",
                "Source deduction (SD) rate",
                "Corporate income tax rate",
            ],
        }

    @staticmethod
    def _default_ait_rate(contract_type: str) -> float:
        rates = {
            "construction": 3.0,
            "supply": 2.5,
            "service": 5.0,
            "works": 3.0,
        }
        return rates.get(contract_type.lower(), 3.0)

    @staticmethod
    def _default_sd_rate(contract_type: str) -> float:
        rates = {
            "construction": 1.0,
            "supply": 0.5,
            "service": 2.0,
            "works": 1.0,
        }
        return rates.get(contract_type.lower(), 1.0)
