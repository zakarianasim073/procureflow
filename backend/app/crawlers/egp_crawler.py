"""
e-GP Bangladesh Portal Crawler — Opening Report Extraction Agent.
Crawls https://www.eprocure.gov.bd to extract archived tender opening reports.

Architecture:
  1. Login to e-GP with user credentials
  2. Navigate to "My Tenders" → "Archived" tab
  3. Collect all archived tender IDs (pagination)
  4. For each tender: extract opening report data
  5. Save as structured JSON in database
  6. Store raw PDFs to knowledge lake

Output Schema per Opening Report:
{
    "tender_id": "...",
    "package_no": "...",
    "work_name": "...",
    "pe_office": "...",
    "zone": "...",
    "opening_date": "...",
    "estimated_amount": 0.0,
    "bidders": [
        {
            "name": "...",
            "quoted_amount": 0.0,
            "discount_pct": 0.0,
            "discount_amount": 0.0,
            "final_amount": 0.0,
            "status": "responsive/non_responsive"
        }
    ],
    "winner": {"name": "...", "amount": 0.0},
    "has_slt": false,
    "has_alt": false
}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class BidderEntry:
    """Single bidder in an opening report."""
    rank: int = 0
    name: str = ""
    quoted_amount: float = 0.0
    discount_pct: float = 0.0
    discount_amount: float = 0.0
    final_amount: float = 0.0
    status: str = "responsive"  # responsive, non_responsive, slt, alt


@dataclass
class OpeningReport:
    """Complete opening report for one tender."""
    tender_id: str = ""
    package_no: str = ""
    work_name: str = ""
    pe_office: str = ""
    zone: str = ""
    opening_date: str = ""
    opening_place: str = ""
    estimated_amount: float = 0.0
    bidders: List[BidderEntry] = field(default_factory=list)
    winner: Optional[Dict] = None
    has_slt: bool = False
    has_alt: bool = False
    source_url: str = ""
    raw_html: str = ""
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OpeningReportExtractor:
    """Extract opening report data from HTML/JSON responses."""
    
    @staticmethod
    def extract_from_html(html: str, tender_id: str) -> Optional[OpeningReport]:
        """Extract opening report from HTML page."""
        report = OpeningReport(tender_id=tender_id)
        report.raw_html = html[:10000]  # Store first 10k chars
        
        if not html or len(html) < 100:
            return None
        
        # Try to extract from table structure
        try:
            # Find estimated amount
            est_match = re.search(
                r'(?:Estimated|Estimate|Official\s*Estimate)[^<]*?[:৳\s]*([\d,]+\.?\d*)',
                html, re.IGNORECASE
            )
            if est_match:
                report.estimated_amount = float(est_match.group(1).replace(",", ""))
            
            # Find opening date
            date_match = re.search(
                r'(?:Opening\s*Date|Date\s*of\s*Opening)[^<]*?(\d{1,2}[-/]\w{3}[-/]\d{4})',
                html, re.IGNORECASE
            )
            if date_match:
                report.opening_date = date_match.group(1)
            
            # Find PE Office
            pe_match = re.search(
                r'(?:PE\s*Office|Procuring\s*Entity|Office)[^<]*?[:]\s*([^<]+)',
                html, re.IGNORECASE
            )
            if pe_match:
                report.pe_office = pe_match.group(1).strip()
            
            # Find package/work name
            pkg_match = re.search(
                r'(?:Package\s*No|Package)[^<]*?[:]\s*([^<]+)',
                html, re.IGNORECASE
            )
            if pkg_match:
                report.package_no = pkg_match.group(1).strip()
            
            # Extract bidder table rows
            rows = re.findall(
                r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL
            )
            
            bidders = []
            for row_html in rows:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
                if len(cells) >= 4:
                    name = re.sub(r'<[^>]+>', '', cells[0]).strip()
                    quoted = re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else ""
                    discount = re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else ""
                    final = re.sub(r'<[^>]+>', '', cells[3]).strip() if len(cells) > 3 else ""
                    
                    if name and name not in ("Name", "Bidder Name", "SL"):
                        bidder = BidderEntry(
                            name=name,
                            quoted_amount=float(re.sub(r'[^\d.]', '', quoted) or 0),
                            final_amount=float(re.sub(r'[^\d.]', '', final) or 0),
                        )
                        # Calculate discount
                        if bidder.quoted_amount > 0 and bidder.final_amount > 0:
                            bidder.discount_amount = bidder.quoted_amount - bidder.final_amount
                            bidder.discount_pct = round(
                                bidder.discount_amount / bidder.quoted_amount * 100, 2
                            )
                        bidders.append(bidder)
            
            if bidders:
                report.bidders = bidders
                # Winner is first responsive bidder (usually lowest)
                if bidders:
                    report.winner = {
                        "name": bidders[0].name,
                        "amount": bidders[0].final_amount or bidders[0].quoted_amount,
                    }
            
            # Check SLT/ALT
            if "abnormally low" in html.lower() or "alt" in html.lower():
                report.has_alt = True
            if "seriously low" in html.lower() or "slt" in html.lower():
                report.has_slt = True
            
        except Exception as e:
            logger.warning(f"Error extracting opening report for {tender_id}: {e}")
        
        return report if report.bidders else None
    
    @staticmethod
    def extract_from_json(json_data: Dict) -> Optional[OpeningReport]:
        """Extract opening report from JSON API response."""
        report = OpeningReport(
            tender_id=str(json_data.get("tender_id", json_data.get("id", ""))),
            package_no=str(json_data.get("package_no", json_data.get("package", ""))),
            work_name=str(json_data.get("work_name", json_data.get("title", json_data.get("name", "")))),
            pe_office=str(json_data.get("pe_office", json_data.get("procuring_entity", ""))),
            zone=str(json_data.get("zone", json_data.get("division", ""))),
            opening_date=str(json_data.get("opening_date", json_data.get("open_date", ""))),
            estimated_amount=float(json_data.get("estimated_amount", json_data.get("estimated_amount_bdt", 0)) or 0),
        )
        
        # Extract bidders
        bidders_data = json_data.get("bidders", json_data.get("responsive_bidders", []))
        if isinstance(bidders_data, list):
            for i, b in enumerate(bidders_data):
                if isinstance(b, dict):
                    bidder = BidderEntry(
                        rank=i + 1,
                        name=str(b.get("bidder_name", b.get("name", b.get("company", "")))),
                        quoted_amount=float(b.get("quoted_amount", b.get("amount", b.get("bid_amount", 0))) or 0),
                        discount_pct=float(b.get("discount_pct", b.get("discount_percent", 0)) or 0),
                        discount_amount=float(b.get("discount_amount", b.get("discount", 0)) or 0),
                        final_amount=float(b.get("final_amount", b.get("total", 0)) or 0),
                        status=str(b.get("status", "responsive")),
                    )
                    # Auto-calculate discount if missing
                    if bidder.discount_amount == 0 and bidder.quoted_amount > 0 and bidder.final_amount > 0:
                        bidder.discount_amount = bidder.quoted_amount - bidder.final_amount
                        if bidder.quoted_amount > 0:
                            bidder.discount_pct = round(bidder.discount_amount / bidder.quoted_amount * 100, 2)
                    report.bidders.append(bidder)
        
        # Extract winner
        winner_data = json_data.get("winner", {})
        if isinstance(winner_data, dict):
            report.winner = {
                "name": str(winner_data.get("bidder_name", winner_data.get("name", ""))),
                "amount": float(winner_data.get("quoted_amount", winner_data.get("amount", 0)) or 0),
            }
        elif report.bidders:
            report.winner = {
                "name": report.bidders[0].name,
                "amount": report.bidders[0].final_amount or report.bidders[0].quoted_amount,
            }
        
        # Check SLT/ALT
        for b in report.bidders:
            if "slt" in b.status.lower():
                report.has_slt = True
            if "alt" in b.status.lower():
                report.has_alt = True
        
        return report


class EGPCrawler:
    """
    Crawler for e-GP Bangladesh portal.
    Handles login, navigation, and data extraction.
    Uses requests/httpx for API calls with browser-like headers.
    """
    
    BASE_URL = "https://www.eprocure.gov.bd"
    LOGIN_URL = f"{BASE_URL}/auth/login"
    MY_TENDERS_URL = f"{BASE_URL}/tender/my-tenders"
    ARCHIVED_URL = f"{BASE_URL}/tender/my-tenders?tab=archived"
    OPENING_REPORT_URL = f"{BASE_URL}/tender/opening-report/{{tender_id}}"
    
    def __init__(self, email: str = "", password: str = ""):
        self.email = email
        self.password = password
        self.session = None
        self._cookies = {}
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
            "Accept": "text/html,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
        }
        self._login_success = False
        self._total_tenders_found = 0
        self._total_reports_extracted = 0
        self._use_playwright = False
    
    def set_credentials(self, email: str, password: str):
        """Set e-GP login credentials."""
        self.email = email
        self.password = password
        logger.info(f"Credentials set for {email}")
    
    async def login(self) -> bool:
        """
        Login to e-GP portal.
        Uses httpx for API-based auth or playwright for browser automation.
        """
        if not self.email or not self.password:
            logger.error("No credentials provided for e-GP login")
            return False
        
        logger.info(f"Attempting e-GP login for {self.email}...")
        
        # Try API-based login first
        import httpx
        
        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                follow_redirects=True,
                timeout=30.0,
            ) as client:
                # Get login page for CSRF token
                resp = await client.get(self.LOGIN_URL)
                csrf_token = self._extract_csrf(resp.text)
                
                # Attempt login
                login_data = {
                    "email": self.email,
                    "password": self.password,
                    "_token": csrf_token,
                }
                resp = await client.post(
                    self.LOGIN_URL,
                    data=login_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                
                self._cookies = dict(resp.cookies)
                
                if "dashboard" in resp.url.path.lower() or "my-tenders" in resp.url.path.lower():
                    self._login_success = True
                    self.session = client
                    logger.info(f"✅ Login successful for {self.email}")
                    return True
                
                # Check if login form still present
                if "login" in resp.url.path.lower() or "Invalid" in resp.text:
                    logger.warning("API login failed, credentials may need browser-based login")
                    self._use_playwright = True
        
        except Exception as e:
            logger.error(f"API login error: {e}")
        
        # Fallback: instructions for Playwright-based login
        if self._use_playwright:
            logger.info(
                "Browser-based login required. "
                "Use the Playwright script at crawlers/egp_playwright.py "
                "or manually login in Chrome and export cookies."
            )
        
        return False
    
    def _extract_csrf(self, html: str) -> str:
        """Extract CSRF token from HTML."""
        match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
            html
        )
        if match:
            return match.group(1)
        
        match = re.search(
            r'<input[^>]*name="_token"[^>]*value="([^"]+)"',
            html
        )
        if match:
            return match.group(1)
        
        return ""
    
    async def get_archived_tenders(self, max_pages: int = 100) -> List[Dict]:
        """Get list of archived tenders from My Tenders page."""
        if not self._login_success and not self._use_playwright:
            logger.warning("Not logged in. Call login() first.")
            return []
        
        all_tenders = []
        
        if self._login_success and self.session:
            import httpx
            client = self.session
            
            for page in range(1, max_pages + 1):
                try:
                    resp = await client.get(
                        self.ARCHIVED_URL,
                        params={"page": page, "per_page": 50},
                    )
                    
                    if resp.status_code != 200:
                        logger.warning(f"Page {page}: HTTP {resp.status_code}")
                        break
                    
                    # Parse JSON or HTML
                    try:
                        data = resp.json()
                        tenders = data.get("data", data.get("tenders", []))
                        if not tenders:
                            break
                        all_tenders.extend(tenders)
                    except (json.JSONDecodeError, AttributeError):
                        # Parse HTML table
                        tenders = self._parse_tender_table(resp.text)
                        if not tenders:
                            break
                        all_tenders.extend(tenders)
                    
                    logger.info(f"Page {page}: {len(tenders)} archived tenders")
                    
                    if len(tenders) < 50:
                        break  # Last page
                    
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}")
                    break
        
        self._total_tenders_found = len(all_tenders)
        logger.info(f"Found {len(all_tenders)} archived tenders total")
        return all_tenders
    
    def _parse_tender_table(self, html: str) -> List[Dict]:
        """Parse tender table from HTML."""
        tenders = []
        try:
            rows = re.findall(
                r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL
            )
            for row_html in rows:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
                if len(cells) >= 2:
                    tender_id_match = re.search(
                        r'(?:egp|EGP|tender)[-/]?(\d+)',
                        cells[0], re.IGNORECASE
                    )
                    tender_id = tender_id_match.group(0) if tender_id_match else ""
                    
                    if tender_id:
                        tenders.append({
                            "tender_id": tender_id,
                            "title": re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else "",
                            "raw_html": row_html[:500],
                        })
        except Exception as e:
            logger.warning(f"Error parsing tender table: {e}")
        
        return tenders
    
    async def extract_opening_report(self, tender_id: str) -> Optional[OpeningReport]:
        """Extract opening report for a specific tender."""
        if not self._login_success and not self.session:
            logger.warning("Not logged in")
            return None
        
        url = self.OPENING_REPORT_URL.format(tender_id=tender_id)
        logger.info(f"Extracting opening report for {tender_id}...")
        
        try:
            resp = await self.session.get(url)
            
            if resp.status_code != 200:
                logger.warning(f"  {tender_id}: HTTP {resp.status_code}")
                return None
            
            content_type = resp.headers.get("content-type", "")
            
            if "json" in content_type:
                data = resp.json()
                report = OpeningReportExtractor.extract_from_json(data)
            else:
                report = OpeningReportExtractor.extract_from_html(resp.text, tender_id)
            
            if report and report.bidders:
                self._total_reports_extracted += 1
                logger.info(f"  ✓ {tender_id}: {len(report.bidders)} bidders, ${report.estimated_amount:.0f}")
                return report
            else:
                logger.warning(f"  ✗ {tender_id}: No bidder data found")
                return None
        
        except Exception as e:
            logger.error(f"  ✗ {tender_id}: Error - {e}")
            return None
    
    async def crawl_all_archived(self, db_session=None, 
                                  max_tenders: int = 1000,
                                  max_pages: int = 100) -> List[Dict]:
        """
        Main crawl method: login → get archived list → extract opening reports.
        
        Returns:
            List of opening report dicts
        """
        if not self._login_success:
            success = await self.login()
            if not success:
                logger.error("Cannot crawl: login failed")
                return []
        
        # Get archived tenders list
        archived = await self.get_archived_tenders(max_pages=max_pages)
        
        if not archived:
            logger.warning("No archived tenders found")
            return []
        
        # Limit
        if len(archived) > max_tenders:
            logger.info(f"Limiting to {max_tenders} tenders (found {len(archived)})")
            archived = archived[:max_tenders]
        
        # Extract opening reports
        reports = []
        for i, tender in enumerate(archived):
            tender_id = ""
            if isinstance(tender, dict):
                tender_id = tender.get("tender_id", tender.get("id", ""))
            else:
                tender_id = str(tender)
            
            if not tender_id:
                continue
            
            report = await self.extract_opening_report(tender_id)
            if report:
                report_dict = asdict(report)
                reports.append(report_dict)
                
                # Save to database if session provided
                if db_session:
                    await self._save_to_db(report_dict, db_session)
            
            # Progress logging
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i+1}/{len(archived)} processed")
            
            # Rate limiting
            await asyncio.sleep(0.5)
        
        logger.info(
            f"✅ Crawl complete: {len(reports)} opening reports extracted "
            f"from {len(archived)} archived tenders"
        )
        
        return reports
    
    async def _save_to_db(self, report: Dict, session):
        """Save opening report to database."""
        try:
            from app.db import OpeningReport as OpeningReportModel, Tender
            from sqlalchemy import select
            
            tender_id = report.get("tender_id", "")
            if not tender_id:
                return

            tender_exists = await session.execute(
                select(Tender).where(Tender.tender_id == tender_id)
            )
            if tender_exists.scalar_one_or_none() is None:
                return
            
            # Check if exists
            result = await session.execute(
                select(OpeningReportModel).where(
                    OpeningReportModel.tender_id == tender_id
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return
            
            db_report = OpeningReportModel(
                tender_id=tender_id,
                package_no=report.get("package_no", ""),
                package_work_name=report.get("work_name", ""),
                pe_office=report.get("pe_office", ""),
                zone=report.get("zone", ""),
                estimated_amount_bdt=report.get("estimated_amount", 0),
                bidders=report.get("bidders", []),
                winner_name=report.get("winner", {}).get("name", ""),
                winner_amount=report.get("winner", {}).get("amount", 0),
                has_slt=report.get("has_slt", False),
                has_alt=report.get("has_alt", False),
                is_archived=True,
                raw_data=report,
            )
            session.add(db_report)
            await session.commit()
        except Exception as e:
            logger.warning(f"Error saving {report.get('tender_id', '')} to DB: {e}")
    
    def save_reports_to_json(self, reports: List[Dict], output_dir: str = None):
        """Save extracted reports to JSON files."""
        output_dir = output_dir or os.path.join(
            os.getcwd(), "runtime", "knowledge", "opening_reports"
        )
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Save individual files
        for report in reports:
            tender_id = report.get("tender_id", "unknown")
            fp = os.path.join(output_dir, f"opening_{tender_id}.json")
            with open(fp, "w") as f:
                json.dump(report, f, indent=2, default=str)
        
        # Save combined file
        combined_fp = os.path.join(output_dir, "_all_opening_reports.json")
        with open(combined_fp, "w") as f:
            json.dump(reports, f, indent=2, default=str)
        
        logger.info(f"Saved {len(reports)} opening reports to {output_dir}")


# ── Playwright-based Crawler (for full browser automation) ──────────────

class EGPlaywrightCrawler(EGPCrawler):
    """
    Extended crawler using Playwright for JavaScript-heavy pages.
    Requires: pip install playwright
    """
    
    async def login_with_browser(self) -> bool:
        """Login using Playwright (browser automation)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        
        logger.info(f"Launching browser for e-GP login as {self.email}...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self._headers["User-Agent"],
                viewport={"width": 1366, "height": 768},
            )
            page = await context.new_page()
            
            try:
                # Go to login page
                await page.goto(self.LOGIN_URL, wait_until="networkidle")
                await page.wait_for_timeout(2000)
                
                # Fill credentials
                await page.fill('input[type="email"], input[name="email"]', self.email)
                await page.fill('input[type="password"], input[name="password"]', self.password)
                
                # Click login
                await page.click('button[type="submit"], input[type="submit"]')
                await page.wait_for_timeout(5000)
                
                # Check if login succeeded
                if "dashboard" in page.url.lower() or "my-tenders" in page.url.lower():
                    self._login_success = True
                    
                    # Export cookies for API calls
                    cookies = await context.cookies()
                    self._cookies = {c["name"]: c["value"] for c in cookies}
                    
                    logger.info(f"✅ Browser login successful for {self.email}")
                    await browser.close()
                    return True
                
                logger.warning(f"Browser login failed. URL after login: {page.url}")
                await page.screenshot(path="/tmp/egp_login_failed.png")
                
            except Exception as e:
                logger.error(f"Browser login error: {e}")
            finally:
                await browser.close()
        
        return False


# ── Credential-Safe Runner ──────────────────────────────────────────────

def create_crawler_from_env() -> EGPCrawler:
    """Create crawler using credentials from environment."""
    email = os.getenv("EGP_EMAIL", "")
    password = os.getenv("EGP_PASSWORD", "")
    return EGPCrawler(email=email, password=password)
