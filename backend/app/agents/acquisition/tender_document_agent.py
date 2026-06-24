from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class TenderDocumentAgent(BaseAgent):
    agent_id = "agent-034-tender-document"
    agent_name = "Tender Document AI"
    description = "Extracts key terms from uploaded tender PDFs: eligibility criteria, deadlines, earnest money, document checklist, and BOQ items."
    dependencies: List[str] = []
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        text = context.get("document_text", "")
        pdf_filename = context.get("pdf_filename", "unknown.pdf")
        tender_id = context.get("tender_id", "")

        extracted = await self._extract_document(text)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output={
                "tender_id": tender_id,
                "pdf_filename": pdf_filename,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                **extracted,
            },
        )

    async def _extract_document(self, text: str) -> Dict:
        return {
            "deadlines": self._extract_deadlines(text),
            "earnest_money": self._extract_earnest_money(text),
            "eligibility_criteria": self._extract_eligibility(text),
            "document_checklist": self._extract_document_checklist(text),
            "boq_summary": self._extract_boq_summary(text),
            "security_money": self._extract_security(text),
            "key_terms": self._extract_key_terms(text),
            "raw_sections": self._split_sections(text),
        }

    def _extract_deadlines(self, text: str) -> Dict[str, Optional[str]]:
        patterns = {
            "submission_deadline": [
                r"(?:submission|bid\s*submission|tender\s*submission)\s*(?:deadline|closing|date|time)[:\s]*(.+?)(?:\n|$)",
                r"(?:last\s*date\s*of\s*)?(?:submission|sale|receipt)\s*(?:of\s*)?(?:tender|bid)[:\s]*(.+?)(?:\n|$)",
            ],
            "pre_bid_meeting": [
                r"(?:pre[- ]?bid\s*meeting|pre[- ]?tender\s*meeting)[:\s]*(.+?)(?:\n|$)",
            ],
            "tender_opening": [
                r"(?:tender\s*opening|bid\s*opening|opening\s*(?:date|time))[:\s]*(.+?)(?:\n|$)",
            ],
        }
        result: Dict[str, Optional[str]] = {}
        for key, pats in patterns.items():
            for p in pats:
                m = re.search(p, text, re.IGNORECASE)
                if m:
                    result[key] = m.group(1).strip()
                    break
            if key not in result:
                result[key] = None
        return result

    def _extract_earnest_money(self, text: str) -> Optional[Dict]:
        patterns = [
            r"(?:earnest\s*money|EMD|bid\s*security|earnest\s*money\s*deposit)[:\s]*BDT?\s*([\d,]+)",
            r"(?:earnest\s*money|EMD)[:\s]*([\d,]+)\s*(?:BDT|Tk|/=)",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    return {"amount_bdt": float(raw), "raw": m.group(0).strip()}
                except ValueError:
                    pass
        return None

    def _extract_security(self, text: str) -> Optional[Dict]:
        patterns = [
            r"(?:performance\s*security|security\s*money|contract\s*security)[:\s]*BDT?\s*([\d,]+)",
            r"(?:performance\s*security|security\s*money)[:\s]*([\d,]+)\s*(?:BDT|Tk|/=)",
            r"(?:performance\s*security|security\s*money)[:\s]*([\d.]+)\s*%",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(",", "")
                is_pct = "%" in m.group(0)
                try:
                    val = float(raw)
                    return {"value": val, "type": "percentage" if is_pct else "fixed", "raw": m.group(0).strip()}
                except ValueError:
                    pass
        return None

    def _extract_eligibility(self, text: str) -> List[str]:
        criteria = []
        markers = [
            r"(?:eligibility|qualification|pre[- ]?qualification)\s*(?:criteria|requirement|condition)?[:\s]*?(.*?)(?:\n\n|\Z)",
            r"(?:eligible|qualifications?)[:\s]*?(.*?)(?:\n\n|\Z)",
        ]
        for marker in markers:
            m = re.search(marker, text, re.IGNORECASE | re.DOTALL)
            if m:
                block = m.group(1)
                lines = [l.strip("•- \t") for l in block.split("\n") if len(l.strip()) > 10]
                criteria.extend(lines[:15])
                break
        return criteria[:10]

    def _extract_document_checklist(self, text: str) -> List[str]:
        docs = []
        markers = [
            r"(?:required\s*documents?|documents?\s*checklist|checklist|list\s*of\s*documents?)[:\s]*?(.*?)(?:\n\n|\Z)",
            r"(?:documents?\s*to\s*be\s*submitted|submission\s*checklist)[:\s]*?(.*?)(?:\n\n|\Z)",
        ]
        for marker in markers:
            m = re.search(marker, text, re.IGNORECASE | re.DOTALL)
            if m:
                block = m.group(1)
                lines = [l.strip("•- \t") for l in block.split("\n") if len(l.strip()) > 5]
                docs.extend(lines[:20])
                break
        return docs[:15]

    def _extract_boq_summary(self, text: str) -> Dict:
        sections = re.split(r"\n(?=\d+\s*[.])", text)
        items = []
        for sec in sections[:30]:
            m = re.match(r"(\d+)\s*[.]\s*(.+?)(\d[\d,]*\.?\d*)\s*(?:BDT|Tk|/=)?\s*$", sec.strip(), re.DOTALL)
            if m:
                items.append({"item_no": m.group(1), "description": m.group(2).strip(), "amount": m.group(3)})
        return {"total_items": len(items), "items": items[:15]}

    def _extract_key_terms(self, text: str) -> List[Dict]:
        terms = []
        patterns = [
            (r"(?:contract\s*period|completion\s*period|duration)[:\s]*(.+?)(?:\n|$)", "Contract Period"),
            (r"(?:defect\s*liability|maintenance\s*period)[:\s]*(.+?)(?:\n|$)", "Defect Liability Period"),
            (r"(?:validity\s*period|bid\s*validity)[:\s]*(.+?)(?:\n|$)", "Bid Validity"),
            (r"(?:liquidated\s*damages?|LD|penalty)[:\s]*(.+?)(?:\n|$)", "Liquidated Damages"),
            (r"(?:advance\s*payment|mobilization\s*advance)[:\s]*(.+?)(?:\n|$)", "Advance Payment"),
            (r"(?:retention\s*money|retention)[:\s]*(.+?)(?:\n|$)", "Retention Money"),
        ]
        for pat, label in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                terms.append({"label": label, "value": m.group(1).strip()})
        return terms

    def _split_sections(self, text: str) -> List[Dict]:
        lines = text.split("\n")
        sections = []
        current = {"title": "General", "content": ""}
        for line in lines:
            if re.match(r"^[A-Z][A-Z\s/&-]{3,50}$", line.strip()):
                if current["content"].strip():
                    sections.append(current)
                current = {"title": line.strip(), "content": ""}
            else:
                current["content"] += line + "\n"
        if current["content"].strip():
            sections.append(current)
        return sections[:20]
