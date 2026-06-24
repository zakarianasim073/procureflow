"""
eGP Portal Explorer — Interactive Portal Structure Browser
Run this from your Windows machine to explore the full eGP portal
and discover all sections, endpoints, and document structures.

Usage:
  python -m app.agents.portal_explorer explore    # Full exploration
  python -m app.agents.portal_explorer tender 1278365  # Explore specific tender
  python -m app.agents.portal_explorer documents 1278365  # Get tender documents
  python -m app.agents.portal_explorer mytenders   # List my purchased tenders
  python -m app.agents.portal_explorer archived    # Archived my tenders
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from typing import Any, Dict, List, Optional

from .egp_client import eGPClient, BASE_URL
from .credentials import get_credentials

logger = logging.getLogger(__name__)


class PortalExplorer:
    """Interactive eGP Portal Structure Explorer."""
    
    def __init__(self, email: str = "", password: str = ""):
        self.client = eGPClient(email=email, password=password, timeout=30)
        self.session_file = "/tmp/portal_session.json"
    
    def login(self) -> bool:
        """Login to the portal."""
        creds = get_credentials()
        if not self.client.email:
            self.client.set_credentials(creds.egp.email, creds.egp.password)
        return self.client.login()
    
    def explore_homepage(self) -> Dict:
        """Explore the main portal homepage and discover all sections."""
        print("\n" + "=" * 70)
        print("  EXPLORING eGP PORTAL HOMEPAGE")
        print("=" * 70)
        
        result = {"public_sections": [], "auth_sections": [], "endpoints": []}
        
        try:
            import httpx
            c = httpx.Client(verify=False, follow_redirects=True, timeout=15)
            r = c.get(BASE_URL)
            
            # Find all links/sections
            links = re.findall(r'<a\s+[^>]*href=(["\'])([^"\']+)\1[^>]*>(.*?)</a>', r.text, re.DOTALL)
            
            for _, href, text in links:
                t = re.sub(r'<[^>]+>', '', text).strip()
                if t and len(t) > 2:
                    entry = {"name": t, "url": href[:150]}
                    if any(kw in href.lower() for kw in ['login', 'signup', 'register']):
                        result["auth_sections"].append(entry)
                    else:
                        result["public_sections"].append(entry)
                    print(f"  📄 {t[:60]:60s} → {href[:80]}")
            
            # Find all JavaScript endpoints
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
            endpoints = set()
            for s in scripts:
                for m in re.finditer(r'["\'](/[^"\']*(?:Servlet|jsp)[^"\']*)["\']', s):
                    endpoints.add(m.group(1))
            for ep in sorted(endpoints):
                result["endpoints"].append(ep)
                print(f"  🔗 Endpoint: {ep}")
            
            print(f"\n✅ Found {len(result['public_sections'])} public sections, {len(result['endpoints'])} endpoints")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        return result
    
    def explore_tender_details(self, tender_id: str) -> Dict:
        """Explore the detailed structure of a specific tender."""
        print("\n" + "=" * 70)
        print(f"  EXPLORING TENDER {tender_id} DETAILS")
        print("=" * 70)
        
        result = {"tender_id": tender_id, "sections": [], "documents": [], "actions": []}
        
        # Get tender details
        import httpx
        c = httpx.Client(verify=False, follow_redirects=True, timeout=15)
        
        # Public view
        r = c.post(f"{BASE_URL}/resources/common/ViewTender.jsp",
                   data={"id": tender_id, "h": "t"})
        
        if r.status_code == 200 and len(r.text) > 500:
            # Parse all tables (sections)
            tables = re.findall(r'<table[^>]*>(.*?)</table>', r.text, re.DOTALL)
            for i, t in enumerate(tables):
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.DOTALL)
                section_data = []
                for row in rows:
                    cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
                    texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                    if any(x for x in texts):
                        section_data.append(texts)
                if section_data:
                    print(f"\n  📋 Section {i}:")
                    for data in section_data[:5]:
                        print(f"     {data}")
                    result["sections"].append(section_data)
            
            # Find all actions/links
            links = re.findall(r'<a\s+[^>]*href=(["\'])([^"\']+)\1[^>]*>(.*?)</a>', r.text, re.DOTALL)
            for _, href, text in links:
                t = re.sub(r'<[^>]+>', '', text).strip()
                if t and len(t) > 2:
                    entry = {"action": t, "url": href[:150]}
                    h = href.lower()
                    if any(kw in h for kw in ['doc', 'download', 'nit', 'boq']):
                        result["documents"].append(entry)
                    else:
                        result["actions"].append(entry)
                    print(f"     🔗 {t[:50]:50s} → {href[:80]}")
        
        # If logged in, try authenticated view
        if self.client.login():
            print("\n  🔐 Authenticated sections:")
            r2 = self.client.client.get(f"{BASE_URL}/resources/common/ViewTender.jsp?id={tender_id}&h=t")
            if len(r2.text) > 500 and r2.text != r.text:
                links2 = re.findall(r'<a\s+[^>]*href=(["\'])([^"\']+)\1[^>]*>(.*?)</a>', r2.text, re.DOTALL)
                for _, href, text in links2:
                    t = re.sub(r'<[^>]+>', '', text).strip()
                    if t and t not in [x["action"] for x in result["actions"]]:
                        entry = {"action": t, "url": href[:150]}
                        result["actions"].append(entry)
                        print(f"     🔐 {t[:50]:50s} → {href[:80]}")
        
        self.client.close()
        return result
    
    def explore_my_tenders(self, status: str = "Archive") -> List[Dict]:
        """Explore My Tender section for purchased tenders."""
        print("\n" + "=" * 70)
        print(f"  EXPLORING MY TENDER - {status.upper()}")
        print("=" * 70)
        
        results = []
        
        if not self.client.login():
            print("  ❌ Login required for My Tender")
            return results
        
        # Try Tenderer path
        try:
            r = self.client.client.get(f"{BASE_URL}/tenderer/MyTenders.jsp", follow_redirects=False)
            print(f"  /tenderer/MyTenders.jsp → {r.status_code}")
            if r.status_code == 302:
                loc = r.headers.get("Location", "")
                print(f"  Redirects to: {loc}")
                r = self.client.client.get(loc if loc.startswith("http") else f"{BASE_URL}{loc}")
                print(f"  Final: {r.status_code}, {len(r.text)} bytes")
                
                if len(r.text) > 500:
                    # Check for archive tab
                    # Try different servlet calls for My Tender data
                    # The AJAX endpoint varies - try multiple funNames
                    for funName in ["MyTender", "ScheduleTender", "PurchasedTender"]:
                        for viewType in ["Archive", "Live", "AllTenders"]:
                            r2 = self.client.client.post(
                                f"{BASE_URL}/TenderDetailsServlet",
                                data={"funName": funName, "viewType": viewType,
                                      "pageNo": "1", "size": "50", "h": "t"}
                            )
                            if r2.status_code == 200 and len(r2.text) > 100:
                                print(f"\n  ✅ TenderDetails ({funName}/{viewType}): {len(r2.text)} bytes")
                                print(f"     Response: {r2.text[:200]}")
                                results.append({"funName": funName, "viewType": viewType, "data": r2.text[:500]})
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        self.client.close()
        return results
    
    def explore_tender_documents(self, tender_id: str) -> Dict:
        """Explore document structure for a tender."""
        print("\n" + "=" * 70)
        print(f"  EXPLORING DOCUMENTS FOR TENDER {tender_id}")
        print("=" * 70)
        
        result = {"tender_id": tender_id, "documents": [], "forms": [], "downloads": []}
        
        if not self.client.login():
            print("  ❌ Login required for documents")
            return result
        
        # Try document access paths
        paths = [
            f"/tenderer/LotPckDocs.jsp?tenderId={tender_id}",
            f"/resources/common/LotPckDocs.jsp?tenderId={tender_id}",
            f"/tenderer/Docs.jsp?tenderId={tender_id}",
            f"/resources/common/TenderDocuments.jsp?id={tender_id}",
        ]
        
        for path in paths:
            try:
                r = self.client.client.get(f"{BASE_URL}{path}")
                print(f"\n  {path}")
                print(f"     Status: {r.status_code}, Size: {len(r.text)} bytes")
                
                if r.status_code == 200 and len(r.text) > 500:
                    print(f"  ✅ Accessible! Analyzing content...")
                    
                    # Find document links
                    links = re.findall(r'<a\s+[^>]*href=(["\'])([^"\']+)\1[^>]*>(.*?)</a>', r.text, re.DOTALL)
                    for _, href, text in links:
                        t = re.sub(r'<[^>]+>', '', text).strip()
                        h = href.lower()
                        if t and len(t) > 2:
                            doc_type = "unknown"
                            if 'nit' in h or 'notice' in h: doc_type = "NIT"
                            elif 'boq' in h: doc_type = "BOQ"
                            elif 'gcc' in h: doc_type = "GCC"
                            elif 'pcc' in h: doc_type = "PCC"
                            elif 'tdc' in h: doc_type = "TDC"
                            elif 'draw' in h or 'design' in h: doc_type = "Drawing/Design"
                            elif 'form' in h or 'format' in h: doc_type = "Form/Format"
                            elif 'schedule' in h: doc_type = "Schedule"
                            elif 'corrigendum' in h: doc_type = "Corrigendum"
                            elif 'upload' in h or 'submission' in h: doc_type = "Upload/Submission"
                            
                            entry = {"name": t, "url": href[:150], "type": doc_type}
                            result["documents"].append(entry)
                            print(f"     📄 [{doc_type:20s}] {t[:50]:50s} → {href[:80]}")
                    
                    # Find form fields
                    forms = re.findall(r'<form[^>]*>(.*?)</form>', r.text, re.DOTALL)
                    for i, form in enumerate(forms):
                        inputs = re.findall(r'<input[^>]*name=(["\'])([^"\']+)\1[^>]*>', form)
                        if inputs:
                            print(f"\n     📝 Form {i}: {len(inputs)} fields")
                            for _, name in inputs[:10]:
                                print(f"        Field: {name}")
                            result["forms"].append({"form_index": i, "fields": [n for _, n in inputs]})
                    
                    # Find download servlets
                    downloads = re.findall(r'["\'](/[^"\']*Download[^"\']*Servlet[^"\']*)["\']', r.text)
                    for d in downloads:
                        print(f"     ⬇️  Download: {d}")
                        result["downloads"].append(d)
                        
            except Exception as e:
                print(f"     ❌ Error: {e}")
        
        self.client.close()
        return result


def main():
    parser = argparse.ArgumentParser(description="eGP Portal Explorer")
    parser.add_argument("command", nargs="?", default="explore",
                       choices=["explore", "tender", "documents", "mytenders", "archived"])
    parser.add_argument("tender_id", nargs="?", default="", help="Tender ID")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    
    explorer = PortalExplorer()
    
    if args.command == "explore":
        explorer.explore_homepage()
    elif args.command == "tender" and args.tender_id:
        explorer.explore_tender_details(args.tender_id)
    elif args.command == "documents" and args.tender_id:
        explorer.explore_tender_documents(args.tender_id)
    elif args.command in ("mytenders", "archived"):
        explorer.explore_my_tenders("Archive")
    else:
        print("Usage: python -m app.agents.portal_explorer [command] [tender_id]")
        print("Commands: explore, tender <id>, documents <id>, mytenders, archived")


if __name__ == "__main__":
    main()
