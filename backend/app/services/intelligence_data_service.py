"""
PostgreSQL-backed intelligence service.

This service is the single source of truth for:
- importing crawled JSON into structured PostgreSQL tables
- matching APP/live tender data with award data by normalized package number
- rebuilding lifecycle, contractor DNA, and aggregate intelligence tables
- serving dashboard and analytics queries without JSON fallbacks
"""
from __future__ import annotations

import json
import logging
import os
import re
from html import unescape
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from sqlalchemy import and_, case, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PACKAGE_PATTERNS = [
    re.compile(r"\bpackage(?:\s+no\.?|\s*[:-])?\s*([a-z0-9][a-z0-9\-_/]+)\b", re.IGNORECASE),
    re.compile(r"\bpkg(?:\s+no\.?|\s*[:-])?\s*([a-z0-9][a-z0-9\-_/]+)\b", re.IGNORECASE),
    re.compile(r"\bwp[-/\s]*([0-9]{1,3}[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\blot(?:\s+no\.?|\s*[:-])?\s*([a-z0-9][a-z0-9\-_/]+)\b", re.IGNORECASE),
    re.compile(r"\b([a-z]{1,8}-\d{1,4}[a-z]?)\b", re.IGNORECASE),
    re.compile(r"\b([a-z]{1,8}/\d{1,4}[a-z]?)\b", re.IGNORECASE),
]

LEADING_REFERENCE_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9./_-]{4,80})\b")
TRAILING_DATETIME_PATTERN = re.compile(
    r"\s+\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$",
    re.IGNORECASE,
)

TITLE_STOPWORDS = {
    "construction", "reconstruction", "repair", "renovation", "improvement", "maintenance", "works", "work",
    "road", "bridge", "culvert", "under", "during", "year", "supply", "installation", "procurement",
    "office", "department", "division", "upazila", "district", "government", "building", "including",
    "necessary", "various", "different", "public", "worksdepartment", "fiscal", "period",
}

CONTRACTOR_EXCLUSION_PATTERNS = [
    re.compile(r"\bjv\b", re.IGNORECASE),
    re.compile(r"\bjoint venture\b", re.IGNORECASE),
    re.compile(r"\bconsortium\b", re.IGNORECASE),
]

MIN_CREDIBLE_NPP = 0.05
MAX_CREDIBLE_NPP = 1.5
MIN_CREDIBLE_ESTIMATE_BDT = 1000.0
MIN_CREDIBLE_AWARD_BDT = 1000.0


