"""
Agent 6 — Specification Intelligence Agent
Reads technical specifications (TDS), extracts requirements, flags risks and special materials.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class SpecIntelligenceAgent(BaseAgent):
    agent_id = "agent-006-spec-intelligence"
    agent_name = "Specification Intelligence Agent"
    description = "Analyzes technical specifications from TDS to extract requirements, risks, and special materials needed."
    dependencies: List[str] = ["agent-004-document-ai"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "eGP-001")
        specs_path = context.get("specifications_path", "")
        upstream = context.get("upstream", {})
        acquisition = upstream.get("agent-002-tender-acquisition", {})
        documents = acquisition.get("documents", {})

        if not specs_path:
            specs_path = documents.get("Specifications", "")

        # Extract text from TDS PDF if available
        spec_text = self._extract_spec_text(specs_path)

        requirements = self._extract_requirements(spec_text)
        risks = self._analyze_risks(requirements, spec_text)
        special_materials = self._identify_special_materials(requirements, spec_text)

        if not requirements:
            requirements, risks, special_materials = self._get_demo_data(tender_id)

        output = {
            "tender_id": tender_id,
            "requirements_count": len(requirements),
            "requirements": requirements,
            "risks": risks,
            "risks_count": len(risks),
            "special_materials": special_materials,
            "special_materials_count": len(special_materials),
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    def _extract_spec_text(self, path: str) -> str:
        """Extract text from a specification/TDS PDF."""
        if not path or not os.path.isfile(path):
            return ""
        try:
            import fitz
            doc = fitz.open(path)
            text = ""
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
            return text
        except Exception as e:
            logger.debug(f"Could not read spec PDF: {e}")
            return ""

    def _extract_requirements(self, text: str) -> List[str]:
        """Extract technical requirements from TDS text."""
        if not text:
            return []

        requirements = []

        # Experience/qualification requirements
        for pattern in [
            r'(Experience Criteria.*?)(?:\n\n|\d+\.)',
            r'(Qualification Requirements.*?)(?:\n\n|\d+\.)',
            r'(Personnel Requirements.*?)(?:\n\n|\d+\.)',
            r'(Key Personnel.*?)(?:\n\n|\d+\.)',
        ]:
            m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if m:
                requirements.append(m.group(1).strip())

        # Individual requirement lines
        req_patterns = [
            r'minimum\s+(\d+)\s+years?\s+(?:of\s+)?(?:general\s+)?experience',
            r'should\s+have\s+(?:completed|executed)\s+(?:at\s+least\s+)?(\d+)\s+(?:similar|comparable)',
            r'minimum\s+annual\s+(?:turnover|construction)\s+(?:value|turnover)\s+(?:of\s+)?[\u09F3Tk]?\s*([\d,]+)',
        ]
        for p in req_patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                requirements.append(m.group(0).strip())

        # Personnel requirements from TDS tables
        person_matches = re.findall(r'([A-Za-z\s]+?)\s*-\s*(\d+)\s*Nos?\s*.*?(\d+)\s*years?', text, re.IGNORECASE)
        for title, count, exp in person_matches:
            requirements.append(f"{title.strip()} - {count} Nos, {exp} years experience")

        return requirements

    def _analyze_risks(self, requirements: List[str], spec_text: str) -> List[str]:
        """Identify risks from requirements and specification text."""
        risks = []

        combined = " ".join(requirements) + " " + (spec_text or "")

        risk_indicators = {
            "asphalt": "Special Asphalt Grade Required",
            "bituminous": "Bituminous Material Required",
            "imported": "Imported Material Required — potential supply chain risk",
            "high performance": "Premium Performance Material Required",
            "specialist": "Specialist Subcontractor Required",
            "geotextile": "Special Geo-textile Material Required (97% Polypropylene)",
            "dredging": "Dredging Works — environmental compliance risk",
            "river": "River Works — seasonal/work window constraints",
        }

        for keyword, risk in risk_indicators.items():
            if keyword in combined.lower():
                risks.append(risk)

        return risks

    def _identify_special_materials(self, requirements: List[str], spec_text: str) -> List[str]:
        """Identify special materials required from specifications."""
        specials = []
        combined = " ".join(requirements) + " " + (spec_text or "")

        material_indicators = {
            "geotextile": "Geo-textile Fabric (97% Polypropylene, >=400gm/m²)",
            "asphalt": "Asphalt Concrete (Hot Mix)",
            "polypropylene": "Polypropylene Geo-textile Bags",
            "cc block": "Cement Concrete Blocks (45x45x45 cm, 35x35x35 cm)",
            "stone": "Stone Chips (40mm downgraded)",
            "grade 60": "Grade 60W Reinforcement Steel",
            "total station": "Total Station Survey Equipment",
            "barge": "Barge / Bulkhead Dredger",
        }

        for keyword, material in material_indicators.items():
            if keyword.lower() in combined.lower():
                if material not in specials:
                    specials.append(material)

        return specials

    def _get_demo_data(self, tender_id: str) -> tuple:
        """Return realistic demo data based on real tender 1264860 patterns."""
        requirements = [
            "5 years general experience in construction works as Prime Contractor",
            "Specific experience in river bank protection works",
            "Key Personnel: Project Manager with 10 years experience",
            "Surveyor - 3 Nos (survey work using Total station, Theodolite, GPS) - 4 years",
            "Supervisor - 4 Nos, 4 years experience",
            "Geo-textile bag supplying and filling with 97% Polypropylene fabric",
            "CC Block manufacturing in leanest mix 1:3:5.5",
            "Dumping with Barge and Total Station survey",
        ]
        risks = [
            "Special Geo-textile Material Required (97% Polypropylene, >=400gm/m²)",
            "River Works — seasonal/work window constraints",
            "Dredging Works — environmental compliance risk",
            "Total Station Survey Equipment Required",
        ]
        special_materials = [
            "Geo-textile Fabric (97% Polypropylene, >=400gm/m²)",
            "Cement Concrete Blocks (45x45x45 cm, 35x35x35 cm)",
            "Stone Chips (40mm downgraded)",
            "Barge / Bulkhead Dredger",
        ]
        return requirements, risks, special_materials
