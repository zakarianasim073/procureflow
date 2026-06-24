"""
PPR 2025 Contractor DNA Builder — Offline ETL

Auto-discovers ALL data sources under backend/runtime/:
  - APP corpus:  knowledge/app/*.json + data_intel/tenders_*.json
  - Award corpus: knowledge/awards/*.json + data_intel/awards_*.json

Maps planned procurement (APP) → awarded contracts → contractor profiles.

Usage:
    python tools/build_contractor_dna.py --rebuild
    python tools/build_contractor_dna.py --agency LGED    # filter single agency
    python tools/build_contractor_dna.py --rebuild --dry  # preview only
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("contractor_dna_etl")


# ── paths ──────────────────────────────────────────────────────────────

BACKEND = Path(__file__).resolve().parent.parent / "backend"
RUNTIME = BACKEND / "runtime"
KNOWLEDGE = RUNTIME / "knowledge"
DATA_INTEL = RUNTIME / "data_intel"


# ── helpers ────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "_", s)
    return s.strip("_") or "unknown"


def normalize_title(raw: str) -> str:
    s = raw.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_agency_id(
    procuring_entity: str = "",
    office: str = "",
) -> str:
    """Guess a short agency code from procuring_entity and/or office fields."""
    text = (procuring_entity + " " + office).lower()
    if "bwdb" in text or "bangladesh water development" in text or ("ministry of water resources" in text and "bwdb" in text):
        return "BWDB"
    if "lged" in text or "local government engineering" in text:
        return "LGED"
    if "pwd" in text or "public works department" in text:
        return "PWD"
    if "railway" in text:
        return "RAILWAY"
    if "rural electrification" in text or "rebs" in text:
        return "REB"
    if "electricity" in text or "power" in text or "egcb" in text or "bpd" in text or "pgcb" in text:
        return "POWER"
    if "education" in text or "hed" in text:
        return "EDUCATION"
    if "road transport" in text or "rhd" in text:
        return "RHD"
    if "health" in text:
        return "HEALTH"
    if "housing" in text:
        return "HOUSING"
    if "industri" in text or "bcic" in text:
        return "INDUSTRY"
    if "home" in text or "prison" in text:
        return "HOME"
    if "water resources" in text:
        return "BWDB"  # Ministry of Water Resources projects (often BWDB/other water bodies)
    return "OTHER"


def normalize_tender_id(raw: str) -> str:
    """Strip APP- prefix etc. → bare numeric ID."""
    return re.sub(r"(?i)app[-_]?", "", str(raw)).strip()


# ── source discovery ───────────────────────────────────────────────────

def json_records(path: Path) -> List[Dict]:
    """Load a JSON file that is either a list or has records/data key."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"  Cannot parse {path.name}: {e}")
        return []
    if isinstance(data, list):
        return data
    for key in ("records", "data", "tenders"):
        if isinstance(data.get(key), list):
            return data[key]
    return [data]


def discover_app_sources(agency: Optional[str] = None) -> List[Dict]:
    """
    Build APP corpus from:
      1. knowledge/app/*.json
      2. data_intel/tenders_all_*.json  (latest snapshot)
      3. data_intel/tenders_live_*.json (latest snapshot)
      4. data_intel/bwdb_all_tenders.json
    """
    records: List[Dict] = []
    seen: Set[str] = set()

    def _add(batch, source_label: str):
        for r in batch:
            if not isinstance(r, dict):
                continue
            tid = normalize_tender_id(r.get("tender_id", "") or "")
            if tid:
                key = f"APP|{tid}"
                if key in seen:
                    continue
                seen.add(key)
            # Normalise into APP schema
            rec = {
                "tender_id": tid,
                "title": r.get("title", ""),
                "package_no": r.get("package_no") or r.get("package_no") or tid,
                "estimated_amount_bdt": float(r.get("estimated_amount_bdt") or r.get("estimated_value_bdt", 0) or 0),
                "procurement_type": r.get("procurement_type") or r.get("status", "Works"),
                "procuring_entity": r.get("procuring_entity", ""),
                "deadline": r.get("deadline", ""),
                "agency_target": extract_agency_id(
                    procuring_entity=r.get("procuring_entity", ""),
                    office=r.get("office", ""),
                ),
                "_source": source_label,
            }
            if agency and rec["agency_target"].upper() != agency.upper():
                continue
            records.append(rec)

    # 1. knowledge/app/
    for fp in sorted((KNOWLEDGE / "app").glob("*.json")):
        _add(json_records(fp), f"app/{fp.name}")

    # 2. tenders_all_* → latest only
    all_files = sorted((DATA_INTEL).glob("tenders_all_*.json"))
    if all_files:
        _add(json_records(all_files[-1]), f"data_intel/{all_files[-1].name}")

    # 3. tenders_live_* → latest
    live_files = sorted((DATA_INTEL).glob("tenders_live_*.json"))
    if live_files:
        _add(json_records(live_files[-1]), f"data_intel/{live_files[-1].name}")

    # 4. knowledge/tenders/ (live tender data, complements APP)
    tenders_dir = KNOWLEDGE / "tenders"
    if tenders_dir.exists():
        for fp in sorted(tenders_dir.glob("*.json")):
            _add(json_records(fp), f"tenders/{fp.name}")

    # 5. bwdb_all_tenders.json (complements app/BWDB.json)
    bwdb_fp = DATA_INTEL / "bwdb_all_tenders.json"
    if bwdb_fp.exists():
        _add(json_records(bwdb_fp), "data_intel/bwdb_all_tenders.json")

    logger.info(f"APP corpus: {len(records)} records from {len(seen)} unique IDs across {len(records)}")
    return records


