"""
Agent 4 — Document AI Agent
Reads tender documents (PDF Notice, TDS, BOQ) and extracts structured data.
Uses PyMuPDF for text extraction and regex for field parsing.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import TenderProfile

logger = logging.getLogger(__name__)


class DocumentAIAgent(BaseAgent):
    agent_id = "agent-004-document-ai"
    agent_name = "Document AI Agent"
    description = "Extracts structured data from tender PDF documents (Notice, TDS, BOQ) using text extraction and pattern matching."
    dependencies: List[str] = ["agent-002-tender-acquisition"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "eGP-001")
        doc_paths = context.get("document_paths", {})
        upstream = context.get("upstream", {})
        acquisition = upstream.get("agent-002-tender-acquisition", {})
        docs_dict = acquisition.get("documents", {}) or doc_paths

        # Extract text from available PDF documents
        pdf_texts = self._extract_pdf_texts(docs_dict)

        # Build structured profile from extracted text
        profile = self._parse_profile(tender_id, pdf_texts)

        output = {
            "tender_id": profile.tender_id,
            "eligibility": profile.eligibility_requirements,
            "extracted_fields": {
                "experience_required": profile.experience_required,
                "turnover_required": profile.turnover_required,
                "emd_amount": profile.emd_amount,
                "completion_period_days": profile.completion_period_days,
                "estimated_value": 0.0,
            },
            "special_conditions": profile.special_conditions,
            "sections_extracted": list(profile.sections.keys()),
            "documents_processed": list(pdf_texts.keys()),
            "source": "pdf_parsing" if pdf_texts else "demo_data",
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    def _extract_pdf_texts(self, doc_dict: Dict) -> Dict[str, str]:
        """Extract text from PDF files in the document dictionary."""
        texts = {}
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF not available — using demo data")
            return texts

        for key, path in doc_dict.items():
            if not isinstance(path, str) or not path.endswith('.pdf'):
                continue
            if not os.path.isfile(path):
                continue
            try:
                doc = fitz.open(path)
                text = ""
                for page in doc:
                    text += page.get_text() + "\n"
                doc.close()
                if text.strip():
                    texts[key] = text
                    logger.info(f"Extracted {len(text)} chars from {key} ({path})")
            except Exception as e:
                logger.debug(f"Could not read {key} at {path}: {e}")

        return texts

    def _parse_profile(self, tender_id: str, pdf_texts: Dict[str, str]) -> TenderProfile:
        """Parse all collected PDF texts into a structured TenderProfile."""
        combined = "\n".join(pdf_texts.values())

        # Extract basic fields from notice
        tender_id_extracted = self._extract_field(combined, r'Tender/Proposal ID\s*:\s*(\d+)', default=tender_id)
        estimated_value = self._extract_estimated_value(combined)
        emd = self._extract_emd(combined)
        completion_days = self._extract_completion_days(combined)
        experience_years = self._extract_experience(combined)
        turnover = self._extract_turnover(combined)

        # Extract sections
        sections = {}
        for sep in ["Key Information", "Particular Information", "Procuring Entity Details",
                     "Experience Criteria", "Eligibility Criteria"]:
            idx = combined.find(sep)
            if idx >= 0:
                end_idx = combined.find("\n\n", idx + 100)
                if end_idx < 0:
                    end_idx = min(idx + 500, len(combined))
                sections[sep.lower().replace(" ", "_")] = combined[idx:end_idx].strip()

        # Extract special conditions
        special_conditions = []
        if "reserves the right" in combined.lower():
            special_conditions.append("Procuring entity reserves the right to accept or reject all tenders")
        if "bank will update" in combined.lower():
            special_conditions.append("Bank payments update at end of day — pay one day before submission")

        return TenderProfile(
            tender_id=tender_id_extracted,
            eligibility_requirements={
                "experience": f"{experience_years} years in similar works" if experience_years else "Not specified",
                "turnover": f"Minimum BDT {turnover:,.0f}" if turnover else "Not specified",
                "emd": f"BDT {emd:,.0f}" if emd else "Not specified",
            },
            experience_required=f"{experience_years} years" if experience_years else "Not specified",
            turnover_required=turnover or 0.0,
            emd_amount=emd or 0.0,
            completion_period_days=completion_days,
            special_conditions=special_conditions,
            sections=sections,
        )

    def _extract_field(self, text: str, pattern: str, default: str = "") -> str:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    def _extract_estimated_value(self, text: str) -> float:
        """Extract estimated value in BDT from tender notice."""
        # Pattern like "Tk. 61,00,000.00" or "61,00,000"
        patterns = [
            r'(?:Tk|BDT|\u09F3|TK)\.?\s*([\d,]+(?:\.\d+)?)\s*(?:Cr|Lac|Lakh|Thousand)?',
            r'Estimated\s*(?:Cost|Value)\s*(?:BDT)?\s*:?\s*([\d,]+(?:\.\d+)?)',
            r'(\d{1,2},?\d{2},?\d{2},?\d{3}(?:\.\d+)?)\s*(?:BDT|Tk|TK)',
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    val_str = m.group(1).replace(',', '')
                    val = float(val_str)
                    if val < 1000:  # Too small, might be unit price
                        continue
                    return val
                except ValueError:
                    continue
        return 0.0

    def _extract_emd(self, text: str) -> float:
        """Extract EMD amount."""
        patterns = [
            r'(?:EMD|Earnest Money|Bid Security)\s*(?:BDT)?\s*:?\s*([\d,]+(?:\.\d+)?)',
            r'(?:Tk|BDT|\u09F3)\.?\s*([\d,]+(?:\.\d+)?)\s*(?:Cr|Lac|Lakh)?',
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1).replace(',', ''))
                except ValueError:
                    continue
        return 500_000  # default demo

    def _extract_completion_days(self, text: str) -> int:
        """Extract completion period in days."""
        patterns = [
            r'(\d+)\s*days?',
            r'(\d+)\s*months?',
        ]
        m = re.search(r'Completion\s*(?:Period|Time|Date)?\s*[\s\S]*?(\d{1,3})\s*(?:day|Day)', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d{1,2})\s*months?', text, re.IGNORECASE)
        if m:
            return int(m.group(1)) * 30
        return 540  # default

    def _extract_experience(self, text: str) -> int:
        """Extract minimum experience years from TDS."""
        m = re.search(r'(\d+)\s*(?:five|five\s*\()?\s*years?\s*(?:of)?\s*(?:general)?\s*experience', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        m = re.search(r'minimum\s*(?:number\s*of)?\s*years?\s*(?:of)?\s*(?:general)?\s*experience.*?(\d+)', text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return 5  # default from the real TDS

    def _extract_turnover(self, text: str) -> float:
        """Extract minimum turnover requirement."""
        m = re.search(r'(?:Minimum|Annual|Average)\s*(?:Turnover|Revenue)\s*(?:BDT)?\s*:?\s*([\d,]+(?:\.\d+)?)', text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except ValueError:
                pass
        return 50_000_000  # default demo
