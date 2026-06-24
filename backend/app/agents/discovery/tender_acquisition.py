"""
Agent 2 - Tender Acquisition Agent
Acquires tender metadata and documents from the live e-GP portal.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import sys
import time
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.credentials import get_credentials
from app.agents.egp_client import BASE_URL, TenderInfo, eGPClient



logger = logging.getLogger(__name__)


class TenderAcquisitionAgent(BaseAgent):
    agent_id = "agent-002-tender-acquisition"
    agent_name = "Tender Acquisition"
    description = "Acquires tender metadata and documents from the e-GP portal"
    dependencies = ["agent-001-tender-radar"]
    version = "1.4.0"

    def __init__(self, brain=None):
        super().__init__(brain)
        self._client: Optional[eGPClient] = None

    @property
    def client(self) -> eGPClient:
        return self._get_client_sync()

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _runtime_root(self) -> Path:
        return self._repo_root() / "runtime" / "tender_acquisition"

    def _log_root(self) -> Path:
        return self._repo_root() / "runtime" / "logs" / "tender_acquisition"

    def _safe_slug(self, value: str) -> str:
        text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
        return text.strip("._") or "tender"

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._jsonable(v) for v in value]
        if isinstance(value, tuple):
            return [self._jsonable(v) for v in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (datetime,)):
            return value.isoformat()
        return value

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._jsonable(payload), indent=2, ensure_ascii=True), encoding="utf-8")

    def _append_jsonl(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(self._jsonable(payload), ensure_ascii=True))
            fh.write("\n")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _guess_ext_from_mime(self, mime_type: str, fallback_name: str = "") -> str:
        lower = f"{mime_type} {fallback_name}".lower()
        if "pdf" in lower:
            return ".pdf"
        if "zip" in lower:
            return ".zip"
        if "html" in lower:
            return ".html"
        if "json" in lower:
            return ".json"
        if "xml" in lower:
            return ".xml"
        if "docx" in lower or "wordprocessingml" in lower:
            return ".docx"
        if "sheet" in lower or "excel" in lower or "spreadsheetml" in lower:
            return ".xlsx"
        if "text/plain" in lower:
            return ".txt"
        return ".bin"

    def import_browser_bridge_artifacts(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tender_id = self._safe_slug(payload.get("tender_id", ""))
        if not tender_id:
            raise ValueError("tender_id is required")

        tender_dir = self._runtime_root() / tender_id
        docs_dir = tender_dir / "documents"
        logs_dir = self._log_root() / tender_id
        tender_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = tender_dir / "manifest.json"
        summary_path = tender_dir / "summary.txt"
        run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_log_path = logs_dir / f"{run_stamp}_browser_bridge.jsonl"

        manifest = self._read_json(manifest_path)
        if not manifest:
            manifest = {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "tender_id": tender_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "partial",
                "tender_info": {},
                "search_hits": [],
                "documents": [],
                "downloaded_files": [],
                "crawler": {},
                "errors": [],
            }

        browser_capture = payload.get("browser_capture", {}) if isinstance(payload.get("browser_capture"), dict) else {}
        artifacts = payload.get("artifacts", []) if isinstance(payload.get("artifacts"), list) else []
        imported_files: List[Dict[str, Any]] = []
        document_entries: List[Dict[str, Any]] = manifest.get("documents", []) if isinstance(manifest.get("documents"), list) else []
        downloaded_files: List[Dict[str, Any]] = manifest.get("downloaded_files", []) if isinstance(manifest.get("downloaded_files"), list) else []

        self._append_jsonl(run_log_path, {"event": "browser_bridge_start", "artifact_count": len(artifacts)})

        for index, artifact in enumerate(artifacts, start=1):
            if not isinstance(artifact, dict):
                continue
            name = str(artifact.get("name") or artifact.get("url") or f"artifact_{index}").strip()
            url = str(artifact.get("url") or "").strip()
            doc_type = str(artifact.get("type") or artifact.get("kind") or "browser_capture").strip()
            mime_type = str(artifact.get("mime_type") or artifact.get("mimeType") or "").strip()
            ext = self._guess_ext_from_mime(mime_type, fallback_name=name)
            filename = self._resolve_document_name(name, doc_type or "browser_capture", ext)
            save_path = docs_dir / filename

            bytes_written = 0
            if artifact.get("base64"):
                raw = base64.b64decode(str(artifact["base64"]))
                save_path.write_bytes(raw)
                bytes_written = len(raw)
            elif artifact.get("text") is not None:
                text_content = str(artifact.get("text") or "")
                save_path.write_text(text_content, encoding="utf-8")
                bytes_written = len(text_content.encode("utf-8"))
            else:
                continue

            entry = {
                "source": "browser_bridge",
                "name": name,
                "url": url,
                "type": doc_type,
                "kind": self._classify_document(doc_type, name, url),
                "mime_type": mime_type,
            }
            document_entries.append(entry)
            file_record = {
                "doc_type": doc_type,
                "path": str(save_path),
                "size_bytes": bytes_written,
                "source": "browser_bridge",
                "url": url,
                "mime_type": mime_type,
            }
            downloaded_files.append(file_record)
            imported_files.append(file_record)
            self._append_jsonl(run_log_path, {"event": "browser_bridge_saved", "path": str(save_path), "url": url, "size_bytes": bytes_written})

        manifest["documents"] = document_entries
        manifest["downloaded_files"] = downloaded_files
        manifest["browser_bridge"] = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_url": browser_capture.get("source_url", ""),
            "page_title": browser_capture.get("page_title", ""),
            "artifact_count": len(imported_files),
            "run_log_path": str(run_log_path),
        }
        if imported_files:
            manifest["status"] = "partial" if manifest.get("errors") else "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(manifest_path, manifest)

        summary_lines = [
            f"Tender ID: {tender_id}",
            f"Status: {manifest.get('status', 'partial')}",
            f"Browser bridge imported: {len(imported_files)}",
            f"Total documents tracked: {len(document_entries)}",
            f"Total downloaded files: {len(downloaded_files)}",
            f"Source URL: {browser_capture.get('source_url', '')}",
        ]
        summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
        self._append_jsonl(run_log_path, {"event": "browser_bridge_complete", "imported_files": len(imported_files), "manifest_path": str(manifest_path)})

        return {
            "tender_id": tender_id,
            "imported_files": imported_files,
            "manifest_path": str(manifest_path),
            "summary_path": str(summary_path),
            "run_log_path": str(run_log_path),
            "storage_dir": str(tender_dir),
            "status": manifest.get("status", "partial"),
        }

    def _get_client_sync(self) -> eGPClient:
        if self._client is None:
            creds = get_credentials()
            self._client = eGPClient(
                email=creds.egp.email,
                password=creds.egp.password,
                timeout=120,
            )
            if creds.egp.is_valid:
                try:
                    self._client.login()
                except Exception as exc:
                    logger.debug("eGP login failed during sync init: %s", exc)
        return self._client

    def _apply_browser_cookies(self, client: eGPClient, cookies: Dict[str, str]) -> None:
        if not cookies:
            return
        for name, value in cookies.items():
            if not value:
                continue
            try:
                client.client.cookies.set(name, value, domain="www.eprocure.gov.bd", path="/")
            except Exception:
                client.client.cookies.set(name, value)

        jsession = cookies.get("JSESSIONID", "")
        cptu_cookie = cookies.get("CPTU-COOKIE", "")
        if jsession:
            client.session.jsessionid = jsession
        if cptu_cookie:
            client.session.cptu_cookie = cptu_cookie
        if jsession or cptu_cookie:
            client.session.is_authenticated = True

    async def _get_client_async(self) -> eGPClient:
        if self._client is None:
            creds = await asyncio.to_thread(get_credentials)
            self._client = eGPClient(
                email=creds.egp.email,
                password=creds.egp.password,
                timeout=120,
            )
            if creds.egp.is_valid:
                try:
                    await asyncio.to_thread(self._client.login)
                except Exception as exc:
                    logger.debug("eGP login failed during async init: %s", exc)
        return self._client

    def _tender_info_to_dict(self, tender: Optional[TenderInfo]) -> Dict[str, Any]:
        if not tender:
            return {}
        return {
            "tender_id": tender.tender_id,
            "title": tender.title,
            "procuring_entity": tender.procuring_entity,
            "published_date": tender.published_date,
            "deadline": tender.deadline,
            "estimated_value_bdt": tender.estimated_value_bdt,
            "category": tender.category,
            "location": tender.location,
            "document_fees": tender.document_fees,
            "bid_security": tender.bid_security,
            "status": tender.status,
        }

    def _resolve_document_name(self, name: str, doc_type: str, ext: str) -> str:
        base = self._safe_slug(name or doc_type or "document")
        if not base.lower().endswith(ext.lower()):
            return f"{base}{ext}"
        return base

    def _guess_ext(self, doc_type: str, content: bytes = b"", url: str = "") -> str:
        lower = f"{doc_type} {url}".lower()
        if ".xlsx" in lower or ".xls" in lower:
            return ".xlsx"
        if ".docx" in lower or ".doc" in lower:
            return ".docx"
        if "boq" in lower:
            return ".xlsx"
        if any(k in lower for k in ["drawing", "design", "spec", "notice", "nit", "tds", "tender"]):
            return ".pdf"
        if content.startswith(b"%PDF"):
            return ".pdf"
        return ".bin"

    def _classify_document(self, doc_type: str, name: str, url: str) -> str:
        combined = f"{doc_type} {name} {url}".lower()
        if "nit" in combined or "notice" in combined:
            return "notice"
        if "tds" in combined or "tender data" in combined or "tender data sheet" in combined:
            return "tds"
        if "boq" in combined:
            return "boq"
        if "drawing" in combined or "design" in combined:
            return "drawing"
        if "corrig" in combined or "addendum" in combined:
            return "corrigendum"
        if "spec" in combined or "instruction" in combined:
            return "specification"
        if "form" in combined or "format" in combined or "schedule" in combined:
            return "forms"
        return "other"

    async def _crawl_dashboard(self, tender_id: str, cookies: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Fetch TenderDocView.jsp via subprocess httpx — bypasses in-process connectivity issues."""
        sub_script = Path(__file__).resolve().parent / "_sub_dl.py"
        docs_dir = self._runtime_root() / tender_id / "documents"
        uploads_dir = self._repo_root() / "uploads" / tender_id
        docs_dir.mkdir(parents=True, exist_ok=True)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(sub_script),
                tender_id, str(docs_dir), str(uploads_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            out_text = stdout.decode("utf-8", errors="replace")
            lines = [l.strip() for l in out_text.strip().splitlines() if l.strip()]
            if lines:
                result_json = lines[-1]
                sub_results = json.loads(result_json)
                if isinstance(sub_results, list):
                    # Build document listing from downloaded files
                    documents = []
                    for item in sub_results:
                        url = item.get("url", "")
                        name = item.get("doc_type", "document")
                        documents.append({"name": name, "url": url, "type": name, "kind": "downloaded"})
                    return {"status": "success", "documents": documents, "tender_id": tender_id}
            return {"status": "failed", "error": "subprocess produced no parsable output", "tender_id": tender_id, "documents": []}
        except Exception as exc:
            logger.warning("Subprocess dashboard crawl failed for %s: %s", tender_id, exc)
            return {"status": "failed", "error": str(exc), "tender_id": tender_id, "documents": []}

    async def _download_document_bytes(self, client: eGPClient, tender_id: str, doc_type: str) -> Optional[bytes]:
        try:
            return await asyncio.to_thread(client.download_document, tender_id, doc_type)
        except Exception as exc:
            logger.debug("Download failed for %s/%s: %s", tender_id, doc_type, exc)
            return None

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        started_at = datetime.now(timezone.utc)
        upstream = context.get("upstream", {})
        radar_output = upstream.get("agent-001-tender-radar", {})

        tender_id = str(context.get("tender_id", "")).strip()
        if not tender_id:
            tenders = radar_output.get("tenders_found", [])
            if tenders:
                first = tenders[0]
                if isinstance(first, dict):
                    tender_id = str(first.get("tender_id", "")).strip()
                else:
                    tender_id = str(first).strip()

        if not tender_id:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="No tender_id provided",
                output={"status": "missing_tender_id", "tender_id": ""},
            )

        tender_id = self._safe_slug(tender_id)
        logger.info("Acquiring tender %s from e-GP", tender_id)

        run_id = context.get("_request_id") or context.get("request_id") or f"acq-{int(time.time())}"
        run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        tender_dir = self._runtime_root() / tender_id
        docs_dir = tender_dir / "documents"
        logs_dir = self._log_root() / tender_id
        tender_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        run_log_path = logs_dir / f"{run_stamp}_{run_id}.jsonl"
        manifest_path = tender_dir / "manifest.json"
        summary_path = tender_dir / "summary.txt"

        manifest: Dict[str, Any] = {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "run_id": run_id,
            "tender_id": tender_id,
            "started_at": started_at.isoformat(),
            "status": "started",
            "tender_info": {},
            "search_hits": [],
            "documents": [],
            "downloaded_files": [],
            "crawler": {},
            "errors": [],
        }
        self._write_json(manifest_path, manifest)
        self._append_jsonl(run_log_path, {"event": "start", "manifest_path": str(manifest_path)})

        status = AgentStatus.SUCCESS
        errors: List[str] = []
        downloaded_files: List[Dict[str, Any]] = []
        document_index: List[Dict[str, Any]] = []
        search_hits: List[Dict[str, Any]] = []
        tender_info: Optional[TenderInfo] = None
        crawler_output: Dict[str, Any] = {}
        browser_cookies = context.get("egp_cookies") or {}

        try:
            client = await self._get_client_async()
            if not browser_cookies:
                fallback_cookies = {}
                if client.session.jsessionid:
                    fallback_cookies["JSESSIONID"] = client.session.jsessionid
                if client.session.cptu_cookie:
                    fallback_cookies["CPTU-COOKIE"] = client.session.cptu_cookie
                browser_cookies = fallback_cookies
            if isinstance(browser_cookies, dict) and browser_cookies:
                self._apply_browser_cookies(client, browser_cookies)
                manifest["browser_cookies"] = sorted(browser_cookies.keys())
                self._append_jsonl(
                    run_log_path,
                    {"event": "browser_cookies_applied", "cookie_names": sorted(browser_cookies.keys())},
                )

            # Confirm the tender exists in the live/search index first.
            try:
                search_results = await asyncio.to_thread(client.search_tender, tender_id)
                for item in search_results:
                    if isinstance(item, TenderInfo):
                        search_hits.append(self._tender_info_to_dict(item))
                if not search_hits:
                    public_hits = await asyncio.to_thread(client.search_tender_public, tender_id)
                    for item in public_hits:
                        if isinstance(item, TenderInfo):
                            search_hits.append(self._tender_info_to_dict(item))
                self._append_jsonl(run_log_path, {"event": "search_complete", "hits": len(search_hits)})
            except Exception as exc:
                errors.append(f"search_failed: {exc}")
                logger.warning("Tender search failed for %s: %s", tender_id, exc)

            # Resolve the actual tender metadata.
            try:
                tender_info = await asyncio.to_thread(client.get_tender_by_id, tender_id)
                manifest["tender_info"] = self._tender_info_to_dict(tender_info)
                self._append_jsonl(run_log_path, {"event": "tender_info", "found": bool(tender_info)})
            except Exception as exc:
                errors.append(f"tender_lookup_failed: {exc}")
                logger.warning("Tender lookup failed for %s: %s", tender_id, exc)

            # Extract dashboard notice / TDS / BOQ structure using the browser crawler.
            try:
                crawler_output = await self._crawl_dashboard(
                    tender_id,
                    cookies=browser_cookies if isinstance(browser_cookies, dict) else None,
                )
                manifest["crawler"] = crawler_output
                crawler_status = str(crawler_output.get("status", ""))
                crawler_error = str(crawler_output.get("error", "") or "")
                if crawler_status and crawler_status not in {"completed", "success"}:
                    errors.append(f"crawler_status:{crawler_status}")
                if crawler_error:
                    errors.append(f"crawler_error:{crawler_error}")
                self._append_jsonl(
                    run_log_path,
                    {
                        "event": "crawler_complete",
                        "status": crawler_output.get("status"),
                        "documents": len(crawler_output.get("documents", [])),
                    },
                )
            except Exception as exc:
                errors.append(f"crawler_failed: {exc}")
                logger.warning("Crawler failed for %s: %s", tender_id, exc)

            # Extract document tab links and try to download all supported documents.
            try:
                docs_result = await asyncio.to_thread(client.get_tender_documents, tender_id)
            except Exception as exc:
                docs_result = {"tender_id": tender_id, "documents": [], "forms": [], "download_links": []}
                errors.append(f"document_index_failed: {exc}")
                logger.warning("Document index lookup failed for %s: %s", tender_id, exc)
            else:
                if not docs_result.get("documents") and not docs_result.get("download_links"):
                    errors.append("document_index_empty")

            # ── Direct e-GP document download via subprocess (bypasses in-process httpx issues) ──
            sub_script = str(Path(__file__).resolve().parent / "_sub_dl.py")
            uploads_dir = self._repo_root() / "uploads" / tender_id
            uploads_dir.mkdir(parents=True, exist_ok=True)
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, sub_script,
                    tender_id, str(docs_dir), str(uploads_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
                out_text = stdout.decode("utf-8", errors="replace")
                err_text = stderr.decode("utf-8", errors="replace")
                for line in err_text.strip().splitlines():
                    if line.strip():
                        logger.warning("Sub dl stderr: %s", line.strip())
                lines = [l.strip() for l in out_text.strip().splitlines() if l.strip()]
                if lines:
                    try:
                        sub_results = json.loads(lines[-1])
                        if isinstance(sub_results, list):
                            for item in sub_results:
                                if item not in downloaded_files:
                                    downloaded_files.append(item)
                            logger.info("Subprocess download returned %d files", len(sub_results))
                    except (json.JSONDecodeError, Exception) as exc:
                        logger.warning("Could not parse subprocess result JSON: %s", exc)
                else:
                    logger.warning("Subprocess produced no output")
            except Exception as exc:
                errors.append(f"egp_direct_download_failed: {exc}")
                logger.warning("e-GP direct download failed for %s: %s", tender_id, exc)

            # Merge crawler documents and document-tab links into one index.
            crawler_docs = crawler_output.get("documents", []) if isinstance(crawler_output, dict) else []
            tab_docs = docs_result.get("documents", []) if isinstance(docs_result, dict) else []
            download_links = docs_result.get("download_links", []) if isinstance(docs_result, dict) else []
            forms = docs_result.get("forms", []) if isinstance(docs_result, dict) else []

            def _push_document(entry: Dict[str, Any], source: str) -> None:
                nonlocal document_index
                name = str(entry.get("name") or entry.get("title") or entry.get("type") or "document")
                url = str(entry.get("url") or entry.get("href") or "")
                doc_type = str(entry.get("type") or self._classify_document(name, name, url))
                record = {
                    "source": source,
                    "name": name,
                    "url": url,
                    "type": doc_type,
                    "kind": self._classify_document(doc_type, name, url),
                }
                document_index.append(record)

            for entry in crawler_docs:
                if isinstance(entry, dict):
                    _push_document(entry, "crawler")
            for entry in tab_docs:
                if isinstance(entry, dict):
                    _push_document(entry, "document_tab")
            for entry in download_links:
                if isinstance(entry, dict):
                    _push_document(entry, "download_link")

            # Add forms as separate records.
            for idx, form in enumerate(forms):
                if isinstance(form, dict):
                    document_index.append(
                        {
                            "source": "form_fields",
                            "name": f"form_{idx + 1}",
                            "url": "",
                            "type": "forms",
                            "kind": "forms",
                            "fields": form.get("fields", []),
                        }
                    )

            # Download the primary documents.
            primary_doc_types = ["NIT", "BOQ", "Drawings", "Corrigendum", "Specifications"]
            for doc_type in primary_doc_types:
                content = await self._download_document_bytes(client, tender_id, doc_type)
                if not content:
                    continue
                ext = self._guess_ext(doc_type, content=content)
                filename = self._resolve_document_name(doc_type, doc_type, ext)
                file_path = docs_dir / filename
                file_path.write_bytes(content)
                downloaded_files.append(
                    {
                        "doc_type": doc_type,
                        "path": str(file_path),
                        "size_bytes": len(content),
                        "source": "download_document",
                    }
                )
                self._append_jsonl(run_log_path, {"event": "downloaded", "doc_type": doc_type, "path": str(file_path)})

            # Download any additional document-tab links where the URL is usable.
            for entry in document_index:
                url = str(entry.get("url") or "").strip()
                if not url:
                    continue
                kind = str(entry.get("kind") or entry.get("type") or "").lower()
                name = str(entry.get("name") or entry.get("type") or "document")
                if kind in {"forms", "other"} and "download" not in url.lower() and "servlet" not in url.lower():
                    continue
                try:
                    resolved = urljoin(BASE_URL, url)
                    if resolved.lower().startswith("javascript:"):
                        continue
                    resp = await asyncio.to_thread(client.client.get, resolved, timeout=30)
                    if resp.status_code != 200 or len(resp.content) < 20:
                        continue
                    ext = self._guess_ext(kind or name, content=resp.content, url=resolved)
                    safe_name = self._resolve_document_name(name, kind or "document", ext)
                    save_path = docs_dir / safe_name
                    if not save_path.exists():
                        save_path.write_bytes(resp.content)
                        downloaded_files.append(
                            {
                                "doc_type": kind or "document",
                                "path": str(save_path),
                                "size_bytes": len(resp.content),
                                "source": "document_tab",
                            }
                        )
                except Exception as exc:
                    logger.debug("Tab document fetch failed for %s: %s", url, exc)

            if downloaded_files and "document_index_empty" in errors:
                errors = [err for err in errors if err != "document_index_empty"]

            # Pull a compact extraction summary from the crawler output.
            notice = crawler_output.get("notice", {}) if isinstance(crawler_output, dict) else {}
            tds = crawler_output.get("tds", {}) if isinstance(crawler_output, dict) else {}
            boq = crawler_output.get("boq", {}) if isinstance(crawler_output, dict) else {}

            manifest.update(
                {
                    "status": "completed" if not errors else "partial",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "tender_info": self._tender_info_to_dict(tender_info),
                    "search_hits": search_hits,
                    "documents": document_index,
                    "downloaded_files": downloaded_files,
                    "crawler": crawler_output,
                    "notice": notice,
                    "tds": tds,
                    "boq": boq,
                    "errors": errors,
                }
            )

            summary_lines = [
                f"Tender ID: {tender_id}",
                f"Status: {manifest['status']}",
                f"Title: {manifest['tender_info'].get('title', '')}",
                f"Procuring Entity: {manifest['tender_info'].get('procuring_entity', '')}",
                f"Search hits: {len(search_hits)}",
                f"Index documents: {len(document_index)}",
                f"Downloaded files: {len(downloaded_files)}",
                f"Notice fields: {len(notice) if isinstance(notice, dict) else 0}",
                f"TDS fields: {len(tds) if isinstance(tds, dict) else 0}",
                f"BOQ fields: {len(boq) if isinstance(boq, dict) else 0}",
                f"Errors: {len(errors)}",
            ]
            summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
            self._write_json(manifest_path, manifest)
            self._append_jsonl(
                run_log_path,
                {
                    "event": "complete",
                    "status": manifest["status"],
                    "downloaded_files": len(downloaded_files),
                    "manifest_path": str(manifest_path),
                    "summary_path": str(summary_path),
                },
            )

            # Keep the acquired data visible to upstream agents.
            acquired = {
                "tender_id": tender_id,
                "status": manifest["status"],
                "tender_info": manifest["tender_info"],
                "search_hits": search_hits,
                "notice": notice,
                "tds": tds,
                "boq": boq,
                "documents": document_index,
                "downloaded_files": downloaded_files,
                "manifest_path": str(manifest_path),
                "summary_path": str(summary_path),
                "run_log_path": str(run_log_path),
                "storage_dir": str(tender_dir),
                "downloads_attempted": True,
                "errors": errors,
            }

            # ── Share knowledge with brain (extracted PDF text content) ──
            await self.share_knowledge(
                entry_type="tender_document",
                tender_id=tender_id,
                data=acquired,
                summary=f"Documents acquired for {tender_id}",
                tags=["tender_acquisition", "documents", "egp"],
            )

            # Also extract and share BOQ + TDS text content for downstream agents
            boq_text = None
            tds_text = None
            try:
                import pdfplumber
                for f in downloaded_files:
                    fp = f.get("path", "")
                    if not fp or not Path(fp).exists():
                        continue
                    kind = (f.get("kind") or f.get("doc_type") or "").lower()
                    fname_lower = Path(fp).name.lower() + " " + str(fp).lower()
                    # Detect BOQ/TDS by path keywords when kind field is generic
                    is_boq = "boq" in kind or "bill" in kind or "quantity" in kind or "section6" in fname_lower
                    is_tds = "tds" in kind or "tender data" in kind or "data sheet" in kind or "section2" in fname_lower
                    if not (is_boq or is_tds):
                        continue
                    try:
                        with pdfplumber.open(fp) as pdf:
                            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                        if text.strip():
                            if is_boq:
                                boq_text = text[:50000]
                            elif is_tds:
                                tds_text = text[:50000]
                    except Exception:
                        pass
            except Exception:
                pass

            if boq_text:
                await self.share_knowledge(
                    entry_type="boq_text",
                    tender_id=tender_id,
                    data={"text": boq_text, "file_count": 1, "tender_id": tender_id},
                    summary=f"BOQ text content for {tender_id}",
                    tags=["boq", "extracted_text"],
                )
            if tds_text:
                await self.share_knowledge(
                    entry_type="tds_text",
                    tender_id=tender_id,
                    data={"text": tds_text, "file_count": 1, "tender_id": tender_id},
                    summary=f"TDS text content for {tender_id}",
                    tags=["tds", "extracted_text"],
                )

            if document_index and self.brain:
                if any(item.get("kind") == "boq" for item in document_index):
                    await self.ask_agent(
                        "agent-005-boq-intelligence",
                        "analyze_boq",
                        {"tender_id": tender_id, "boq": boq, "documents": document_index},
                    )
                if any(item.get("kind") in {"tds", "specification"} for item in document_index):
                    await self.ask_agent(
                        "agent-006-spec-intelligence",
                        "analyze_specs",
                        {"tender_id": tender_id, "tds": tds, "documents": document_index},
                    )

            return AgentResult(
                status=AgentStatus.SUCCESS,
                output=acquired,
            )

        except Exception as exc:
            errors.append(str(exc))
            manifest.update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "errors": errors,
                }
            )
            try:
                self._write_json(manifest_path, manifest)
                self._append_jsonl(run_log_path, {"event": "failed", "error": str(exc)})
                summary_path.write_text(
                    "\n".join(
                        [
                            f"Tender ID: {tender_id}",
                            "Status: failed",
                            f"Error: {exc}",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            return AgentResult(
                status=AgentStatus.FAILED,
                error=str(exc),
                output={
                    "tender_id": tender_id,
                    "status": "failed",
                    "manifest_path": str(manifest_path),
                    "run_log_path": str(run_log_path),
                    "errors": errors,
                },
            )