def discover_award_sources(agency: Optional[str] = None) -> List[Dict]:
    """
    Build deduplicated award corpus from:
      1. knowledge/awards_batch/*.json  (47,904 records, primary source)
      2. data_intel/awards_*.json       (secondary, smaller set)
      3. knowledge/awards/*.json        (copies, fallback)
    """
    records: List[Dict] = []
    seen: Set[str] = set()

    def _add(batch, source_label: str):
        for r in batch:
            if not isinstance(r, dict):
                continue
            tid = normalize_tender_id(r.get("tender_id", "") or "")
            winner = (r.get("winner") or "").strip()
            if not tid or not winner or winner == "Unknown":
                continue
            key = f"AWD|{tid}|{winner}"
            if key in seen:
                continue
            seen.add(key)
            rec = {
                "tender_id": tid,
                "winner": winner,
                "amount_bdt": float(r.get("amount_bdt", 0) or 0),
                "title": r.get("title", ""),
                "procuring_entity": r.get("procuring_entity", ""),
                "office": r.get("office", ""),
                "location": r.get("location", ""),
                "award_date": r.get("award_date", ""),
                "source": r.get("source", source_label),
                "agency_target": extract_agency_id(
                    procuring_entity=r.get("procuring_entity", ""),
                    office=r.get("office", ""),
                ),
            }
            if agency and rec["agency_target"].upper() != agency.upper():
                continue
            records.append(rec)

    # 1. knowledge/awards_batch/ (49 files, 47,904 records across agencies)
    ab = KNOWLEDGE / "awards_batch"
    if ab.exists():
        for fp in sorted(ab.glob("*.json")):
            _add(json_records(fp), f"awards_batch/{fp.name}")

    # 2. data_intel/awards_* → all files deduped across them
    for fp in sorted((DATA_INTEL).glob("awards_*.json")):
        _add(json_records(fp), f"data_intel/{fp.name}")

    # 3. knowledge/awards/ (individual award files, may overlap)
    for fp in sorted((KNOWLEDGE / "awards").glob("*.json")):
        _add(json_records(fp), f"knowledge/awards/{fp.name}")

    logger.info(f"Award corpus: {len(records)} records from {len(seen)} unique tender+winner combos")
    return records


# ── matching ───────────────────────────────────────────────────────────

