"""
Agent 34 — Tender Preparation Agent
Extracts knowledge from the eGP portal Contract Signing tab (post-award) to
discover all forms, mapped documents, and field mappings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus
from .egp_client import eGPClient, BASE_URL
from .credentials import get_credentials

logger = logging.getLogger(__name__)


class TenderPreparationAgent(BaseAgent):
    agent_id = "agent-034-tender-preparation"
    agent_name = "Tender Preparation"
    description = (
        "Navigates the eGP portal Contract Signing tab to discover forms, "
        "mapped documents, and field mappings for tender preparation."
    )
    dependencies: List[str] = ["agent-002-tender-acquisition"]
    version = "1.0.0"

    def __init__(self):
        super().__init__()
        self._client: Optional[eGPClient] = None

    async def _get_client(self) -> eGPClient:
        if self._client is None:
            creds = await asyncio.to_thread(get_credentials)
            self._client = eGPClient(
                email=creds.egp.email if hasattr(creds, 'egp') else '',
                password=creds.egp.password if hasattr(creds, 'egp') else ''
            )
            if hasattr(creds, 'egp') and creds.egp.is_valid:
                await asyncio.to_thread(self._client.login)
        return self._client

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        upstream = context.get("upstream", {})
        acq_output = upstream.get("agent-002-tender-acquisition", {})

        tender_id = context.get("tender_id", "") or acq_output.get("tender_id", "")
        if not tender_id:
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                output={"error": "No tender ID provided", "note": "Cannot access contract signing without a tender ID"},
            )

        logger.info(f"Tender Preparation for tender: {tender_id}")

        storage_base = get_credentials().storage_path
        tender_dir = os.path.join(storage_base, str(tender_id), "tender_preparation")
        os.makedirs(tender_dir, exist_ok=True)

        result = {
            "tender_id": tender_id,
            "forms": [],
            "mapped_documents": [],
            "field_mappings": {},
            "all_fields": [],
            "preparation_notes": [],
        }

        try:
            client = await self._get_client()

            # Step 1: Find tender in My Tender → Archived
            logger.info(f"[Portal Navigation] Searching My Tender → Archived for {tender_id}")
            my_tenders = await asyncio.to_thread(client.search_my_tender, tender_id)
            found_in_my_tender = any(tender_id in t.tender_id for t in my_tenders)
            result["found_in_my_tender"] = found_in_my_tender

            # Step 2: Access tender dashboard to find contract signing tab
            logger.info(f"[Portal Navigation] Accessing tender dashboard for contract signing tab")
            dashboard_links = []
            try:
                resp = client.client.post(
                    f"{BASE_URL}/resources/common/ViewTender.jsp",
                    data={"id": tender_id, "h": "t"},
                    timeout=30,
                )
                if resp.status_code == 200 and len(resp.text) > 500:
                    dashboard_links = client._extract_links_from_html(resp.text)
            except Exception as exc:
                logger.debug(f"Dashboard access failed: {exc}")

            # Step 3: Get the full contract signing section
            logger.info(f"[Portal Navigation] Fetching Contract Signing section")
            signing_data = await asyncio.to_thread(client.get_contract_signing, tender_id)

            # Step 4: Categorize what was found
            result["forms"] = signing_data.get("forms", [])
            result["mapped_documents"] = signing_data.get("mapped_documents", [])
            result["all_fields"] = signing_data.get("all_fields", [])

            # Step 5: Build field mappings — group fields by form
            form_fields = signing_data.get("form_fields", [])
            for i, ff in enumerate(form_fields):
                source = ff.get("source_page", f"form_{i}")
                fields = ff.get("fields", [])
                result["field_mappings"][f"form_{i}"] = {
                    "source": source,
                    "fields": fields,
                    "count": len(fields),
                }

            # Step 6: Generate preparation notes
            result["preparation_notes"] = self._generate_preparation_notes(
                signing_data, dashboard_links, tender_id
            )

            # Step 7: Save the extracted data to storage
            manifest_path = os.path.join(tender_dir, "tender_preparation_manifest.json")
            with open(manifest_path, "w") as f:
                json.dump({
                    "tender_id": tender_id,
                    "total_forms": signing_data.get("total_forms", 0),
                    "total_mapped_docs": signing_data.get("total_mapped_docs", 0),
                    "total_unique_fields": signing_data.get("total_unique_fields", 0),
                    "form_types_found": signing_data.get("form_types_found", []),
                    "all_fields": result["all_fields"],
                }, f, indent=2)
            result["manifest_path"] = manifest_path

            # Step 8: Download forms and mapped documents
            downloaded = 0
            for entry in result["forms"] + result["mapped_documents"]:
                doc_url = entry.get("url", "")
                doc_name = entry.get("name", f"doc_{downloaded}")
                doc_type = entry.get("type", "unknown")
                if doc_url:
                    try:
                        url = doc_url if doc_url.startswith("http") else f"{BASE_URL}{doc_url}"
                        doc_resp = client.client.get(url, timeout=30)
                        if doc_resp.status_code == 200 and len(doc_resp.content) > 100:
                            ext = ".pdf"
                            if any(k in doc_url.lower() for k in ['.xls', '.xlsx']):
                                ext = ".xlsx"
                            elif any(k in doc_url.lower() for k in ['.doc', '.docx']):
                                ext = ".docx"
                            safe_name = re.sub(r'[^\w\-_. ]', '_', doc_name)[:60]
                            save_path = os.path.join(tender_dir, f"{doc_type}_{safe_name}{ext}")
                            with open(save_path, "wb") as f:
                                f.write(doc_resp.content)
                            downloaded += 1
                    except Exception as de:
                        logger.debug(f"Could not download {doc_name}: {de}")

            result["forms_downloaded"] = downloaded

        except Exception as exc:
            logger.warning(f"Contract signing access failed (offline/demo mode): {exc}")
            result["error"] = str(exc)

        summary = (
            f"Tender Preparation for {tender_id}: "
            f"{len(result['forms'])} forms, "
            f"{len(result['mapped_documents'])} mapped docs, "
            f"{len(result['all_fields'])} unique fields, "
            f"{result.get('forms_downloaded', 0)} downloaded"
        )
        logger.info(summary)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=result,
        )

    def _generate_preparation_notes(
        self, signing_data: Dict, dashboard_links: List, tender_id: str
    ) -> List[str]:
        """Generate human-readable preparation notes from the data found."""
        notes = []
        forms = signing_data.get("forms", [])
        mapped = signing_data.get("mapped_documents", [])
        all_fields = signing_data.get("all_fields", [])

        if forms:
            notes.append(f"Found {len(forms)} forms to fill in Contract Signing tab:")
            for f in forms[:10]:
                notes.append(f"  - {f.get('name', 'unnamed')} ({f.get('type', 'unknown')})")

        if mapped:
            notes.append(f"Found {len(mapped)} mapped documents:")
            for d in mapped[:10]:
                notes.append(f"  - {d.get('name', 'unnamed')} ({d.get('type', 'unknown')})")

        if all_fields:
            notes.append(f"Total {len(all_fields)} unique form fields to fill:")
            for f in sorted(all_fields)[:20]:
                notes.append(f"  - Field: {f}")
            if len(all_fields) > 20:
                notes.append(f"  ... and {len(all_fields) - 20} more fields")

        if not forms and not mapped:
            notes.append(
                f"No contract signing data found for tender {tender_id}. "
                "This may mean the tender is not yet awarded, "
                "or the eGP credentials lack access to this tender."
            )

        return notes


# Also expose the knowledge extraction as a standalone function
def extract_contract_signing_knowledge(
    tender_id: str, email: str = "", password: str = ""
) -> Dict[str, Any]:
    """Standalone function to extract contract signing knowledge from the portal."""
    client = eGPClient(email=email, password=password)
    try:
        if email and password:
            client.login()
        result = client.get_contract_signing(tender_id)
        return {
            "tender_id": tender_id,
            "forms_count": result.get("total_forms", 0),
            "mapped_docs_count": result.get("total_mapped_docs", 0),
            "unique_fields": result.get("all_fields", []),
            "form_types": result.get("form_types_found", []),
            "forms": result.get("forms", []),
            "mapped_documents": result.get("mapped_documents", []),
        }
    finally:
        client.close()
