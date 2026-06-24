"""
e-GP Document Acquisition Crawler
Walks through e-GP's exact UI flow to extract tender documents.

Workflow (matching e-GP UI):
  1. Login → Dashboard
  2. Homepage → "Advance Search" tab
  3. Enter Tender ID → Search
  4. Click tender result → Tender Dashboard
  5. "Document" tab → Notice (NIT) → Extract/download
  6. "Tender Data Sheet" tab → Qualification Criteria → Extract all
  7. Store everything in TenderDataPool

Output per tender:
  - Notice (NIT): basic info, dates, amounts
  - TDS: qualification criteria (experience, turnover, equipment, personnel, licenses)
  - All stored in TenderDataPool → queriable by TenderDashboardAgent
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from app.crawlers.egp_crawler import EGPCrawler

logger = logging.getLogger(__name__)

# e-GP URLs
ALL_TENDERS_URL = "https://www.eprocure.gov.bd/resources/common/AllTenders.jsp?h=f"
DASHBOARD_URL = "https://www.eprocure.gov.bd/tenderer/TendererDashboard.jsp?tenderid={tender_id}"
DOCS_URL = "https://www.eprocure.gov.bd/tenderer/LotPckDocs.jsp?tab=1&tenderId={tender_id}"
DOCVIEW_URL = "https://www.eprocure.gov.bd/tenderer/TenderDocView.jsp?tenderId={tender_id}"
TDS_DASHBOARD_FRAGMENT = "TenderTDSDashBoard.jsp"
TDS_VIEW_FRAGMENT = "ViewTenderTDS.jsp"

# For older tenders (archived)
ARCHIVED_NOTICE_URL = "https://www.eprocure.gov.bd/tenderer/ArchivedViewNotice.jsp"
ARCHIVED_TDS_URL = "https://www.eprocure.gov.bd/tenderer/ArchivedViewTDS.jsp"


class EGPDocumentCrawler(EGPCrawler):
    """
    Crawls e-GP to extract ALL tender documents following the official UI flow.
    
    Uses Playwright for JavaScript-heavy pages (Advance Search, Tabs).
    Falls back to direct HTTP for simpler pages.
    """
    
    def __init__(self, email: str = "", password: str = "", cookies: Dict = None):
        super().__init__(email, password)
        if cookies:
            self._cookies = cookies
            self._login_success = True
    
    async def acquire_documents(self, tender_id: str) -> Dict[str, Any]:
        """
        Full document acquisition for a single tender.
        Follows e-GP UI flow: Login → Search → Document Tab → TDS → Extract
        """
        result = {
            "tender_id": tender_id,
            "status": "started",
            "notice": {},
            "tds": {},
            "boq": {},
            "documents": [],
            "error": None,
        }
        
        try:
            # Step 1: Ensure we're logged in
            if not self._login_success:
                logger.info(f"Logging in for document acquisition...")
                if self.email and self.password:
                    await self.login()
                if not self._login_success:
                    result["status"] = "login_required"
                    result["error"] = "Need login credentials or cookies"
                    return result
            
            # Step 2: Use browser to navigate the UI
            await self._browser_acquire(tender_id, result)
            
        except Exception as e:
            logger.error(f"Document acquisition failed for {tender_id}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result
    
    async def _browser_acquire(self, tender_id: str, result: Dict):
        """Use Playwright browser to navigate e-GP UI."""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self._headers["User-Agent"],
                viewport={"width": 1366, "height": 768},
            )
            
            # Add cookies if we have them
            if self._cookies:
                pw_cookies = []
                for name, value in self._cookies.items():
                    pw_cookies.append({
                        "name": name, "value": value,
                        "domain": ".eprocure.gov.bd", "path": "/",
                    })
                await context.add_cookies(pw_cookies)
            
            page = await context.new_page()
            page.set_default_timeout(30000)
            
            try:
                logger.info("🔍 Navigating directly to authenticated tender pages...")

                dashboard_url = DASHBOARD_URL.format(tender_id=tender_id)
                docs_url = DOCS_URL.format(tender_id=tender_id)
                docview_url = DOCVIEW_URL.format(tender_id=tender_id)

                await page.goto(dashboard_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                if "login" in page.url.lower() or "sessiontimedout" in page.url.lower():
                    logger.warning("Session expired. Need fresh login.")
                    result["status"] = "session_expired"
                    await browser.close()
                    return

                result["dashboard_url"] = page.url
                notice_data = await self._extract_notice_from_page(page)
                if notice_data:
                    result["notice"] = notice_data
                    result["documents"].append({
                        "type": "notice",
                        "format": "html",
                        "data": notice_data,
                        "url": page.url,
                    })

                await page.goto(docs_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                docs_html = await page.content()
                result["documents"].extend(self._extract_document_links(docs_html, "LotPckDocs"))

                await page.goto(docview_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                docview_html = await page.content()
                result["documents"].extend(self._extract_document_links(docview_html, "TenderDocView"))

                tds_data = await self._extract_tds_from_page(page)
                if tds_data:
                    result["tds"] = tds_data
                    result["documents"].append({
                        "type": "tds",
                        "format": "html",
                        "data": tds_data,
                        "url": page.url,
                    })

                boq_data = await self._extract_boq_from_page(page)
                if boq_data:
                    result["boq"] = boq_data
                    result["documents"].append({
                        "type": "boq",
                        "format": "html",
                        "data": boq_data,
                        "url": page.url,
                    })

                tds_links = [
                    link for link in result["documents"]
                    if TDS_DASHBOARD_FRAGMENT in str(link.get("url", "")) or TDS_VIEW_FRAGMENT in str(link.get("url", ""))
                ]
                if tds_links:
                    result["tds_links"] = tds_links
                
                # Step 8: Take screenshot for reference
                try:
                    screenshot_path = f"/tmp/egp_tender_{tender_id}.png"
                    await page.screenshot(path=screenshot_path)
                    result["screenshot"] = screenshot_path
                except Exception:
                    pass
                
                result["status"] = "completed"
                logger.info(f"✅ Document acquisition complete for {tender_id}")
                
            except Exception as e:
                logger.error(f"Browser error: {e}")
                result["status"] = "error"
                result["error"] = str(e)
                try:
                    await page.screenshot(path=f"/tmp/egp_error_{tender_id}.png")
                except Exception:
                    pass
            finally:
                await browser.close()
    
    async def _extract_notice_from_page(self, page) -> Dict:
        """Extract Notice (NIT) information from current page."""
        data = {}
        try:
            content = await page.content()
            
            # Try to find key fields in the page
            fields = {
                "tender_id": ["tender id", "tenderid", "tender_no", "tender number"],
                "package_no": ["package", "package no", "package number", "pkg"],
                "work_name": ["work name", "work", "description", "project name", "title"],
                "procuring_entity": ["procuring", "entity", "procurer", "department"],
                "pe_office": ["office", "address"],
                "zone": ["zone", "region", "circle"],
                "division": ["division"],
                "district": ["district"],
                "estimated_amount": ["estimated", "estimate", "cost", "budget", "amount"],
                "tender_security": ["security", "tender security", "bid security", "earnest"],
                "completion_period": ["completion", "period", "duration", "delivery", "time"],
                "closing_date": ["closing", "submission", "deadline", "last date"],
                "opening_date": ["opening", "open date", "date of opening"],
                "publication_date": ["publication", "publish", "issue date"],
            }
            
            html_lower = content.lower()
            for field, keywords in fields.items():
                for kw in keywords:
                    # Look for pattern: keyword followed by value
                    patterns = [
                        rf'{kw}[\s:]*</[^>]*>[\s]*<[^>]*>([^<]+)',
                        rf'{kw}[\s:]*([^<]+)',
                        rf'<td[^>]*>{kw}[\s:]*</td>\s*<td[^>]*>([^<]+)',
                        rf'<th[^>]*>{kw}[\s:]*</th>\s*<td[^>]*>([^<]+)',
                    ]
                    for pat in patterns:
                        m = re.search(pat, html_lower, re.I)
                        if m:
                            val = m.group(1).strip()
                            if val and len(val) > 1:
                                data[field] = val[:200]
                            break
                    if field in data:
                        break
            
            # Parse dates
            for date_field in ["closing_date", "opening_date", "publication_date"]:
                if date_field in data:
                    val = data[date_field]
                    # Try to parse various date formats
                    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"]:
                        try:
                            dt = datetime.strptime(re.sub(r'[^0-9a-zA-Z/\- ]', '', val)[:20], fmt)
                            data[date_field] = dt.isoformat()
                            break
                        except ValueError:
                            continue
            
            # Parse amounts
            for amount_field in ["estimated_amount", "tender_security"]:
                if amount_field in data:
                    nums = re.findall(r'[\d,]+', data[amount_field])
                    if nums:
                        try:
                            data[amount_field] = float(nums[0].replace(',', ''))
                        except ValueError:
                            pass
            
        except Exception as e:
            logger.warning(f"Notice extraction error: {e}")
        
        return data
    
    async def _extract_tds_from_page(self, page) -> Dict:
        """Extract Tender Data Sheet → Qualification Criteria."""
        data = {}
        try:
            content = await page.content()
            html_lower = content.lower()
            
            # Try to find TDS-specific sections
            sections = [
                "qualification criteria", "eligibility criteria", "qualification requirement",
                "experience required", "turnover", "liquid asset", "equipment",
                "personnel", "manpower", "key staff", "similar work",
                "tender capacity", "annual construction",
            ]
            
            # Extract table data if present
            tables = re.findall(r'<table[^>]*>(.*?)</table>', content, re.I | re.S)
            for tbl in tables:
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.I | re.S)
                for row in rows:
                    cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.I | re.S)
                    if len(cells) >= 2:
                        key = re.sub(r'<[^>]+>', '', cells[0]).strip().lower()
                        val = re.sub(r'<[^>]+>', '', cells[1]).strip()
                        
                        # Qualification criteria mapping
                        if "experience" in key and "year" in key:
                            nums = re.findall(r'\d+', val)
                            if nums: data["min_experience_years"] = int(nums[0])
                        elif "turnover" in key:
                            nums = re.findall(r'[\d,]+', val)
                            if nums: data["min_turnover_bdt"] = float(nums[0].replace(',', ''))
                        elif "liquid" in key or "working capital" in key:
                            nums = re.findall(r'[\d,]+', val)
                            if nums: data["min_liquid_assets_bdt"] = float(nums[0].replace(',', ''))
                        elif "construction" in key or "annual volume" in key:
                            nums = re.findall(r'[\d,]+', val)
                            if nums: data["min_annual_construction_volume"] = float(nums[0].replace(',', ''))
                        elif "similar" in key and "work" in key:
                            nums = re.findall(r'\d+', val)
                            if nums: data["similar_works_required"] = int(nums[0])
            
            # Extract equipment list
            equipment = []
            for pattern in [r'<li[^>]*>(.*?)</li>', r'<td[^>]*>(.*?)</td>']:
                items = re.findall(pattern, content, re.I | re.S)
                for item in items:
                    text = re.sub(r'<[^>]+>', '', item).strip()
                    equip_kw = ["excavator", "bulldozer", "compactor", "dredger", "truck", 
                                 "crane", "loader", "grader", "roller", "mixer", "vibrator",
                                 "generator", "pump", "welding", "bending", "testing"]
                    if any(kw in text.lower() for kw in equip_kw) and len(text) > 5:
                        equipment.append(text)
            if equipment:
                data["required_equipment"] = equipment
            
            # Extract personnel list
            personnel = []
            pers_kw = ["engineer", "manager", "surveyor", "officer", "supervisor", 
                       "technician", "accountant", "safety", "qa/qc", "quality"]
            for pattern in [r'<li[^>]*>(.*?)</li>', r'<td[^>]*>(.*?)</td>']:
                items = re.findall(pattern, content, re.I | re.S)
                for item in items:
                    text = re.sub(r'<[^>]+>', '', item).strip()
                    if any(kw in text.lower() for kw in pers_kw) and len(text) > 5:
                        personnel.append(text)
            if personnel:
                data["required_personnel"] = personnel
            
        except Exception as e:
            logger.warning(f"TDS extraction error: {e}")
        
        return data
    
    async def _extract_boq_from_page(self, page) -> Dict:
        """Extract BOQ items if available."""
        data = {"items": []}
        try:
            content = await page.content()
            
            # Look for BOQ table
            tables = re.findall(r'<table[^>]*>(.*?)</table>', content, re.I | re.S)
            for tbl in tables:
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.I | re.S)
                for row in rows[1:]:  # Skip header
                    cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.I | re.S)
                    if len(cells) >= 4:
                        item = {
                            "item_no": re.sub(r'<[^>]+>', '', cells[0]).strip(),
                            "description": re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else "",
                            "unit": re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else "",
                            "quantity": self._parse_num(cells[3]) if len(cells) > 3 else 0,
                        }
                        if len(cells) > 4:
                            item["rate"] = self._parse_num(cells[4])
                        if len(cells) > 5:
                            item["total_amount"] = self._parse_num(cells[5])
                        if item.get("description"):
                            data["items"].append(item)
            
            data["item_count"] = len(data["items"])
            data["total_amount"] = sum(i.get("total_amount", 0) or 0 for i in data["items"])
            
        except Exception as e:
            logger.warning(f"BOQ extraction error: {e}")
        
        return data
    
    def _parse_num(self, val) -> float:
        """Parse a number from HTML cell."""
        text = re.sub(r'<[^>]+>', '', val).strip()
        nums = re.findall(r'[\d,]+\.?\d*', text)
        if nums:
            try:
                return float(nums[0].replace(',', ''))
            except ValueError:
                pass
        return 0.0

    def _extract_document_links(self, html: str, source_page: str) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        for href, text in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            label = re.sub(r"<[^>]+>", "", text).strip()
            if not label and "TenderSecUploadServlet" not in href:
                continue
            lowered = f"{href} {label}".lower()
            doc_type = "other"
            if "tendertdsdashboard.jsp" in lowered or "viewtendertds.jsp" in lowered:
                doc_type = "tds"
            elif "bill of quantities" in lowered or "boq" in lowered:
                doc_type = "boq"
            elif "drawing" in lowered:
                doc_type = "drawing"
            elif "form" in lowered:
                doc_type = "forms"
            elif "download" in lowered or "tendersecuploadservlet" in lowered:
                doc_type = "download"
            documents.append({
                "name": label or href.split("/")[-1],
                "url": urljoin("https://www.eprocure.gov.bd", href),
                "type": doc_type,
                "source_page": source_page,
            })
        return documents
    
    def get_summary(self, result: Dict) -> Dict:
        """Get a human-readable summary of acquired document data."""
        notice = result.get("notice", {})
        tds = result.get("tds", {})
        boq = result.get("boq", {})
        
        return {
            "tender_id": result["tender_id"],
            "status": result["status"],
            "notice_fields": len(notice),
            "tds_fields": {
                "experience_years": tds.get("min_experience_years"),
                "turnover": tds.get("min_turnover_bdt"),
                "liquid_assets": tds.get("min_liquid_assets_bdt"),
                "equipment_items": len(tds.get("required_equipment", [])),
                "personnel_roles": len(tds.get("required_personnel", [])),
            },
            "boq_items": boq.get("item_count", 0),
            "documents_collected": len(result.get("documents", [])),
        }
