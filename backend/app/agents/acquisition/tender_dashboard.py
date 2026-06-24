"""
Tender Dashboard Agent â€” Extract, structure & report on all tender documents.
Turns raw notices/PDFs/JSON into structured data in TenderDataPool.

Pipeline:
  Notice (PDF/JSON) 
    â†’ Parse NIT (basic info, dates, amounts)
    â†’ Extract TDS (qualification criteria, equipment, manpower, turnover)
    â†’ Extract BOQ (items, quantities, units, rates)
    â†’ Store in TenderDataPool
    â†’ Generate Tender Readiness Report
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.db.database import get_sync_engine, get_session
from app.db.models import TenderDataPool, TenderDocument, TenderReport
from sqlalchemy import select, text

logger = logging.getLogger(__name__)


class TenderDashboardAgent(BaseAgent):
    """
    Agent that extracts ALL data from tender documents and builds 
    the Tender Dashboard â€” a complete structured view of every tender.
    
    Can work with:
    - PDF notices â†’ text extraction â†’ structured data
    - JSON notices â†’ direct structured mapping
    - HTML notices â†’ tag parsing â†’ structured data
    """
    
    agent_id = "agent-035-tender-dashboard"
    agent_name = "Tender Dashboard"
    description = "Extracts ALL tender data from documents into structured pool"
    dependencies = ["agent-002-tender-acquisition"]
    version = "1.0.0"
    
    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "")
        action = context.get("action", "full_extraction")
        
        if action == "full_extraction":
            return await self._full_extraction(tender_id, context)
        elif action == "extract_notice":
            return await self._extract_notice(tender_id, context)
        elif action == "extract_tds":
            return await self._extract_tds(tender_id, context)
        elif action == "extract_boq":
            return await self._extract_boq(tender_id, context)
        elif action == "generate_report":
            return await self._generate_report(tender_id, context)
        elif action == "get_dashboard":
            return await self._get_dashboard(tender_id)
        else:
            # Full extraction as default
            return await self._full_extraction(tender_id, context)
    
    async def _full_extraction(self, tender_id: str, context: Dict) -> AgentResult:
        """Run full extraction pipeline: Notice â†’ TDS â†’ BOQ â†’ Report."""
        notice_result = await self._extract_notice(tender_id, context)
        tds_result = await self._extract_tds(tender_id, context)
        boq_result = await self._extract_boq(tender_id, context)
        report = await self._generate_report(tender_id, context)
        
        # Share to Knowledge Lake
        await self.share_knowledge(
            entry_type="tender_dashboard", tender_id=tender_id,
            data={
                "notice": notice_result.get("data", {}),
                "qualification": tds_result.get("data", {}),
                "boq_summary": boq_result.get("summary", {}),
                "report_summary": report.get("summary", ""),
            },
            summary=f"Full tender dashboard built for {tender_id}",
            tags=["tender_dashboard", "full_extraction"]
        )
        
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "tender_id": tender_id,
            "notice_extracted": notice_result.get("status"),
            "tds_extracted": tds_result.get("status"),
            "boq_extracted": boq_result.get("status"),
            "report_generated": report.get("status"),
            "dashboard_ready": True,
        })
    
    async def _extract_notice(self, tender_id: str, context: Dict) -> Dict:
        """Extract basic info from tender notice (NIT)."""
        raw_data = context.get("raw_data", {})
        notice_data = raw_data if isinstance(raw_data, dict) else {}
        
        # If we have a notice URL, try to fetch and parse
        notice_url = context.get("notice_url", context.get("nit_url", ""))
        
        # Structured extraction from whatever source we have
        extracted = {
            "tender_id": tender_id,
            "package_no": notice_data.get("package_no") or context.get("package_no", ""),
            "work_name": notice_data.get("work_name") or context.get("work_name", ""),
            "procuring_entity": notice_data.get("procuring_entity") or context.get("agency", ""),
            "pe_office": notice_data.get("pe_office") or context.get("office", ""),
            "zone": notice_data.get("zone") or context.get("zone", ""),
            "division": notice_data.get("division") or context.get("division", ""),
            "district": notice_data.get("district") or context.get("district", ""),
            "publication_date": notice_data.get("publication_date") or context.get("pub_date", ""),
            "closing_date": notice_data.get("closing_date") or context.get("close_date", ""),
            "opening_date": notice_data.get("opening_date") or context.get("open_date", ""),
            "estimated_amount_bdt": self._safe_float(notice_data.get("estimated_amount") or context.get("estimated_amount", 0)),
            "tender_security_amount": self._safe_float(notice_data.get("tender_security") or context.get("security_amount", 0)),
            "performance_security_amount": self._safe_float(notice_data.get("performance_security") or context.get("performance_amount", 0)),
            "completion_period_days": self._safe_int(notice_data.get("completion_period") or context.get("completion_days", 0)),
            "tender_fee": self._safe_float(notice_data.get("tender_fee") or context.get("fee", 0)),
            "source_format": context.get("source_format", "json"),
        }
        
        # Save to database
        await self._save_to_pool(tender_id, extracted)
        
        return {"status": "extracted", "data": extracted}
    
    async def _extract_tds(self, tender_id: str, context: Dict) -> Dict:
        """Extract TDS / Qualification criteria from tender documents."""
        raw_data = context.get("raw_data", {})
        tds_data = raw_data.get("tds", raw_data.get("qualification", {}))
        
        if not tds_data and context.get("tds_text"):
            # Parse from text
            tds_data = self._parse_tds_text(context["tds_text"])
        
        extracted = {
            "tender_id": tender_id,
            "min_experience_years": self._safe_int(tds_data.get("min_experience_years") or tds_data.get("experience_years", 0)),
            "min_turnover_bdt": self._safe_float(tds_data.get("min_turnover_bdt") or tds_data.get("turnover", 0)),
            "min_liquid_assets_bdt": self._safe_float(tds_data.get("min_liquid_assets_bdt") or tds_data.get("liquid_assets", 0)),
            "min_annual_construction_volume": self._safe_float(tds_data.get("min_annual_construction_volume") or tds_data.get("construction_volume", 0)),
            "similar_works_required": self._safe_int(tds_data.get("similar_works_required") or tds_data.get("similar_works", 0)),
            "required_equipment": self._ensure_list(tds_data.get("required_equipment") or tds_data.get("equipment", [])),
            "required_personnel": self._ensure_list(tds_data.get("required_personnel") or tds_data.get("personnel", [])),
            "required_licenses": self._ensure_list(tds_data.get("required_licenses") or tds_data.get("licenses", [])),
            "special_qualifications": self._ensure_list(tds_data.get("special_qualifications") or tds_data.get("special_conditions", [])),
        }
        
        await self._save_to_pool(tender_id, extracted)
        
        return {"status": "extracted", "data": extracted}
    
    async def _extract_boq(self, tender_id: str, context: Dict) -> Dict:
        """Extract BOQ items from tender documents."""
        raw_data = context.get("raw_data", {})
        boq_data = raw_data.get("boq", raw_data.get("bill_of_quantities", {}))
        
        if not boq_data and context.get("boq_text"):
            boq_data = self._parse_boq_text(context["boq_text"])
        
        boq_items = self._ensure_list(boq_data.get("items") or boq_data.get("boq_items", []))
        
        # Calculate totals
        total = sum(
            self._safe_float(item.get("total_amount") or 
                (self._safe_float(item.get("rate", 0)) * self._safe_float(item.get("quantity", 0))))
            for item in boq_items
        )
        
        extracted = {
            "tender_id": tender_id,
            "boq_items": boq_items,
            "boq_total": total,
            "item_count": len(boq_items),
            "boq_categories": list(set(
                item.get("category", item.get("section", "General"))
                for item in boq_items
            )),
        }
        
        await self._save_to_pool(tender_id, extracted)
        
        return {
            "status": "extracted",
            "data": extracted,
            "summary": {
                "total_items": len(boq_items),
                "total_amount": total,
                "categories": extracted["boq_categories"],
            }
        }
    
    async def _generate_report(self, tender_id: str, context: Dict) -> Dict:
        """Generate a comprehensive tender readiness report."""
        # Get pooled data
        pool_data = await self._get_pool_data(tender_id)
        
        if not pool_data:
            return {"status": "no_data", "summary": "No extracted data found"}
        
        # Generate report
        report = {
            "tender_id": tender_id,
            "report_type": "tender_readiness",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sections": {
                "basic_info": {
                    "package_no": pool_data.get("package_no", ""),
                    "work_name": pool_data.get("work_name", ""),
                    "procuring_entity": pool_data.get("procuring_entity", ""),
                    "estimated_amount": float(pool_data.get("estimated_amount_bdt", 0) or 0),
                    "completion_days": pool_data.get("completion_period_days", 0),
                },
                "qualification_summary": self._build_qual_summary(pool_data),
                "boq_summary": {
                    "total_items": len(pool_data.get("boq_items", []) or []),
                    "total_amount": float(pool_data.get("boq_total", 0) or 0),
                },
                "required_equipment": pool_data.get("required_equipment", []),
                "required_personnel": pool_data.get("required_personnel", []),
                "readiness_check": self._check_readiness(pool_data, context),
            }
        }
        
        # Save report
        session = get_session()
        async with session as s:
            db_report = TenderReport(
                tender_id=tender_id,
                report_type="tender_readiness",
                report_data=report,
                summary=f"Tender readiness report for {tender_id}",
                recommendations=report["sections"]["readiness_check"].get("recommendations", []),
                generated_by=self.agent_id,
            )
            s.add(db_report)
            await s.commit()
        
        return {
            "status": "generated", 
            "summary": f"Full tender readiness report generated",
            "readiness_score": report["sections"]["readiness_check"].get("score", 0),
            "data": report,
        }
    
    async def _get_dashboard(self, tender_id: str) -> Dict:
        """Get the full tender dashboard from the pool."""
        pool_data = await self._get_pool_data(tender_id)
        
        # Get related documents
        docs = []
        session = get_session()
        async with session as s:
            result = await s.execute(
                select(TenderDocument).where(TenderDocument.tender_id == tender_id)
            )
            for doc in result.scalars():
                docs.append({
                    "id": doc.id, "doc_type": doc.doc_type, "format": doc.format,
                    "filename": doc.filename, "extraction_status": doc.extraction_status,
                })
        
        # Get reports
        reports = []
        async with session as s:
            result = await s.execute(
                select(TenderReport).where(TenderReport.tender_id == tender_id)
            )
            for r in result.scalars():
                reports.append({
                    "id": r.id, "report_type": r.report_type,
                    "summary": r.summary, "generated_by": r.generated_by,
                })
        
        return {
            "tender_id": tender_id,
            "pool_data": pool_data,
            "documents": docs,
            "reports": reports,
        }
    
    async def _save_to_pool(self, tender_id: str, data: Dict):
        """Save extracted data to TenderDataPool with proper type conversion."""
        text_fields = {
            "tender_id", "package_no", "work_name", "procuring_entity", "pe_office",
            "zone", "division", "district", "nit_url", "tds_url", "boq_url",
            "drawings_url", "source_format"
        }

        def _convert(key, val):
            if val is None:
                return None
            if key in text_fields or key.endswith("_url") or key.endswith("_id"):
                return str(val)
            if isinstance(val, str):
                # Try to convert numeric strings
                try:
                    if '.' in val or val.isdigit():
                        return float(val.replace(',', ''))
                except (ValueError, AttributeError):
                    pass
                # Try date strings
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        return datetime.strptime(val, fmt)
                    except ValueError:
                        continue
                # Return string as-is for text fields
                return val
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, dict) or isinstance(val, list):
                return val
            return str(val) if val else None
        
        session = get_session()
        async with session as s:
            result = await s.execute(
                select(TenderDataPool).where(TenderDataPool.tender_id == tender_id)
            )
            existing = result.scalars().first()
            
            if existing:
                for key, value in data.items():
                    if value is not None and hasattr(existing, key):
                        setattr(existing, key, _convert(key, value))
                existing.extraction_status = "complete"
                existing.updated_at = datetime.now(timezone.utc)
            else:
                pool_entry = TenderDataPool(tender_id=tender_id, extraction_status="complete")
                for key, value in data.items():
                    if value is not None and hasattr(pool_entry, key):
                        setattr(pool_entry, key, _convert(key, value))
                s.add(pool_entry)
            
            await s.commit()
    
    async def _get_pool_data(self, tender_id: str) -> Dict:
        """Get data from TenderDataPool."""
        session = get_session()
        async with session as s:
            result = await s.execute(
                select(TenderDataPool).where(TenderDataPool.tender_id == tender_id)
            )
            entry = result.scalars().first()
            if entry:
                return {c.name: getattr(entry, c.name) for c in entry.__table__.columns}
            return {}
    
    def _parse_tds_text(self, text_content: str) -> Dict:
        """Parse TDS/qualification criteria from raw text."""
        result = {}
        
        # Experience years
        m = re.search(r'(\d+)\s*(?:years?|yrs?)\s*(?:experience|general experience)', text_content, re.I)
        if m: result["experience_years"] = int(m.group(1))
        
        # Turnover
        m = re.search(r'(?:minimum|min)?\s*(?:annual\s+)?turnover.*?(?:BDT|Tk|à§³)\s*([\d.,]+)', text_content, re.I)
        if m: result["turnover"] = self._parse_amount(m.group(1))
        
        # Liquid assets
        m = re.search(r'(?:liquid\s+assets|liquid\s+fund|working\s+capital).*?(?:BDT|Tk|à§³)\s*([\d.,]+)', text_content, re.I)
        if m: result["liquid_assets"] = self._parse_amount(m.group(1))
        
        # Similar works
        m = re.search(r'(\d+)\s*(?:similar|same)\s*(?:work|nature|contract)', text_content, re.I)
        if m: result["similar_works"] = int(m.group(1))
        
        # Equipment
        equipment = []
        eq_section = re.search(r'(?:equipment|machinery|plant).*?(?:\n\n|\Z)', text_content, re.I | re.S)
        if eq_section:
            for line in eq_section.group(0).split('\n'):
                line = line.strip()
                if line and len(line) > 5 and not line.startswith('#'):
                    equipment.append(line)
        if equipment:
            result["equipment"] = equipment
        
        # Personnel
        personnel = []
        pers_section = re.search(r'(?:personnel|manpower|staff|key\s*personnel).*?(?:\n\n|\Z)', text_content, re.I | re.S)
        if pers_section:
            for line in pers_section.group(0).split('\n'):
                line = line.strip()
                if line and len(line) > 5:
                    personnel.append(line)
        if personnel:
            result["personnel"] = personnel
        
        return result
    
    def _parse_boq_text(self, text_content: str) -> Dict:
        """Parse BOQ items from raw text."""
        items = []
        lines = text_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Try to match: item_no description unit quantity rate amount
            m = re.match(r'(\d+(?:\.\d+)?)\s+(.+?)\s+(No|Lump|LS|kg|m3|m2|m|km|each|day|month|year|set|lot)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', line, re.I)
            if m:
                items.append({
                    "item_no": m.group(1),
                    "description": m.group(2).strip(),
                    "unit": m.group(3),
                    "quantity": self._parse_amount(m.group(4)),
                    "rate": self._parse_amount(m.group(5)),
                    "total_amount": self._parse_amount(m.group(6)),
                })
            i += 1
        
        return {"items": items}
    
    def _build_qual_summary(self, pool_data: Dict) -> Dict:
        """Build qualification criteria summary."""
        return {
            "experience_years": pool_data.get("min_experience_years", 0),
            "turnover_required": float(pool_data.get("min_turnover_bdt", 0) or 0),
            "liquid_assets_required": float(pool_data.get("min_liquid_assets_bdt", 0) or 0),
            "similar_works": pool_data.get("similar_works_required", 0),
            "equipment_count": len(pool_data.get("required_equipment", []) or []),
            "personnel_count": len(pool_data.get("required_personnel", []) or []),
        }
    
    def _check_readiness(self, pool_data: Dict, context: Dict) -> Dict:
        """Check tender readiness based on extracted data."""
        company = context.get("company_profile", {})
        score = 50  # Start at 50%
        recommendations = []
        
        est_amount = float(pool_data.get("estimated_amount_bdt", 0) or 0)
        turnover_req = float(pool_data.get("min_turnover_bdt", 0) or 0)
        liquid_req = float(pool_data.get("min_liquid_assets_bdt", 0) or 0)
        
        # Check turnover
        company_turnover = float(company.get("turnover", 0))
        if company_turnover >= turnover_req:
            score += 15
        else:
            recommendations.append(f"Insufficient turnover: need {turnover_req:,.0f}, have {company_turnover:,.0f}")
        
        # Check liquid assets
        company_liquid = float(company.get("liquid_assets", 0))
        if company_liquid >= liquid_req:
            score += 10
        else:
            recommendations.append(f"Insufficient liquid assets: need {liquid_req:,.0f}")
        
        # Check experience
        company_exp = int(company.get("experience_years", 0))
        exp_req = int(pool_data.get("min_experience_years", 0))
        if company_exp >= exp_req:
            score += 10
        else:
            recommendations.append(f"Insufficient experience: need {exp_req} years")
        
        # Check equipment match
        equipment_req = pool_data.get("required_equipment", [])
        company_equip = company.get("equipment", [])
        if equipment_req:
            missing_equip = [e for e in equipment_req if e not in company_equip]
            if missing_equip:
                recommendations.append(f"Missing equipment: {', '.join(missing_equip[:3])}")
                score -= 5
        
        # Check personnel match
        personnel_req = pool_data.get("required_personnel", [])
        company_personnel = company.get("personnel", [])
        if personnel_req:
            missing_pers = [p for p in personnel_req if p not in company_personnel]
            if missing_pers:
                recommendations.append(f"Missing personnel: {', '.join(missing_pers[:3])}")
                score -= 5
        
        score = max(0, min(100, score))
        
        return {
            "score": score,
            "ready": score >= 60,
            "level": "high" if score >= 80 else "medium" if score >= 60 else "low",
            "recommendations": recommendations,
        }
    
    @staticmethod
    def _safe_float(val) -> float:
        if val is None: return 0.0
        try: return float(val)
        except: return 0.0
    
    @staticmethod
    def _safe_int(val) -> int:
        if val is None: return 0
        try: return int(val)
        except: return 0
    
    @staticmethod
    def _parse_amount(val: str) -> float:
        try: return float(val.replace(',', '').replace(' ', ''))
        except: return 0.0
    
    @staticmethod
    def _ensure_list(val) -> List:
        if val is None: return []
        if isinstance(val, list): return val
        if isinstance(val, str): return [val]
        if isinstance(val, dict): return list(val.values())
        return list(val) if hasattr(val, '__iter__') else [val]
