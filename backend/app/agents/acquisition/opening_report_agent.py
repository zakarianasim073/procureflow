from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.credentials import get_credentials
from app.agents.egp_client import eGPClient

logger = logging.getLogger(__name__)


class OpeningReportAgent(BaseAgent):
    agent_id = "agent-045-opening-report"
    agent_name = "Opening Report"
    description = "Fetches archived tender opening reports from My Tenders -> Archived -> Opening -> TOR2/TORR2"
    dependencies: List[str] = []
    version = "1.0.0"

    def __init__(self, brain=None):
        super().__init__(brain)
        self._client: Optional[eGPClient] = None

    async def _get_client(self) -> eGPClient:
        if self._client is None:
            creds = await asyncio.to_thread(get_credentials)
            self._client = eGPClient(
                email=creds.egp.email if hasattr(creds, "egp") else "",
                password=creds.egp.password if hasattr(creds, "egp") else "",
                timeout=30,
            )
            if hasattr(creds, "egp") and creds.egp.is_valid:
                await asyncio.to_thread(self._client.login)
        return self._client

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _runtime_dir(self, tender_id: str) -> Path:
        return self._repo_root() / "runtime" / "opening_reports" / tender_id

    def _safe_slug(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("._") or "tender"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = str(context.get("tender_id", "")).strip()
        if not tender_id:
            upstream = context.get("upstream", {})
            acquisition = upstream.get("agent-002-tender-acquisition", {})
            tender_id = str(acquisition.get("tender_id", "")).strip()

        if not tender_id:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="No tender_id provided",
                output={"status": "missing_tender_id"},
            )

        tender_id = self._safe_slug(tender_id)
        runtime_dir = self._runtime_dir(tender_id)
        runtime_dir.mkdir(parents=True, exist_ok=True)

        client = await self._get_client()
        report = await asyncio.to_thread(client.get_opening_report_tor2, tender_id, "0", True, False)

        pdf_path = ""
        pdf_bytes = report.pop("pdf_bytes", b"") if isinstance(report, dict) else b""
        if pdf_bytes:
            pdf_path = str(runtime_dir / f"{tender_id}_TOR2.pdf")
            Path(pdf_path).write_bytes(pdf_bytes)

        metadata = report.get("metadata", {}) if isinstance(report, dict) else {}
        report["pdf_path"] = pdf_path
        report["runtime_dir"] = str(runtime_dir)
        report["route"] = "My Tenders -> Archived -> Dashboard -> Opening -> TOR2/TORR2"

        manifest_path = runtime_dir / "opening_report_manifest.json"
        manifest_path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")

        summary_lines = [
            f"Tender ID: {tender_id}",
            f"Status: {report.get('status', 'unknown')}",
            f"Package No: {metadata.get('package_no', '')}",
            f"Opening Date: {metadata.get('opening_date', '')}",
            f"Procuring Entity: {metadata.get('procuring_entity', '')}",
            f"Bidder Count: {metadata.get('bidder_count', 0)}",
            f"Price Bid Count: {metadata.get('price_bid_count', 0)}",
            f"PDF Saved: {pdf_path or 'no'}",
            f"Generated At: {datetime.now(timezone.utc).isoformat()}",
        ]
        summary_path = runtime_dir / "summary.txt"
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

        output = {
            **report,
            "manifest_path": str(manifest_path),
            "summary_path": str(summary_path),
        }

        status = AgentStatus.SUCCESS if report.get("status") == "success" else AgentStatus.FAILED
        error = "; ".join(report.get("errors", [])) if status == AgentStatus.FAILED else ""
        return AgentResult(status=status, output=output, error=error)