def match_app_to_awards(
    app_records: List[Dict],
    award_records: List[Dict],
) -> List[Dict]:
    """
    Join APP ↔ awards by:
      1. Exact tender_id match (after normalizing prefixes)
      2. Fuzzy title token overlap (≥0.35)
    """
    # Index APP by tender_id
    app_by_tid: Dict[str, Dict] = {}
    app_by_title_tokens: Dict = {}
    for app in app_records:
        tid = app.get("tender_id", "")
        if tid:
            app_by_tid[tid] = app
        nt = normalize_title(app.get("title", ""))
        tokens = frozenset(nt.split())
        app_by_title_tokens.setdefault(tokens, []).append(app)

    matches: List[Dict] = []
    matched_ids: Set[str] = set()

    for award in award_records:
        aid = award.get("tender_id", "")
        best_app = None
        match_type = "none"

        # Strategy 1: exact tender_id
        if aid and aid in app_by_tid:
            best_app = app_by_tid[aid]
            match_type = "tid_exact"

        # Strategy 2: fuzzy title
        if best_app is None:
            award_nt = normalize_title(award.get("title", ""))
            award_tokens = set(award_nt.split())
            best_score = 0.0
            for app_tokens, app_list in app_by_title_tokens.items():
                overlap = award_tokens & app_tokens
                union = award_tokens | app_tokens
                if not union:
                    continue
                score = len(overlap) / len(union)
                if score > best_score and score >= 0.35:
                    best_score = score
                    best_app = app_list[0]
                    match_type = f"title_fuzzy_{best_score:.2f}"

        # Compute amounts
        estimated = best_app.get("estimated_amount_bdt", 0) if best_app else 0
        award_amt = award.get("amount_bdt", 0)
        discount = round((1 - award_amt / estimated) * 100, 2) if (estimated > 0 and award_amt > 0) else 0.0

        # Year from award_date
        year = 0
        ad = award.get("award_date", "")
        m = re.search(r"(\d{4})", ad)
        if m:
            year = int(m.group(1))

        matches.append({
            "award_tender_id": aid,
            "app_tender_id": best_app.get("tender_id", "") if best_app else "",
            "app_package_no": best_app.get("package_no", "") if best_app else "",
            "title_app": best_app.get("title", "")[:120] if best_app else "",
            "title_award": award.get("title", "")[:120],
            "estimated_amount_bdt": estimated,
            "award_amount_bdt": award_amt,
            "discount_pct": discount,
            "winner": award["winner"],
            "agency": award["agency_target"],
            "office": award.get("office", ""),
            "location": award.get("location", ""),
            "procuring_entity": award.get("procuring_entity", ""),
            "year": year,
            "award_source": award.get("source", ""),
            "procurement_nature": (best_app.get("procurement_type", "Works") if best_app else "Works"),
            "match_type": match_type,
        })

        if best_app:
            matched_ids.add(aid)

    matched_ct = sum(1 for m in matches if m["match_type"] != "none")
    standalone = sum(1 for m in matches if m["match_type"] == "none")
    logger.info(f"Matched {matched_ct} APP→award + {standalone} standalone awards = {len(matches)} total")
    return matches


# ── aggregation ────────────────────────────────────────────────────────

def aggregate_contractor_profiles(matches: List[Dict]) -> Dict[str, Dict]:
    """Group matches by winner → build contractor DNA profile."""
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for m in matches:
        groups[m["winner"]].append(m)

    profiles: Dict[str, Dict] = {}

    for name, entries in groups.items():
        wins = len(entries)
        amounts = [e["award_amount_bdt"] for e in entries if e["award_amount_bdt"]]
        discounts = [e["discount_pct"] for e in entries if e["match_type"] != "none" and (e["discount_pct"] != 0 or e["app_tender_id"])]
        years = sorted(set(e["year"] for e in entries if e["year"] > 0))
        total_amount = sum(amounts)
        avg_amount = round(total_amount / len(amounts), 2) if amounts else 0
        avg_discount = round(sum(discounts) / len(discounts), 2) if discounts else 0

        # Per-agency breakdown
        ag_groups: Dict[str, List[Dict]] = defaultdict(list)
        for e in entries:
            ag_groups[e["agency"]].append(e)

        agencies: Dict[str, Any] = {}
        for ag, ag_entries in ag_groups.items():
            ag_amts = [e["award_amount_bdt"] for e in ag_entries if e["award_amount_bdt"]]
            ag_ys = sorted(set(e["year"] for e in ag_entries if e["year"] > 0))
            recent = sorted(ag_entries, key=lambda x: x["year"], reverse=True)[:20]
            agencies[ag] = {
                "wins": len(ag_entries),
                "total_amount": round(sum(ag_amts), 2),
                "avg_amount": round(sum(ag_amts) / len(ag_amts), 2) if ag_amts else 0,
                "first_award": str(min(ag_ys)) if ag_ys else "",
                "last_award": str(max(ag_ys)) if ag_ys else "",
                "tenders": [
                    {
                        "tender_id": r["award_tender_id"],
                        "title": r["title_award"],
                        "amount": r["award_amount_bdt"],
                        "year": r["year"],
                        "discount": r["discount_pct"],
                    }
                    for r in recent
                ],
            }

        # Procurement type breakdown
        ptype_count: Dict[str, int] = defaultdict(int)
        for e in entries:
            ptype_count[e.get("procurement_nature", "Works")] += 1

        top_agency = max(agencies, key=lambda a: agencies[a]["wins"]) if agencies else "NONE"

        profiles[name] = {
            "contractor_name": name,
            "slug": slugify(name),
            "total_wins": wins,
            "total_amount_bdt": round(total_amount, 2),
            "avg_amount_bdt": avg_amount,
            "avg_discount_percent": avg_discount,
            "years_active": [min(years), max(years)] if years else [],
            "procurement_type_breakdown": dict(ptype_count),
            "agencies": agencies,
            "top_agency": top_agency,
            "top_agency_wins": agencies[top_agency]["wins"] if top_agency in agencies else wins,
            "win_probability": (
                {ag: round(agencies[ag]["wins"] / wins, 2) for ag in agencies}
                if wins > 0 else {}
            ),
            "_domain": "contractor_dna",
        }

    logger.info(f"Aggregated {len(profiles)} contractor profiles")
    return profiles


