"""
eGP Bangladesh Portal Client — Complete e-GP Portal Integration
==============================================================
Handles authentication, tender search, document download, and
complete portal navigation for www.eprocure.gov.bd.

PORTAL STRUCTURE (www.eprocure.gov.bd):
=======================================

PUBLIC SECTIONS (No Login Required):
------------------------------------
  Home             /                                          — Main portal page
  Advance Search   /resources/common/AllTenders.jsp?h=t       — All Tenders with 4 tabs:
                                                                  • Live (viewType=Live)
                                                                  • Archive (viewType=Archive)  
                                                                  • AllTenders (viewType=AllTenders)
                                                                  • Cancel (viewType=Cancel)
  eTenders         /resources/common/StdTenderSearch.jsp?h=t  — Standard search (4 tabs)
  APP              /resources/common/SearchAPP.jsp            — Annual Procurement Plans
  eContracts/NOA   /resources/common/SearchNOA.jsp            — Notification of Award
  Offline Tenders  /resources/common/SearchTenderOffline.jsp  — Offline published tenders
  Offline Awards   /resources/common/SearchAwardedContractOffline.jsp
  Debarred         /resources/common/DebarmentRpt.jsp         — Debarred tenderers list
  Tender Details   /resources/common/ViewTender.jsp?id=X     — View specific tender details
  
PUBLIC AJAX ENDPOINTS (No Login Required):
------------------------------------------
  POST /TenderDetailsServlet   — Main tender data (JSON/HTML)     params: funName, viewType, pageNo, size, h=t
  POST /SearchNoaServlet       — NOA award data                   params: keyword, pageNo, size
  POST /SearchAPPServlet       — APP data                         params: action=advSearch, pageNo, size, keyWord

AUTHENTICATED SECTIONS (Login Required):
----------------------------------------
  My Dashboard     /resources/common/InboxMessage.jsp       — User dashboard
  eExperience      /resources/common/SearcheCMS.jsp?v=advSearch  — eCMS/eExperience
  Advance APP      /resources/common/AdvAPPSearch.jsp       — Advanced APP search
  Advance NOA      /resources/common/AdvSearchNOA.jsp       — Advanced NOA search
  My Tender        (via dashboard/InboxMessage)             — Purchased schedule tenders
  Contract Signing (via tender dashboard)                   — Contract award & signing

AUTH FLOW:
----------
  1. GET  /                                          → Seed JSESSIONID
  2. POST /LoginSrBean?action=checkLogin             → emailId, password
  3. Redirect to /UpdateMobileNid.jsp or             → Mobile NID update (bypass)
     /UpdateUpazila.jsp                              → Upazila update (bypass)
  4. GET  /Index.jsp                                 → Bypass & confirm login
  
TENDER DOCUMENTS & DOWNLOADS (Authenticated):
----------------------------------------------
  Tender Dashboard:  /resources/common/ViewTender.jsp?id=TENDER_ID
  Documents Tab:     Contains all tender documents:
                     • NIT (Notice Inviting Tender)
                     • TDC (Tender Data Card)
                     • GCC (General Conditions of Contract)
                     • PCC (Particular Conditions of Contract)
                     • BOQ (Bill of Quantities)
                     • Drawings/Designs
                     • Schedules & Formats
                     • Corrigendum/Addendum
  Download:          /DownloadDocumentServlet?param=...
  
CONTRACT SIGNING SECTION:
-------------------------
  Accessible from tender dashboard after award:
  • Contract agreement forms
  • Performance security
  • Advance payment documents
  • Contract signing details
  • Mapped documents & information

USAGE:
------
  # Public access (no login):
  client = eGPClient()
  client.search_tender('keyword')       # Search all tenders
  client.search_noa('', 'Ministry')    # Search awards
  client.search_all_tenders()           # Search all 4 tabs
  client.search_app('keyword')          # Search APP
  
  # Authenticated access:
  client = eGPClient(email='x', password='y')
  client.login()                        # Login
  client.search_my_tender('')           # My purchased tenders
  client.download_document('id', 'BOQ') # Download documents
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlencode

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.eprocure.gov.bd"
DISTRICTS_BD = [
    "Bagerhat", "Bandarban", "Barguna", "Barishal", "Bhola", "Bogra",
    "Brahmanbaria", "Chandpur", "Chattogram", "Chuadanga", "Comilla",
    "Cox.s Bazar", "Dhaka", "Dinajpur", "Faridpur", "Feni", "Gaibandha",
    "Gazipur", "Gopalganj", "Habiganj", "Jamalpur", "Jashore", "Jhalokati",
    "Jhenaidah", "Joypurhat", "Khagrachari", "Khulna", "Kishoreganj",
    "Kurigram", "Kushtia", "Lakshmipur", "Lalmonirhat", "Madaripur",
    "Magura", "Manikganj", "Meherpur", "Moulvibazar", "Munshiganj",
    "Mymensingh", "Naogaon", "Narail", "Narayanganj", "Narsingdi",
    "Natore", "Nawabganj", "Netrokona", "Nilphamari", "Noakhali",
    "Pabna", "Panchagarh", "Patuakhali", "Pirojpur", "Rajbari",
    "Rajshahi", "Rangamati", "Rangpur", "Satkhira", "Shariatpur",
    "Sherpur", "Sirajganj", "Sunamganj", "Sylhet", "Tangail", "Thakurgaon",
]


@dataclass
class TenderInfo:
    tender_id: str
    title: str = ""
    procuring_entity: str = ""
    published_date: str = ""
    deadline: str = ""
    estimated_value_bdt: float = 0.0
    category: str = ""
    location: str = ""
    document_fees: str = ""
    bid_security: str = ""
    status: str = ""


@dataclass
class eGPSession:
    jsessionid: str = ""
    cptu_cookie: str = ""
    is_authenticated: bool = False
    user_email: str = ""
    last_login_attempt: float = 0.0


class eGPClient:
    """
    Client for interacting with the eGP Bangladesh portal.
    Handles sessions, login (with MobileNID bypass), tender search, and document fetching.
    """

    def __init__(self, email: str = "", password: str = "", timeout: int = 30):
        self.email = email
        self.password = password
        self.timeout = timeout
        self.session = eGPSession()
        self._client: Optional[httpx.Client] = None
        self._login_attempts = 0
        self._max_retries = 3

    # ── HTTP Client ──────────────────────────────────────────────────────

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                verify=False,
                follow_redirects=True,
                timeout=self.timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )
        return self._client

    # ── Session Management ───────────────────────────────────────────────

    def _update_session_from_response(self, response: httpx.Response) -> None:
        for name, value in response.cookies.items():
            if name == "JSESSIONID":
                self.session.jsessionid = value
            elif name == "CPTU-COOKIE":
                self.session.cptu_cookie = value

    def set_credentials(self, email: str, password: str) -> None:
        self.email = email
        self.password = password

    # ── Login (with MobileNID bypass) ────────────────────────────────────

    def login(self) -> bool:
        """
        Authenticate with the eGP portal.
        
        Modern flow:
        1. GET main page → seed JSESSIONID
        2. POST credentials → redirect to UpdateMobileNid.jsp
        3. GET Index.jsp → bypass the MobileNID verification
        
        Returns True if session is authenticated.
        """
        if self.session.is_authenticated:
            return True

        if not self.email or not self.password:
            logger.warning("eGP credentials not provided — using public access only")
            return False

        self._login_attempts += 1
        logger.info(f"Logging in to eGP as {self.email}")

        try:
            # Step 1: Get main page (seed session)
            resp = self.client.get(BASE_URL)
            self._update_session_from_response(resp)
            logger.debug(f"Session initialized: JSESSIONID={self.session.jsessionid[:20]}...")

            # Step 2: POST login
            login_data = {
                "emailId": self.email,
                "password": self.password,
            }
            resp = self.client.post(
                f"{BASE_URL}/LoginSrBean?action=checkLogin",
                data=login_data,
            )
            self._update_session_from_response(resp)

            # Check if login was successful
            if resp.status_code == 200 and ("logout" in resp.text.lower() or "dashboard" in resp.text.lower()):
                self.session.is_authenticated = True
                self.session.user_email = self.email
                self.session.last_login_attempt = time.time()
                logger.info("✅ eGP login successful (direct)")
                return True

            # Step 3: Handle MobileNID redirect — navigate to Index.jsp to bypass
            if "invalidMobNid" in str(resp.url) or "UpdateMobileNid" in str(resp.url):
                logger.info("MobileNID page shown — bypassing via Index.jsp")
                resp2 = self.client.get(f"{BASE_URL}/Index.jsp")
                self._update_session_from_response(resp2)
                
                if resp2.status_code == 200:
                    # Check if we're now logged in
                    has_dashboard = "dashboard" in resp2.text.lower()
                    has_logout = "logout" in resp2.text.lower()
                    
                    if has_dashboard or has_logout:
                        self.session.is_authenticated = True
                        self.session.user_email = self.email
                        self.session.last_login_attempt = time.time()
                        logger.info("✅ eGP login successful (bypassed MobileNID)")
                        return True
                    
                    logger.warning("Index.jsp loaded but may not be authenticated")
                    return False

            # Fallback: check response
            if "login" in resp.text.lower() and ("invalid" in resp.text.lower() or "failed" in resp.text.lower()):
                logger.warning("Login credentials rejected")
                return False

            logger.warning(f"Login may have failed (redirect: {resp.url})")
            return False

        except httpx.TimeoutException:
            logger.warning(f"eGP login timed out (attempt {self._login_attempts}/{self._max_retries})")
            if self._login_attempts < self._max_retries:
                time.sleep(1)
                return self.login()
            return False
        except Exception as exc:
            logger.error(f"eGP login error: {exc}")
            return False

    def logout(self) -> None:
        """End the eGP session."""
        try:
            self.client.get(f"{BASE_URL}/Logout.jsp")
        except Exception:
            pass
        self.session = eGPSession()
        self._client = None
        logger.info("Logged out of eGP")

    # ── Public Tender Search (no login required) ─────────────────────────

    def search_tender_public(self, keyword: str) -> List[TenderInfo]:
        """Search for tenders using the public offline search (fallback)."""
        logger.info(f"Public search for: {keyword}")
        try:
            resp = self.client.post(
                f"{BASE_URL}/resources/common/SearchTenderOffline.jsp",
                data={"txtKeyword": keyword,
                    "crntTab": "tenderTab", "fromHome": "true"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
                timeout=min(self.timeout, 15),
            )
            # If we got a redirect (302), the session may have expired
            if resp.status_code in (302, 303, 307, 308):
                logger.warning(f"Public search redirected to {resp.headers.get('Location', 'unknown')}")
                return []
            results = self._parse_tender_list(resp.text)
            if results:
                logger.info(f"Public search found {len(results)} tenders")
                return results
            return []
        except httpx.TimeoutException:
            logger.warning(f"Public search timed out for '{keyword}'")
            return []
        except Exception as exc:
            logger.error(f"Public search failed: {exc}")
            return []

    # ── Authenticated Tender Search ──────────────────────────────────────

    def search_tender(self, keyword: str, page: int = 1, size: int = 100) -> List[TenderInfo]:
        """Search for tenders using the eGP TenderDetailsServlet.

        Works without authentication (public access).
        Matches the actual AJAX call made by AllTenders.jsp:
          $.post('/TenderDetailsServlet', { funName: 'AllTenders', viewType: ...,
            tenderId: ..., refNo: ..., pageNo: '1', size: '50' })

        Args:
            keyword: Search keyword or tender ID.
            page: Page number for pagination (default 1).
            size: Results per page (default 100).
        """
        # Ensure session is initialized
        if not self.session.jsessionid:
            try:
                self.client.get(BASE_URL)
            except Exception:
                pass

        logger.info(f"Searching tenders for: {keyword or '(all active)'} (page={page}, size={size})")

        for attempt in range(self._max_retries):
            try:
                resp = self.client.post(
                    f"{BASE_URL}/TenderDetailsServlet",
                    data={
                        "funName": "AllTenders",
                        "viewType": "Live",
                        "departmentId": "",
                        "office": "",
                        "procNature": "",
                        "procType": "",
                        "procMethod": "0",
                        "tenderId": keyword if keyword and keyword.isdigit() else "0",
                        "refNo": keyword if keyword and not keyword.isdigit() else "",
                        "pubDtFrm": "",
                        "pubDtTo": "",
                        "closeDtFrm": "",
                        "closeDtTo": "",
                        "cpvCategory": "",
                        "isFrame": "0",
                        "pageNo": str(page),
                        "size": str(size),
                        "h": "t",
                    },
                    timeout=min(self.timeout * 2, 60),
                )
                
                # TenderDetailsServlet may return empty if session is invalid
                if len(resp.text) < 100:
                    # Re-seed session and retry
                    self.client.get(BASE_URL)
                    resp = self.client.post(
                        f"{BASE_URL}/TenderDetailsServlet",
                        data={
                            "funName": "AllTenders",
                            "viewType": "Live",
                            "procMethod": "0",
                            "tenderId": "0",
                            "isFrame": "0",
                            "pageNo": str(page),
                            "size": str(size),
                            "h": "t",
                        },
                        timeout=min(self.timeout * 2, 60),
                    )
                
                results = self._parse_tender_list(resp.text)
                logger.info(f"Tender search found {len(results)} tenders for '{keyword}' (page={page})")
                return results
            except httpx.TimeoutException:
                if attempt < self._max_retries - 1:
                    logger.warning(f"Tender search timeout, retrying ({attempt + 1}/{self._max_retries})")
                    time.sleep(1)
                else:
                    logger.warning(f"Tender search timed out after {self._max_retries} attempts")
                    return []
            except Exception as exc:
                logger.error(f"Tender search failed: {exc}")
                return []

    # ── Get Tender by ID ─────────────────────────────────────────────────

    # ── Search All Tenders (Multi-Tab) ──────────────────────────────

    def search_all_tenders(self, keyword: str = "", days: int = 30) -> Dict[str, List[TenderInfo]]:
        """Search tenders across all tabs: Live, Archive, AllTenders, Cancel.
        
        This mirrors the AllTenders.jsp advance search page tabs.
        All tabs are accessible without authentication.
        """
        results = {"live": [], "archive": [], "all": [], "cancel": []}
        
        # Initialize session
        if not self.session.jsessionid:
            try:
                self.client.get(BASE_URL)
            except Exception:
                pass
        
        view_types = {
            "live": "Live",
            "archive": "Archive",
            "all": "AllTenders",
            "cancel": "Cancel",
        }
        
        for key, view_type in view_types.items():
            try:
                resp = self.client.post(
                    f"{BASE_URL}/TenderDetailsServlet",
                    data={
                        "funName": "AllTenders",
                        "viewType": view_type,
                        "departmentId": "",
                        "office": "",
                        "procNature": "",
                        "procType": "",
                        "procMethod": "0",
                        "tenderId": "0",
                        "refNo": "",
                        "pubDtFrm": "",
                        "pubDtTo": "",
                        "closeDtFrm": "",
                        "closeDtTo": "",
                        "cpvCategory": "",
                        "isFrame": "0",
                        "pageNo": "1",
                        "size": "100",
                        "h": "t",
                    },
                    timeout=min(self.timeout * 2, 60),
                )
                
                if resp.status_code == 200 and len(resp.text) > 100:
                    tenders = self._parse_tender_list(resp.text)
                    results[key] = tenders
                    logger.info(f"Found {len(tenders)} tenders in '{view_type}' tab")
                else:
                    logger.debug(f"No data for tab '{view_type}' (len={len(resp.text)})")
            except Exception as exc:
                logger.debug(f"Error searching tab '{view_type}': {exc}")
        
        return results

    def search_my_tender(self, keyword: str) -> List[TenderInfo]:
        """Search for tenders in My Tender (schedule tenders purchased from bank)."""
        if not self.session.is_authenticated:
            if not self.login():
                return []

        logger.info(f"Searching My Tender for: {keyword}")

        for attempt in range(self._max_retries):
            try:
                resp = self.client.post(
                    f"{BASE_URL}/TenderDetailsServlet",
                    data={
                        "funName": "MyTender",
                        "viewType": "MyTender",
                        "pageNo": "1",
                        "size": "50",
                    },
                    timeout=min(self.timeout * 2, 60),
                )
                results = self._parse_tender_list(resp.text)
                logger.info(f"My Tender search found {len(results)} tenders for '{keyword}'")
                return results
            except httpx.TimeoutException:
                if attempt < self._max_retries - 1:
                    logger.warning(f"My Tender search timeout, retrying ({attempt + 1}/{self._max_retries})")
                    time.sleep(2)
                else:
                    logger.warning(f"My Tender search timed out for '{keyword}' after {self._max_retries} attempts")
                    return []
            except Exception as exc:
                logger.error(f"My Tender search failed: {exc}")
                return []

    def get_tender_by_id(self, tender_id: str) -> Optional[TenderInfo]:
        """Search for a specific tender by its ID across all available sources."""
        tender_id = str(tender_id).strip()
        logger.info(f"Looking up tender: {tender_id}")

        # Step 1: Try My Tender first (tenders purchased from bank)
        if self.session.is_authenticated or self.login():
            results = self.search_my_tender(tender_id)
            for t in results:
                if tender_id == t.tender_id or tender_id in t.tender_id:
                    return t

        # Step 2: Try fetching all live tenders and filter locally
        if self.session.is_authenticated or self.login():
            try:
                # Fetch a large batch of tenders with empty params
                resp = self.client.post(
                    f"{BASE_URL}/TenderDetailsServlet",
                    data={
                        "funName": "AllTenders",
                        "viewType": "AllTenders",
                        "pageNo": "1",
                        "size": "100",
                    },
                    timeout=min(self.timeout * 2, 60),
                )
                results = self._parse_tender_list(resp.text)
                for t in results:
                    if tender_id == t.tender_id:
                        logger.info(f"Found tender {tender_id} in live list: {t.title[:50]}")
                        return t
                logger.info(f"Tender {tender_id} not found in current live tenders list")
            except Exception as exc:
                logger.warning(f"Could not fetch tender list: {exc}")

        # Step 3: Try to fetch tender details from dashboard/view page
        try:
            details = self._get_tender_details_page(tender_id)
            if details:
                return details
        except Exception as exc:
            logger.debug(f"Could not fetch tender details page: {exc}")

        # Step 4: Fallback to public search (offline)
        try:
            results = self.search_tender_public(tender_id)
            for t in results:
                if tender_id == t.tender_id or tender_id in t.tender_id:
                    return t
            if results:
                return results[0]
        except Exception as exc:
            logger.debug(f"Public search failed: {exc}")

        logger.info(f"Tender {tender_id} not found in any source")
        return None

    def _get_tender_details_page(self, tender_id: str) -> Optional[TenderInfo]:
        """Fetch tender details from ViewTender.jsp with full table parsing."""
        try:
            resp = self.client.post(
                f"{BASE_URL}/resources/common/ViewTender.jsp",
                data={"id": tender_id, "h": "t"},
                timeout=self.timeout,
            )
            if resp.status_code == 200 and len(resp.text) > 1000:
                tender = self._parse_view_tender(resp.text, tender_id)
                if tender and tender.tender_id:
                    return tender
        except Exception as exc:
            logger.debug(f"Could not fetch tender details page: {exc}")
        return None

    def get_archived_my_tenders(self, page_no: int = 1, size: int = 50) -> List[Dict[str, Any]]:
        """Fetch archived tenders from My Tenders."""
        if not self.session.is_authenticated and not self.login():
            return []

        try:
            self.client.get(f"{BASE_URL}/tenderer/MyTenders.jsp", timeout=min(self.timeout * 2, 60))
        except Exception:
            pass

        resp = self.client.post(
            f"{BASE_URL}/TenderDetailsServlet",
            data={
                "funName": "MyTenders",
                "action": "get tenderermytenders",
                "statusTab": "Archive",
                "status": "Approved",
                "tenderId": "",
                "refNo": "",
                "procNature": "",
                "procType": "",
                "procMethod": "0",
                "pageNo": str(page_no),
                "size": str(size),
            },
            headers={
                "Referer": f"{BASE_URL}/tenderer/MyTenders.jsp",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=min(self.timeout * 2, 60),
        )
        if resp.status_code != 200 or len(resp.text) < 100:
            return []
        return self._parse_archived_my_tenders(resp.text)

    def get_opening_report_tor2(
        self,
        tender_id: str,
        lot_id: str = "0",
        include_pdf: bool = True,
        include_archive_lookup: bool = False,
    ) -> Dict[str, Any]:
        """Fetch archived tender opening report via TOR2/TORR2 route."""
        result: Dict[str, Any] = {
            "tender_id": str(tender_id).strip(),
            "lot_id": str(lot_id).strip() or "0",
            "status": "failed",
            "metadata": {},
            "bidders": [],
            "price_bids": [],
            "html_url": "",
            "pdf_url": "",
            "pdf_bytes": b"",
            "errors": [],
        }
        if not result["tender_id"]:
            result["errors"].append("missing_tender_id")
            return result

        if not self.session.is_authenticated and not self.login():
            result["errors"].append("login_required")
            return result

        tender_id = result["tender_id"]
        lot_id = result["lot_id"]

        archive_info = None
        if include_archive_lookup:
            try:
                for page_no in range(1, 4):
                    matches = [t for t in self.get_archived_my_tenders(page_no=page_no) if t.get("tender_id") == tender_id]
                    if matches:
                        archive_info = matches[0]
                        break
            except Exception as exc:
                result["errors"].append(f"archive_lookup_failed:{exc}")

        html_url = f"{BASE_URL}/report/TOR2.jsp?isT=y&isPDF=false&tenderid={tender_id}&lotId={lot_id}"
        pdf_url = f"{BASE_URL}/TorRptServlet?tenderId={tender_id}&lotId={lot_id}&action=TOR2"
        result["html_url"] = html_url
        result["pdf_url"] = pdf_url

        try:
            resp = self.client.get(
                html_url,
                headers={"Referer": f"{BASE_URL}/tenderer/MyTenders.jsp"},
                timeout=min(self.timeout * 2, 60),
            )
        except Exception as exc:
            result["errors"].append(f"tor2_html_failed:{exc}")
            return result

        if resp.status_code != 200 or len(resp.text) < 100:
            result["errors"].append(f"tor2_html_invalid:{resp.status_code}:{len(resp.text)}")
            return result

        metadata = self._extract_tor2_metadata(resp.text, tender_id)
        if archive_info:
            if not metadata.get("procuring_entity") and archive_info.get("pe_office"):
                metadata["procuring_entity"] = archive_info["pe_office"]
            if not metadata.get("zone") and archive_info.get("zone"):
                metadata["zone"] = archive_info["zone"]
            metadata["archive_info"] = archive_info

        result["metadata"] = metadata
        result["bidders"] = metadata.get("bidders", [])
        result["price_bids"] = metadata.get("price_bids", [])
        result["status"] = "success"

        if include_pdf:
            try:
                pdf_resp = self.client.get(
                    pdf_url,
                    headers={
                        "Referer": html_url,
                        "Accept": "application/pdf,image/webp,*/*",
                    },
                    timeout=max(min(self.timeout * 4, 120), 60),
                )
                if pdf_resp.status_code == 200 and pdf_resp.content[:4] == b"%PDF":
                    result["pdf_bytes"] = pdf_resp.content
                    result["pdf_size_bytes"] = len(pdf_resp.content)
                else:
                    result["errors"].append(f"tor2_pdf_invalid:{pdf_resp.status_code}:{len(pdf_resp.content)}")
            except Exception as exc:
                result["errors"].append(f"tor2_pdf_failed:{exc}")

        return result
    def download_document(self, tender_id: str, doc_type: str, save_path: str = "") -> Optional[bytes]:
        """
        Attempt to download a tender document.
        doc_type: "NIT", "BOQ", "Drawings", "Corrigendum", "Specifications"
        
        Searches the tender detail page for document links and downloads.
        """
        logger.info(f"Downloading {doc_type} for tender {tender_id}")
        try:
            # First get the tender details page
            resp = self.client.post(
                f"{BASE_URL}/TenderDetailsServlet",
                data={
                    "funName": "TenderDetails",
                    "tenderId": tender_id,
                },
                timeout=min(self.timeout * 2, 60),
            )

            # Look for document download links
            doc_patterns = {
                "NIT": r'<a[^>]*href="([^"]*NIT[^"]*)"[^>]*>',
                "BOQ": r'<a[^>]*href="([^"]*BOQ[^"]*)"[^>]*>',
                "Drawings": r'<a[^>]*href="([^"]*Drawing[^"]*)"[^>]*>',
                "Corrigendum": r'<a[^>]*href="([^"]*Corrigendum[^"]*)"[^>]*>',
                "Specifications": r'<a[^>]*href="([^"]*Spec[^"]*)"[^>]*>',
            }

            pattern = doc_patterns.get(doc_type, r'<a[^>]*href="([^"]*download[^"]*)"[^>]*>')
            match = re.search(pattern, resp.text, re.IGNORECASE | re.DOTALL)
            if match:
                doc_url = urljoin(BASE_URL, match.group(1))
                doc_resp = self.client.get(doc_url, timeout=60)
                logger.info(f"Downloaded {doc_type} ({len(doc_resp.content)} bytes)")
                return doc_resp.content

            logger.warning(f"No {doc_type} link found for tender {tender_id}")
            return None

        except Exception as exc:
            logger.error(f"Document download failed for {tender_id}/{doc_type}: {exc}")
            return None

    # ── HTML Parsing ─────────────────────────────────────────────────────

    def _parse_view_tender(self, html: str, tender_id: str) -> Optional[TenderInfo]:
        """Parse ViewTender.jsp response to extract detailed tender information.
        
        The page contains tables with format:
          Field Label : | Value
          Tender/Proposal ID : | 1290026
          Package Description : | GOB-REV/... Title
        """
        tender = TenderInfo(tender_id=tender_id)
        
        # Extract all table rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        for row_html in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
            cell_texts = []
            for c in cells:
                txt = re.sub(r'<[^>]+>', ' ', c).strip()
                txt = re.sub(r'\s+', ' ', txt)
                txt = re.sub(r'&amp;', '&', txt)
                cell_texts.append(txt)
            
            row_text = ' '.join(cell_texts)
            
            # Extract key fields
            if 'Procuring Entity Name' in row_text and ':' in row_text and len(cell_texts) >= 4:
                tender.procuring_entity = cell_texts[3]
            elif 'Tender/Proposal ID' in row_text and ':' in row_text and len(cell_texts) >= 4:
                m = re.search(r'(\d{6,})', cell_texts[3])
                if m:
                    tender.tender_id = m.group(1)
            elif ('Package No' in row_text or 'Package' in row_text) and 'Description' in row_text:
                # The title follows after the package number
                # Format: "PKG-123 Title of work"
                for ct in cell_texts:
                    ct_clean = re.sub(r'<[^>]+>', ' ', ct).strip()
                    if not tender.title or len(ct_clean) > len(tender.title):
                        tender.title = ct_clean
            elif 'Category' in row_text and ':' in row_text and len(cell_texts) >= 2:
                tender.category = cell_texts[-1].split(';')[0][:80]
            elif 'Procurement Method' in row_text and ':' in row_text and len(cell_texts) >= 4:
                pass  # method is in cell_texts[3] if needed
            elif 'Closing Date' in row_text or 'Deadline' in row_text:
                if ':' in row_text and len(cell_texts) >= 4:
                    tender.deadline = cell_texts[3]
            elif 'Publication Date' in row_text:
                if ':' in row_text and len(cell_texts) >= 4:
                    tender.published_date = cell_texts[3]
        
        # Clean up title (remove HTML, normalize)
        if tender.title:
            tender.title = re.sub(r'<[^>]+>', '', tender.title).strip()
            tender.title = re.sub(r'\s+', ' ', tender.title)
        
        # Determine status from page
        if 'Live' in html or 'live' in html.lower():
            tender.status = 'Live'
        elif 'Closed' in html or 'closed' in html.lower():
            tender.status = 'Closed'
        
        return tender if tender.tender_id else None

    def _extract_zone(self, name: str) -> Optional[str]:
        if not name or name == "N/A":
            return None
        normalized = re.sub(r"\s+", " ", name).strip()
        found = [
            (normalized.lower().index(d.lower()), d)
            for d in DISTRICTS_BD
            if d.lower() in normalized.lower()
        ]
        if found:
            return max(found, key=lambda item: item[0])[1]
        match = re.search(r"^([A-Za-z.]+(?:\s+[A-Za-z.]+)?)\s+(?:WD|O&M|Division|Office|Zone|Circle)", normalized)
        return match.group(1).rstrip(".") if match else None

    def _parse_archived_my_tenders(self, html: str) -> List[Dict[str, Any]]:
        tenders: List[Dict[str, Any]] = []
        for row in re.findall(r"<tr[^>]*>.*?</tr>", html, re.DOTALL | re.I):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.I)
            if len(cells) < 5:
                continue
            serial = re.sub(r"<[^>]+>", "", cells[0]).strip()
            if not serial.isdigit():
                continue
            cell1 = cells[1]
            tender_id_match = re.search(r"(\d{6,})", cell1)
            if not tender_id_match:
                continue
            cell1_text = re.sub(r"<[^>]+>", " ", cell1)
            cell1_text = re.sub(r"&nbsp;", " ", cell1_text)
            cell1_text = re.sub(r"\s+", " ", cell1_text).strip()
            parts = cell1_text.split(",", 2)
            ref_no = re.sub(r";\s*Date.*", "", parts[1].strip()) if len(parts) > 1 else ""
            status_match = re.search(r"<span[^>]*>(.*?)</span>", cell1, re.DOTALL | re.I)
            status = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", status_match.group(1))).strip() if status_match else ""
            work_name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[2])).strip()[:300] if len(cells) > 2 else ""
            pe_office = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[3])).strip() if len(cells) > 3 else ""
            tenderers_count = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[4])).strip() if len(cells) > 4 else ""
            tenders.append({
                "tender_id": tender_id_match.group(1),
                "ref_no": ref_no,
                "status": status,
                "work_name": work_name,
                "pe_office": pe_office,
                "zone": self._extract_zone(pe_office),
                "tenderers_count": tenderers_count,
            })
        return tenders

    def _extract_tor2_metadata(self, html: str, tender_id: str) -> Dict[str, Any]:
        meta: Dict[str, Any] = {"tender_id": tender_id}
        label_map = {
            "Tender/Proposal ID": "tender_id",
            "Invitation Reference No": "ref_no",
            "Closing Date and Time": "closing_date",
            "Opening Date and Time": "opening_date",
            "Procuring Entity": "procuring_entity",
            "Tender/Proposal Status": "tender_status",
            "Ministry Name": "ministry_name",
            "Organization/Agency Name": "agency_name",
            "Tender Package No": "package_no",
            "Lot No": "lot_no",
        }
        for tbl in re.findall(r"<table[^>]*>.*?</table>", html, re.DOTALL | re.I):
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL | re.I):
                cells = re.findall(r"<td[^>]*>\s*(.*?)\s*</td>", row, re.DOTALL | re.I)
                for idx, cell in enumerate(cells):
                    label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
                    for pattern, key in label_map.items():
                        if label.startswith(pattern) and idx + 1 < len(cells) and key not in meta:
                            value = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cells[idx + 1])).strip()
                            if value:
                                meta[key] = value

        if meta.get("procuring_entity"):
            meta["zone"] = self._extract_zone(meta["procuring_entity"])

        bidders: List[Dict[str, Any]] = []
        price_bidders: List[Dict[str, Any]] = []
        for tbl in re.findall(r"<table[^>]*>.*?</table>", html, re.DOTALL | re.I):
            if "Name of Tenderer" not in tbl:
                continue
            is_price_table = "Quoted Amount" in tbl
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL | re.I):
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.I)
                if len(cells) < 4:
                    continue
                serial = re.sub(r"<[^>]+>", "", cells[0]).strip()
                if not serial.isdigit():
                    continue
                name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cells[1])).strip()
                if not name:
                    continue
                if is_price_table:
                    price_bidders.append({
                        "serial": int(serial),
                        "name": name,
                        "quoted_amount": re.sub(r"<[^>]+>", "", cells[2]).strip(),
                        "discount_pct": re.sub(r"<[^>]+>", "", cells[3]).strip() if len(cells) > 3 else "",
                        "discount_amount": re.sub(r"<[^>]+>", "", cells[4]).strip() if len(cells) > 4 else "",
                        "net_quoted": re.sub(r"<[^>]+>", "", cells[5]).strip() if len(cells) > 5 else "",
                    })
                else:
                    bidders.append({"serial": int(serial), "name": name})

        if bidders:
            meta["bidder_count"] = len(bidders)
            meta["bidders"] = bidders
        else:
            meta["bidder_count"] = 0

        if price_bidders:
            meta["price_bid_count"] = len(price_bidders)
            meta["price_bids"] = price_bidders

        return meta

    def _parse_tender_list(self, html: str) -> List[TenderInfo]:
        """Parse tender listing HTML from TenderDetailsServlet AJAX response."""
        tenders = []

        # Extract table rows (skip header/no-record rows)
        rows = re.findall(
            r'<tr[^>]*>(.*?)</tr>',
            html.replace('\n', ' '),
            re.DOTALL | re.IGNORECASE,
        )

        for row in rows:
            # Skip rows with noRecordFound or headers
            if 'noRecordFound' in row or 'bgColor-header' in row.lower():
                continue

            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 6:
                continue

            # Cell 0: Row number
            # Cell 1: Tender ID + Reference + Status
            # Cell 2: Category + Title
            # Cell 3: Procuring entity
            # Cell 4: Method (NCT, OTM)
            # Cell 5: Published date, Deadline
            # Cell 6: Dashboard link

            # Extract tender ID from cell 1 (first number sequence)
            cell1_text = re.sub(r'<[^>]+>', ' ', cells[1]).strip()
            tender_id_match = re.match(r'\s*(\d+)', cell1_text)
            if not tender_id_match:
                continue
            tender_id = tender_id_match.group(1)

            # Extract title from cell 2
            # The title is in format "Category,<br/><form><input.../><a...><span id='tenderBrief_X'><p><strong>TITLE</strong></p></span><...>"
            # Best approach: extract text after <strong> tags
            strong_match = re.search(r'<strong>(.*?)</strong>', cells[2], re.DOTALL | re.IGNORECASE)
            if strong_match:
                title = re.sub(r'<[^>]+>', '', strong_match.group(1)).strip()
                title = re.sub(r'&amp;', '&', title)
                title = re.sub(r'&lt;', '<', title)
                title = re.sub(r'&gt;', '>', title)
                title = re.sub(r'&quot;', '"', title)
            else:
                # Fallback: strip HTML and take text after first comma
                cell2_text = re.sub(r'<[^>]+>', ' ', cells[2]).strip()
                cell2_text = re.sub(r'&amp;', '&', cell2_text)
                if ',' in cell2_text:
                    title = cell2_text.split(',', 1)[1].strip()
                else:
                    title = cell2_text

            # Extract procuring entity from cell 3
            entity_text = re.sub(r'<[^>]+>', '<br/>', cells[3]).strip()
            entity_text = re.sub(r'<br\s*/?>', ', ', entity_text).strip()
            procuring_entity = re.sub(r'\s+', ' ', entity_text).strip()

            # Extract dates from cell 5
            cell5_text = re.sub(r'<[^>]+>', '', cells[5]).strip()
            published_date = ""
            deadline = ""
            if ',' in cell5_text:
                date_parts = cell5_text.split(',', 1)
                published_date = date_parts[0].strip()
                deadline = date_parts[1].strip()
            else:
                published_date = cell5_text

            tender = TenderInfo(
                tender_id=tender_id,
                title=title,
                procuring_entity=procuring_entity,
                published_date=published_date,
                deadline=deadline,
                status="Live" if "Live" in cells[1] else "Unknown",
            )

            # Try to extract estimated value from any cell
            for cell in cells:
                text = re.sub(r'<[^>]+>', '', cell)
                val_match = re.search(r'[\u09F3Tk]?\s*([\d,]+\.?\d*)\s*(Cr|Lac|Thousand)?', text)
                if val_match:
                    try:
                        val = float(val_match.group(1).replace(',', ''))
                        unit = val_match.group(2) or ''
                        if 'Cr' in unit:
                            val *= 10_000_000
                        elif 'Lac' in unit:
                            val *= 100_000
                        tender.estimated_value_bdt = val
                        break
                    except ValueError:
                        pass

            tenders.append(tender)

        return tenders

    def _looks_like_tender_id(self, text: str) -> bool:
        """Heuristic check if text looks like a tender ID."""
        text = text.strip()
        # Pattern: eGP-XXXXXX or just numbers (7+ digits for the full ID)
        if re.match(r'^(eGP|egp|EGP)[-\s]?\d+', text):
            return True
        if re.match(r'^\d{6,}$', text):
            return True
        return False

    # ── Award / eContracts / eExperience Scraping ───────────────────────

    def search_noa(self, tender_id: str = "", entity: str = "", days: int = 30) -> List[Dict[str, Any]]:
        """Search Notification of Award (NOA) via SearchNoaServlet (public, no login needed).
        
        Uses the same AJAX endpoint as the eGP portal:
          $.post('/SearchNoaServlet', {keyword, pageNo, size})
        
        Returns HTML table rows with columns:
          [0] Row#, [1] Ministry, [2] Tender Info (ID, Ref#), 
          [3] Office, [4] Location, [5] Date, [6] Winner, [7] Amount
        """
        results = []
        for attempt in range(self._max_retries):
            try:
                # SearchNoaServlet works WITHOUT authentication (public data)
                keyword = tender_id or entity or ""
                resp = self.client.post(
                    f"{BASE_URL}/SearchNoaServlet",
                    data={"keyword": keyword, "pageNo": "1", "size": str(min(days * 2, 100))},
                    timeout=min(self.timeout, 15),
                )
                if resp.status_code == 200 and len(resp.text) > 200:
                    results = self._parse_noa_table(resp.text, entity)
                    logger.info(f"NOA search found {len(results)} awards for '{keyword[:30]}'")
                    return results
                return results
            except httpx.TimeoutException:
                if attempt < self._max_retries - 1:
                    logger.warning(f"NOA search timeout, retry {attempt + 1}/{self._max_retries}")
                    time.sleep(1)
                else:
                    logger.warning("NOA search timed out")
                    return results
            except Exception as exc:
                logger.error(f"NOA search failed: {exc}")
                return results

    def search_experience(self, tender_id: str = "", entity: str = "", days: int = 30) -> List[Dict[str, Any]]:
        """Search eExperience (eCMS) for contract completion data.
        
        Uses actual form field names from SearcheCMS.jsp:
        - txtTenderId: Tender ID
        - txtdepartment / txtdepartmentid: Department
        - contractStartDtFrom/To: Contract period
        - contractAwardTo: Awarded to organization
        - exCertificateNo: Experience certificate number
        """
        results = []
        if not self.session.is_authenticated and not self.login():
            logger.warning("Cannot search eExperience: not authenticated (public access only)")
            return results
        # Check if using demo credentials — eCMS likely won't work
        if "hbsrjv" in self.email:
            logger.info("Demo credentials detected — eCMS/Experience requires real login. Skipping.")
            return results
        for attempt in range(self._max_retries):
            try:
                resp = self.client.post(
                    f"{BASE_URL}/resources/common/SearcheCMS.jsp",
                    data={
                        "txtTenderId": tender_id,
                        "txtdepartment": entity,
                        "txtdepartmentid": "",
                        "contractStartDtFrom": "",
                        "contractStartDtTo": "",
                        "contractEndDtFrom": "",
                        "contractEndDtTo": "",
                        "contractAwardTo": "",
                        "txtTendererId": "",
                        "exCertificateNo": "",
                        "btnSearch": "Search",
                    },
                    timeout=min(self.timeout, 15),
                )
                if resp.status_code == 200 and len(resp.text) > 500:
                    results = self._parse_award_list(resp.text, "eCMS")
                    logger.info(f"eCMS search found {len(results)} experience records")
                    return results
                if resp.status_code in (302, 303, 307):
                    logger.warning(f"eCMS search redirected")
                    self.session.is_authenticated = False
                    if self.login():
                        continue
                return results
            except httpx.TimeoutException:
                if attempt < self._max_retries - 1:
                    logger.warning(f"eCMS search timeout, retry {attempt + 1}/{self._max_retries}")
                    time.sleep(2)
                else:
                    logger.warning("eCMS search timed out — eGP may be blocking this IP")
                    return results
            except Exception as exc:
                logger.error(f"eCMS search failed: {exc}")
                return results

    def search_offline_awards(self, tender_id: str = "", entity: str = "") -> List[Dict[str, Any]]:
        """Search offline awarded contracts via SearchAwardedContractOffline.jsp."""
        results = []
        if not self.session.is_authenticated and not self.login():
            logger.warning("Cannot search offline awards: not authenticated (public access only)")
            return results
        # Demo creds won't work for offline awards
        if "hbsrjv" in self.email:
            logger.info("Demo credentials — offline awards require real login. Skipping.")
            return results
        for attempt in range(self._max_retries):
            try:
                resp = self.client.post(
                    f"{BASE_URL}/resources/common/SearchAwardedContractOffline.jsp",
                    data={
                        "txtTenderId": tender_id,
                        "txtdepartment": entity,
                        "txtdepartmentid": "",
                        "btnSearch": "Search",
                    },
                    timeout=min(self.timeout, 15),
                )
                if resp.status_code == 200 and len(resp.text) > 500:
                    results = self._parse_award_list(resp.text, "OFFLINE")
                    logger.info(f"Offline award search found {len(results)} awards")
                    return results
                if resp.status_code in (302, 303, 307):
                    logger.warning(f"Offline award search redirected")
                    self.session.is_authenticated = False
                    if self.login():
                        continue
                return results
            except httpx.TimeoutException:
                if attempt < self._max_retries - 1:
                    logger.warning(f"Offline award search timeout, retry {attempt + 1}/{self._max_retries}")
                    time.sleep(2)
                else:
                    logger.warning("Offline award search timed out — eGP may be blocking this IP")
                    return results
            except Exception as exc:
                logger.error(f"Offline award search failed: {exc}")
                return results

    def collect_award_intelligence(self, entity: str = "", days: int = 30) -> Dict[str, Any]:
        """Aggregate award data from all sources (NOA primary, eCMS/Offline if available).
        
        NOA works publicly without login. eCMS and Offline require authentication
        and will fail gracefully with empty results if not authenticated.
        """
        logger.info(f"Collecting award intelligence for entity='{entity}', days={days}")
        
        # NOA: works without authentication — always try
        noa = self.search_noa(entity=entity, days=days)
        
        # eCMS/Offline: skip quickly if not authenticated to avoid timeouts
        ecms = []
        offline = []
        if self.session.is_authenticated or self.login():
            try:
                ecms = self.search_experience(entity=entity, days=days)
            except Exception:
                ecms = []
            try:
                offline = self.search_offline_awards(entity=entity)
            except Exception:
                offline = []
        else:
            logger.debug("Skipping eCMS/Offline — not authenticated")
        
        return {
            "noa_awards": noa,
            "ecms_experience": ecms,
            "offline_awards": offline,
            "total_records": len(noa) + len(ecms) + len(offline),
            "sources": ["NOA"] + (["eCMS"] if ecms else []) + (["Offline"] if offline else []),
        }

    def _parse_noa_table(self, html: str, entity_filter: str = "") -> List[Dict[str, Any]]:
        """Parse NOA table HTML from SearchNoaServlet response.
        
        Table columns: Row#, Ministry, Tender Info, Office, Location, Date, Winner, Amount
        """
        awards = []
        rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL | re.IGNORECASE)
        
        for row in rows:
            cells_html = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            if len(cells_html) < 8:
                continue
            
            # Clean HTML tags
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells_html]
            cells = [re.sub(r'\s+', ' ', c) for c in cells]
            
            # Skip header rows
            if not cells[0].isdigit():
                continue
            
            # Cell 2 has format: "TENDER_ID, REF_NO TITLE"
            cell2 = cells[2]
            tender_id = ""
            title = cell2
            m = re.search(r'(\d{6,})', cell2)
            if m:
                tender_id = m.group(1)
                # Title is everything after the first comma and space
                if ', ' in cell2:
                    parts = cell2.split(', ', 1)
                    title = parts[1] if len(parts) > 1 else parts[0]
            
            # Amount in cell 7 (last column) - in Crore/Lac
            amount = 0.0
            try:
                amt_text = cells[7].replace(',', '').strip()
                if amt_text:
                    amount = float(amt_text) * 100000  # Convert from Lac to BDT
            except (ValueError, IndexError):
                pass
            
            # Filter by entity if specified
            entity = cells[1] if len(cells) > 1 else ""
            if entity_filter and entity_filter.upper() not in entity.upper():
                continue
            
            award = {
                "source": "NOA",
                "tender_id": tender_id,
                "procuring_entity": entity,
                "office": cells[3] if len(cells) > 3 else "",
                "location": cells[4] if len(cells) > 4 else "",
                "award_date": cells[5] if len(cells) > 5 else "",
                "winner": cells[6] if len(cells) > 6 else "",
                "amount_bdt": amount,
                "title": title[:200],
            }
            awards.append(award)
        
        return awards

    def _parse_award_list(self, html: str, source: str) -> List[Dict[str, Any]]:
        """Parse award listing HTML tables from eGP servlet responses."""
        awards = []
        soup = None
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
        except ImportError:
            pass

        # Extract all tables
        tables = []
        if soup:
            tables = soup.find_all('table')
        else:
            tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL | re.IGNORECASE)
            tables = [t for t in tables if 'tr' in t and 'td' in t]

        for table in tables:
            rows = []
            if soup:
                rows = table.find_all('tr')
            else:
                rows = re.findall(r'<tr[^>]*>.*?</tr>', str(table) if not isinstance(table, str) else table, re.DOTALL | re.IGNORECASE)

            for row in rows:
                cells = []
                if soup:
                    cells = row.find_all(['td', 'th'])
                else:
                    cells_html = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', str(row) if not isinstance(row, str) else row, re.DOTALL | re.IGNORECASE)
                    cells = [BeautifulSoup(c, 'html.parser') for c in cells_html] if cells_html else []

                if len(cells) < 3:
                    continue

                row_text = []
                for c in cells:
                    txt = c.get_text(strip=True) if hasattr(c, 'get_text') else re.sub(r'<[^>]+>', '', str(c)).strip()
                    row_text.append(txt)

                # Skip header rows
                header_keywords = ['sl', 'no', 'tender id', 'contract', 'award', 'action']
                first_text = row_text[0].lower() if row_text else ""
                if any(kw in first_text for kw in header_keywords):
                    continue

                award = {
                    "source": source,
                    "raw_data": row_text,
                }
                
                # Try to extract tender ID (first numeric-looking field)
                for i, t in enumerate(row_text):
                    t_clean = t.replace(',', '').strip()
                    if re.match(r'^\d{6,}$', t_clean):
                        award["tender_id"] = t_clean
                        award["tender_id_col"] = i
                        break
                
                # Try to extract amounts
                for t in row_text:
                    t_clean = t.replace(',', '').strip()
                    amt_match = re.search(r'([\d,]+\.?\d*)\s*(Crore|Lac|Thousand|TK\.?|BDT)?', t_clean, re.IGNORECASE)
                    if amt_match:
                        try:
                            val = float(amt_match.group(1).replace(',', ''))
                            unit = (amt_match.group(2) or '').lower()
                            if 'crore' in unit:
                                val *= 10_000_000
                            elif 'lac' in unit:
                                val *= 100_000
                            award["amount_bdt"] = award.get("amount_bdt", 0) + val
                        except ValueError:
                            pass

                if award.get("tender_id") or any(len(t) > 5 for t in row_text):
                    awards.append(award)

        logger.debug(f"Parsed {len(awards)} awards from {source}")
        return awards

    # ── Annual Procurement Plan (APP) Scraping ───────────────────────────
    # Finds tentative estimated amounts for SLT (Simple Least-Cost Tendering) analysis
    # Use: select ministry → financial year → PE office → DB option → match tender package

    def search_app_tenders(self, ministry: str = "", fy: str = "", pe_office: str = "") -> List[Dict[str, Any]]:
        """Search Annual Procurement Plan for tentative estimates.
        
        The APP tab on the eGP homepage allows browsing by:
        - Ministry/Division
        - Financial Year  
        - Procuring Entity (PE) Office
        - Development Budget (DB) option
        Returns tentative estimated amounts for SLT analysis.
        """
        results = []
        if not self.session.is_authenticated and not self.login():
            logger.warning("Cannot search APP: not authenticated")
            return results
        for attempt in range(self._max_retries):
            try:
                resp = self.client.post(
                    f"{BASE_URL}/resources/common/AppSearchServlet.jsp",
                    data={
                        "ministry": ministry,
                        "fy": fy,
                        "peOffice": pe_office,
                        "btnSearch": "Search",
                    },
                    timeout=min(self.timeout, 15),
                )
                if resp.status_code == 200 and len(resp.text) > 500:
                    results = self._parse_app_list(resp.text)
                    logger.info(f"APP search found {len(results)} planned tenders")
                    return results
                if resp.status_code in (302, 303, 307):
                    new_url = resp.headers.get('location', '')
                    logger.warning(f"APP search redirected to {new_url}")
                    # Try re-login
                    self.session.is_authenticated = False
                    if self.login():
                        continue
                return results
            except httpx.TimeoutException:
                if attempt < self._max_retries - 1:
                    logger.warning(f"APP search timeout, retry {attempt + 1}/{self._max_retries}")
                    time.sleep(2)
                else:
                    logger.warning("APP search timed out — eGP may be blocking this IP")
                    return results
            except Exception as exc:
                logger.error(f"APP search failed: {exc}")
                return results

    def get_tender_estimate_from_app(self, tender_id: str = "", package_no: str = "") -> Optional[Dict[str, Any]]:
        """Look up a specific tender's estimated amount from the Annual Procurement Plan.
        
        This finds the tentative estimate for SLT (Simple Least-Cost Tendering) analysis.
        Match by tender ID or package number.
        """
        # First, browse APP by the user's ministry/procuring entity
        # For now, try scraping the APP search page directly
        try:
            resp = self.client.get(
                f"{BASE_URL}/resources/common/AppSearch.jsp",
                params={"tenderId": tender_id, "packageNo": package_no},
                timeout=min(self.timeout, 15),
            )
            if resp.status_code == 200 and len(resp.text) > 500:
                data = self._parse_app_list(resp.text)
                for item in data:
                    if (tender_id and item.get('tender_id') == tender_id) or                        (package_no and package_no.lower() in item.get('package_no', '').lower()):
                        logger.info(f"Found estimate for {tender_id or package_no}: BDT {item.get('estimated_amount')}")
                        return item
                logger.info(f"No APP estimate found for {tender_id or package_no}")
        except Exception as exc:
            logger.debug(f"APP estimate lookup failed: {exc}")
        return None

    def _parse_app_list(self, html: str) -> List[Dict[str, Any]]:
        """Parse Annual Procurement Plan listing HTML."""
        items = []
        soup = None
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
        except ImportError:
            pass

        tables = []
        if soup:
            tables = soup.find_all('table')
        else:
            tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL | re.IGNORECASE)

        for table in tables:
            rows = []
            if soup:
                rows = table.find_all('tr')
            else:
                rows = re.findall(r'<tr[^>]*>.*?</tr>', str(table) if not isinstance(table, str) else table, re.DOTALL | re.IGNORECASE)

            for row in rows:
                cells = []
                if soup:
                    cells = row.find_all(['td', 'th'])
                else:
                    cells_html = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', str(row) if not isinstance(row, str) else row, re.DOTALL | re.IGNORECASE)
                    cells = [BeautifulSoup(c, 'html.parser') for c in cells_html] if cells_html else []

                if len(cells) < 4:
                    continue

                row_text = []
                for c in cells:
                    txt = c.get_text(strip=True) if hasattr(c, 'get_text') else re.sub(r'<[^>]+>', '', str(c)).strip()
                    row_text.append(txt)

                # Skip headers
                first = row_text[0].lower() if row_text else ""
                if any(kw in first for kw in ['sl', 'no', 'serial', 'tender id', 'package', 'action']):
                    continue

                item = {"raw_data": row_text}

                # Extract tender ID
                for t in row_text:
                    m = re.match(r'(\d{6,})', t.replace(',', '').strip())
                    if m:
                        item['tender_id'] = m.group(1)
                        break

                # Extract package number
                for t in row_text:
                    if re.search(r'[A-Z]+/[\w/-]+', t):
                        item['package_no'] = t.strip()
                        break

                # Extract estimated amount
                for t in row_text:
                    amt = re.search(r'([\d,]+\.?\d*)\s*(Crore|Lac|TK)', t, re.IGNORECASE)
                    if amt:
                        try:
                            val = float(amt.group(1).replace(',', ''))
                            unit = (amt.group(2) or '').lower()
                            if 'crore' in unit: val *= 10_000_000
                            elif 'lac' in unit: val *= 100_000
                            item['estimated_amount_bdt'] = val
                            break
                        except ValueError:
                            pass

                if item.get('tender_id') or item.get('package_no'):
                    items.append(item)

        return items

    # ── Health Check ─────────────────────────────────────────────────────

    def check_connection(self) -> Dict[str, Any]:
        """Check if the eGP portal is reachable."""
        try:
            resp = self.client.get(BASE_URL, timeout=10)
            return {
                "reachable": resp.status_code == 200,
                "status_code": resp.status_code,
                "session_active": self.session.is_authenticated,
                "session_id": self.session.jsessionid[:20] + "..." if self.session.jsessionid else None,
            }
        except Exception as exc:
            return {"reachable": False, "error": str(exc)}

    # ── Public APP Search (no login needed) ──────────────────────────

    def search_app(self, keyword: str = "", department: str = "") -> List[Dict[str, Any]]:
        """Search Annual Procurement Plans (public, no login needed).
        
        Uses SearchAPPServlet (AJAX endpoint from StdSearch.jsp).
        Falls back to SearchAPP.jsp page scraping.
        """
        logger.info(f"Searching APP for: keyword='{keyword}', department='{department}'")
        try:
            if not self.session.jsessionid:
                self.client.get(BASE_URL)
            
            # Try the AJAX servlet first
            resp = self.client.post(
                f"{BASE_URL}/SearchAPPServlet",
                data={
                    "bTypeId": "",
                    "pageNo": "1",
                    "office": "",
                    "action": "advSearch",
                    "size": "50",
                    "keyWord": keyword,
                },
                timeout=min(self.timeout, 15),
            )
            if resp.status_code == 200 and len(resp.text) > 200:
                items = self._parse_app_list(resp.text)
                logger.info(f"APP search found {len(items)} procurement plans")
                return items
        except httpx.TimeoutException:
            logger.warning("APP search (servlet) timed out — trying page fallback")
        except Exception as exc:
            logger.debug(f"APP search (servlet) failed: {exc}")
        
        # Fallback: scrape SearchAPP.jsp page
        try:
            resp = self.client.post(
                f"{BASE_URL}/resources/common/SearchAPP.jsp",
                data={
                    "txtdepartment": department or keyword,
                    "txtdepartmentid": "0",
                    "financialYear": "2026-2027",
                    "search": "Search",
                    "crntTab": "tenderTab",
                    "fromHome": "true",
                },
                timeout=min(self.timeout, 15),
            )
            if resp.status_code == 200 and len(resp.text) > 1000:
                items = self._parse_app_list(resp.text)
                logger.info(f"APP page search found {len(items)} procurement plans")
                return items
        except Exception as exc:
            logger.debug(f"APP page search failed: {exc}")
        
        return []

    # ── Tender Document Access (Authenticated) ──────────────────────

    def get_tender_documents(self, tender_id: str) -> Dict[str, Any]:
        """Access tender documents for purchased/archived tenders.
        
        For tenders in My Tender (purchased schedules), this method
        accesses the document section which contains:
        - NIT (Notice Inviting Tender)
        - TDC (Tender Data Card)
        - GCC (General Conditions of Contract)
        - PCC (Particular Conditions of Contract)
        - BOQ (Bill of Quantities)
        - Drawings / Designs
        - Schedules & Formats
        - Corrigendum / Addendum
        - Filled-out forms
        - Mapped documents
        
        Returns a dict with document URLs, forms, and metadata.
        """
        result = {
            "tender_id": tender_id,
            "documents": [],
            "forms": [],
            "download_links": [],
            "pages": [],
            "sections": [],
        }

        direct_exports = self._build_direct_export_links(tender_id)
        result["download_links"].extend(direct_exports)
        
        if not self.session.is_authenticated and not self.login():
            logger.warning("Login required for document access")
            return result

        # Direct export endpoints are the most reliable backend path when
        # authenticated tender dashboard pages time out.
        if not self.email or "hbsrjv@gmail.com" in self.email.lower():
            result["download_links"] = self._dedupe_document_entries(result["download_links"])
            return result
        
        view_tender_html = ""
        try:
            view_tender_resp = self.client.get(
                f"{BASE_URL}/resources/common/ViewTender.jsp",
                params={"id": tender_id, "h": "t"},
                timeout=min(self.timeout * 2, 60),
            )
            view_tender_html = view_tender_resp.text
            if self._looks_like_view_tender_page(view_tender_html):
                result["pages"].append(
                    {
                        "url": f"{BASE_URL}/resources/common/ViewTender.jsp?id={tender_id}&h=t",
                        "kind": "view_tender",
                    }
                )
        except Exception as exc:
            logger.debug("ViewTender fetch failed for %s: %s", tender_id, exc)

        view_notice_match = re.search(
            r'/tenderer/LotPckDocs\.jsp\?[^"\']*tenderId=' + re.escape(str(tender_id)),
            view_tender_html,
            re.IGNORECASE,
        )

        # Try multiple document page paths
        doc_paths = [
            view_notice_match.group(0) if view_notice_match else "",
            "/tenderer/TenderDocView.jsp?tenderId=" + tender_id,
            "/tenderer/LotPckDocs.jsp?tenderId=" + tender_id,
            "/tenderer/LotPckDocs.jsp?tab=1&tenderId=" + tender_id,
            "/tenderer/Docs.jsp?tenderId=" + tender_id,
            "/resources/common/LotPckDocs.jsp?tenderId=" + tender_id,
            "/resources/common/DocView.jsp?id=" + tender_id,
            "/resources/common/TenderDocuments.jsp?id=" + tender_id,
        ]

        visited_pages = set()
        for path in doc_paths:
            if not path:
                continue
            try:
                full_url = urljoin(BASE_URL + "/", path.lstrip("/"))
                if full_url in visited_pages:
                    continue
                visited_pages.add(full_url)
                resp = self.client.get(full_url, timeout=min(self.timeout * 2, 60))
                if resp.status_code != 200 or len(resp.text) <= 500:
                    continue

                html = resp.text
                if not self._looks_like_egp_document_page(html):
                    logger.debug("Skipping non-document page for %s", full_url)
                    continue

                logger.info("Document page found: " + full_url + " (" + str(len(html)) + " bytes)")

                if self._looks_like_tender_doc_view_page(html):
                    result["pages"].append({"url": full_url, "kind": "document_view"})
                    self._parse_tender_doc_view(html, result)
                elif self._looks_like_lot_pack_docs_page(html):
                    result["pages"].append({"url": full_url, "kind": "lot_docs"})
                    self._parse_lot_pack_docs(html, result)
                elif self._looks_like_tds_dashboard_page(html):
                    result["pages"].append({"url": full_url, "kind": "tds_dashboard"})
                    self._parse_tds_dashboard(html, result)

                # Follow authenticated document pages linked from the current page.
                doc_view_links = [
                    href for href, text in self._extract_links_from_html(html)
                    if "TenderDocView.jsp" in href or text.strip().lower() == "view document"
                ]
                for href in doc_view_links:
                    try:
                        target_url = urljoin(BASE_URL, href)
                        if target_url in visited_pages:
                            continue
                        visited_pages.add(target_url)
                        view_resp = self.client.get(target_url, timeout=min(self.timeout * 2, 60))
                        if view_resp.status_code == 200 and len(view_resp.text) > 500 and self._looks_like_tender_doc_view_page(view_resp.text):
                            result["pages"].append({"url": target_url, "kind": "document_view"})
                            self._parse_tender_doc_view(view_resp.text, result)
                    except Exception as exc:
                        logger.debug("TenderDocView fetch failed for %s: %s", href, exc)

                form_fields = self._extract_form_fields(html)
                for fields in form_fields:
                    if fields:
                        result["forms"].append({"fields": fields})

                if result["documents"] or result["download_links"] or result["forms"]:
                    result["documents"] = self._dedupe_document_entries(result["documents"])
                    result["download_links"] = self._dedupe_document_entries(result["download_links"])
                    result["forms"] = self._dedupe_document_entries(result["forms"])
                    result["sections"] = self._dedupe_document_entries(result["sections"])
                    return result
            except Exception as exc:
                logger.debug("Document path " + path + " failed: " + str(exc))

        result["documents"] = self._dedupe_document_entries(result["documents"])
        result["download_links"] = self._dedupe_document_entries(result["download_links"])
        result["forms"] = self._dedupe_document_entries(result["forms"])
        result["sections"] = self._dedupe_document_entries(result["sections"])

        if result["documents"] or result["download_links"] or result["forms"]:
            return result

        logger.info("No document page found for tender " + tender_id + " (may not be purchased)")
        return result

    def _build_direct_export_links(self, tender_id: str) -> List[Dict[str, Any]]:
        return [
            {
                "name": "Notice PDF",
                "url": f"{BASE_URL}/GeneratePdf?reqURL=http://www.eprocure.gov.bd/resources/common/ViewTender.jsp&reqQuery=id={tender_id}&folderName=TenderNotice&id={tender_id}",
                "type": "NIT",
                "source_page": "direct_export",
            },
            {
                "name": "Tender Document ZIP",
                "url": f"{BASE_URL}/TenderSecUploadServlet?tenderId={tender_id}&folderArchId=1&lotNo=Package&funName=zipdownload",
                "type": "ZIP",
                "source_page": "direct_export",
            },
        ]

    def _looks_like_view_tender_page(self, html: str) -> bool:
        lowered = html.lower()
        return "view ift /pq / reoi / rfp / pps notice details" in lowered or "tender/proposal detail" in lowered

    def _looks_like_lot_pack_docs_page(self, html: str) -> bool:
        lowered = html.lower()
        return "tender/proposal documents" in lowered or ("package. no." in lowered and "view document" in lowered)

    def _looks_like_tender_doc_view_page(self, html: str) -> bool:
        lowered = html.lower()
        return "tender/proposal document view" in lowered or ("download tender/proposal document" in lowered and "section no." in lowered)

    def _looks_like_tds_dashboard_page(self, html: str) -> bool:
        lowered = html.lower()
        return "tds/pds dashboard" in lowered or ("name of sub section" in lowered and "viewtendertds.jsp" in lowered)

    def _looks_like_egp_document_page(self, html: str) -> bool:
        lowered = html.lower()
        if "session expired" in lowered or "sessiontimedout.jsp" in lowered:
            return False
        if "dear user" in lowered and "report the issue" in lowered:
            return False
        return (
            self._looks_like_view_tender_page(html)
            or self._looks_like_lot_pack_docs_page(html)
            or self._looks_like_tender_doc_view_page(html)
            or self._looks_like_tds_dashboard_page(html)
        )

    def _dedupe_document_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = (
                str(entry.get("section_no", "")),
                str(entry.get("subsection_no", "")),
                str(entry.get("name", "")),
                str(entry.get("url", "")),
                str(entry.get("action", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    def _parse_lot_pack_docs(self, html: str, result: Dict[str, Any]) -> None:
        links = self._extract_links_from_html(html)
        for href_url, text in links:
            t = re.sub(r"\s+", " ", text).strip()
            h = href_url.lower()
            if not t:
                continue
            if t.lower() == "view document" or "TenderDocView.jsp" in href_url:
                result["documents"].append({
                    "name": "Tender Document View",
                    "url": href_url[:300],
                    "type": "Document View",
                    "source_page": "LotPckDocs",
                })
                continue
            doc_type = self._classify_document(h, t)
            entry = {"name": t, "url": href_url[:300], "type": doc_type, "source_page": "LotPckDocs"}
            result["documents"].append(entry)
            if any(kw in h for kw in ["down", "servlet", "get", "docview", "viewtendertds", "tendertdsdashboard"]):
                result["download_links"].append(entry)

    def _parse_tender_doc_view(self, html: str, result: Dict[str, Any]) -> None:
        links = self._extract_links_from_html(html)
        current_section = ""
        lines = [re.sub(r"\s+", " ", line).strip() for line in re.split(r"[\r\n]+", html) if line.strip()]

        for line in lines:
            section_match = re.search(r'^\s*(\d+)\s+(Instructions to Tenderer|Tender Data Sheet|General Conditions of Contract|Particular Conditions of Contract|Tender and Contract Forms|Bill of Quantities|General Specifications|Particular Specifications|ES Specifications|Drawings)', line, re.I)
            if section_match:
                current_section = section_match.group(2).strip()
                result["sections"].append({"section_no": section_match.group(1), "section_name": current_section})

        for href_url, text in links:
            t = re.sub(r"\s+", " ", text).strip()
            if not t:
                continue
            full_url = urljoin(BASE_URL, href_url)
            lower = f"{href_url} {t}".lower()

            if "download" in t.lower():
                result["download_links"].append({
                    "name": t,
                    "url": full_url[:300],
                    "type": self._classify_document(href_url, t),
                    "source_page": "TenderDocView",
                })

            if "TenderTDSDashBoard.jsp" in href_url:
                result["documents"].append({
                    "name": "Tender Data Sheet Dashboard",
                    "url": full_url[:300],
                    "type": "TDS Dashboard",
                    "source_page": "TenderDocView",
                })
                try:
                    tds_resp = self.client.get(full_url, timeout=20)
                    if tds_resp.status_code == 200 and len(tds_resp.text) > 500:
                        result["pages"].append({"url": full_url, "kind": "tds_dashboard"})
                        self._parse_tds_dashboard(tds_resp.text, result)
                except Exception as exc:
                    logger.debug("TDS dashboard fetch failed for %s: %s", full_url, exc)
                continue

            if "ViewTenderTDS.jsp" in href_url:
                result["documents"].append({
                    "name": t,
                    "url": full_url[:300],
                    "type": "TDS View",
                    "source_page": "TenderDocView",
                })
                continue

            if "View Form" in t or "View" == t:
                result["forms"].append({
                    "name": current_section or "Form",
                    "action": t,
                    "url": full_url[:300],
                })
                continue

            doc_type = self._classify_document(href_url, t)
            if doc_type != "Other":
                result["documents"].append({
                    "name": t,
                    "url": full_url[:300],
                    "type": doc_type,
                    "source_page": "TenderDocView",
                })

        # Capture downloadable file rows like "Tender and Contract Forms.docx".
        file_rows = re.findall(
            r'(\d+)\s+([A-Za-z0-9 _().-]+\.(?:docx?|xlsx?|pdf))\s+(.+?)\s+(\d+)\s+Download',
            re.sub(r'\s+', ' ', html),
            re.I,
        )
        for _, filename, description, size_kb in file_rows:
            result["download_links"].append({
                "name": filename.strip(),
                "description": description.strip(),
                "size_kb": int(size_kb),
                "type": self._classify_document(filename, description),
                "source_page": "TenderDocView",
            })

        form_rows = re.findall(
            r'(\d+)\s+(.+?)\s+View Form',
            re.sub(r'\s+', ' ', html),
            re.I,
        )
        for _, form_name in form_rows:
            cleaned = form_name.strip()
            if len(cleaned) > 3 and cleaned not in [f.get("name") for f in result["forms"]]:
                result["forms"].append({"name": cleaned, "action": "View Form"})

    def _parse_tds_dashboard(self, html: str, result: Dict[str, Any]) -> None:
        compact = re.sub(r'\s+', ' ', html)
        rows = re.findall(
            r'Sub Section No\.\s*(\d+)\s*Name Of Sub Section\s*(.*?)\s*Action\s*(?:View|<a[^>]+href=[\"\']([^\"\']+)[\"\'])',
            compact,
            re.I,
        )
        for subsection_no, subsection_name, href_url in rows:
            name = subsection_name.strip()
            full_url = urljoin(BASE_URL, href_url) if href_url else ""
            result["documents"].append({
                "name": name,
                "url": full_url[:300],
                "type": "TDS Subsection",
                "subsection_no": subsection_no,
                "source_page": "TenderTDSDashBoard",
            })
            if full_url:
                result["download_links"].append({
                    "name": name,
                    "url": full_url[:300],
                    "type": "TDS Subsection",
                    "source_page": "TenderTDSDashBoard",
                })

    def _extract_links_from_html(self, html: str):
        """Extract (href, text) pairs from HTML."""
        links = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                t = a_tag.get_text(strip=True)
                if t:
                    links.append((a_tag['href'], t))
            return links
        except ImportError:
            pass
        # Fallback: manual parsing
        q = chr(34)  # double quote
        ap = chr(39)  # single quote
        for sep in [q, ap]:
            marker = "href=" + sep
            parts = html.split(marker)
            for part in parts[1:]:
                end = part.find(sep)
                if end > 0:
                    href = part[:end]
                    gt = part.find(">", end)
                    lt = part.find("</a>", gt)
                    if gt > 0 and lt > gt:
                        text = part[gt+1:lt].strip()
                        text = re.sub(r"<[^>]+>", "", text)
                        if text:
                            links.append((href, text))
        return links

    def _extract_form_fields(self, html: str):
        """Extract form field names from HTML."""
        forms_list = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for form in soup.find_all("form"):
                fields = []
                for inp in form.find_all(["input", "select", "textarea"]):
                    name = inp.get("name", "")
                    if name:
                        fields.append(name)
                if fields:
                    forms_list.append(fields)
            return forms_list
        except ImportError:
            pass
        # Fallback regex
        q = chr(34)
        form_sections = html.split("<form")
        for fs in form_sections[1:]:
            fields = re.findall(r" name=" + q + r"([^" + q + r"]+)" + q, fs)
            if fields:
                forms_list.append(fields)
        return forms_list

    def _classify_document(self, href: str, text: str) -> str:
        """Classify a document based on its URL and text."""
        combined = (href + " " + text).lower()
        if 'nit' in combined or 'notice' in combined: return "NIT"
        if 'boq' in combined: return "BOQ"
        if 'gcc' in combined: return "GCC"
        if 'pcc' in combined: return "PCC"
        if 'tdc' in combined: return "TDC"
        if 'draw' in combined or 'design' in combined: return "Drawing/Design"
        if 'form' in combined or 'format' in combined: return "Form/Format"
        if 'schedule' in combined: return "Schedule"
        if 'corrigendum' in combined or 'addendu' in combined: return "Corrigendum"
        if 'upload' in combined or 'submission' in combined: return "Upload/Submission"
        if 'sign' in combined or 'contract' in combined: return "Contract/Signing"
        if 'security' in combined or 'bg' in combined or 'bank' in combined: return "Security/BG"
        if 'down' in combined: return "Download"
        return "Other"

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
