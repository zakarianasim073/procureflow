"""
Procurement Flow Specialist BD — Data Intelligence Service
Central brain for scraping, storing, querying, and analyzing tender data.
Collects from eGP portal, stores in PostgreSQL + JSON fallback, provides analytics.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("procureflow.data_intelligence")


class DataIntelligenceService:
    """
    Central data intelligence engine.
    
    Capabilities:
    - Scrape all live tenders from eGP
    - Scrape NOA awards (public, no login needed)
    - Store everything in PostgreSQL + JSON files
    - Query/filter by agency, value, date
    - Track historical collections
    - Detect BWDB tenders above threshold
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self._egp_client = None
        self._db = db
        self.data_dir = Path(__file__).parent.parent.parent / "runtime" / "data_intel"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.collection_log = self.data_dir / "collection_log.json"
        self.dedup_db = self.data_dir / "dedup_index.json"
        self._init_log()
        self._init_dedup()

    def set_db(self, db: AsyncSession):
        self._db = db

    def _init_log(self):
        if not self.collection_log.exists():
            self._write_log({
                "created": datetime.now(timezone.utc).isoformat(),
                "collections": [],
                "total_tenders_collected": 0,
                "total_awards_collected": 0,
            })

    def _init_dedup(self):
        if not self.dedup_db.exists():
            self.dedup_db.write_text(json.dumps({
                "seen_tender_ids": [],
                "seen_award_keys": [],
                "last_collection": {},
            }))

    def _load_dedup(self) -> Dict:
        try:
            return json.loads(self.dedup_db.read_text())
        except Exception:
            return {"seen_tender_ids": [], "seen_award_keys": [], "last_collection": {}}

    def _save_dedup(self, data: Dict):
        self.dedup_db.write_text(json.dumps(data, indent=2, default=str))

    def _load_all_seen_ids(self) -> set:
        """Load all previously collected tender IDs from ALL stored files."""
        seen = set()
        for f in sorted(self.data_dir.glob("tenders_*.json")):
            try:
                tenders = json.loads(f.read_text())
                for t in tenders:
                    tid = str(t.get("tender_id", "") or "")
                    if tid:
                        seen.add(tid)
            except Exception:
                continue
        return seen

    def _read_log(self) -> Dict:
        try:
            return json.loads(self.collection_log.read_text())
        except Exception:
            return {"collections": [], "total_tenders_collected": 0, "total_awards_collected": 0}

    def _write_log(self, data: Dict):
        self.collection_log.write_text(json.dumps(data, indent=2, default=str))

    @property
    def egp_client(self):
        if self._egp_client is None:
            from app.agents.egp_client import eGPClient
            from app.agents.credentials import get_credentials
            creds = get_credentials()
            self._egp_client = eGPClient(email=creds.egp.email, password=creds.egp.password, timeout=30)
            if creds.egp.is_valid:
                self._egp_client.login()
        return self._egp_client

    # ── Tender Collection ──────────────────────────────────────────────

    def collect_live_tenders(self, keyword: str = "", max_pages: int = 5) -> Dict[str, Any]:
        """
        Collect live tenders from eGP, paginating through results.
        Tracks last_page per keyword to resume from where we left off.
        Returns summary of what was collected.
        """
        logger.info(f"Collecting live tenders (keyword='{keyword}', max_pages={max_pages})")

        # Resume from last collected page for this keyword
        dedup = self._load_dedup()
        last_page = dedup.get("last_collection", {}).get(keyword or "(all)", 0)
        start_page = last_page + 1

        all_tenders = []
        errors = []

        for page in range(start_page, start_page + max_pages):
            try:
                results = self.egp_client.search_tender(keyword, page=page)
                if results:
                    all_tenders.extend(results)
                    logger.info(f"Page {page}: collected {len(results)} tenders")
                else:
                    break
            except Exception as e:
                errors.append(str(e))
                logger.warning(f"Page {page} failed: {e}")
                break

        # Store to local JSON
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = self.data_dir / f"tenders_{timestamp}.json"
        tender_data = []
        for t in all_tenders:
            tender_data.append({
                "tender_id": t.tender_id,
                "title": t.title,
                "procuring_entity": t.procuring_entity,
                "published_date": t.published_date,
                "deadline": t.deadline,
                "estimated_value_bdt": t.estimated_value_bdt,
                "category": t.category,
                "status": t.status,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        # Deduplicate by tender_id (globally across all previous collections)
        global_seen_ids = self._load_all_seen_ids()
        seen = set()
        unique_tenders = []
        for t in tender_data:
            tid = str(t.get("tender_id", ""))
            if tid and tid not in seen and tid not in global_seen_ids:
                seen.add(tid)
                unique_tenders.append(t)

        logger.info(f"After dedup: {len(unique_tenders)} new tenders (skipped {len(tender_data) - len(unique_tenders)} already collected)")
        if not unique_tenders:
            logger.info("No new tenders found — skipping file write")
            return {"collected": 0, "file": None, "errors": errors, "skipped": True}

        filepath.write_text(json.dumps(unique_tenders, indent=2, default=str))
        logger.info(f"Saved {len(unique_tenders)} unique tenders to {filepath.name}")

        # Update collection log
        log = self._read_log()
        log["collections"].append({
            "timestamp": timestamp,
            "type": "live_tenders",
            "count": len(unique_tenders),
            "file": filepath.name,
            "errors": errors,
        })
        log["total_tenders_collected"] = log.get("total_tenders_collected", 0) + len(unique_tenders)
        self._write_log(log)

        # Persist last collected page per keyword for resume capability
        dedup = self._load_dedup()
        if "last_collection" not in dedup:
            dedup["last_collection"] = {}
        dedup["last_collection"][keyword or "(all)"] = page
        self._save_dedup(dedup)

        return {
            "collected": len(unique_tenders),
            "file": str(filepath),
            "errors": errors,
        }

    def collect_all_tender_tabs(self) -> Dict[str, Any]:
        """Collect tenders from all tabs: Live, Archive, All, Cancel.
        Deduplicates globally across all previously collected files.
        """
        logger.info("Collecting tenders from ALL tabs...")
        global_seen_ids = self._load_all_seen_ids()
        result = self.egp_client.search_all_tenders()
        totals = {}
        new_total = 0
        for tab, tenders in result.items():
            if not tenders:
                totals[tab] = 0
                continue
            data = []
            for t in tenders:
                tid = str(getattr(t, "tender_id", "") or "")
                if tid and tid not in global_seen_ids:
                    global_seen_ids.add(tid)
                    data.append({
                        "tender_id": tid,
                        "title": getattr(t, "title", ""),
                        "procuring_entity": getattr(t, "procuring_entity", ""),
                        "deadline": getattr(t, "deadline", ""),
                        "estimated_value_bdt": getattr(t, "estimated_value_bdt", 0),
                        "status": getattr(t, "status", ""),
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                    })
            totals[tab] = len(data)
            new_total += len(data)
            if data:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                fp = self.data_dir / f"tenders_{tab}_{ts}.json"
                fp.write_text(json.dumps(data, indent=2, default=str))

        logger.info(f"Collected {new_total} new tenders across all tabs (skipped duplicates)")
        log = self._read_log()
        log["collections"].append({
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
            "type": "all_tabs",
            "count": new_total,
            "details": totals,
        })
        log["total_tenders_collected"] = log.get("total_tenders_collected", 0) + new_total
        self._write_log(log)

        return {"collected": new_total, "breakdown": totals}

    # ── Award Collection ──────────────────────────────────────────────

    def collect_noa_awards(self, entity: str = "", days: int = 90, max_pages: int = 5) -> Dict[str, Any]:
        """
        Collect NOA (Notification of Award) data.
        Works without authentication (public endpoint).
        Collects up to max_pages of results.
        Deduplicates globally and tracks last page per entity.
        """
        logger.info(f"Collecting NOA awards (entity='{entity}', days={days})")

        # Load all previously collected award keys for dedup
        seen_award_keys: set = set()
        for f in sorted(self.data_dir.glob("awards_*.json")):
            try:
                awards = json.loads(f.read_text())
                for a in awards:
                    k = str(a.get("tender_id", a.get("ref_no", "")))
                    if k:
                        seen_award_keys.add(k)
            except Exception:
                continue

        # Resume from last page for this entity
        dedup = self._load_dedup()
        entity_key = entity or "(all)"
        last_page = dedup.get("last_collection", {}).get(f"awards_{entity_key}", 0)
        start_page = last_page + 1

        all_awards = []
        for page in range(start_page, start_page + max_pages):
            try:
                results = self.egp_client.search_noa(entity=entity, days=days)
                if results:
                    for r in results:
                        k = str(getattr(r, "tender_id", getattr(r, "ref_no", "")))
                        if k and k not in seen_award_keys:
                            seen_award_keys.add(k)
                            all_awards.append(r)
                else:
                    break
            except Exception as e:
                logger.warning(f"NOA page {page} failed: {e}")
                break

        if not all_awards:
            logger.info("No new awards found — skipping file write")
            return {"collected": 0, "file": None, "skipped": True}

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fp = self.data_dir / f"awards_{ts}.json"
        fp.write_text(json.dumps(all_awards, indent=2, default=str))
        logger.info(f"Saved {len(all_awards)} awards to {fp.name}")

        log = self._read_log()
        log["collections"].append({
            "timestamp": ts,
            "type": "noa_awards",
            "count": len(all_awards),
            "file": fp.name,
        })
        log["total_awards_collected"] = log.get("total_awards_collected", 0) + len(all_awards)
        self._write_log(log)

        # Persist last page per entity
        dedup = self._load_dedup()
        if "last_collection" not in dedup:
            dedup["last_collection"] = {}
        dedup["last_collection"][f"awards_{entity_key}"] = page
        self._save_dedup(dedup)

        return {"collected": len(all_awards), "file": str(fp)}

    # -- List / Store / Share Awards (used by AwardIntelligenceAgent) --

    def list_awards(self, agency: str = "", limit: int = 100) -> List[Dict]:
        """List previously collected awards, optionally filtered by agency keyword."""
        all_awards: List[Dict] = []
        # Walk files newest-first so we return most recent records
        files = sorted(self.data_dir.glob("awards_*.json"), reverse=True)
        for f in files:
            try:
                awards = json.loads(f.read_text(encoding="utf-8"))
                for a in awards:
                    if agency:
                        entity = (
                            a.get("procuring_entity")
                            or a.get("office")
                            or a.get("agency_target")
                            or ""
                        ).lower()
                        if agency.lower() not in entity:
                            continue
                    all_awards.append(a)
                    if len(all_awards) >= limit:
                        logger.info(
                            f"list_awards: {len(all_awards)} awards found for "
                            f"agency='{agency}' (limit={limit})"
                        )
                        return all_awards
            except Exception as exc:
                logger.debug(f"list_awards: skipping file {f.name}: {exc}")
                continue
        logger.info(
            f"list_awards: {len(all_awards)} awards found for "
            f"agency='{agency}' (limit={limit})"
        )
        return all_awards

    def save_award(self, award: Dict) -> bool:
        """Save a single award dict to a running JSON store on disk."""
        try:
            running_file = self.data_dir / "awards_running.json"
            if running_file.exists():
                existing = json.loads(running_file.read_text(encoding="utf-8"))
            else:
                existing = []
            existing.append(award)
            # Keep at most 50_000 entries to avoid unbounded growth
            if len(existing) > 50_000:
                existing = existing[-50_000:]
            running_file.write_text(
                json.dumps(existing, indent=2, default=str, ensure_ascii=False)
            )
            return True
        except Exception as exc:
            logger.warning(f"save_award failed for tender {award.get('tender_id', '?')}: {exc}")
            return False

    def share_with_agents(self, award: Dict, agent_ids: List[str]) -> bool:
        """Share an award record with downstream agents via a shared knowledge file."""
        try:
            shared_dir = self.data_dir / "shared"
            shared_dir.mkdir(parents=True, exist_ok=True)
            shared_file = shared_dir / "shared_awards.json"
            if shared_file.exists():
                records = json.loads(shared_file.read_text(encoding="utf-8"))
            else:
                records = []
            records.append({
                "award": award,
                "shared_with": agent_ids,
                "shared_at": datetime.now(timezone.utc).isoformat(),
            })
            # Keep last 10 000 entries to bound file size
            if len(records) > 10_000:
                records = records[-10_000:]
            shared_file.write_text(
                json.dumps(records, indent=2, default=str, ensure_ascii=False)
            )
            return True
        except Exception as exc:
            logger.warning(
                f"share_with_agents failed for tender {award.get('tender_id', '?')}: {exc}"
            )
            return False

    # -- Query / Filter -------------------------------------------------

    def get_tenders_by_agency(self, entity_keyword: str, min_value: float = 0) -> List[Dict]:
        """Query collected tenders by procuring entity keyword."""
        results = []
        for f in sorted(self.data_dir.glob("tenders_*.json")):
            try:
                tenders = json.loads(f.read_text())
                for t in tenders:
                    entity = (t.get("procuring_entity") or "").lower()
                    if entity_keyword.lower() in entity:
                        val = t.get("estimated_value_bdt", 0) or 0
                        if val >= min_value:
                            results.append(t)
            except Exception:
                continue
        return results

    def get_bwdb_tenders_above(self, min_crore: float = 5) -> List[Dict]:
        """Get all BWDB tenders with estimated value above threshold (in crore)."""
        min_bdt = min_crore * 10_000_000
        return self.get_tenders_by_agency("BWDB", min_value=min_bdt)

    def get_statistics(self) -> Dict[str, Any]:
        """Return comprehensive collection statistics."""
        log = self._read_log()
        total_tenders = 0
        total_awards = 0
        agency_counts: Dict[str, int] = {}
        bwdb_high_value = 0

        for f in sorted(self.data_dir.glob("tenders_*.json")):
            try:
                tenders = json.loads(f.read_text())
                total_tenders += len(tenders)
                for t in tenders:
                    entity = (t.get("procuring_entity") or "Unknown").strip()
                    agency_counts[entity] = agency_counts.get(entity, 0) + 1
                    if "BWDB" in entity.upper():
                        val = t.get("estimated_value_bdt", 0) or 0
                        if val >= 50_000_000:
                            bwdb_high_value += 1
            except Exception:
                continue

        for f in sorted(self.data_dir.glob("awards_*.json")):
            try:
                awards_data = json.loads(f.read_text())
                total_awards += len(awards_data)
            except Exception:
                continue

        top_agencies = sorted(agency_counts.items(), key=lambda x: -x[1])[:20]

        return {
            "total_tenders_collected": total_tenders,
            "total_awards_collected": total_awards,
            "bwdb_high_value_tenders": bwdb_high_value,
            "unique_agencies": len(agency_counts),
            "top_agencies": [{"name": n, "count": c} for n, c in top_agencies],
            "collections": log.get("collections", []),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # ── Bulk Collection (for daily agent) ─────────────────────────────

    def run_bulk_collection(self, target_count: int = 1000) -> Dict[str, Any]:
        """
        Run a bulk collection pass aiming for at least target_count tenders.
        Combines multiple sources and pages.
        """
        logger.info(f"Starting bulk collection, target: {target_count} tenders")
        start_time = time.time()

        # Phase 1: Collect all tabs (Live + Archive + All + Cancel)
        tabs_result = self.collect_all_tender_tabs()
        total = tabs_result.get("collected", 0)

        # Phase 2: If not enough, do keyword-based searches
        keywords = ["construction", "civil", "road", "building", "bridge", "water"]
        kw_idx = 0
        while total < target_count and kw_idx < len(keywords):
            result = self.collect_live_tenders(keyword=keywords[kw_idx], max_pages=3)
            total += result.get("collected", 0)
            kw_idx += 1

        # Phase 3: Collect awards
        award_result = self.collect_noa_awards(days=180, max_pages=10)

        elapsed = time.time() - start_time
        summary = {
            "total_tenders": total,
            "total_awards": award_result.get("collected", 0),
            "target_met": total >= target_count,
            "duration_seconds": round(elapsed, 1),
            "tabs_breakdown": tabs_result.get("breakdown", {}),
        }
        logger.info(f"Bulk collection complete: {json.dumps(summary, indent=2)}")
        return summary


data_intelligence = DataIntelligenceService()