@dataclass
class ImportProgress:
    """Mutable progress tracker shared between the service and the status endpoint."""
    state: str = "queued"
    started: bool = False
    current_phase: str = "waiting"
    current_file: str = ""
    files_completed: int = 0
    files_total: int = 0
    current_file_records: int = 0
    current_file_imported: int = 0
    records_committed: int = 0
    records: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    summary: Optional[Dict[str, int]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        pct = (self.files_completed / self.files_total * 100) if self.files_total > 0 else 0
        return {
            "state": self.state,
            "started": self.started,
            "current_phase": self.current_phase,
            "current_file": self.current_file,
            "files_completed": self.files_completed,
            "files_total": self.files_total,
            "progress_pct": round(pct, 1),
            "current_file_records": self.current_file_records,
            "current_file_imported": self.current_file_imported,
            "records_committed": self.records_committed,
            "records": dict(self.records),
            "summary": self.summary,
            "error": self.error,
        }

RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "runtime"
LEGACY_ROOTS = [
    RUNTIME_DIR / "data_intel",
    RUNTIME_DIR / "knowledge",
    Path(__file__).resolve().parent.parent.parent.parent / "data",
]


class IntelligenceDataService:
    _agency_cache: Optional[List[Dict[str, str]]] = None
    _department_tree_cache: Optional[List[Dict[str, Any]]] = None

    def __init__(self, db: AsyncSession):
        self.db = db
        self._batch_size = max(int(os.getenv("INTEL_IMPORT_BATCH_SIZE", "500")), 50)
        self._tender_cache: Optional[Dict[str, Any]] = None
        self._app_record_cache: Optional[Dict[str, Any]] = None
        self._live_tender_cache: Optional[Dict[str, Any]] = None
        self._award_key_cache: Optional[set[tuple[str, str, Optional[str]]]] = None
        self._contractor_cache: Optional[Dict[str, Any]] = None
        self._lifecycle_key_cache: Optional[set[tuple[str, str, Optional[str]]]] = None
        self._eexperience_schema_ready = False

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _uuid() -> str:
        return str(uuid4())

    @staticmethod
    def _to_iso_date(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        raw = str(value).strip()
        if not raw:
            return None
        raw = raw.replace("Z", "+00:00")
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y",
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y %H:%M:%S",
            "%d %b %Y",
        ):
            try:
                return datetime.strptime(raw[:19], fmt).date().isoformat()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(raw).date().isoformat()
        except ValueError:
            return raw[:10]

    @classmethod
    def _is_credible_npp_row(cls, row: Any) -> bool:
        npp = cls._safe_float(getattr(row, "npp_ratio", 0))
        estimate = cls._safe_float(getattr(row, "estimated_cost_bdt", 0))
        award = cls._safe_float(getattr(row, "award_amount_bdt", 0))
        match_type = str(getattr(row, "match_type", "") or "")
        data_source = str(getattr(row, "data_source", "") or "")
        if match_type not in ("package_exact", "title_similarity"):
            return False
        if data_source != "matched":
            return False
        if estimate < MIN_CREDIBLE_ESTIMATE_BDT or award < MIN_CREDIBLE_AWARD_BDT:
            return False
        return MIN_CREDIBLE_NPP <= npp <= MAX_CREDIBLE_NPP

    @staticmethod
    def normalize_package_no(value: Any) -> str:
        if value is None:
            return ""
        raw = str(value).strip().upper()
        if not raw:
            return ""
        raw = raw.replace("\\", "/")
        raw = re.sub(r"\s+", "", raw)
        raw = re.sub(r"[^A-Z0-9/.-]", "", raw)
        return raw

    @staticmethod
    def _normalize_title(value: str) -> str:
        text = unescape(value or "").strip()
        text = TRAILING_DATETIME_PATTERN.sub("", text)
        lead_match = LEADING_REFERENCE_PATTERN.match(text)
        if lead_match:
            lead = lead_match.group(1)
            if any(ch in lead for ch in ("/", "-", "_", ".")) and any(ch.isdigit() for ch in lead):
                text = text[lead_match.end():].strip(" -:;,.")
        text = text.lower()
        text = re.sub(r"[\(\)\[\],.:;'\"]", " ", text)
        text = re.sub(r"&[#A-Z0-9a-z]+;", " ", text)
        text = re.sub(r"[^a-z0-9/\-\s]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        parts = [part for part in text.split() if part not in TITLE_STOPWORDS and len(part) > 2]
        return " ".join(parts)

    @staticmethod
    def _normalize_contractor_name(value: Any) -> str:
        raw = unescape(str(value or "")).strip().upper()
        if not raw:
            return ""
        raw = raw.replace("&AMP;", "&")
        raw = re.sub(r"\s+", " ", raw)
        return raw.strip()

    @staticmethod
    def _normalize_contractor_alias(value: Any) -> str:
        raw = unescape(str(value or "")).strip().upper()
        if not raw:
            return ""
        raw = re.sub(r"\b(M/S|M\.S\.|MESSRS|MS)\b", " ", raw)
        raw = raw.replace("&AMP;", "&")
        raw = re.sub(r"[^A-Z0-9&]+", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw

    @staticmethod
    def _normalize_search_text(value: Any) -> str:
        """Normalize contractor text for fuzzy search and matching."""
        raw = unescape(str(value or "")).strip().upper()
        if not raw:
            return ""
        raw = raw.replace("&AMP;", "&")
        raw = re.sub(r"\b(M/S|M\.S\.|MESSRS|MS)\b", " ", raw)
        raw = re.sub(r"[^A-Z0-9]+", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw

    def _contractor_match_score(self, query_norm: str, candidate_name: Any, contractor_id: Any = None) -> int:
        """Score contractor candidates by exactness, token overlap, and fuzzy similarity."""
        candidate_norm = self._normalize_search_text(candidate_name)
        if not query_norm or not candidate_norm:
            return 0

        if contractor_id and str(contractor_id).strip().upper() == query_norm:
            return 1000
        if candidate_norm == query_norm:
            return 900

        candidate_tokens = set(candidate_norm.split())
        query_tokens = set(query_norm.split())
        overlap = len(candidate_tokens & query_tokens)
        score = overlap * 20

        if query_norm in candidate_norm:
            score += 60
        if candidate_norm in query_norm:
            score += 30

        ratio = SequenceMatcher(None, candidate_norm, query_norm).ratio()
        score += int(ratio * 100)
        return score

    def _resolve_award_reference(self, award: Any) -> str:
        source_tender_id = self.normalize_package_no(getattr(award, "source_tender_id", None) or "")
        if source_tender_id:
            return source_tender_id
        return self.normalize_package_no(getattr(award, "package_no", None) or "")

    def _canonical_award_key(self, award: Any) -> Optional[tuple[str, str, str, str, str]]:
        ref = self._resolve_award_reference(award)
        contractor = self._normalize_contractor_alias(getattr(award, "contractor_name", None))
        award_date = self._to_iso_date(getattr(award, "award_date", None)) or ""
        amount = self._safe_float(getattr(award, "amount_bdt", 0))
        amount_key = f"{round(amount, 2):.2f}" if amount > 0 else ""
        if ref and contractor and (award_date or amount_key):
            return ("award_event", ref, contractor, award_date, amount_key)
        return None

    def _score_award_record(self, award: Any, app_tender_ids: set[str]) -> tuple[int, int, str]:
        score = 0
        linked_tender_id = str(getattr(award, "procurement_tender_id", "") or "")
        if linked_tender_id in app_tender_ids:
            score += 50
        if getattr(award, "source_tender_id", None):
            score += 20
        if getattr(award, "package_no", None):
            score += 10
        if self._to_iso_date(getattr(award, "award_date", None)):
            score += 8
        if self._safe_float(getattr(award, "amount_bdt", 0)) > 0:
            score += 8
        if getattr(award, "agency_code", None):
            score += 4
        if getattr(award, "pe_office", None):
            score += 4
        if getattr(award, "district", None):
            score += 3
        if getattr(award, "procurement_method", None):
            score += 3
        if getattr(award, "detail_url", None):
            score += 2
        title_len = len(str(getattr(award, "title", "") or "").strip())
        score += min(title_len // 40, 4)
        created_at = getattr(award, "created_at", None)
        created_stamp = created_at.isoformat() if created_at else ""
        return (score, title_len, created_stamp)

    def _deduplicate_awards(self, awards: List[Any], app_tender_ids: set[str]) -> tuple[List[Any], Dict[str, int]]:
        canonical: Dict[tuple[str, str, str, str, str], tuple[tuple[int, int, str], Any]] = {}
        passthrough_dedup: Dict[tuple[str, str], tuple[tuple[int, int, str], Any]] = {}
        duplicates_removed = 0

        for award in awards:
            key = self._canonical_award_key(award)
            if key is None:
                # Secondary dedup for passthrough: deduplicate by (tender_id, contractor)
                ref = self._resolve_award_reference(award)
                contractor = self._normalize_contractor_alias(getattr(award, "contractor_name", None))
                alt_key = (ref, contractor) if ref else None
                if alt_key:
                    score = self._score_award_record(award, app_tender_ids)
                    existing = passthrough_dedup.get(alt_key)
                    if existing is None or score > existing[0]:
                        if existing is not None:
                            duplicates_removed += 1
                        passthrough_dedup[alt_key] = (score, award)
                    else:
                        duplicates_removed += 1
                continue
            score = self._score_award_record(award, app_tender_ids)
            existing = canonical.get(key)
            if existing is None or score > existing[0]:
                if existing is not None:
                    duplicates_removed += 1
                canonical[key] = (score, award)
            else:
                duplicates_removed += 1

        canonical_awards = [payload[1] for payload in passthrough_dedup.values()] + [payload[1] for payload in canonical.values()]
        canonical_awards.sort(
            key=lambda award: (
                self._to_iso_date(getattr(award, "award_date", None)) or "",
                self.normalize_package_no(getattr(award, "package_no", None) or ""),
                self._normalize_contractor_name(getattr(award, "contractor_name", None)),
            )
        )
        return canonical_awards, {
            "raw_awards": len(awards),
            "canonical_awards": len(canonical_awards),
            "duplicates_removed": duplicates_removed,
        }

    @classmethod
    def _extract_reference_candidates(cls, *values: Any) -> List[str]:
        refs: List[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            text = unescape(str(value)).strip()
            normalized = cls.normalize_package_no(text)
            if normalized and normalized not in seen:
                refs.append(normalized)
                seen.add(normalized)
            match = LEADING_REFERENCE_PATTERN.match(text)
            if match:
                lead = cls.normalize_package_no(match.group(1))
                if lead and len(lead) >= 5 and any(ch.isdigit() for ch in lead) and lead not in seen:
                    refs.append(lead)
                    seen.add(lead)
            extracted = cls._extract_package_from_title(text)
            if extracted and extracted not in seen:
                refs.append(extracted)
                seen.add(extracted)
        return refs

    @classmethod
    def _extract_package_from_title(cls, title: str) -> Optional[str]:
        for pattern in PACKAGE_PATTERNS:
            match = pattern.search(title or "")
            if match:
                candidate = cls.normalize_package_no(match.group(1))
                if candidate:
                    return candidate
        return None

    @classmethod
    def _extract_package_candidates(cls, *values: Any) -> List[str]:
        candidates: List[str] = []
        for value in values:
            if not value:
                continue
            normalized = cls.normalize_package_no(value)
            if normalized:
                candidates.append(normalized)
            extracted = cls._extract_package_from_title(str(value))
            if extracted:
                candidates.append(extracted)
        deduped: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                deduped.append(candidate)
                seen.add(candidate)
        return deduped

    @staticmethod
    def _safe_float(value: Any) -> float:
        if value in (None, ""):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value).replace(",", "").strip()
        raw = raw.replace("BDT", "").replace("TK", "").strip()
        try:
            return float(raw)
        except ValueError:
            m = re.search(r"-?\d+(?:\.\d+)?", raw)
            return float(m.group(0)) if m else 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        if value in (None, ""):
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(round(value))
        raw = str(value).strip()
        if not raw:
            return 0
        match = re.search(r"-?\d+", raw.replace(",", ""))
        return int(match.group(0)) if match else 0

    @staticmethod
    def _safe_bool(value: Any) -> Optional[bool]:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return value
        raw = str(value).strip().lower()
        if raw in {"true", "yes", "y", "1", "completed on time", "on time"}:
            return True
        if raw in {"false", "no", "n", "0", "delayed", "late"}:
            return False
        return None

    @classmethod
    def _normalize_live_estimate(cls, value: Any) -> float:
        amount = cls._safe_float(value)
        # Many live tender dumps contain ordinal row numbers in this field.
        if amount <= 1000:
            return 0.0
        return amount

    @staticmethod
    def _normalize_spaces(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @classmethod
    def _compact_live_entity(cls, value: Any) -> str:
        parts = [cls._normalize_spaces(part) for part in str(value or "").split(",,")]
        parts = [part for part in parts if part]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return " | ".join(parts)
        return " | ".join([parts[0], parts[-1]])

    @classmethod
    def _infer_ministry_from_entity(cls, value: Any) -> str:
        parts = [cls._normalize_spaces(part) for part in str(value or "").split(",,")]
        parts = [part for part in parts if part]
        if parts:
            return parts[0]
        text = cls._normalize_spaces(value)
        return text or "Unknown Ministry"

    @classmethod
    def _extract_amount_unit_hint(cls, value: Any) -> Optional[str]:
        """Best-effort hint for whether a notice expressed money in Lakh or Crore."""
        if value in (None, "", [], {}):
            return None
        if isinstance(value, dict):
            preferred_keys = (
                "estimated_value", "estimated_amount", "estimated_cost", "amount", "cost",
                "budget", "value", "app_estimate", "estimate",
            )
            for key, item in value.items():
                key_text = str(key).lower()
                hint = cls._extract_amount_unit_hint(item)
                if hint:
                    return hint
                if any(token in key_text for token in preferred_keys):
                    hint = cls._extract_amount_unit_hint(item)
                    if hint:
                        return hint
            return None
        if isinstance(value, list):
            for item in value:
                hint = cls._extract_amount_unit_hint(item)
                if hint:
                    return hint
            return None

        text = cls._normalize_spaces(value)
        if not text:
            return None
        match = re.search(r"(?:tk|bdt|৳)?\s*[\d,]+(?:\.\d+)?\s*(crore|cr|lac|lakh)\b", text, re.IGNORECASE)
        if not match:
            return None
        unit = match.group(1).lower()
        if unit in {"crore", "cr"}:
            return "crore"
        if unit in {"lac", "lakh"}:
            return "lakh"
        return None

    @classmethod
    def _format_money_display(
        cls,
        amount: Any,
        unit_hint: Optional[str] = None,
        source_hint: Optional[str] = None,
    ) -> str:
        value = cls._safe_float(amount)
        if value <= 0:
            return "—"

        hint = (unit_hint or "").strip().lower()
        source = (source_hint or "").strip().upper()
        crore_value = value / 10_000_000
        lakh_value = value / 100_000
        if hint == "crore":
            return f"BDT {crore_value:,.2f} Cr"
        if hint == "lakh":
            return f"BDT {lakh_value:,.0f} Lakh" if abs(lakh_value - round(lakh_value)) < 0.01 else f"BDT {lakh_value:,.2f} Lakh"

        if source == "APP" and value < 100_000:
            return f"BDT {value:,.0f} Lakh" if abs(value - round(value)) < 0.01 else f"BDT {value:,.2f} Lakh"

        if source == "APP" and value < 100_000_000:
            return f"BDT {lakh_value:,.0f} Lakh" if abs(lakh_value - round(lakh_value)) < 0.01 else f"BDT {lakh_value:,.2f} Lakh"

        if value < 100_000:
            return f"BDT {value:,.2f}"

        if value < 10_000_000:
            return f"BDT {lakh_value:,.0f} Lakh" if abs(lakh_value - round(lakh_value)) < 0.01 else f"BDT {lakh_value:,.2f} Lakh"

        if abs(lakh_value - round(lakh_value)) < 0.01 and lakh_value < 100_000:
            return f"BDT {lakh_value:,.0f} Lakh"
        return f"BDT {crore_value:,.2f} Cr"

    @classmethod
    def _should_exclude_contractor_name(cls, value: Any) -> bool:
        name = cls._normalize_spaces(value)
        if not name:
            return True
        upper = name.upper()
        if len(name) < 5:
            return True
        if len(re.sub(r"[^A-Za-z]", "", name)) < 4:
            return True
        if "JV" in re.sub(r"[^A-Z]", "", upper):
            return True
        if any(pattern.search(name) for pattern in CONTRACTOR_EXCLUSION_PATTERNS):
            return True
        noise_markers = ("UNKNOWN", "N/A", "TEST", "DUMMY", "NOT AVAILABLE")
        if any(marker in upper for marker in noise_markers):
            return True
        return False

    @classmethod
    def _is_valid_eexperience_record(cls, item: Dict[str, Any]) -> bool:
        title = cls._normalize_spaces(item.get("title"))
        pe_office = cls._normalize_spaces(item.get("pe_office"))
        contractor = cls._normalize_spaces(item.get("contractor_name") or item.get("winner"))
        status = cls._normalize_spaces(item.get("work_status") or item.get("completion_status") or item.get("status")).lower()
        start_date = cls._to_iso_date(item.get("contract_start_date"))
        end_date = cls._to_iso_date(item.get("contract_end_date") or item.get("planned_completion_date") or item.get("actual_completion_date"))
        amount = cls._safe_float(item.get("contract_value_bdt") or item.get("amount_bdt") or item.get("contract_value"))
        combined = " ".join(v.lower() for v in (title, pe_office, contractor) if v)
        if not title or not pe_office or cls._should_exclude_contractor_name(contractor):
            return False
        if any(marker in combined for marker in ("home page", "forgot password", "user login", "annual procurement plans", "econtracts", "eexperience", "copyright", "view all notifications")):
            return False
        if status not in {"completed", "ongoing"}:
            return False
        if amount <= 0:
            return False
        if not start_date or not end_date:
            return False
        return True

    @staticmethod
    def _coalesce(*values: Any) -> Any:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return None

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        if row is None:
            return {}
        payload: Dict[str, Any] = {}
        for col in row.__table__.columns:
            val = getattr(row, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            payload[col.name] = val
        return payload

    @staticmethod
    def _iter_json_files() -> Iterable[Path]:
        def classify(path: Path) -> Optional[str]:
            lowered = str(path).replace("\\", "/").lower()
            name = path.name.lower()
            if name == "structure.json":
                return "app"
            if name == "contractors.json":
                return "contractor"
            if name == "flat.json" and "/econtracts/" in lowered:
                return "lifecycle"
            if "/awards_batch/" in lowered:
                return "award"
            if name.startswith("awards_") or name.startswith("noa_") or "experience" in name:
                return "award"
            if "/tenders/" in lowered:
                return "tender"
            if name.startswith("tenders_") or name.startswith("bwdb_") or name.startswith("live_"):
                return "tender"
            return None

        priority = {"app": 0, "tender": 1, "award": 2, "contractor": 3, "lifecycle": 4}
        candidates: List[tuple[int, str, Path]] = []
        seen: set[Path] = set()
        for root in LEGACY_ROOTS:
            if not root.exists():
                continue
            for path in root.rglob("*.json"):
                if path in seen:
                    continue
                kind = classify(path)
                if not kind:
                    continue
                seen.add(path)
                candidates.append((priority[kind], str(path).lower(), path))
        for _, _, path in sorted(candidates):
            yield path

    @staticmethod
    def _relative_path(path: Path) -> str:
        for base in (RUNTIME_DIR, *LEGACY_ROOTS):
            try:
                return str(path.relative_to(base)).replace("\\", "/")
            except ValueError:
                continue
        return path.name

    async def _ensure_tender_cache(self) -> Dict[str, Any]:
        from app.models.intelligence import ProcurementTender

        if self._tender_cache is None:
            self._tender_cache = {
                row.package_no: row
                for row in (await self.db.execute(select(ProcurementTender))).scalars().all()
            }
        return self._tender_cache

    async def _ensure_app_record_cache(self) -> Dict[str, Any]:
        from app.models.intelligence import APPRecord

        if self._app_record_cache is None:
            self._app_record_cache = {
                row.procurement_tender_id: row
                for row in (await self.db.execute(select(APPRecord))).scalars().all()
            }
        return self._app_record_cache

    async def _ensure_live_tender_cache(self) -> Dict[str, Any]:
        from app.models.intelligence import LiveTenderSource

        if self._live_tender_cache is None:
            self._live_tender_cache = {
                row.source_tender_id: row
                for row in (await self.db.execute(select(LiveTenderSource))).scalars().all()
            }
        return self._live_tender_cache

    async def _ensure_award_key_cache(self) -> set[tuple[str, str, Optional[str]]]:
        from app.models.intelligence import AwardRecordV2

        if self._award_key_cache is None:
            self._award_key_cache = {
                (row.procurement_tender_id, row.contractor_name or "", row.award_date)
                for row in (await self.db.execute(select(AwardRecordV2))).scalars().all()
            }
        return self._award_key_cache

    async def _ensure_contractor_cache(self) -> Dict[str, Any]:
        from app.models.intelligence import Contractor

        if self._contractor_cache is None:
            self._contractor_cache = {
                row.contractor_name: row
                for row in (await self.db.execute(select(Contractor))).scalars().all()
            }
        return self._contractor_cache

    async def _ensure_lifecycle_key_cache(self) -> set[tuple[str, str, Optional[str]]]:
        from app.models.intelligence import ProcurementLifecycle

        if self._lifecycle_key_cache is None:
            self._lifecycle_key_cache = {
                (row.package_no, row.winner or "", row.award_date)
                for row in (await self.db.execute(select(ProcurementLifecycle))).scalars().all()
            }
        return self._lifecycle_key_cache

    async def _commit_import_batch(
        self,
        progress: Optional[ImportProgress],
        processed_total: int,
        imported_total: int,
        committed_now: int,
    ) -> None:
        await self.db.flush()
        await self.db.commit()
        if progress:
            progress.current_file_records = processed_total
            progress.current_file_imported = imported_total
            progress.records_committed += committed_now

    async def _load_agency_cache(self) -> List[Dict[str, str]]:
        from app.models.intelligence import Agency

        if self.__class__._agency_cache is None:
            result = await self.db.execute(select(Agency))
            self.__class__._agency_cache = [
                {
                    "agency_code": agency.agency_code or "",
                    "agency_name": agency.agency_name or "",
                    "keyword": agency.keyword or "",
                }
                for agency in result.scalars().all()
            ]
        return self.__class__._agency_cache

    async def _ensure_eexperience_schema(self) -> None:
        if self._eexperience_schema_ready:
            return
        ddl = [
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS completed_value_bdt DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS planned_completion_date VARCHAR(20)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS actual_completion_date VARCHAR(20)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS completion_status VARCHAR(50)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS work_status VARCHAR(100)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS progress_pct DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS delay_days INTEGER DEFAULT 0",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS extension_days INTEGER DEFAULT 0",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS completed_on_time BOOLEAN",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS performance_rating VARCHAR(50)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS completion_certificate_no VARCHAR(200)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS bill_no VARCHAR(200)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS fiscal_year VARCHAR(20)",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS remarks TEXT",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS raw_payload JSON",
            "ALTER TABLE econtract_execution ADD COLUMN IF NOT EXISTS data_source VARCHAR(50)",
        ]
        for stmt in ddl:
            await self.db.execute(text(stmt))
        # Backfill data_source from raw_payload for records that have it
        backfill = (
            "UPDATE econtract_execution SET data_source = raw_payload->>'source' "
            "WHERE data_source IS NULL AND raw_payload IS NOT NULL "
            "AND raw_payload->>'source' IS NOT NULL"
        )
        await self.db.execute(text(backfill))
        # Set default for remaining nulls
        await self.db.execute(text(
            "UPDATE econtract_execution SET data_source = 'EEXPERIENCE' WHERE data_source IS NULL OR data_source = ''"
        ))
        await self.db.commit()
        self._eexperience_schema_ready = True

    @staticmethod
    def _guess_agency_code_from_keywords(text_value: str) -> Optional[str]:
        upper = (text_value or "").upper()
        keyword_map = {
            "LGED": ("LGED", "LOCAL GOVERNMENT ENGINEERING"),
            "PWD": ("PWD", "PUBLIC WORKS"),
            "BWDB": ("BWDB", "BANGLADESH WATER DEVELOPMENT"),
            "RHD": ("RHD", "ROADS AND HIGHWAYS"),
            "DPHE": ("DPHE", "PUBLIC HEALTH ENGINEERING"),
            "BREB": ("BREB", "RURAL ELECTRIFICATION"),
            "BADC": ("BADC", "AGRICULTURAL DEVELOPMENT"),
        }
        for agency_code, markers in keyword_map.items():
            if any(marker in upper for marker in markers):
                return agency_code
        return None

    async def _guess_agency_code(self, text_value: str) -> Optional[str]:
        raw = (text_value or "").strip()
        if not raw:
            return None
        upper = raw.upper()
        for agency in await self._load_agency_cache():
            keyword = (agency.get("keyword") or agency.get("agency_code") or "").upper()
            name = (agency.get("agency_name") or "").upper()
            if keyword and keyword in upper:
                return agency.get("agency_code") or None
            if name and name in upper:
                return agency.get("agency_code") or None
            agency_code = (agency.get("agency_code") or "").upper()
            if agency_code and agency_code in upper:
                return agency.get("agency_code") or None
        return self._guess_agency_code_from_keywords(raw)

    async def _get_or_create_tender(
        self,
        package_no: str,
        *,
        title: Optional[str] = None,
        agency_code: Optional[str] = None,
        pe_office: Optional[str] = None,
        procurement_method: Optional[str] = None,
        match_type: str = "unmatched_app",
    ):
        from app.models.intelligence import ProcurementTender

        cache = await self._ensure_tender_cache()
        tender = cache.get(package_no)
        if tender is None:
            tender = ProcurementTender(
                id=self._uuid(),
                package_no=package_no,
                title=title,
                agency_code=agency_code,
                pe_office=pe_office,
                procurement_method=procurement_method,
                match_type=match_type,
            )
            self.db.add(tender)
            await self.db.flush()
            cache[package_no] = tender
            return tender, True

        if title and not tender.title:
            tender.title = title
        if agency_code and not tender.agency_code:
            tender.agency_code = agency_code
        if pe_office and not tender.pe_office:
            tender.pe_office = pe_office
        if procurement_method and not tender.procurement_method:
            tender.procurement_method = procurement_method
        if tender.match_type != "package_exact" and match_type == "package_exact":
            tender.match_type = "package_exact"
        return tender, False

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    async def import_existing_json_data(self, progress: Optional[ImportProgress] = None) -> Dict[str, int]:
        summary = {
            "files_scanned": 0,
            "tenders_imported": 0,
            "awards_imported": 0,
            "awards_relinked": 0,
            "app_packages_imported": 0,
            "contractors_seeded": 0,
            "lifecycle_seeded": 0,
        }
        deferred_lifecycle_paths: List[Path] = []
        all_files = list(self._iter_json_files())

        if progress:
            progress.state = "running"
            progress.started = True
            progress.current_phase = "importing"
            progress.files_total = len(all_files)

        for path in all_files:
            summary["files_scanned"] += 1
            lowered = str(path).lower()

            if progress:
                progress.current_file = self._relative_path(path)
                progress.current_file_records = 0
                progress.current_file_imported = 0

            try:
                if path.name == "structure.json":
                    count = await self.import_app_structure_from_json(path, progress=progress)
                    summary["app_packages_imported"] += count
                    if progress: progress.records["app_packages_imported"] += count
                elif path.name == "contractors.json":
                    count = await self.import_contractors_from_json(path, progress=progress)
                    summary["contractors_seeded"] += count
                    if progress: progress.records["contractors_seeded"] += count
                elif path.name == "flat.json":
                    # flat.json is a derived lifecycle export and gets rebuilt below.
                    # Defer it and use only as a fallback when no award/app sources were imported.
                    deferred_lifecycle_paths.append(path)
                elif "award" in lowered:
                    count = await self.import_awards_from_json(path, progress=progress)
                    summary["awards_imported"] += count
                    if progress: progress.records["awards_imported"] += count
                elif "tender" in lowered or "bwdb" in lowered or "live_" in path.name.lower():
                    count = await self.import_live_tenders_from_json(path, progress=progress)
                    summary["tenders_imported"] += count
                    if progress: progress.records["tenders_imported"] += count
            except Exception as exc:
                logger.warning("Skipping legacy file %s: %s", path, exc)
                await self.db.rollback()

            await self.db.commit()
            if progress:
                progress.files_completed += 1

        if summary["awards_imported"] == 0 and summary["app_packages_imported"] == 0:
            for path in deferred_lifecycle_paths:
                if progress:
                    progress.current_file = self._relative_path(path)
                    progress.current_file_records = 0
                    progress.current_file_imported = 0
                try:
                    count = await self.import_lifecycle_from_json(path, progress=progress)
                    summary["lifecycle_seeded"] += count
                    if progress: progress.records["lifecycle_seeded"] += count
                except Exception as exc:
                    logger.warning("Skipping deferred lifecycle file %s: %s", path, exc)
                    await self.db.rollback()
                await self.db.commit()
                if progress:
                    progress.files_completed += 1
        else:
            for path in deferred_lifecycle_paths:
                if progress:
                    progress.current_phase = "reconciling_award_packages"
                    progress.current_file = self._relative_path(path)
                    progress.current_file_records = 0
                    progress.current_file_imported = 0
                count = await self.reconcile_award_package_mapping_from_json(path, progress=progress)
                summary["awards_relinked"] += count
                if progress:
                    progress.records["awards_relinked"] += count

        if progress:
            progress.current_phase = "matching_awards_to_app"
            progress.current_file = "postgresql/app_award_reconciliation"
            progress.current_file_records = 0
            progress.current_file_imported = 0
        match_summary = await self.reconcile_awards_to_app_records(progress=progress)
        summary.update(match_summary)
        if progress:
            progress.records["matched_by_package"] += match_summary.get("matched_by_package", 0)
            progress.records["matched_by_title"] += match_summary.get("matched_by_title", 0)

        if progress:
            progress.current_phase = "rebuilding_lifecycle"
        await self.rebuild_procurement_lifecycle()
        await self.db.commit()

        if progress:
            progress.current_phase = "rebuilding_contractor_dna"
        await self.rebuild_contractor_intelligence()
        await self.db.commit()

        if progress:
            progress.current_phase = "rebuilding_aggregates"
        await self.rebuild_aggregate_intelligence()
        await self.db.commit()

        if progress:
            progress.state = "completed"
            progress.current_phase = "done"
            progress.summary = summary
        return summary

    async def import_live_tenders_from_json(self, json_path: Path, progress: Optional[ImportProgress] = None) -> int:
        from app.models.intelligence import APPRecord, LiveTenderSource

        if not json_path.exists():
            return 0
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("bwdb_all", payload.get("tenders", []))
        imported = 0
        processed = 0
        ops_since_commit = 0
        app_cache = await self._ensure_app_record_cache()
        live_cache = await self._ensure_live_tender_cache()

        for item in records:
            source_tender_id = str(self._coalesce(item.get("tender_id"), item.get("id"), item.get("package_no"), "")).strip()
            package_no = self.normalize_package_no(
                self._coalesce(item.get("package_no"), source_tender_id)
            )
            if not package_no:
                continue
            procuring_entity = self._coalesce(item.get("procuring_entity"), item.get("pe_office"))
            agency_code = await self._guess_agency_code(str(procuring_entity or ""))
            tender, _ = await self._get_or_create_tender(
                package_no,
                title=item.get("title"),
                agency_code=agency_code,
                pe_office=procuring_entity,
                procurement_method=item.get("procurement_method"),
                match_type="unmatched_app",
            )
            estimate_value = self._normalize_live_estimate(
                self._coalesce(item.get("estimated_value_bdt"), item.get("estimated_cost_bdt"))
            )
            live_record = live_cache.get(source_tender_id)
            if live_record is None and source_tender_id:
                live_record = LiveTenderSource(
                    id=self._uuid(),
                    procurement_tender_id=tender.id,
                    source_tender_id=source_tender_id,
                    title=item.get("title"),
                    procuring_entity=procuring_entity,
                    published_date=self._to_iso_date(item.get("published_date")),
                    deadline=self._to_iso_date(item.get("deadline")),
                    status=item.get("status"),
                    financial_year=item.get("financial_year"),
                    category=item.get("category"),
                    estimated_value_bdt=estimate_value,
                    source_file=self._relative_path(json_path),
                    source_type="live_tender_json",
                    raw_payload=item,
                )
                self.db.add(live_record)
                live_cache[source_tender_id] = live_record
            elif live_record is not None:
                live_record.procurement_tender_id = live_record.procurement_tender_id or tender.id
                live_record.title = self._coalesce(live_record.title, item.get("title"))
                live_record.procuring_entity = self._coalesce(live_record.procuring_entity, procuring_entity)
                live_record.published_date = self._coalesce(live_record.published_date, self._to_iso_date(item.get("published_date")))
                live_record.deadline = self._coalesce(live_record.deadline, self._to_iso_date(item.get("deadline")))
                live_record.status = self._coalesce(live_record.status, item.get("status"))
                live_record.financial_year = self._coalesce(live_record.financial_year, item.get("financial_year"))
                live_record.category = self._coalesce(live_record.category, item.get("category"))
                live_record.source_file = self._coalesce(live_record.source_file, self._relative_path(json_path))
                live_record.estimated_value_bdt = live_record.estimated_value_bdt or estimate_value
                live_record.raw_payload = live_record.raw_payload or item

            app_record = app_cache.get(tender.id)
            if app_record is None and estimate_value > 0:
                app_record = APPRecord(
                    id=self._uuid(),
                    procurement_tender_id=tender.id,
                    source_tender_id=source_tender_id or package_no,
                    title=item.get("title"),
                    estimated_cost_bdt=estimate_value,
                    status=item.get("status"),
                    published_date=self._to_iso_date(item.get("published_date")),
                    deadline=self._to_iso_date(item.get("deadline")),
                    financial_year=item.get("financial_year"),
                    app_code=item.get("app_code") or "LIVE_TENDER",
                    category=item.get("category"),
                )
                self.db.add(app_record)
                app_cache[tender.id] = app_record
                imported += 1
            else:
                if app_record is not None:
                    app_record.title = self._coalesce(app_record.title, item.get("title"))
                    app_record.estimated_cost_bdt = app_record.estimated_cost_bdt or estimate_value
                    app_record.status = self._coalesce(app_record.status, item.get("status"))
                    app_record.published_date = self._coalesce(app_record.published_date, self._to_iso_date(item.get("published_date")))
                    app_record.deadline = self._coalesce(app_record.deadline, self._to_iso_date(item.get("deadline")))
                    app_record.category = self._coalesce(app_record.category, item.get("category"))

            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = imported
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, imported, ops_since_commit)
                ops_since_commit = 0

        if ops_since_commit:
            await self._commit_import_batch(progress, processed, imported, ops_since_commit)
        else:
            await self.db.flush()
        return imported

    async def import_awards_from_json(self, json_path: Path, progress: Optional[ImportProgress] = None) -> int:
        from app.models.intelligence import AwardRecordV2

        if not json_path.exists():
            return 0
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("awards", [payload] if isinstance(payload, dict) else [])
        imported = 0
        processed = 0
        ops_since_commit = 0
        award_key_cache = await self._ensure_award_key_cache()

        for item in records:
            package_no = self.normalize_package_no(
                self._coalesce(item.get("package_no"), item.get("tender_id"), item.get("ref_no"), item.get("id"))
            )
            if not package_no:
                continue
            pe_office = self._coalesce(item.get("pe_office"), item.get("procuring_entity"), item.get("agency"))
            agency_code = self._coalesce(item.get("agency_code"), await self._guess_agency_code(str(pe_office or "")))
            tender, _ = await self._get_or_create_tender(
                package_no,
                title=self._coalesce(item.get("title"), item.get("work_name")),
                agency_code=agency_code,
                pe_office=pe_office,
                procurement_method=item.get("procurement_method"),
                match_type="unmatched_ec",
            )

            contractor_name = self._coalesce(item.get("winner"), item.get("contractor_name"), item.get("contractor"), "Unknown")
            award_date = self._to_iso_date(self._coalesce(item.get("award_date"), item.get("contract_date")))
            award_key = (tender.id, contractor_name, award_date)
            if award_key in award_key_cache:
                continue

            self.db.add(
                AwardRecordV2(
                    id=self._uuid(),
                    procurement_tender_id=tender.id,
                    source_tender_id=str(self._coalesce(item.get("tender_id"), item.get("ref_no"), package_no)),
                    package_no=package_no,
                    title=self._coalesce(item.get("title"), item.get("work_name")),
                    contractor_name=contractor_name,
                    amount_bdt=self._safe_float(self._coalesce(item.get("award_amount"), item.get("amount_bdt"), item.get("awarded_amount"))),
                    procurement_method=item.get("procurement_method"),
                    award_date=award_date,
                    detail_url=item.get("detail_url"),
                    agency_code=agency_code,
                    district=self._coalesce(item.get("district"), item.get("location")),
                    pe_office=pe_office,
                )
            )
            award_key_cache.add(award_key)
            imported += 1
            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = imported
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, imported, ops_since_commit)
                ops_since_commit = 0

        if ops_since_commit:
            await self._commit_import_batch(progress, processed, imported, ops_since_commit)
        else:
            await self.db.flush()
        return imported

    async def import_app_structure_from_json(self, json_path: Optional[Path] = None, progress: Optional[ImportProgress] = None) -> int:
        from app.models.intelligence import APPRecord

        fp = json_path or (RUNTIME_DIR / "knowledge" / "app" / "structure.json")
        if not fp.exists():
            return 0
        payload = json.loads(fp.read_text(encoding="utf-8"))
        ministries = payload.get("ministries", [])
        imported = 0
        processed = 0
        ops_since_commit = 0
        app_cache = await self._ensure_app_record_cache()

        for ministry in ministries:
            for pe in ministry.get("pe_offices", []):
                pe_office = pe.get("pe_office", "")
                agency_code = await self._guess_agency_code(pe_office)
                for pkg in pe.get("packages", []):
                    package_no = self.normalize_package_no(pkg.get("package_no"))
                    if not package_no:
                        continue
                    tender, _ = await self._get_or_create_tender(
                        package_no,
                        title=pkg.get("contract_package_title"),
                        agency_code=agency_code,
                        pe_office=pe_office,
                        procurement_method=pkg.get("procurement_method"),
                        match_type="unmatched_app",
                    )
                    app_record = app_cache.get(tender.id)
                    if app_record is None:
                        app_record = APPRecord(
                            id=self._uuid(),
                            procurement_tender_id=tender.id,
                            source_tender_id=package_no,
                            title=pkg.get("contract_package_title"),
                            estimated_cost_bdt=self._safe_float(pkg.get("estimated_cost_bdt")),
                            status=pkg.get("status") or "APP",
                            published_date=self._to_iso_date(pkg.get("published_date")),
                            deadline=self._to_iso_date(pkg.get("deadline")),
                            financial_year=pkg.get("financial_year"),
                            app_code=pkg.get("app_code"),
                            category=pkg.get("category"),
                        )
                        self.db.add(app_record)
                        app_cache[tender.id] = app_record
                        imported += 1
                    else:
                        app_record.title = self._coalesce(app_record.title, pkg.get("contract_package_title"))
                        app_record.estimated_cost_bdt = app_record.estimated_cost_bdt or self._safe_float(pkg.get("estimated_cost_bdt"))
                        app_record.status = self._coalesce(app_record.status, pkg.get("status"), "APP")
                        app_record.deadline = self._coalesce(app_record.deadline, self._to_iso_date(pkg.get("deadline")))
                        app_record.category = self._coalesce(app_record.category, pkg.get("category"))

                    processed += 1
                    ops_since_commit += 1
                    if progress:
                        progress.current_file_records = processed
                        progress.current_file_imported = imported
                    if ops_since_commit >= self._batch_size:
                        await self._commit_import_batch(progress, processed, imported, ops_since_commit)
                        ops_since_commit = 0

        if ops_since_commit:
            await self._commit_import_batch(progress, processed, imported, ops_since_commit)
        else:
            await self.db.flush()
        return imported

    async def import_contractors_from_json(self, json_path: Optional[Path] = None, progress: Optional[ImportProgress] = None) -> int:
        from app.models.intelligence import Contractor

        fp = json_path or (RUNTIME_DIR / "knowledge" / "contractordna" / "contractors.json")
        if not fp.exists():
            return 0
        records = json.loads(fp.read_text(encoding="utf-8"))
        imported = 0
        processed = 0
        ops_since_commit = 0
        contractor_cache = await self._ensure_contractor_cache()
        for item in records:
            name = (item.get("contractor_name") or "").strip()
            if not name:
                continue
            existing = contractor_cache.get(name)
            if existing:
                continue
            contractor = Contractor(
                id=self._uuid(),
                contractor_name=name,
                total_contracts=int(item.get("total_contracts", 0) or 0),
                total_amount_bdt=self._safe_float(item.get("total_amount_bdt")),
                agencies_worked=item.get("agencies", []),
                districts_worked=item.get("districts", []),
                avg_npp=self._safe_float(item.get("avg_npp")),
                first_award_date=self._to_iso_date(item.get("earliest_contract_date")),
                last_award_date=self._to_iso_date(item.get("latest_contract_date")),
            )
            self.db.add(contractor)
            contractor_cache[name] = contractor
            imported += 1
            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = imported
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, imported, ops_since_commit)
                ops_since_commit = 0
        if ops_since_commit:
            await self._commit_import_batch(progress, processed, imported, ops_since_commit)
        else:
            await self.db.flush()
        return imported

    async def import_lifecycle_from_json(self, flat_path: Optional[Path] = None, progress: Optional[ImportProgress] = None) -> int:
        from app.models.intelligence import ProcurementLifecycle
        from sqlalchemy.exc import IntegrityError

        fp = flat_path or (RUNTIME_DIR / "knowledge" / "econtracts" / "flat.json")
        if not fp.exists():
            return 0
        records = json.loads(fp.read_text(encoding="utf-8"))
        imported = 0
        processed = 0
        ops_since_commit = 0
        lifecycle_key_cache = await self._ensure_lifecycle_key_cache()
        for item in records:
            package_no = self.normalize_package_no(item.get("package_no"))
            if not package_no:
                continue
            winner = item.get("winner", "") or ""
            award_date = self._to_iso_date(item.get("award_date"))
            lifecycle_key = (package_no, winner, award_date)
            if lifecycle_key in lifecycle_key_cache:
                continue
            try:
                self.db.add(
                    ProcurementLifecycle(
                        id=self._uuid(),
                        package_no=package_no,
                        agency_code=item.get("agency_code"),
                        zone_name=item.get("district"),
                        title=(item.get("title") or "")[:500],
                        estimated_cost_bdt=self._safe_float(item.get("estimated_cost_bdt")),
                        award_amount_bdt=self._safe_float(self._coalesce(item.get("amount_bdt"), item.get("award_amount"))),
                        npp_ratio=self._safe_float(item.get("npp_ratio")),
                        winner=winner,
                        award_date=award_date,
                        procurement_method=item.get("procurement_method"),
                        pe_office=item.get("pe_office"),
                        match_type=item.get("match_type", "unmatched_ec"),
                        data_source=item.get("data_source", "ec_only"),
                        tender_id=str(item.get("tender_id")) if item.get("tender_id") else None,
                    )
                )
                lifecycle_key_cache.add(lifecycle_key)
                imported += 1
            except IntegrityError:
                await self.db.rollback()
                lifecycle_key_cache.add(lifecycle_key)
            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = imported
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, imported, ops_since_commit)
                ops_since_commit = 0
        if ops_since_commit:
            await self._commit_import_batch(progress, processed, imported, ops_since_commit)
        else:
            await self.db.flush()
        return imported

    async def import_eexperience_from_json(self, json_path: Path, progress: Optional[ImportProgress] = None) -> int:
        from app.models.intelligence import EContractExecution

        if not json_path.exists():
            return 0
        await self._ensure_eexperience_schema()
        records = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(records, dict):
            records = records.get("records", records.get("experience", [records]))
        imported = 0
        processed = 0
        ops_since_commit = 0
        existing = {
            (r.tender_id, r.contractor_name or "", r.contract_start_date or "")
            for r in (await self.db.execute(select(EContractExecution))).scalars().all()
        }
        for item in records:
            if not self._is_valid_eexperience_record(item):
                continue
            tender_id = str(item.get("tender_id", item.get("id", ""))).strip()
            contractor = (item.get("contractor_name") or item.get("winner") or "").strip()
            start_date = self._to_iso_date(item.get("contract_start_date"))
            dedup_key = (tender_id, contractor, start_date or "")
            if dedup_key in existing:
                continue
            package_no = self.normalize_package_no(
                self._coalesce(item.get("package_no"), item.get("ref_no"), str(tender_id))
            )
            agency_code = item.get("agency_code") or await self._guess_agency_code(
                str(item.get("agency_name") or item.get("pe_office") or "")
            )
            planned_completion_date = self._to_iso_date(
                self._coalesce(item.get("planned_completion_date"), item.get("scheduled_completion_date"), item.get("completion_due_date"))
            )
            actual_completion_date = self._to_iso_date(
                self._coalesce(item.get("actual_completion_date"), item.get("completed_date"), item.get("completion_date"), item.get("work_completion_date"))
            )
            completion_status = self._coalesce(
                item.get("completion_status"),
                item.get("completion_state"),
                item.get("completed_works_status"),
                item.get("status"),
            )
            progress_pct = self._safe_float(
                self._coalesce(item.get("progress_pct"), item.get("completion_pct"), item.get("completion_progress"), item.get("work_progress"))
            )
            delay_days = self._safe_int(
                self._coalesce(item.get("delay_days"), item.get("completion_delay_days"), item.get("delayed_days"))
            )
            extension_days = self._safe_int(
                self._coalesce(item.get("extension_days"), item.get("time_extension_days"), item.get("extended_days"))
            )
            completed_on_time = self._safe_bool(
                self._coalesce(item.get("completed_on_time"), item.get("on_time_completion"))
            )
            self.db.add(
                EContractExecution(
                    id=self._uuid(),
                    package_no=package_no or f"EEXP-{tender_id}",
                    title=item.get("title", ""),
                    agency_code=agency_code,
                    agency_name=item.get("agency_name", ""),
                    pe_office=item.get("pe_office", ""),
                    contractor_name=contractor or None,
                    contract_value_bdt=self._safe_float(
                        self._coalesce(item.get("contract_value_bdt"), item.get("amount_bdt"), item.get("contract_value"))
                    ),
                    completed_value_bdt=self._safe_float(
                        self._coalesce(item.get("completed_value_bdt"), item.get("executed_value_bdt"), item.get("final_bill_value_bdt"), item.get("completed_value"))
                    ),
                    contract_start_date=start_date,
                    contract_end_date=self._to_iso_date(item.get("contract_end_date")),
                    planned_completion_date=planned_completion_date,
                    actual_completion_date=actual_completion_date,
                    award_date=self._to_iso_date(item.get("award_date")),
                    status=item.get("status", "completed"),
                    completion_status=completion_status,
                    work_status=self._coalesce(item.get("work_status"), item.get("execution_status"), item.get("current_status")),
                    progress_pct=progress_pct,
                    delay_days=delay_days,
                    extension_days=extension_days,
                    completed_on_time=completed_on_time,
                    performance_rating=self._coalesce(item.get("performance_rating"), item.get("rating"), item.get("grade")),
                    completion_certificate_no=self._coalesce(item.get("completion_certificate_no"), item.get("completion_cert_no"), item.get("certificate_no")),
                    bill_no=self._coalesce(item.get("bill_no"), item.get("running_bill_no"), item.get("final_bill_no")),
                    fiscal_year=self._coalesce(item.get("fiscal_year"), item.get("financial_year")),
                    tender_id=tender_id or None,
                    district=item.get("district", ""),
                    source_url=item.get("source_url", ""),
                    data_source=item.get("source") or item.get("data_source") or "EEXPERIENCE",
                    remarks=self._coalesce(item.get("remarks"), item.get("notes"), item.get("comment")),
                    raw_payload=item,
                )
            )
            existing.add(dedup_key)
            imported += 1
            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = imported
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, imported, ops_since_commit)
                ops_since_commit = 0
        if ops_since_commit:
            await self._commit_import_batch(progress, processed, imported, ops_since_commit)
        else:
            await self.db.flush()
        return imported

    async def reconcile_award_package_mapping_from_json(
        self,
        flat_path: Path,
        progress: Optional[ImportProgress] = None,
    ) -> int:
        from app.models.intelligence import AwardRecordV2

        if not flat_path.exists():
            return 0

        payload = json.loads(flat_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return 0

        awards = (await self.db.execute(select(AwardRecordV2))).scalars().all()
        awards_by_source: Dict[str, List[AwardRecordV2]] = defaultdict(list)
        for award in awards:
            source_id = (award.source_tender_id or "").strip()
            if source_id:
                awards_by_source[source_id].append(award)

        relinked = 0
        processed = 0
        ops_since_commit = 0
        seen_awards: set[str] = set()

        for item in payload:
            source_tender_id = str(self._coalesce(item.get("tender_id"), item.get("id"), "")).strip()
            package_no = self.normalize_package_no(item.get("package_no"))
            if not source_tender_id or not package_no:
                continue

            candidates = awards_by_source.get(source_tender_id, [])
            if not candidates:
                continue

            tender, _ = await self._get_or_create_tender(
                package_no,
                title=item.get("title"),
                agency_code=item.get("agency_code"),
                pe_office=item.get("pe_office"),
                procurement_method=item.get("procurement_method"),
                match_type="package_exact",
            )

            winner = (item.get("winner") or "").strip().upper()
            award_date = self._to_iso_date(item.get("award_date"))
            matched_award: Optional[AwardRecordV2] = None

            for award in candidates:
                if award.id in seen_awards:
                    continue
                if winner and (award.contractor_name or "").strip().upper() != winner:
                    continue
                if award_date and self._to_iso_date(award.award_date) not in (None, award_date):
                    continue
                matched_award = award
                break

            if matched_award is None:
                for award in candidates:
                    if award.id in seen_awards:
                        continue
                    matched_award = award
                    break

            if matched_award is None:
                continue

            seen_awards.add(matched_award.id)
            matched_award.procurement_tender_id = tender.id
            matched_award.package_no = package_no
            matched_award.title = self._coalesce(matched_award.title, item.get("title"))
            matched_award.agency_code = self._coalesce(matched_award.agency_code, item.get("agency_code"))
            matched_award.district = self._coalesce(matched_award.district, item.get("district"))
            matched_award.pe_office = self._coalesce(matched_award.pe_office, item.get("pe_office"))
            matched_award.procurement_method = self._coalesce(
                matched_award.procurement_method,
                item.get("procurement_method"),
            )
            relinked += 1
            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = relinked
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, relinked, ops_since_commit)
                ops_since_commit = 0

        if ops_since_commit:
            await self._commit_import_batch(progress, processed, relinked, ops_since_commit)
        else:
            await self.db.flush()
        return relinked

    async def reconcile_awards_to_app_records(self, progress: Optional[ImportProgress] = None) -> Dict[str, int]:
        from app.models.intelligence import APPRecord, AwardRecordV2, ProcurementTender

        app_rows = (
            await self.db.execute(
                select(ProcurementTender, APPRecord).join(APPRecord, APPRecord.procurement_tender_id == ProcurementTender.id)
            )
        ).all()
        app_by_tender_id: Dict[str, APPRecord] = {}
        tender_by_id: Dict[str, ProcurementTender] = {}
        package_index: Dict[str, List[ProcurementTender]] = defaultdict(list)
        reference_index: Dict[str, List[ProcurementTender]] = defaultdict(list)
        app_title_index: Dict[str, Dict[str, Any]] = {}
        token_index: Dict[str, set[str]] = defaultdict(set)
        agency_index: Dict[str, set[str]] = defaultdict(set)
        token_frequency: Dict[str, int] = defaultdict(int)

        for tender, app_record in app_rows:
            tender_by_id[tender.id] = tender
            app_by_tender_id[tender.id] = app_record
            title_source = str(app_record.title or tender.title or "")
            title_norm = self._normalize_title(title_source)
            package_candidates = self._extract_package_candidates(tender.package_no, title_source)
            for candidate in package_candidates:
                package_index[candidate].append(tender)
            for candidate in self._extract_reference_candidates(
                tender.package_no,
                app_record.source_tender_id,
                app_record.app_code,
                title_source,
            ):
                reference_index[candidate].append(tender)
            app_title_index[tender.id] = {
                "tender": tender,
                "app": app_record,
                "title_norm": title_norm,
                "title_tokens": set(title_norm.split()),
            }
            for token in list(app_title_index[tender.id]["title_tokens"])[:30]:
                token_index[token].add(tender.id)
                token_frequency[token] += 1
            agency_code = (tender.agency_code or "").upper()
            if agency_code:
                agency_index[agency_code].add(tender.id)

        awards = (await self.db.execute(select(AwardRecordV2))).scalars().all()
        matched_by_package = 0
        matched_by_title = 0
        processed = 0
        ops_since_commit = 0

        def pick_best_package_match(candidates: List[ProcurementTender], award: AwardRecordV2) -> Optional[ProcurementTender]:
            if not candidates:
                return None
            if len(candidates) == 1:
                return candidates[0]
            award_agency = (award.agency_code or "").upper()
            award_pe = (award.pe_office or "").upper()
            scored: List[tuple[int, ProcurementTender]] = []
            for tender in candidates:
                score = 0
                if award_agency and (tender.agency_code or "").upper() == award_agency:
                    score += 4
                if award_pe and tender.pe_office and tender.pe_office.upper() in award_pe:
                    score += 2
                if tender.title:
                    score += 1
                scored.append((score, tender))
            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[0][1]

        def pick_best_title_match(award: AwardRecordV2) -> Optional[ProcurementTender]:
            award_title = self._normalize_title(str(award.title or ""))
            award_tokens = set(award_title.split())
            if len(award_tokens) < 4:
                return None

            candidate_ids: set[str] = set()
            for token in list(award_tokens)[:12]:
                candidate_ids.update(token_index.get(token, set()))
            if not candidate_ids:
                return None

            best: Optional[ProcurementTender] = None
            best_score = 0.0
            award_agency = (award.agency_code or "").upper()
            award_pe = (award.pe_office or "").upper()
            if award_agency and agency_index.get(award_agency):
                candidate_ids &= agency_index[award_agency]
            if not candidate_ids:
                return None

            for tender_id in list(candidate_ids)[:500]:
                payload = app_title_index.get(tender_id)
                if not payload:
                    continue
                app_tokens = payload["title_tokens"]
                if len(app_tokens) < 4:
                    continue
                common = award_tokens & app_tokens
                common_count = len(common)
                if common_count < 3:
                    continue
                precision = common_count / max(len(award_tokens), 1)
                recall = common_count / max(len(app_tokens), 1)
                overlap = (2 * precision * recall) / max(precision + recall, 1e-9)
                if overlap < 0.28:
                    continue
                weighted_common = sum(1 / max(token_frequency.get(token, 1), 1) for token in common)
                weighted_award = sum(1 / max(token_frequency.get(token, 1), 1) for token in award_tokens)
                weighted_app = sum(1 / max(token_frequency.get(token, 1), 1) for token in app_tokens)
                weighted_overlap = 0.0
                if weighted_award > 0 and weighted_app > 0:
                    weighted_precision = weighted_common / weighted_award
                    weighted_recall = weighted_common / weighted_app
                    weighted_overlap = (2 * weighted_precision * weighted_recall) / max(weighted_precision + weighted_recall, 1e-9)
                rare_common = sum(1 for token in common if token_frequency.get(token, 0) <= 25 and len(token) >= 5)
                if weighted_overlap < 0.18 and rare_common < 2:
                    continue
                seq = SequenceMatcher(None, award_title, payload["title_norm"]).ratio()
                contains_bonus = 0.0
                if award_title and payload["title_norm"]:
                    if award_title in payload["title_norm"] or payload["title_norm"] in award_title:
                        contains_bonus = 0.08
                score = overlap * 0.35 + weighted_overlap * 0.30 + seq * 0.27 + contains_bonus
                tender = payload["tender"]
                if award_agency and (tender.agency_code or "").upper() == award_agency:
                    score += 0.08
                if award_pe and tender.pe_office and tender.pe_office.upper() in award_pe:
                    score += 0.05
                if score > best_score and (
                    score >= 0.60
                    or (common_count >= 5 and weighted_overlap >= 0.28 and seq >= 0.66)
                    or seq >= 0.84
                ):
                    best_score = score
                    best = tender
            return best

        for award in awards:
            current_tender = tender_by_id.get(award.procurement_tender_id)
            if current_tender and app_by_tender_id.get(current_tender.id):
                processed += 1
                continue

            matched_tender: Optional[ProcurementTender] = None
            ref_candidates = self._extract_reference_candidates(
                award.package_no,
                award.source_tender_id,
                award.title,
            )
            for candidate in ref_candidates:
                possible = reference_index.get(candidate, [])
                matched_tender = pick_best_package_match(possible, award)
                if matched_tender:
                    matched_by_package += 1
                    matched_tender.match_type = "package_exact"
                    break

            candidates = self._extract_package_candidates(
                award.package_no,
                award.title,
                award.source_tender_id,
            )
            if matched_tender is None:
                for candidate in candidates:
                    possible = package_index.get(candidate, [])
                    matched_tender = pick_best_package_match(possible, award)
                    if matched_tender:
                        matched_by_package += 1
                        matched_tender.match_type = "package_exact"
                        break

            if matched_tender is None:
                matched_tender = pick_best_title_match(award)
                if matched_tender:
                    matched_by_title += 1
                    if matched_tender.match_type != "package_exact":
                        matched_tender.match_type = "title_similarity"

            if matched_tender is not None:
                award.procurement_tender_id = matched_tender.id
                award.package_no = matched_tender.package_no
                award.agency_code = self._coalesce(award.agency_code, matched_tender.agency_code)
                award.pe_office = self._coalesce(award.pe_office, matched_tender.pe_office)

            processed += 1
            ops_since_commit += 1
            if progress:
                progress.current_file_records = processed
                progress.current_file_imported = matched_by_package + matched_by_title
            if ops_since_commit >= self._batch_size:
                await self._commit_import_batch(progress, processed, matched_by_package + matched_by_title, ops_since_commit)
                ops_since_commit = 0

        if ops_since_commit:
            await self._commit_import_batch(progress, processed, matched_by_package + matched_by_title, ops_since_commit)
        else:
            await self.db.flush()
        return {
            "matched_by_package": matched_by_package,
            "matched_by_title": matched_by_title,
            "matched_total": matched_by_package + matched_by_title,
        }

    async def rebuild_procurement_lifecycle(self) -> Dict[str, int]:
        from app.models.intelligence import APPRecord, AwardRecordV2, ProcurementLifecycle, ProcurementTender

        await self.db.execute(delete(ProcurementLifecycle))
        tenders = (
            await self.db.execute(select(ProcurementTender).order_by(ProcurementTender.package_no))
        ).scalars().all()
        app_records = {
            row.procurement_tender_id: row
            for row in (await self.db.execute(select(APPRecord))).scalars().all()
        }
        app_tender_ids = set(app_records.keys())
        awards_by_tender: Dict[str, list] = defaultdict(list)
        raw_awards = (await self.db.execute(select(AwardRecordV2))).scalars().all()
        canonical_awards, dedup_stats = self._deduplicate_awards(raw_awards, app_tender_ids)
        for award in canonical_awards:
            awards_by_tender[award.procurement_tender_id].append(award)

        rows_inserted = 0
        matched = 0
        matched_tenders = 0
        ec_only = 0
        app_only = 0
        for tender in tenders:
            app_record = app_records.get(tender.id)
            awards = awards_by_tender.get(tender.id, [])
            if awards:
                if app_record:
                    matched_tenders += len(awards)
                else:
                    ec_only += len(awards)
                for award in awards:
                    estimate = self._safe_float(app_record.estimated_cost_bdt if app_record else 0)
                    award_amount = self._safe_float(award.amount_bdt)
                    npp_ratio = round(award_amount / estimate, 6) if estimate > 0 else 0.0
                    match_type = tender.match_type if app_record and tender.match_type in ("package_exact", "title_similarity") else ("package_exact" if app_record else "unmatched_ec")
                    if app_record:
                        matched += 1
                    self.db.add(
                        ProcurementLifecycle(
                            id=self._uuid(),
                            package_no=tender.package_no,
                            agency_code=self._coalesce(award.agency_code, tender.agency_code),
                            zone_name=award.district,
                            title=self._coalesce(award.title, tender.title, app_record.title if app_record else None),
                            estimated_cost_bdt=estimate,
                            award_amount_bdt=award_amount,
                            npp_ratio=npp_ratio,
                            winner=award.contractor_name,
                            award_date=award.award_date,
                            procurement_method=self._coalesce(award.procurement_method, tender.procurement_method),
                            pe_office=self._coalesce(award.pe_office, tender.pe_office),
                            match_type=match_type,
                            data_source="matched" if app_record else "ec_only",
                            tender_id=tender.id,
                        )
                    )
                    rows_inserted += 1
                if app_record and tender.match_type not in ("package_exact", "title_similarity"):
                    tender.match_type = "package_exact"
                elif not app_record:
                    tender.match_type = "unmatched_ec"
                continue

            if app_record:
                app_only += 1
                self.db.add(
                    ProcurementLifecycle(
                        id=self._uuid(),
                        package_no=tender.package_no,
                        agency_code=tender.agency_code,
                        zone_name=None,
                        title=self._coalesce(app_record.title, tender.title),
                        estimated_cost_bdt=self._safe_float(app_record.estimated_cost_bdt),
                        award_amount_bdt=0.0,
                        npp_ratio=0.0,
                        winner=None,
                        award_date=None,
                        procurement_method=tender.procurement_method,
                        pe_office=tender.pe_office,
                        match_type="unmatched_app",
                        tender_id=tender.id,
                        data_source="app_only",
                    )
                )
                tender.match_type = "unmatched_app"
                rows_inserted += 1

        await self.db.flush()
        return {
            "rows_inserted": rows_inserted,
            "matched_packages": matched,
            "matched": matched_tenders,
            "app_only": app_only,
            "ec_only": ec_only,
            **dedup_stats,
        }

    async def backfill_live_tender_shell_records(self) -> Dict[str, int]:
        from app.models.intelligence import APPRecord, AwardRecordV2, ProcurementTender

        app_cache = await self._ensure_app_record_cache()
        tenders = (
            await self.db.execute(
                select(ProcurementTender, AwardRecordV2)
                .join(AwardRecordV2, AwardRecordV2.procurement_tender_id == ProcurementTender.id)
                .where(ProcurementTender.agency_code.in_(("PWD", "RHD")))
                .order_by(AwardRecordV2.award_date.desc().nullslast())
            )
        ).all()

        created = 0
        seen_tenders: set[str] = set()
        for tender, award in tenders:
            if tender.id in seen_tenders:
                continue
            seen_tenders.add(tender.id)
            if tender.id in app_cache:
                continue

            title = str(tender.title or "")
            award_date = self._to_iso_date(award.award_date) or ""
            looks_current = (
                "2025-2026" in title
                or "25-26" in title
                or award_date >= "2025-01-01"
            )
            if not title or not looks_current:
                continue

            app_record = APPRecord(
                id=self._uuid(),
                procurement_tender_id=tender.id,
                source_tender_id=tender.package_no,
                title=tender.title,
                estimated_cost_bdt=0.0,
                status="LIVE_TENDER_SHELL",
                published_date=None,
                deadline=None,
                financial_year="2025-2026" if ("2025-2026" in title or "25-26" in title) else None,
                app_code="LIVE_TENDER_SHELL",
                category=tender.procurement_method or "live_tender_shell",
            )
            self.db.add(app_record)
            app_cache[tender.id] = app_record
            created += 1

        await self.db.flush()
        return {"created": created}

    async def rebuild_contractor_intelligence(self) -> Dict[str, int]:
        from app.models.intelligence import Contractor, ContractorDNA, EContractExecution, ProcurementLifecycle

        await self.db.execute(text("TRUNCATE TABLE contractor_dna"))
        await self.db.flush()
        awards = (
            await self.db.execute(
                select(ProcurementLifecycle).where(ProcurementLifecycle.winner.is_not(None))
            )
        ).scalars().all()
        grouped: Dict[str, list] = defaultdict(list)
        for row in awards:
            grouped[row.winner].append(row)

        existing_contractors = {
            row.contractor_name: row
            for row in (await self.db.execute(select(Contractor))).scalars().all()
        }

        # Gather eExperience execution stats per contractor
        await self._ensure_eexperience_schema()
        exec_rows = (await self.db.execute(select(EContractExecution))).scalars().all()
        exec_by_contractor: Dict[str, list] = defaultdict(list)
        for er in exec_rows:
            if er.contractor_name:
                exec_by_contractor[er.contractor_name].append(er)

        contractors_updated = 0
        for name, rows in grouped.items():
            total_amount = sum(self._safe_float(r.award_amount_bdt) for r in rows)
            total_contracts = len(rows)
            agencies = sorted({r.agency_code for r in rows if r.agency_code})
            zones = sorted({r.zone_name for r in rows if r.zone_name})
            npps = [self._safe_float(r.npp_ratio) for r in rows if self._is_credible_npp_row(r)]
            avg_npp = round(sum(npps) / len(npps), 6) if npps else 0.0
            first_award = min((r.award_date for r in rows if r.award_date), default=None)
            last_award = max((r.award_date for r in rows if r.award_date), default=None)
            preferred_agency = max(agencies, key=lambda ag: sum(1 for r in rows if r.agency_code == ag)) if agencies else None
            preferred_zone = max(zones, key=lambda zn: sum(1 for r in rows if r.zone_name == zn)) if zones else None
            avg_award = round(total_amount / total_contracts, 2) if total_contracts else 0.0
            volatility = 0.0
            if len(npps) > 1:
                mean = sum(npps) / len(npps)
                volatility = (sum((v - mean) ** 2 for v in npps) / len(npps)) ** 0.5

            # eExperience performance enrichment
            erows = exec_by_contractor.get(name, [])
            total_exp_contracts = len(erows)
            total_exp_value = sum(self._safe_float(r.contract_value_bdt) for r in erows)
            completed_count = sum(
                1 for r in erows
                if r.actual_completion_date or (r.completion_status and "complete" in r.completion_status.lower())
                or (r.status and "complete" in r.status.lower())
            )
            on_time_count = sum(1 for r in erows if r.completed_on_time is True)
            delays = [r.delay_days for r in erows if r.delay_days and r.delay_days > 0]
            completion_rate = round((completed_count / max(total_exp_contracts, 1)) * 100, 2) if total_exp_contracts else 0.0
            on_time_rate = round((on_time_count / max(completed_count, 1)) * 100, 2) if completed_count else 0.0
            avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0

            contractor = existing_contractors.get(name)
            if contractor is None:
                contractor = Contractor(id=self._uuid(), contractor_name=name)
                self.db.add(contractor)
                await self.db.flush()
                existing_contractors[name] = contractor
            contractor.total_contracts = total_contracts
            contractor.total_amount_bdt = total_amount
            contractor.agencies_worked = agencies
            contractor.districts_worked = zones
            contractor.avg_npp = avg_npp
            contractor.first_award_date = first_award
            contractor.last_award_date = last_award

            # Health score = composite of execution quality + pricing + scale
            completion_norm = completion_rate / 100.0
            on_time_norm = on_time_rate / 100.0
            delay_penalty = max(0.0, 1.0 - (avg_delay / 365.0)) if avg_delay > 0 else 1.0
            npp_score = max(0.0, 1.0 - (avg_npp / 0.30)) if avg_npp else 0.5  # lower NPP = better
            diversity_score = min(1.0, (len(agencies) * 0.1 + len(zones) * 0.05))
            health_score = round(
                completion_norm * 0.30
                + on_time_norm * 0.25
                + delay_penalty * 0.15
                + npp_score * 0.15
                + diversity_score * 0.15,
                4,
            )

            self.db.add(
                ContractorDNA(
                    id=self._uuid(),
                    contractor_id=contractor.id,
                    total_contracts=total_contracts,
                    total_amount_bdt=total_amount,
                    avg_award_bdt=avg_award,
                    agencies_worked=len(agencies),
                    districts_worked=len(zones),
                    preferred_agency=preferred_agency,
                    preferred_zone=preferred_zone,
                    avg_npp=avg_npp,
                    npp_volatility=volatility,
                    win_rate=0.0,
                    avg_discount_pct=max(0.0, round((1 - avg_npp) * 100, 4)) if avg_npp else 0.0,
                    first_award_date=first_award,
                    last_award_date=last_award,
                    completion_rate=completion_rate,
                    on_time_rate=on_time_rate,
                    avg_delay_days=avg_delay,
                    total_experience_contracts=total_exp_contracts,
                    total_experience_value_bdt=round(total_exp_value, 2),
                    health_score=health_score,
                )
            )
            contractors_updated += 1

        await self.db.flush()
        return {"contractors_updated": contractors_updated}

    async def rebuild_aggregate_intelligence(self) -> Dict[str, int]:
        from app.models.intelligence import (
            AgencyIntelligence,
            AwardIntelligence,
            DiscountPattern,
            ProcurementLifecycle,
            ZoneIntelligence,
        )

        await self.db.execute(delete(AgencyIntelligence))
        await self.db.execute(delete(ZoneIntelligence))
        await self.db.execute(delete(DiscountPattern))
        await self.db.execute(delete(AwardIntelligence))
        await self.db.flush()

        rows = (await self.db.execute(select(ProcurementLifecycle))).scalars().all()
        by_agency: Dict[str, list] = defaultdict(list)
        by_zone: Dict[str, list] = defaultdict(list)
        by_agency_quarter: Dict[tuple, list] = defaultdict(list)
        by_discount_bucket: Dict[tuple, list] = defaultdict(list)

        for row in rows:
            if row.agency_code:
                by_agency[row.agency_code].append(row)
            if row.zone_name:
                by_zone[row.zone_name].append(row)
            if row.agency_code:
                award_iso = self._to_iso_date(row.award_date) or "0000-01-01"
                year = award_iso[:4]
                quarter = 1
                if len(award_iso) >= 7 and award_iso[5:7].isdigit():
                    month = int(award_iso[5:7])
                    quarter = ((month - 1) // 3) + 1
                by_agency_quarter[(row.agency_code, year, quarter)].append(row)
                by_discount_bucket[(row.agency_code, row.zone_name or "", row.procurement_method or "")].append(row)

        for agency_code, agency_rows in by_agency.items():
            awards = [r for r in agency_rows if self._safe_float(r.award_amount_bdt) > 0]
            npps = [self._safe_float(r.npp_ratio) for r in awards if self._is_credible_npp_row(r)]
            self.db.add(
                AgencyIntelligence(
                    id=self._uuid(),
                    agency_code=agency_code,
                    total_contracts=len(awards),
                    total_amount_bdt=sum(self._safe_float(r.award_amount_bdt) for r in awards),
                    avg_npp=(sum(npps) / len(npps)) if npps else 0.0,
                    npp_trend="stable",
                    preferred_method=max(
                        (r.procurement_method for r in awards if r.procurement_method),
                        key=lambda method: sum(1 for r in awards if r.procurement_method == method),
                        default=None,
                    ),
                )
            )

        for zone_name, zone_rows in by_zone.items():
            awards = [r for r in zone_rows if self._safe_float(r.award_amount_bdt) > 0]
            npps = [self._safe_float(r.npp_ratio) for r in awards if self._is_credible_npp_row(r)]
            self.db.add(
                ZoneIntelligence(
                    id=self._uuid(),
                    zone_name=zone_name,
                    total_contracts=len(awards),
                    total_amount_bdt=sum(self._safe_float(r.award_amount_bdt) for r in awards),
                    active_agencies=len({r.agency_code for r in awards if r.agency_code}),
                    avg_npp=(sum(npps) / len(npps)) if npps else 0.0,
                )
            )

        for (agency_code, zone_name, method), bucket_rows in by_discount_bucket.items():
            npps = [self._safe_float(r.npp_ratio) for r in bucket_rows if self._is_credible_npp_row(r)]
            if not npps:
                continue
            ordered = sorted(npps)
            mid = len(ordered) // 2
            median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
            mean = sum(ordered) / len(ordered)
            stddev = (sum((v - mean) ** 2 for v in ordered) / len(ordered)) ** 0.5 if len(ordered) > 1 else 0.0
            self.db.add(
                DiscountPattern(
                    id=self._uuid(),
                    agency_code=agency_code,
                    zone_name=zone_name or None,
                    procurement_method=method or None,
                    sample_size=len(ordered),
                    avg_npp=mean,
                    min_npp=min(ordered),
                    max_npp=max(ordered),
                    median_npp=median,
                    stddev_npp=stddev,
                    total_amount_bdt=sum(self._safe_float(r.award_amount_bdt) for r in bucket_rows),
                )
            )

        for (agency_code, year, quarter), q_rows in by_agency_quarter.items():
            awards = [r for r in q_rows if self._safe_float(r.award_amount_bdt) > 0]
            if not awards:
                continue
            npps = [self._safe_float(r.npp_ratio) for r in awards if self._is_credible_npp_row(r)]
            self.db.add(
                AwardIntelligence(
                    id=self._uuid(),
                    agency_code=agency_code,
                    fiscal_year=year,
                    quarter=quarter,
                    total_contracts=len(awards),
                    total_amount_bdt=sum(self._safe_float(r.award_amount_bdt) for r in awards),
                    avg_npp=(sum(npps) / len(npps)) if npps else 0.0,
                    avg_contract_amount=sum(self._safe_float(r.award_amount_bdt) for r in awards) / len(awards),
                )
            )

        await self.db.flush()
        return {
            "agencies": len(by_agency),
            "zones": len(by_zone),
            "award_quarters": len(by_agency_quarter),
        }

    # ------------------------------------------------------------------
    # Query API used by routes
    # ------------------------------------------------------------------

    async def list_contractors(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        from app.models.intelligence import Contractor

        result = await self.db.execute(
            select(Contractor)
            .order_by(Contractor.total_amount_bdt.desc(), Contractor.contractor_name.asc())
            .limit(max(limit * 3, 100))
            .offset(offset)
        )
        records = [self._row_to_dict(r) for r in result.scalars().all()]
        filtered = [r for r in records if not self._should_exclude_contractor_name(r.get("contractor_name"))]
        return filtered[:limit]

    async def get_contractor(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        from app.models.intelligence import Contractor

        query_norm = self._normalize_search_text(name_or_id)
        result = await self.db.execute(
            select(Contractor).where(
                or_(
                    Contractor.contractor_name.ilike(f"%{name_or_id}%"),
                    Contractor.contractor_name.ilike(f"%{query_norm}%"),
                    Contractor.id == name_or_id,
                )
            )
        )
        rows = result.scalars().all()
        if rows:
            ranked = sorted(
                (
                    row
                    for row in rows
                    if not self._should_exclude_contractor_name(row.contractor_name)
                ),
                key=lambda row: self._contractor_match_score(query_norm, row.contractor_name, getattr(row, "id", None)),
                reverse=True,
            )
            if ranked:
                return self._row_to_dict(ranked[0])

        fallback = await self.search_contractors(name_or_id, limit=1)
        return fallback[0] if fallback else None

    async def search_contractors(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        from app.models.intelligence import Contractor

        query_norm = self._normalize_search_text(query)
        if not query_norm:
            return []
        tokens = [token for token in query_norm.split() if len(token) >= 2]

        stmt = select(Contractor)
        if tokens:
            token_filters = [Contractor.contractor_name.ilike(f"%{token}%") for token in tokens[:5]]
            stmt = stmt.where(or_(*token_filters))
        stmt = stmt.order_by(Contractor.total_amount_bdt.desc(), Contractor.contractor_name.asc()).limit(max(limit * 10, 100))

        result = await self.db.execute(
            stmt
        )
        rows = [
            r
            for r in result.scalars().all()
            if not self._should_exclude_contractor_name(r.contractor_name)
        ]
        ranked = sorted(
            rows,
            key=lambda row: (
                self._contractor_match_score(query_norm, row.contractor_name, getattr(row, "id", None)),
                self._safe_float(getattr(row, "total_amount_bdt", 0)),
            ),
            reverse=True,
        )
        return [self._row_to_dict(r) for r in ranked[:limit]]

    async def backfill_tender_regimes(self) -> Dict[str, int]:
        """
        Backfill regime labels on legacy tender rows.

        Existing records sometimes predate the `regime` column or have NULL/empty
        values after imports. This keeps the public dashboards and filters aligned
        with the PPR2008/PPR2025 split.
        """
        from app.agents.core.regime import get_regime

        columns_result = await self.db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'tenders'
                """
            )
        )
        columns = {row[0] for row in columns_result.all()}
        if "id" not in columns:
            return {"updated": 0, "total": 0, "skipped": 1}

        if "regime" not in columns:
            await self.db.execute(
                text(
                    """
                    ALTER TABLE tenders
                    ADD COLUMN IF NOT EXISTS regime VARCHAR(20) DEFAULT 'PPR2008'
                    """
                )
            )
            await self.db.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_tenders_regime
                    ON tenders (regime)
                    """
                )
            )
            columns.add("regime")

        date_column = next(
            (col for col in ("opening_date", "closing_date", "publication_date", "created_at") if col in columns),
            None,
        )
        if not date_column:
            return {"updated": 0, "total": 0, "skipped": 1}

        rows = (
            await self.db.execute(
                text(
                    f"""
                    SELECT id, {date_column} AS source_date, regime
                    FROM tenders
                    """
                )
            )
        ).all()
        updated = 0
        for row in rows:
            regime = get_regime(row.source_date)
            current_regime = row.regime
            if not current_regime or current_regime != regime:
                await self.db.execute(
                    text("UPDATE tenders SET regime = :regime WHERE id = :id"),
                    {"regime": regime, "id": row.id},
                )
                updated += 1

        if updated:
            await self.db.flush()
        return {"updated": updated, "total": len(rows)}

    async def get_contractor_stats(self) -> Dict[str, Any]:
        from app.models.intelligence import Contractor

        total, total_amount, avg_npp = (
            await self.db.execute(
                select(
                    func.count(Contractor.id),
                    func.coalesce(func.sum(Contractor.total_amount_bdt), 0),
                    func.coalesce(func.avg(Contractor.avg_npp), 0),
                )
            )
        ).one()
        return {
            "total_contractors": total or 0,
            "total_amount_bdt": round(float(total_amount or 0), 2),
            "avg_npp": round(float(avg_npp or 0), 4),
        }

    async def get_contractor_dna(self, contractor_id: str) -> Optional[Dict[str, Any]]:
        from app.models.intelligence import ContractorDNA

        result = await self.db.execute(
            select(ContractorDNA).where(ContractorDNA.contractor_id == contractor_id)
        )
        row = result.scalar_one_or_none()
        return self._row_to_dict(row) if row else None

    async def benchmark_contractor(self, contractor_id: str, agency: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Compare a contractor against peers (same agency or all)."""
        from app.models.intelligence import Contractor, ContractorDNA

        contractor = await self.db.get(Contractor, contractor_id)
        if not contractor:
            return None
        dna = await self.get_contractor_dna(contractor_id)
        if not dna:
            return None

        # Peer group: contractors in the same agency
        if not agency and dna.get("preferred_agency"):
            agency = dna["preferred_agency"]

        peers_query = select(ContractorDNA)
        if agency:
            peers_query = peers_query.where(ContractorDNA.preferred_agency == agency)
        peers = (await self.db.execute(peers_query)).scalars().all()

        if not peers:
            return {"contractor": dna, "peers": [], "percentiles": {}, "verdict": "No peer data"}

        # Compute percentiles for key metrics
        metrics = [
            ("health_score", "higher"),
            ("completion_rate", "higher"),
            ("on_time_rate", "higher"),
            ("avg_discount_pct", "higher"),
            ("total_amount_bdt", "higher"),
            ("total_contracts", "higher"),
            ("avg_npp", "lower"),
            ("npp_volatility", "lower"),
            ("avg_delay_days", "lower"),
        ]
        percentiles = {}
        strengths = []
        weaknesses = []
        for metric, direction in metrics:
            vals = sorted([getattr(p, metric, 0) for p in peers])
            contractor_val = dna.get(metric, 0)
            if not vals or vals[-1] == vals[0]:
                percentile = 50.0
            else:
                count_below = sum(1 for v in vals if v <= contractor_val)
                percentile = round((count_below / len(vals)) * 100, 1)
            percentiles[metric] = {
                "value": contractor_val,
                "percentile": percentile,
                "peer_min": min(vals),
                "peer_max": max(vals),
                "peer_avg": round(sum(vals) / len(vals), 4),
            }
            if direction == "higher":
                if percentile >= 80:
                    strengths.append(metric)
                elif percentile <= 20:
                    weaknesses.append(metric)
            else:
                if percentile <= 20:
                    strengths.append(metric)
                elif percentile >= 80:
                    weaknesses.append(metric)

        return {
            "contractor": dna,
            "peer_count": len(peers),
            "peer_agency": agency,
            "percentiles": percentiles,
            "strengths": strengths,
            "weaknesses": weaknesses,
        }

    async def get_agent_feed(self, agency: Optional[str] = None, limit: int = 25) -> Dict[str, Any]:
        from app.models.intelligence import ContractorDNA
        lifecycle = await self.query_lifecycle(agency=agency, limit=limit, offset=0)
        contractors = await self.list_contractors(limit=min(limit, 20), offset=0)
        agency_intel = await self.get_agency_intelligence(agency)
        contractor_stats = await self.get_contractor_stats()
        lifecycle_stats = await self.get_lifecycle_stats()
        data_quality = await self.get_award_data_quality_stats()
        live_tender_stats = await self.get_live_tender_stats(agency=agency)
        eexperience_stats = await self.get_eexperience_stats()
        recent_eexperience = await self.query_eexperience(agency=agency, limit=min(limit, 10), offset=0)
        execution_intelligence = await self.get_execution_intelligence(agency=agency, limit=min(limit, 8))
        rate_quoted = await self.get_rate_quoted_analysis(agency=agency, limit=min(limit, 10))
        reconciliation = await self.reconcile_execution_to_lifecycle()
        # Top contractors by eExperience completion performance
        top_performers = sorted(
            (await self.db.execute(
                select(ContractorDNA).order_by(ContractorDNA.completion_rate.desc()).limit(10)
            )).scalars().all(),
            key=lambda x: x.completion_rate,
            reverse=True,
        )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agency_filter": agency,
            "lifecycle_stats": lifecycle_stats,
            "data_quality": data_quality,
            "contractor_stats": contractor_stats,
            "live_tender_stats": live_tender_stats,
            "eexperience_stats": eexperience_stats,
            "execution_intelligence": execution_intelligence,
            "rate_quoted": {
                "total_award_bdt": rate_quoted["total_award_bdt"],
                "total_completed_bdt": rate_quoted["total_completed_bdt"],
                "total_variance_bdt": rate_quoted["total_variance_bdt"],
                "avg_variance_pct": rate_quoted["avg_variance_pct"],
                "delayed_count": rate_quoted["delayed_count"],
                "sample_records": rate_quoted["records"],
                "by_agency": rate_quoted["by_agency"],
            },
            "lifecycle_execution_match": {
                "tender_match_rate_pct": reconciliation["tender_match_rate_pct"],
                "app_match_rate_pct": reconciliation["app_match_rate_pct"],
                "matched_to_tender": reconciliation["matched_to_tender"],
                "matched_to_app": reconciliation["matched_to_app"],
                "unmatched": reconciliation["unmatched"],
            },
            "top_contractors_by_completion": [
                {
                    "contractor_id": c.contractor_id,
                    "completion_rate": c.completion_rate,
                    "on_time_rate": c.on_time_rate,
                    "avg_delay_days": c.avg_delay_days,
                    "total_experience_contracts": c.total_experience_contracts,
                }
                for c in top_performers
            ],
            "recent_lifecycle": lifecycle["records"],
            "recent_eexperience": recent_eexperience["records"],
            "top_contractors": contractors,
            "agency_intelligence": agency_intel[: min(limit, 20)],
        }

    async def get_import_counts(self) -> Dict[str, int]:
        from app.models.intelligence import APPRecord, AwardRecordV2, ContractorDNA, Contractor, EContractExecution, LiveTenderSource, ProcurementLifecycle, ProcurementTender

        return {
            "tenders": int(await self.db.scalar(select(func.count(ProcurementTender.id))) or 0),
            "app_records": int(await self.db.scalar(select(func.count(APPRecord.id))) or 0),
            "live_tender_sources": int(await self.db.scalar(select(func.count(LiveTenderSource.id))) or 0),
            "awards": int(await self.db.scalar(select(func.count(AwardRecordV2.id))) or 0),
            "eexperience": int(await self.db.scalar(select(func.count(EContractExecution.id))) or 0),
            "lifecycle": int(await self.db.scalar(select(func.count(ProcurementLifecycle.id))) or 0),
            "contractors": int(await self.db.scalar(select(func.count(Contractor.id))) or 0),
            "contractor_dna": int(await self.db.scalar(select(func.count(ContractorDNA.id))) or 0),
        }

    async def get_award_data_quality_stats(self) -> Dict[str, int]:
        from app.models.intelligence import APPRecord, AwardRecordV2

        app_tender_ids = {
            row.procurement_tender_id
            for row in (await self.db.execute(select(APPRecord.procurement_tender_id))).all()
            if row[0]
        }
        awards = (await self.db.execute(select(AwardRecordV2))).scalars().all()
        dedup_stats = self._deduplicate_awards(awards, app_tender_ids)[1]
        return dedup_stats

    async def list_awards_for_agent(self, agency: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        from app.models.intelligence import AwardRecordV2, ProcurementTender

        stmt = (
            select(AwardRecordV2, ProcurementTender)
            .join(ProcurementTender, ProcurementTender.id == AwardRecordV2.procurement_tender_id)
            .order_by(AwardRecordV2.award_date.desc().nullslast(), AwardRecordV2.created_at.desc())
            .limit(limit)
        )
        if agency:
            stmt = stmt.where(
                or_(
                    AwardRecordV2.agency_code.ilike(f"%{agency}%"),
                    AwardRecordV2.pe_office.ilike(f"%{agency}%"),
                    ProcurementTender.agency_code.ilike(f"%{agency}%"),
                    ProcurementTender.pe_office.ilike(f"%{agency}%"),
                )
            )

        result = await self.db.execute(stmt)
        records: List[Dict[str, Any]] = []
        for award, tender in result.all():
            amount = self._safe_float(award.amount_bdt)
            estimate = 0.0
            discount_pct = 0.0
            if award.package_no and tender.package_no == award.package_no:
                app_cache = await self._ensure_app_record_cache()
                app_record = app_cache.get(tender.id)
                if app_record:
                    estimate = self._safe_float(app_record.estimated_cost_bdt)
                    if estimate > 0 and amount > 0:
                        discount_pct = round(((estimate - amount) / estimate) * 100, 4)
            records.append(
                {
                    "tender_id": award.package_no or tender.package_no or award.source_tender_id,
                    "source_tender_id": award.source_tender_id,
                    "title": award.title or tender.title or "",
                    "procuring_entity": award.pe_office or tender.pe_office or "",
                    "winner": award.contractor_name or "Unknown",
                    "award_amount": amount,
                    "award_date": award.award_date,
                    "discount_percent": discount_pct,
                    "procurement_method": award.procurement_method or tender.procurement_method,
                    "agency_code": award.agency_code or tender.agency_code,
                    "category": "Award",
                    "source": "postgresql",
                }
            )
        return records

    async def query_lifecycle(
        self,
        agency: Optional[str] = None,
        zone: Optional[str] = None,
        contractor: Optional[str] = None,
        min_amount: float = 0,
        max_amount: float = 0,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        method: Optional[str] = None,
        match_type: Optional[str] = None,
        data_source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        from app.models.intelligence import ProcurementLifecycle as PL

        conditions = []
        if agency:
            conditions.append(PL.agency_code.ilike(f"%{agency}%"))
        if zone:
            conditions.append(PL.zone_name.ilike(f"%{zone}%"))
        if contractor:
            conditions.append(PL.winner.ilike(f"%{contractor}%"))
        if min_amount > 0:
            conditions.append(PL.award_amount_bdt >= min_amount)
        if max_amount > 0:
            conditions.append(PL.award_amount_bdt <= max_amount)
        if date_from:
            conditions.append(PL.award_date >= date_from)
        if date_to:
            conditions.append(PL.award_date <= date_to)
        if method:
            conditions.append(PL.procurement_method.ilike(f"%{method}%"))
        if match_type:
            conditions.append(PL.match_type == match_type)
        if data_source:
            conditions.append(PL.data_source == data_source)

        where_clause = and_(*conditions) if conditions else text("1=1")
        total = await self.db.scalar(select(func.count(PL.id)).where(where_clause))
        result = await self.db.execute(
            select(PL)
            .where(where_clause)
            .order_by(PL.award_date.desc().nullslast(), PL.package_no.asc())
            .limit(limit)
            .offset(offset)
        )
        return {
            "total": total or 0,
            "limit": limit,
            "offset": offset,
            "records": [self._row_to_dict(r) for r in result.scalars().all()],
        }

    async def get_lifecycle_stats(self) -> Dict[str, Any]:
        from app.models.intelligence import ProcurementLifecycle as PL

        total, total_estimated, total_awarded, matched_packages, matched_total, title_similarity = (
            await self.db.execute(
                select(
                    func.count(PL.id),
                    func.coalesce(func.sum(PL.estimated_cost_bdt), 0),
                    func.coalesce(func.sum(PL.award_amount_bdt), 0),
                    func.count(PL.id).filter(PL.match_type == "package_exact"),
                    func.count(PL.id).filter(PL.data_source == "matched"),
                    func.count(PL.id).filter(PL.match_type == "title_similarity"),
                )
            )
        ).one()
        total_records = int(total or 0)
        matched_total_count = int(matched_total or 0)
        return {
            "total_records": total_records,
            "total_estimated_bdt": round(float(total_estimated or 0), 2),
            "total_award_bdt": round(float(total_awarded or 0), 2),
            "matched_packages": int(matched_packages or 0),
            "matched_total": matched_total_count,
            "title_similarity_matches": int(title_similarity or 0),
            "match_rate_pct": round((matched_total_count / total_records) * 100, 2) if total_records else 0.0,
        }

    async def get_live_tender_stats(self, agency: Optional[str] = None) -> Dict[str, Any]:
        from app.models.intelligence import LiveTenderSource as LT, ProcurementTender as PT

        stmt = select(LT, PT).join(PT, PT.id == LT.procurement_tender_id)
        if agency:
            stmt = stmt.where(or_(PT.agency_code == agency, LT.procuring_entity.ilike(f"%{agency}%")))
        rows = (await self.db.execute(stmt)).all()
        deadlines = [self._to_iso_date(live.deadline) for live, _ in rows if self._to_iso_date(live.deadline)]
        return {
            "total_live_tenders": len(rows),
            "with_real_estimate": sum(1 for live, _ in rows if self._safe_float(live.estimated_value_bdt) > 0),
            "active_agencies": len({tender.agency_code for live, tender in rows if tender.agency_code}),
            "latest_deadline": max(deadlines) if deadlines else None,
        }

    async def get_agency_intelligence(self, agency_code: Optional[str] = None) -> List[Dict[str, Any]]:
        from app.models.intelligence import AgencyIntelligence

        stmt = select(AgencyIntelligence)
        if agency_code:
            stmt = stmt.where(AgencyIntelligence.agency_code == agency_code)
        stmt = stmt.order_by(AgencyIntelligence.total_amount_bdt.desc())
        result = await self.db.execute(stmt)
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def get_npp_trends(self, months: int = 12) -> List[Dict[str, Any]]:
        from app.models.intelligence import ProcurementLifecycle as PL

        month_expr = func.substr(PL.award_date, 1, 7)
        result = await self.db.execute(
            select(
                PL.agency_code,
                month_expr.label("month"),
                func.avg(PL.npp_ratio).label("avg_npp"),
                func.count(PL.id).label("count"),
            )
            .where(
                and_(
                    PL.npp_ratio >= MIN_CREDIBLE_NPP,
                    PL.npp_ratio <= MAX_CREDIBLE_NPP,
                    PL.estimated_cost_bdt >= MIN_CREDIBLE_ESTIMATE_BDT,
                    PL.award_amount_bdt >= MIN_CREDIBLE_AWARD_BDT,
                    PL.match_type.in_(("package_exact", "title_similarity")),
                    PL.data_source == "matched",
                    PL.award_date.is_not(None),
                )
            )
            .group_by(PL.agency_code, month_expr)
            .order_by(month_expr.asc(), PL.agency_code.asc())
        )
        rows = [
            {
                "agency_code": r[0],
                "agency": r[0],
                "month": r[1],
                "avg_npp": round(float(r[2] or 0), 4),
                "count": int(r[3] or 0),
            }
            for r in result.all()
        ]
        return rows[-months:] if months and len(rows) > months else rows

    async def get_zone_intelligence(self) -> List[Dict[str, Any]]:
        from app.models.intelligence import ZoneIntelligence

        result = await self.db.execute(
            select(ZoneIntelligence).order_by(ZoneIntelligence.total_amount_bdt.desc())
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def get_discount_patterns(
        self,
        agency: Optional[str] = None,
        zone: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from app.models.intelligence import DiscountPattern

        conditions = []
        if agency:
            conditions.append(DiscountPattern.agency_code == agency)
        if zone:
            conditions.append(DiscountPattern.zone_name.ilike(f"%{zone}%"))
        where_clause = and_(*conditions) if conditions else text("1=1")
        result = await self.db.execute(
            select(DiscountPattern)
            .where(where_clause)
            .order_by(DiscountPattern.sample_size.desc(), DiscountPattern.agency_code.asc())
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def get_award_trends(
        self,
        agency: Optional[str] = None,
        fiscal_year: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from app.models.intelligence import AwardIntelligence

        conditions = []
        if agency:
            conditions.append(AwardIntelligence.agency_code == agency)
        if fiscal_year:
            conditions.append(AwardIntelligence.fiscal_year == fiscal_year)
        where_clause = and_(*conditions) if conditions else text("1=1")
        result = await self.db.execute(
            select(AwardIntelligence)
            .where(where_clause)
            .order_by(AwardIntelligence.fiscal_year.asc(), AwardIntelligence.quarter.asc(), AwardIntelligence.agency_code.asc())
        )
        return [self._row_to_dict(r) for r in result.scalars().all()]

    async def get_department_tree(self) -> List[Dict[str, Any]]:
        from app.models.intelligence import Agency, APPRecord, ProcurementTender
        if self._department_tree_cache is not None:
            return self._department_tree_cache

        ministry_expr = func.coalesce(Agency.ministry, Agency.agency_name, ProcurementTender.agency_code, "Unknown Ministry")
        office_expr = func.coalesce(ProcurementTender.pe_office, Agency.agency_name, ProcurementTender.agency_code, "Unknown Office")
        result = await self.db.execute(
            select(
                ministry_expr.label("ministry"),
                office_expr.label("office"),
                func.count(ProcurementTender.id).label("package_count"),
                func.coalesce(func.sum(APPRecord.estimated_cost_bdt), 0).label("total_estimated_bdt"),
            )
            .join(APPRecord, APPRecord.procurement_tender_id == ProcurementTender.id)
            .outerjoin(Agency, Agency.agency_code == ProcurementTender.agency_code)
            .group_by(ministry_expr, office_expr)
            .order_by(ministry_expr.asc(), office_expr.asc())
        )
        ministries: Dict[str, Dict[str, Any]] = {}
        for ministry, office, package_count, total_estimated_bdt in result.all():
            ministry = ministry or "Unknown Ministry"
            office = office or "Unknown Office"
            ministry_entry = ministries.setdefault(
                ministry,
                {
                    "id": ministry,
                    "name": ministry,
                    "type": "Ministry",
                    "office_count": 0,
                    "total_packages": 0,
                    "offices": [],
                },
            )
            ministry_entry["offices"].append(
                {
                    "id": office,
                    "name": office,
                    "package_count": int(package_count or 0),
                    "total_estimated_bdt": round(float(total_estimated_bdt or 0), 2),
                }
            )
            ministry_entry["total_packages"] += int(package_count or 0)

        tree: List[Dict[str, Any]] = []
        for ministry in sorted(ministries.keys()):
            entry = ministries[ministry]
            entry["offices"] = sorted(entry["offices"], key=lambda item: item["name"])
            entry["office_count"] = len(entry["offices"])
            tree.append(entry)

        self._department_tree_cache = tree
        return tree

    async def search_live_tenders(
        self,
        department_id: str = "",
        office_id: str = "",
        keyword: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        from app.models.intelligence import Agency, APPRecord, LiveTenderSource, ProcurementTender

        result = await self.db.execute(
            select(ProcurementTender, LiveTenderSource, APPRecord, Agency)
            .join(LiveTenderSource, LiveTenderSource.procurement_tender_id == ProcurementTender.id)
            .outerjoin(APPRecord, APPRecord.procurement_tender_id == ProcurementTender.id)
            .outerjoin(Agency, Agency.agency_code == ProcurementTender.agency_code)
            .order_by(LiveTenderSource.deadline.asc().nullslast(), ProcurementTender.package_no.asc())
        )
        keyword_lower = keyword.lower().strip()
        rows = []
        today = date.today().isoformat()
        excluded_status_terms = ("archived", "archive", "closed", "cancelled", "canceled", "awarded", "completed")
        live_status_terms = ("live", "open", "ongoing")

        for tender, live_record, app_record, agency in result.all():
            office_source = self._coalesce(live_record.procuring_entity, tender.pe_office, "")
            office = self._compact_live_entity(office_source)
            ministry = self._infer_ministry_from_entity(office_source)
            if (not ministry or ministry == "Unknown Ministry") and agency and agency.ministry:
                ministry = agency.ministry
            status = self._normalize_spaces(live_record.status or "").lower()
            deadline = self._to_iso_date(live_record.deadline)
            app_estimate = self._safe_float(getattr(app_record, "estimated_cost_bdt", 0) if app_record else 0)
            live_estimate = self._safe_float(live_record.estimated_value_bdt)
            has_app = bool(app_record and app_estimate > 0)
            app_unit_hint = self._extract_amount_unit_hint(
                self._coalesce(
                    getattr(app_record, "raw_payload", None),
                    live_record.raw_payload or {},
                )
            )
            primary_title = self._coalesce(
                app_record.title if app_record else None,
                live_record.title,
                tender.title,
                "",
            )
            primary_tender_id = self._coalesce(
                app_record.source_tender_id if app_record else None,
                live_record.source_tender_id,
                tender.package_no,
                "",
            )
            primary_package = self._coalesce(
                app_record.package_no if app_record and hasattr(app_record, "package_no") else None,
                tender.package_no,
                live_record.source_tender_id,
                primary_tender_id,
                "",
            )
            estimate = app_estimate if has_app else (live_estimate or app_estimate)

            if status and any(term in status for term in excluded_status_terms):
                continue
            if status and not any(term in status for term in live_status_terms):
                continue
            if deadline and deadline < today:
                continue
            if department_id and ministry.upper() != department_id.upper():
                continue
            if office_id and office.upper() != office_id.upper():
                continue
            if keyword_lower:
                haystack = " ".join(
                    [
                        tender.package_no or "",
                        live_record.title or tender.title or "",
                        office,
                        live_record.category or "",
                    ]
                ).lower()
                if keyword_lower not in haystack:
                    continue
            rows.append(
                {
                    "tender_id": primary_tender_id,
                    "package_no": tender.package_no,
                    "title": primary_title,
                    "app_tender_id": primary_tender_id,
                    "live_tender_id": primary_tender_id,
                    "app_work_name": primary_title,
                    "live_work_name": self._coalesce(live_record.title, tender.title, ""),
                    "app_estimated_value_bdt": round(app_estimate, 2),
                    "live_estimated_value_bdt": round(live_estimate, 2),
                    "procuring_entity": office,
                    "ministry": ministry,
                    "published_date": live_record.published_date or "",
                    "deadline": deadline or "",
                    "estimated_value_bdt": round(estimate, 2),
                    "estimated_value_source": "APP" if has_app else ("LIVE" if live_estimate else "NONE"),
                    "app_estimated_value_display": self._format_money_display(app_estimate, app_unit_hint, "APP") if has_app else "—",
                    "app_estimated_value_unit": app_unit_hint or "",
                    "notice_data": {
                        "tender_id": primary_tender_id,
                        "app_tender_id": primary_tender_id,
                        "live_tender_id": primary_tender_id,
                        "package_no": primary_package,
                        "work_name": primary_title,
                        "app_work_name": primary_title,
                        "live_work_name": self._coalesce(live_record.title, tender.title, ""),
                        "title": primary_title,
                        "estimated_cost_bdt": round(app_estimate if has_app else estimate, 2),
                        "estimated_amount_bdt": round(app_estimate if has_app else estimate, 2),
                        "app_estimated_value_bdt": round(app_estimate, 2),
                        "app_estimated_value_display": self._format_money_display(app_estimate, app_unit_hint, "APP") if has_app else "—",
                        "app_estimated_value_unit": app_unit_hint or "",
                        "live_estimated_value_bdt": round(live_estimate, 2),
                        "published_date": app_record.published_date if app_record else (live_record.published_date or ""),
                        "deadline": app_record.deadline if app_record else (deadline or ""),
                        "financial_year": app_record.financial_year if app_record else "",
                        "app_code": app_record.app_code if app_record else "",
                        "category": app_record.category if app_record else (live_record.category or ""),
                        "procuring_entity": office_source,
                        "ministry": ministry,
                        "live_status": live_record.status or "Live",
                        "live_value_bdt": round(live_estimate, 2),
                        "app_value_bdt": round(app_estimate, 2),
                        "raw_payload": live_record.raw_payload or {},
                    },
                    "category": live_record.category or "",
                    "location": "",
                    "status": live_record.status or "Live",
                }
            )

        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "tenders": rows[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def get_executive_overview(self) -> Dict[str, Any]:
        from app.models.intelligence import APPRecord, AwardRecordV2, Contractor, ProcurementLifecycle, ProcurementTender
        from app.agents import AgentRegistry
        from app.agents.orchestrator import PIPELINE_DEFINITION, PipelinePhase

        total_tenders = await self.db.scalar(select(func.count(ProcurementTender.id)))
        total_app = await self.db.scalar(select(func.count(APPRecord.id)))
        total_awards = await self.db.scalar(select(func.count(AwardRecordV2.id)))
        total_contractors = await self.db.scalar(select(func.count(Contractor.id)))
        matched = await self.db.scalar(
            select(func.count(ProcurementLifecycle.id)).where(ProcurementLifecycle.match_type == "package_exact")
        )
        total_lifecycle = await self.db.scalar(select(func.count(ProcurementLifecycle.id)))
        # eExperience / eCMS stats
        from app.models.intelligence import EContractExecution as EE
        ee_total = await self.db.scalar(select(func.count(EE.id)).where(EE.data_source == "EEXPERIENCE_ALL"))
        ecms_total = await self.db.scalar(select(func.count(EE.id)).where(EE.data_source == "ECMS_ONGOING"))
        ee_value = await self.db.scalar(select(func.coalesce(func.sum(EE.contract_value_bdt), 0)).where(EE.data_source == "EEXPERIENCE_ALL"))
        ecms_value = await self.db.scalar(select(func.coalesce(func.sum(EE.contract_value_bdt), 0)).where(EE.data_source == "ECMS_ONGOING"))

        registry = AgentRegistry()
        agent_list = registry.list_agents()
        agent_lookup = {agent["agent_id"]: agent for agent in agent_list}
        active_statuses = {"idle", "success", "ready"}
        phase_rows: List[Dict[str, Any]] = []
        by_phase: Dict[str, int] = {}
        phase_labels: Dict[str, str] = {}
        phased_agent_ids: set[str] = set()

        for phase in PipelinePhase:
            agent_ids = PIPELINE_DEFINITION.get(phase, [])
            registered_agents = [agent_lookup[aid] for aid in agent_ids if aid in agent_lookup]
            registered_ids = [agent["agent_id"] for agent in registered_agents]
            phase_label = phase.value.replace("_", " ").title()
            phase_labels[phase.value] = phase_label
            by_phase[phase.value] = len(registered_agents)
            phased_agent_ids.update(registered_ids)
            phase_rows.append({
                "phase": phase.value,
                "label": phase_label,
                "total": len(agent_ids),
                "registered": len(registered_agents),
                "agents": agent_ids,
                "registered_agents": registered_ids,
            })

        total_pipeline_agents = len(phased_agent_ids)
        active_agents = sum(1 for agent in agent_list if agent.get("status") in active_statuses)
        return {
            "slt": {"total_evaluations": 0, "evaluations": []},
            "agents": {
                "total": len(agent_list),
                "active": active_agents,
                "by_phase": by_phase,
                "phase_labels": phase_labels,
                "agent_list": agent_list,
            },
            "bwdb": {
                "tenders_scanned": total_tenders or 0,
                "bwdb_matches": matched or 0,
                "alerts": [],
                "alert_count": 0,
            },
            "embedding": {
                "knowledge_total": (total_tenders or 0) + (total_awards or 0),
                "by_domain": {
                    "tenders": total_tenders or 0,
                    "app": total_app or 0,
                    "awards": total_awards or 0,
                    "contractor_dna": total_contractors or 0,
                    "matches": matched or 0,
                },
            },
            "pipeline": {
                "phases": phase_rows,
                "total_agents_phased": total_pipeline_agents,
            },
            "predictions": {"total_predictions": total_lifecycle or 0, "contractors_with_data": total_contractors or 0},
            "cross_check": {"status": "available", "total_predictions": total_lifecycle or 0, "indexed_awards": total_awards or 0},
            "npp": {
                "total_npp_records": await self.db.scalar(
                    select(func.count(ProcurementLifecycle.id)).where(ProcurementLifecycle.npp_ratio > 0)
                ) or 0,
                "by_agency": {},
                "agencies_with_data": [],
            },
            "documents": {
                "reports_generated": 0,
                "services_available": ["tender_doc_generator", "template_filler", "boq_excel_generator"],
            },
            "storage": {
                "base_dir": str(RUNTIME_DIR),
                "knowledge_lake": (total_tenders or 0) + (total_awards or 0),
                "bwdb_records": matched or 0,
                "econtracts_records": total_awards or 0,
            },
            "execution": {
                "eexperience_completed": int(ee_total or 0),
                "ecms_ongoing": int(ecms_total or 0),
                "eexperience_value_bdt": round(float(ee_value or 0), 2),
                "ecms_value_bdt": round(float(ecms_value or 0), 2),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # eExperience (EContractExecution) queries
    # ------------------------------------------------------------------

    async def query_eexperience(
        self,
        agency: Optional[str] = None,
        contractor: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        work_status: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conditions = []
        if agency:
            conditions.append(or_(EE.agency_code.ilike(f"%{agency}%"), EE.agency_name.ilike(f"%{agency}%"), EE.pe_office.ilike(f"%{agency}%")))
        if contractor:
            conditions.append(EE.contractor_name.ilike(f"%{contractor}%"))
        if date_from:
            conditions.append(EE.contract_start_date >= date_from)
        if date_to:
            conditions.append(EE.contract_end_date <= date_to)
        if status:
            conditions.append(EE.status == status)
        if source:
            conditions.append(EE.data_source == source)
        if work_status:
            conditions.append(EE.work_status.ilike(f"%{work_status}%"))
        if min_value is not None:
            conditions.append(EE.contract_value_bdt >= min_value)
        if max_value is not None:
            conditions.append(EE.contract_value_bdt <= max_value)

        where_clause = and_(*conditions) if conditions else text("1=1")
        total = await self.db.scalar(select(func.count(EE.id)).where(where_clause))
        result = await self.db.execute(
            select(EE)
            .where(where_clause)
            .order_by(EE.actual_completion_date.desc().nullslast(), EE.contract_end_date.desc().nullslast(), EE.contract_start_date.desc().nullslast(), EE.package_no.asc())
            .limit(limit)
            .offset(offset)
        )
        return {
            "total": total or 0,
            "limit": limit,
            "offset": offset,
            "source_filter": source,
            "records": [self._row_to_dict(r) for r in result.scalars().all()],
        }

    async def get_eexperience_stats(self, source: Optional[str] = None) -> Dict[str, Any]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        cond = [EE.data_source == source] if source else []
        where = and_(*cond) if cond else text("1=1")
        total, total_value, total_completed_value, agencies, contractors, completed_records, delayed_records = (
            await self.db.execute(
                select(
                    func.count(EE.id),
                    func.coalesce(func.sum(EE.contract_value_bdt), 0),
                    func.coalesce(func.sum(EE.completed_value_bdt), 0),
                    func.count(func.distinct(EE.agency_code)).filter(EE.agency_code.is_not(None)),
                    func.count(func.distinct(EE.contractor_name)).filter(EE.contractor_name.is_not(None)),
                    func.count(EE.id).filter(
                        or_(EE.actual_completion_date.is_not(None), EE.completion_status.ilike("%complete%"), EE.status.ilike("%complete%"))
                    ),
                    func.count(EE.id).filter(
                        or_(EE.delay_days > 0, EE.completed_on_time.is_(False), EE.completion_status.ilike("%delay%"))
                    ),
                ).where(where)
            )
        ).one()
        return {
            "total_records": int(total or 0),
            "total_value_bdt": round(float(total_value or 0), 2),
            "total_completed_value_bdt": round(float(total_completed_value or 0), 2),
            "unique_agencies": int(agencies or 0),
            "unique_contractors": int(contractors or 0),
            "completed_records": int(completed_records or 0),
            "delayed_records": int(delayed_records or 0),
        }

    async def get_contractor_performance(
        self,
        contractor_name: str,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conditions = [EE.contractor_name.ilike(f"%{contractor_name}%")]
        if source:
            conditions.append(EE.data_source == source)
        where = and_(*conditions)

        total = await self.db.scalar(select(func.count(EE.id)).where(where))
        total_val = await self.db.scalar(select(func.coalesce(func.sum(EE.contract_value_bdt), 0)).where(where))
        completed_val = await self.db.scalar(select(func.coalesce(func.sum(EE.completed_value_bdt), 0)).where(where))

        # Completion rate
        completed_count = await self.db.scalar(
            select(func.count(EE.id)).where(and_(
                where,
                or_(EE.actual_completion_date.is_not(None), EE.completion_status.ilike("%complete%"), EE.status.ilike("%complete%"))
            ))
        )
        completion_rate = round((completed_count or 0) / max(total or 1, 1) * 100, 2)

        # On-time rate
        on_time_count = await self.db.scalar(
            select(func.count(EE.id)).where(and_(where, EE.completed_on_time.is_(True)))
        )
        on_time_rate = round((on_time_count or 0) / max(completed_count or 1, 1) * 100, 2)

        # Avg delay
        avg_delay = await self.db.scalar(select(func.coalesce(func.avg(EE.delay_days), 0)).where(and_(where, EE.delay_days > 0)))

        # Agencies worked with
        agencies_q = await self.db.execute(
            select(EE.agency_code, func.count(EE.id).label("cnt"))
            .where(and_(where, EE.agency_code.is_not(None)))
            .group_by(EE.agency_code)
            .order_by(func.count(EE.id).desc())
            .limit(10)
        )
        agencies = [{"agency_code": r[0], "contracts": int(r[1])} for r in agencies_q.all()]

        # Recent contracts
        recent_q = await self.db.execute(
            select(EE).where(where)
            .order_by(EE.contract_start_date.desc().nullslast())
            .limit(10)
        )
        recent = [self._row_to_dict(r) for r in recent_q.scalars().all()]

        # Value range
        min_v = await self.db.scalar(select(func.min(EE.contract_value_bdt)).where(where))
        max_v = await self.db.scalar(select(func.max(EE.contract_value_bdt)).where(where))

        return {
            "contractor_name": contractor_name,
            "total_contracts": int(total or 0),
            "total_value_bdt": round(float(total_val or 0), 2),
            "completed_value_bdt": round(float(completed_val or 0), 2),
            "completion_rate_pct": completion_rate,
            "on_time_rate_pct": on_time_rate,
            "avg_delay_days": round(float(avg_delay or 0), 1),
            "min_contract_value_bdt": round(float(min_v or 0), 2),
            "max_contract_value_bdt": round(float(max_v or 0), 2),
            "agencies": agencies,
            "recent_contracts": recent,
        }

    async def get_rate_quoted_analysis(
        self,
        agency: Optional[str] = None,
        contractor: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conditions = [EE.contract_value_bdt > 0, EE.completed_value_bdt > 0]
        if agency:
            conditions.append(or_(EE.agency_code.ilike(f"%{agency}%"), EE.agency_name.ilike(f"%{agency}%")))
        if contractor:
            conditions.append(EE.contractor_name.ilike(f"%{contractor}%"))
        if source:
            conditions.append(EE.data_source == source)
        where = and_(*conditions)

        records_q = await self.db.execute(
            select(
                EE.id, EE.package_no, EE.title, EE.agency_code, EE.agency_name,
                EE.contractor_name, EE.contract_value_bdt, EE.completed_value_bdt,
                EE.fiscal_year, EE.completion_status, EE.delay_days, EE.completed_on_time,
                EE.data_source,
            )
            .where(where)
            .order_by(EE.contract_value_bdt.desc())
            .offset(offset)
            .limit(limit)
        )
        records = []
        for r in records_q.all():
            award_val = float(r.contract_value_bdt or 0)
            completed_val = float(r.completed_value_bdt or 0)
            variance = round(completed_val - award_val, 2)
            variance_pct = round((variance / award_val) * 100, 2) if award_val else 0.0
            records.append({
                "id": str(r.id),
                "package_no": r.package_no,
                "title": r.title,
                "agency_code": r.agency_code,
                "agency_name": r.agency_name,
                "contractor_name": r.contractor_name,
                "award_value_bdt": award_val,
                "completed_value_bdt": completed_val,
                "variance_bdt": variance,
                "variance_pct": variance_pct,
                "fiscal_year": r.fiscal_year,
                "completion_status": r.completion_status,
                "delay_days": r.delay_days,
                "completed_on_time": r.completed_on_time,
                "data_source": r.data_source,
            })

        # Aggregations
        agg_q = await self.db.execute(
            select(
                func.count(EE.id),
                func.sum(EE.contract_value_bdt),
                func.sum(EE.completed_value_bdt),
                func.avg(
                    func.nullif(
                        (EE.completed_value_bdt - EE.contract_value_bdt) / func.nullif(EE.contract_value_bdt, 0),
                        0,
                    )
                ),
                func.count(func.nullif(EE.delay_days, 0)),
            ).where(where)
        )
        agg = agg_q.one()
        total_count = int(agg[0] or 0)
        total_award = float(agg[1] or 0)
        total_completed = float(agg[2] or 0)
        avg_variance_pct = round(float(agg[3] or 0) * 100, 2) if agg[3] else 0.0
        delayed_count = int(agg[4] or 0)

        # Per-agency breakdown
        agency_agg_q = await self.db.execute(
            select(
                EE.agency_code,
                func.count(EE.id),
                func.sum(EE.contract_value_bdt),
                func.sum(EE.completed_value_bdt),
            )
            .where(and_(where, EE.agency_code.is_not(None)))
            .group_by(EE.agency_code)
            .order_by(func.count(EE.id).desc())
        )
        by_agency = []
        for r in agency_agg_q.all():
            av = float(r[2] or 0)
            cv = float(r[3] or 0)
            by_agency.append({
                "agency_code": r[0],
                "record_count": int(r[1]),
                "total_award_bdt": round(av, 2),
                "total_completed_bdt": round(cv, 2),
                "variance_bdt": round(cv - av, 2),
                "variance_pct": round(((cv - av) / av) * 100, 2) if av else 0.0,
            })

        return {
            "records": records,
            "total_count": total_count,
            "total_award_bdt": round(total_award, 2),
            "total_completed_bdt": round(total_completed, 2),
            "total_variance_bdt": round(total_completed - total_award, 2),
            "avg_variance_pct": avg_variance_pct,
            "delayed_count": delayed_count,
            "by_agency": by_agency,
            "limit": limit,
            "offset": offset,
        }

    async def reconcile_execution_to_lifecycle(self) -> Dict[str, Any]:
        from app.models.intelligence import APPRecord, EContractExecution, ProcurementTender

        await self._ensure_eexperience_schema()
        exec_records = (
            await self.db.execute(select(EContractExecution))
        ).scalars().all()

        tender_map = {
            t.package_no: t
            for t in (await self.db.execute(select(ProcurementTender))).scalars().all()
            if t.package_no
        }

        # Build APP index: which procurement_tender_ids have an APP record
        app_tender_ids = {
            r.procurement_tender_id
            for r in (await self.db.execute(select(APPRecord))).scalars().all()
            if r.procurement_tender_id
        }

        matched = 0
        unmatched = 0
        app_matched = 0
        updated = 0
        matches = []
        for er in exec_records:
            pno = er.package_no or ""
            tender = tender_map.get(pno)
            if tender:
                matched += 1
                if er.procurement_tender_id != tender.id:
                    er.procurement_tender_id = tender.id
                    updated += 1
                has_app = tender.id in app_tender_ids
                if has_app:
                    app_matched += 1
                matches.append({
                    "execution_id": str(er.id),
                    "package_no": pno,
                    "tender_id": str(tender.id),
                    "contractor_name": er.contractor_name,
                    "agency_code": er.agency_code or tender.agency_code,
                    "contract_value_bdt": er.contract_value_bdt,
                    "completed_value_bdt": er.completed_value_bdt,
                    "completion_status": er.completion_status,
                    "delay_days": er.delay_days,
                    "completed_on_time": er.completed_on_time,
                    "has_app_record": has_app,
                })
            else:
                unmatched += 1

        if updated:
            await self.db.flush()

        return {
            "total_execution_records": len(exec_records),
            "matched_to_tender": matched,
            "matched_to_app": app_matched,
            "unmatched": unmatched,
            "records_updated": updated,
            "tender_match_rate_pct": round(matched / max(len(exec_records), 1) * 100, 1),
            "app_match_rate_pct": round(app_matched / max(len(exec_records), 1) * 100, 1),
            "sample_matches": matches[:20],
        }

    async def get_eexperience_timeline(
        self,
        source: Optional[str] = None,
        granularity: str = "month",
        year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conditions = []
        if source:
            conditions.append(EE.data_source == source)
        if year:
            conditions.append(EE.contract_start_date.startswith(str(year)))
        where = and_(*conditions) if conditions else text("1=1")

        if granularity == "year":
            date_part = func.left(EE.contract_start_date, 4)
        else:
            date_part = func.left(EE.contract_start_date, 7)

        result = await self.db.execute(
            select(
                date_part.label("period"),
                func.count(EE.id).label("count"),
                func.coalesce(func.sum(EE.contract_value_bdt), 0).label("total_value"),
                func.coalesce(func.sum(EE.completed_value_bdt), 0).label("completed_value"),
                func.avg(func.coalesce(EE.progress_pct, 0)).label("avg_progress"),
            )
            .where(and_(where, EE.contract_start_date.is_not(None)))
            .group_by(date_part)
            .order_by(date_part)
        )
        return [
            {
                "period": r[0],
                "contract_count": int(r[1]),
                "total_value_bdt": round(float(r[2]), 2),
                "completed_value_bdt": round(float(r[3]), 2),
                "avg_progress_pct": round(float(r[4] or 0), 2),
            }
            for r in result.all()
        ]

    async def get_agency_comparison(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conditions = [EE.agency_code.is_not(None)]
        if source:
            conditions.append(EE.data_source == source)
        where = and_(*conditions)

        result = await self.db.execute(
            select(
                EE.agency_code,
                func.count(EE.id).label("contract_count"),
                func.coalesce(func.sum(EE.contract_value_bdt), 0).label("total_value"),
                func.avg(func.coalesce(EE.progress_pct, 0)).label("avg_progress"),
                func.avg(func.coalesce(EE.delay_days, 0)).label("avg_delay"),
                func.count(func.distinct(EE.contractor_name)).label("unique_contractors"),
            )
            .where(where)
            .group_by(EE.agency_code)
            .order_by(func.count(EE.id).desc())
        )
        return [
            {
                "agency_code": r[0],
                "contract_count": int(r[1]),
                "total_value_bdt": round(float(r[2]), 2),
                "avg_progress_pct": round(float(r[3] or 0), 2),
                "avg_delay_days": round(float(r[4] or 0), 1),
                "unique_contractors": int(r[5]),
            }
            for r in result.all()
        ]

    async def list_eexperience_agencies(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conds = [EE.agency_code.is_not(None)]
        if source:
            conds.append(EE.data_source == source)
        where = and_(*conds)
        result = await self.db.execute(
            select(EE.agency_code, func.count(EE.id).label("count"), func.sum(EE.contract_value_bdt).label("total_value"))
            .where(where)
            .group_by(EE.agency_code)
            .order_by(func.count(EE.id).desc())
        )
        return [
            {"agency_code": row[0], "record_count": int(row[1]), "total_value_bdt": round(float(row[2] or 0), 2)}
            for row in result.all()
        ]

    async def get_execution_intelligence(self, agency: Optional[str] = None, source: Optional[str] = None, limit: int = 8) -> Dict[str, Any]:
        from app.models.intelligence import EContractExecution as EE

        await self._ensure_eexperience_schema()
        conditions = []
        if agency:
            conditions.append(or_(EE.agency_code.ilike(f"%{agency}%"), EE.agency_name.ilike(f"%{agency}%"), EE.pe_office.ilike(f"%{agency}%")))
        if source:
            conditions.append(EE.data_source == source)
        where_clause = and_(*conditions) if conditions else text("1=1")

        completion_rate_expr = func.avg(
            case(
                (or_(EE.actual_completion_date.is_not(None), EE.completion_status.ilike("%complete%"), EE.status.ilike("%complete%")), 1.0),
                else_=0.0,
            )
        )
        on_time_rate_expr = func.avg(
            case(
                (EE.completed_on_time.is_(True), 1.0),
                else_=0.0,
            )
        )
        avg_progress_expr = func.avg(func.coalesce(EE.progress_pct, 0))
        avg_delay_expr = func.avg(func.coalesce(EE.delay_days, 0))

        summary_row = (
            await self.db.execute(
                select(
                    func.count(EE.id),
                    func.coalesce(func.sum(EE.completed_value_bdt), 0),
                    completion_rate_expr,
                    on_time_rate_expr,
                    avg_progress_expr,
                    avg_delay_expr,
                ).where(where_clause)
            )
        ).one()

        status_rows = (
            await self.db.execute(
                select(
                    func.coalesce(EE.completion_status, EE.work_status, EE.status, "unknown").label("status_label"),
                    func.count(EE.id).label("count"),
                )
                .where(where_clause)
                .group_by("status_label")
                .order_by(func.count(EE.id).desc())
                .limit(6)
            )
        ).all()

        recent = await self.query_eexperience(agency=agency, source=source, limit=limit, offset=0)
        return {
            "summary": {
                "total_records": int(summary_row[0] or 0),
                "completed_value_bdt": round(float(summary_row[1] or 0), 2),
                "completion_rate_pct": round(float(summary_row[2] or 0) * 100, 2),
                "on_time_rate_pct": round(float(summary_row[3] or 0) * 100, 2),
                "avg_progress_pct": round(float(summary_row[4] or 0), 2),
                "avg_delay_days": round(float(summary_row[5] or 0), 2),
            },
            "status_breakdown": [
                {"status": row[0] or "unknown", "count": int(row[1] or 0)}
                for row in status_rows
            ],
            "recent_records": recent["records"],
        }

    # ── New dedicated tables: eexperience_completed & ecms_ongoing ──────────

    async def import_experience_to_dedicated_tables(self) -> Dict[str, int]:
        """Read all_completed.json + all_ongoing.json into dedicated tables."""
        from app.models.intelligence import EExperienceCompleted, ECMSongoing

        base = RUNTIME_DIR / "knowledge" / "eexperience_all"
        results = {"completed": 0, "ongoing": 0, "completed_skipped": 0, "ongoing_skipped": 0}

        # Existing keys for dedup
        existing_completed = {
            (r.package_no, r.contractor_name or "")
            for r in (await self.db.execute(select(EExperienceCompleted))).scalars().all()
        }
        existing_ongoing = {
            (r.package_no, r.contractor_name or "")
            for r in (await self.db.execute(select(ECMSongoing))).scalars().all()
        }

        for subdir, source, model_cls, existing_set, result_key in [
            ("completed", "EEXPERIENCE_ALL", EExperienceCompleted, existing_completed, "completed"),
            ("ongoing", "ECMS_ONGOING", ECMSongoing, existing_ongoing, "ongoing"),
        ]:
            fp = base / subdir / f"all_{subdir}.json"
            if not fp.exists():
                continue
            records = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(records, dict):
                records = records.get("records", records.get(subdir, []))
            imported = 0
            skipped = 0
            for item in records:
                if not isinstance(item, dict):
                    continue
                pno = self.normalize_package_no(
                    self._coalesce(item.get("package_no"), item.get("ref_no"), str(item.get("tender_id", "")))
                ) or f"EEXP-{item.get('tender_id', '')}"
                cname = (item.get("contractor_name") or item.get("winner") or "").strip()
                dedup_key = (pno, cname)
                if dedup_key in existing_set:
                    skipped += 1
                    continue
                existing_set.add(dedup_key)
                start_date = self._to_iso_date(item.get("contract_start_date"))
                end_date = self._to_iso_date(item.get("contract_end_date"))
                planned = self._to_iso_date(item.get("planned_completion_date"))
                actual = self._to_iso_date(item.get("actual_completion_date"))
                pub_date = self._to_iso_date(item.get("published_date"))
                awd_date = self._to_iso_date(item.get("award_date"))

                self.db.add(model_cls(
                    id=self._uuid(),
                    tender_id=str(item.get("tender_id", "")),
                    package_no=pno,
                    title=item.get("title", ""),
                    pe_office=item.get("pe_office", ""),
                    agency_code=item.get("agency_code") or "",
                    procurement_method=item.get("procurement_method", ""),
                    contractor_name=cname or None,
                    company_unique_id=item.get("company_unique_id", ""),
                    experience_certificate_no=self._coalesce(
                        item.get("experience_certificate_no"), item.get("completion_certificate_no")
                    ),
                    contract_value_bdt=self._safe_float(item.get("contract_value_bdt")),
                    completed_value_bdt=self._safe_float(item.get("completed_value_bdt")),
                    contract_start_date=start_date,
                    contract_end_date=end_date,
                    planned_completion_date=planned,
                    actual_completion_date=actual,
                    published_date=pub_date,
                    award_date=awd_date,
                    completion_status=self._coalesce(item.get("completion_status"), item.get("completion_state"), item.get("status")),
                    work_status=self._coalesce(item.get("work_status"), item.get("execution_status")),
                    status=item.get("status", ""),
                    progress_pct=self._safe_float(item.get("progress_pct")),
                    completed_on_time=self._safe_bool(item.get("completed_on_time")),
                    district=item.get("district", ""),
                    source_url=item.get("source_url", ""),
                    data_source=source,
                    raw_payload=item,
                ))
                imported += 1
            results[result_key] = imported
            results[f"{result_key}_skipped"] = skipped

        await self.db.flush()
        return results

    async def import_per_agency_experience(self) -> Dict[str, Any]:
        """Import per-agency experience.json files into dedicated tables.
        
        These files have agency_code populated (unlike the flat bulk crawl files).
        Upserts by tender_id: fills in empty agency_code for matching records,
        inserts new records for unmatched ones.
        """
        from app.models.intelligence import EExperienceCompleted, ECMSongoing

        base = RUNTIME_DIR / "knowledge" / "eexperience"
        all_exp_json = base / "all_experience.json"

        # Collect existing tender_ids for quick lookup
        existing_completed_ids = set()
        r = await self.db.execute(select(EExperienceCompleted.tender_id))
        for row in r:
            tid = row[0]
            if tid:
                existing_completed_ids.add(tid)

        existing_ongoing_ids = set()
        r = await self.db.execute(select(ECMSongoing.tender_id))
        for row in r:
            tid = row[0]
            if tid:
                existing_ongoing_ids.add(tid)

        # Determine whether to use all_experience.json (already aggregated)
        # or per-agency files. all_experience.json is a 1245-record subset
        # of the per-agency files (all its IDs exist in per-agency files).
        # We'll use per-agency files for completeness.
        results = {
            "completed_updated": 0,
            "completed_inserted": 0,
            "ongoing_updated": 0,
            "ongoing_inserted": 0,
            "errors": 0,
            "total_per_agency_records": 0,
        }

        agency_dirs = sorted([
            d for d in base.iterdir()
            if d.is_dir() and (d / "experience.json").exists()
        ])

        for agency_dir in agency_dirs:
            fp = agency_dir / "experience.json"
            try:
                records = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                results["errors"] += 1
                continue
            if not isinstance(records, list):
                continue

            agency_code_from_dir = agency_dir.name
            for item in records:
                if not isinstance(item, dict):
                    continue
                results["total_per_agency_records"] += 1
                status = item.get("status", "").lower()
                tender_id = str(item.get("tender_id", ""))
                pno = self.normalize_package_no(
                    self._coalesce(item.get("package_no"), item.get("ref_no"), tender_id)
                ) or f"EEXP-{tender_id}"
                cname = (item.get("contractor_name") or item.get("winner") or "").strip()
                agency_code = item.get("agency_code") or agency_code_from_dir or ""

                if status == "ongoing":
                    model_cls = ECMSongoing
                    existing_ids = existing_ongoing_ids
                    source = "ECMS_PER_AGENCY"
                    rkey_updated = "ongoing_updated"
                    rkey_inserted = "ongoing_inserted"
                else:
                    model_cls = EExperienceCompleted
                    existing_ids = existing_completed_ids
                    source = "EEXPERIENCE_PER_AGENCY"
                    rkey_updated = "completed_updated"
                    rkey_inserted = "completed_inserted"

                if tender_id and tender_id in existing_ids:
                    # Update agency_code if empty
                    await self.db.execute(
                        text(
                            f"UPDATE {model_cls.__tablename__} "
                            "SET agency_code = :agency "
                            "WHERE tender_id = :tid "
                            "AND (agency_code IS NULL OR agency_code = '')"
                        ).bindparams(agency=agency_code, tid=tender_id)
                    )
                    if model_cls == EExperienceCompleted:
                        existing_completed_ids.add(tender_id)
                    else:
                        existing_ongoing_ids.add(tender_id)
                    results[rkey_updated] += 1
                else:
                    # Insert new record
                    start_date = self._to_iso_date(item.get("contract_start_date"))
                    end_date = self._to_iso_date(item.get("contract_end_date"))
                    planned = self._to_iso_date(item.get("planned_completion_date"))
                    actual = self._to_iso_date(item.get("actual_completion_date"))
                    pub_date = self._to_iso_date(item.get("published_date"))
                    awd_date = self._to_iso_date(item.get("award_date"))

                    rec = model_cls(
                        id=self._uuid(),
                        tender_id=tender_id,
                        package_no=pno,
                        title=item.get("title", ""),
                        pe_office=item.get("pe_office", ""),
                        agency_code=agency_code,
                        procurement_method=item.get("procurement_method", ""),
                        contractor_name=cname or None,
                        company_unique_id=item.get("company_unique_id", ""),
                        experience_certificate_no=self._coalesce(
                            item.get("experience_certificate_no"), item.get("completion_certificate_no")
                        ),
                        contract_value_bdt=self._safe_float(item.get("contract_value_bdt")),
                        completed_value_bdt=self._safe_float(item.get("completed_value_bdt")),
                        contract_start_date=start_date,
                        contract_end_date=end_date,
                        planned_completion_date=planned,
                        actual_completion_date=actual,
                        published_date=pub_date,
                        award_date=awd_date,
                        completion_status=self._coalesce(
                            item.get("completion_status"), item.get("completion_state"), item.get("status")
                        ),
                        work_status=self._coalesce(item.get("work_status"), item.get("execution_status")),
                        status=item.get("status", ""),
                        progress_pct=self._safe_float(item.get("progress_pct")),
                        completed_on_time=self._safe_bool(item.get("completed_on_time")),
                        district=item.get("district", ""),
                        source_url=item.get("source_url", ""),
                        data_source=source,
                        raw_payload=item,
                    )
                    self.db.add(rec)
                    existing_ids.add(tender_id)
                    results[rkey_inserted] += 1

        await self.db.flush()
        return results

    async def query_completed_executions(
        self,
        agency: Optional[str] = None,
        contractor: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        from app.models.intelligence import EExperienceCompleted as M

        where = self._build_execution_where(M, agency, contractor, date_from, date_to)
        total = await self.db.scalar(select(func.count(M.id)).where(where))
        rows = (
            await self.db.execute(
                select(M).where(where).order_by(M.contract_value_bdt.desc()).offset(offset).limit(limit)
            )
        ).scalars().all()
        return {
            "total": int(total or 0),
            "records": [self._row_to_dict(r) for r in rows],
            "limit": limit,
            "offset": offset,
        }

    async def query_ongoing_executions(
        self,
        agency: Optional[str] = None,
        contractor: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        from app.models.intelligence import ECMSongoing as M

        where = self._build_execution_where(M, agency, contractor, date_from, date_to)
        total = await self.db.scalar(select(func.count(M.id)).where(where))
        rows = (
            await self.db.execute(
                select(M).where(where).order_by(M.contract_value_bdt.desc()).offset(offset).limit(limit)
            )
        ).scalars().all()
        return {
            "total": int(total or 0),
            "records": [self._row_to_dict(r) for r in rows],
            "limit": limit,
            "offset": offset,
        }

    def _build_execution_where(
        self,
        model,
        agency: Optional[str] = None,
        contractor: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        conds = []
        if agency:
            conds.append(or_(model.agency_code.ilike(f"%{agency}%"), model.pe_office.ilike(f"%{agency}%")))
        if contractor:
            conds.append(model.contractor_name.ilike(f"%{contractor}%"))
        if date_from:
            conds.append(model.contract_start_date >= date_from)
        if date_to:
            conds.append(model.contract_start_date <= date_to)
        return and_(*conds) if conds else text("1=1")
