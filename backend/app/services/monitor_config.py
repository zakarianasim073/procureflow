"""
Procurement Flow — Monitoring Configuration Service
Persistent monitor config with CRUD + scan orchestration.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("procureflow.monitor")

DEFAULT_CONFIG = {
    "name": "BWDB Monitor",
    "enabled": True,
    "entity_keywords": ["BWDB", "Water Development Board", "পানি উন্নয়ন"],
    "procurement_natures": ["Works", "Goods", "Services"],
    "min_value_bdt": 0,
    "max_value_bdt": 0,
    "alert_channels": {
        "email": {"enabled": True, "recipient": "z.nasim073@gmail.com"},
        "whatsapp": {"enabled": False, "phone": ""},
    },
    "schedule": {
        "interval_minutes": 60,
        "auto_scan": True,
    },
    "filters": {
        "only_deadline_active": True,
        "exclude_expired": True,
    },
    "notify_on": ["new_tender", "high_value"],
    "high_value_threshold_bdt": 5_000_0000,
    "created_at": "",
    "updated_at": "",
}


class MonitorConfigService:
    """Persistent monitoring configuration manager."""

    def __init__(self):
        self.config_dir = os.getenv("TENDERAI_DIR", "./runtime") + "/monitor"
        self.config_file = "monitor_config.json"
        self._config: Dict[str, Any] = {}
        self._load()

    def _config_path(self) -> Path:
        p = Path(self.config_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p / self.config_file

    def _load(self):
        fp = self._config_path()
        if fp.exists():
            try:
                self._config = json.loads(fp.read_text(encoding="utf-8"))
                logger.info(f"Monitor config loaded: {self._config.get('name', 'unknown')}")
            except Exception as e:
                logger.warning(f"Failed to load monitor config: {e}")
                self._config = dict(DEFAULT_CONFIG)
        else:
            self._config = dict(DEFAULT_CONFIG)
            self._config["created_at"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def _save(self):
        self._config["updated_at"] = datetime.now(timezone.utc).isoformat()
        fp = self._config_path()
        fp.write_text(json.dumps(self._config, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Monitor config saved")

    # ── CRUD ───────────────────────────────────────────────────────────

    def get_config(self) -> Dict[str, Any]:
        return dict(self._config)

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        def deep_merge(base, overrides):
            for k, v in overrides.items():
                if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
        deep_merge(self._config, updates)
        self._save()
        return self.get_config()

    def reset_config(self) -> Dict[str, Any]:
        self._config = dict(DEFAULT_CONFIG)
        self._config["created_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return self.get_config()

    def toggle(self, enabled: Optional[bool] = None) -> bool:
        if enabled is not None:
            self._config["enabled"] = enabled
        else:
            self._config["enabled"] = not self._config["enabled"]
        self._save()
        return self._config["enabled"]

    # ── Scan Logic ─────────────────────────────────────────────────────

    def run_scan(self) -> Dict[str, Any]:
        """Run monitoring scan against collected tender data."""
        import glob as glob_mod

        def _notice(t: Dict[str, Any]) -> Dict[str, Any]:
            n = t.get("notice_data")
            return n if isinstance(n, dict) else {}

        def _pick(t: Dict[str, Any], *keys: str, default: Any = "") -> Any:
            n = _notice(t)
            for key in keys:
                value = t.get(key)
                if value not in (None, ""):
                    return value
                value = n.get(key)
                if value not in (None, ""):
                    return value
            return default

        cfg = self._config
        results = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "config_snapshot": {
                "entity_keywords": cfg["entity_keywords"],
                "procurement_natures": cfg["procurement_natures"],
                "min_value_bdt": cfg["min_value_bdt"],
                "max_value_bdt": cfg["max_value_bdt"],
            },
            "matched_tenders": [],
            "alerts_sent": [],
            "total_scanned": 0,
            "total_matched": 0,
        }

        # Find all tender JSON files
        # Try TENDERAI_DIR first, then fallback to app-relative path
        data_intel = Path(os.getenv("TENDERAI_DIR", "./runtime")) / "data_intel"
        if not data_intel.exists():
            data_intel = Path(__file__).resolve().parent.parent.parent / "runtime" / "data_intel"
        if not data_intel.exists():
            results["error"] = "No data_intel directory found"
            return results

        tender_files = sorted(data_intel.glob("bwdb_*.json"))
        if not tender_files:
            tender_files = [data_intel / "bwdb_all_tenders.json"]

        tenders = []
        for tf in tender_files:
            try:
                data = json.loads(tf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Support multiple key names: bwdb_all, bwdb_works, bwdb_tenders
                    items = data.get("bwdb_all") or data.get("bwdb_works") or data.get("bwdb_tenders") or []
                    tenders.extend(items)
                elif isinstance(data, list):
                    tenders.extend(data)
            except Exception:
                continue

        results["total_scanned"] = len(tenders)

        # Apply filters
        keywords = [k.lower() for k in cfg["entity_keywords"]]
        natures = cfg["procurement_natures"]
        min_val = cfg.get("min_value_bdt", 0)
        max_val = cfg.get("max_value_bdt", 0)

        for t in tenders:
            entity = " ".join(
                [
                    str(t.get("procuring_entity", "") or ""),
                    str(_notice(t).get("procuring_entity", "") or ""),
                    str(_notice(t).get("ministry", "") or ""),
                ]
            ).lower()
            title = " ".join(
                [
                    str(t.get("title", "") or ""),
                    str(t.get("work_name", "") or ""),
                    str(t.get("app_work_name", "") or ""),
                    str(t.get("live_work_name", "") or ""),
                    str(_notice(t).get("title", "") or ""),
                    str(_notice(t).get("work_name", "") or ""),
                    str(_notice(t).get("app_work_name", "") or ""),
                    str(_notice(t).get("live_work_name", "") or ""),
                ]
            ).lower()
            nature = t.get("detected_nature", t.get("nature", ""))
            value = _pick(
                t,
                "app_estimated_value_bdt",
                "estimated_value_bdt",
                "live_estimated_value_bdt",
                "estimated_amount_bdt",
                "estimated_cost_bdt",
                "live_value_bdt",
                default=0,
            ) or 0

            # Entity keyword match
            keyword_match = any(kw in entity or kw in title for kw in keywords)

            # Nature filter
            nature_match = not natures or nature in natures

            # Value filter
            value_ok = True
            if min_val > 0 and value < min_val:
                value_ok = False
            if max_val > 0 and value > max_val:
                value_ok = False

            if keyword_match and nature_match and value_ok:
                results["matched_tenders"].append({
                    "tender_id": _pick(t, "app_tender_id", "tender_id", "live_tender_id", "package_no", default=""),
                    "app_tender_id": _pick(t, "app_tender_id", default=""),
                    "live_tender_id": _pick(t, "live_tender_id", default=""),
                    "title": ( _pick(t, "app_work_name", "work_name", "live_work_name", "title", default="") )[:200],
                    "app_work_name": _pick(t, "app_work_name", "work_name", "title", default=""),
                    "live_work_name": _pick(t, "live_work_name", "title", default=""),
                    "procuring_entity": _pick(t, "procuring_entity", default=""),
                    "deadline": _pick(t, "deadline", default=""),
                    "estimated_value_bdt": value,
                    "app_estimated_value_bdt": _pick(t, "app_estimated_value_bdt", "estimated_amount_bdt", "estimated_cost_bdt", default=0),
                    "live_estimated_value_bdt": _pick(t, "live_estimated_value_bdt", "live_value_bdt", default=0),
                    "estimated_value_source": _pick(t, "estimated_value_source", default="LIVE"),
                    "detected_nature": nature,
                    "status": t.get("status", "Live"),
                    "matched_at": datetime.now(timezone.utc).isoformat(),
                })

        results["total_matched"] = len(results["matched_tenders"])
        results["matched_tenders"].sort(key=lambda x: -(x.get("estimated_value_bdt", 0) or 0))

        # Generate alerts
        if results["matched_tenders"]:
            results["alerts_sent"] = self._generate_alerts(results["matched_tenders"])

        return results

    def _generate_alerts(self, matched: List[Dict]) -> List[Dict]:
        """Save alert records for matched tenders."""
        alerts = []
        alerts_dir = Path(self.config_dir) / "alerts"
        alerts_dir.mkdir(parents=True, exist_ok=True)

        for t in matched:
            alert = {
                "tender_id": t["tender_id"],
                "title": t["title"],
                "value": t.get("estimated_value_bdt", 0),
                "entity": t.get("procuring_entity", ""),
                "deadline": t.get("deadline", ""),
                "nature": t.get("detected_nature", ""),
                "alert_type": "high_value" if (t.get("estimated_value_bdt", 0) or 0) >= self._config.get("high_value_threshold_bdt", 0) else "new_tender",
                "channels": self._get_active_channels(),
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "delivered": False,
            }
            fp = alerts_dir / f"{t['tender_id']}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
            fp.write_text(json.dumps(alert, indent=2, ensure_ascii=False), encoding="utf-8")
            alerts.append(alert)

        return alerts

    def _get_active_channels(self) -> List[str]:
        channels = []
        if self._config.get("alert_channels", {}).get("email", {}).get("enabled"):
            channels.append("email")
        if self._config.get("alert_channels", {}).get("whatsapp", {}).get("enabled"):
            channels.append("whatsapp")
        return channels

    def get_alerts(self, limit: int = 50) -> List[Dict]:
        alerts_dir = Path(self.config_dir) / "alerts"
        if not alerts_dir.exists():
            return []
        files = sorted(alerts_dir.glob("*.json"), reverse=True)
        results = []
        for f in files[:limit]:
            try:
                results.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def get_stats(self) -> Dict[str, Any]:
        alerts = self.get_alerts(limit=1000)
        return {
            "enabled": self._config.get("enabled", False),
            "config": self.get_config(),
            "total_alerts": len(alerts),
            "recent_alerts": alerts[:5],
            "active_channels": self._get_active_channels(),
        }


monitor_config_service = MonitorConfigService()