# ── output ─────────────────────────────────────────────────────────────

def write_output(profiles: Dict[str, Dict], rebuild: bool = False) -> None:
    out = KNOWLEDGE / "contractordna"
    out.mkdir(parents=True, exist_ok=True)

    if rebuild:
        for f in out.glob("*.json"):
            f.unlink()
        logger.info(f"Cleared {out}")

    for name, profile in profiles.items():
        slug = profile["slug"]
        (out / f"{slug}.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )

    summary = sorted(
        [
            {
                "slug": p["slug"],
                "contractor_name": p["contractor_name"],
                "total_wins": p["total_wins"],
                "total_amount_bdt": p["total_amount_bdt"],
                "avg_discount_percent": p["avg_discount_percent"],
                "years_active": p["years_active"],
                "top_agency": p["top_agency"],
                "top_agency_wins": p["top_agency_wins"],
            }
            for p in profiles.values()
        ],
        key=lambda x: x["total_wins"],
        reverse=True,
    )

    (out / "_index.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "total_contractors": len(profiles),
                "contractors": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info(f"Wrote {len(profiles)} profiles + _index.json to {out}")


# ── main ───────────────────────────────────────────────────────────────

def main(agency: Optional[str] = None, rebuild: bool = False, dry: bool = False) -> None:
    logger.info(f"Knowledge root: {KNOWLEDGE}")
    if agency:
        logger.info(f"Filter: agency={agency}")

    # Step 1 — APP corpus
    app_recs = discover_app_sources(agency=agency)
    logger.info(f"APP corpus: {len(app_recs)} records")

    # Step 2 — Award corpus
    award_recs = discover_award_sources(agency=agency)
    logger.info(f"Award corpus: {len(award_recs)} records")

    if not app_recs and not award_recs:
        logger.error("No data found in any source. Check backend/runtime/ contents.")
        sys.exit(1)

    if dry:
        logger.info("DRY RUN — skipping matching, aggregation, output")
        return

    # Step 3 — Match
    logger.info("Matching APP ↔ awards …")
    matches = match_app_to_awards(app_recs, award_recs)

    # Step 4 — Aggregate
    logger.info("Aggregating contractor profiles …")
    profiles = aggregate_contractor_profiles(matches)

    # Step 5 — Write
    write_output(profiles, rebuild=rebuild)

    # Summary
    matched = sum(1 for m in matches if m["match_type"] != "none")
    standalone = len(matches) - matched
    logger.info(
        f"Done: {len(profiles)} contractors, "
        f"{matched} matched awards, "
        f"{standalone} standalone awards"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build PPR 2025 Contractor DNA database")
    parser.add_argument("--agency", default=None, help="Filter single agency (default: all)")
    parser.add_argument("--rebuild", action="store_true", help="Force overwrite existing files")
    parser.add_argument("--dry", action="store_true", help="Preview data discovery only")
    args = parser.parse_args()
    main(agency=args.agency, rebuild=args.rebuild, dry=args.dry)
