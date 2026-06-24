"""
Load cached eContracts data & run matching against APP data.
Saves: all_matches.json, contractor_dna.json, npp_trends.json, rate_analytics.json
"""
import json, logging, re, sys
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("match")

KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_intelligence import (
    extract_agency_id, normalize_package_no, normalize_tender_id,
    extract_pkg_from_title, build_contractor_dna,
    build_agency_npp_trends, build_rate_analysis, write_output
)

econtracts_dir = KNOWLEDGE / "econtracts_raw"
all_awards = []
seen_keys = set()

for fp in sorted(econtracts_dir.glob("page_*.json")):
    records = json.loads(fp.read_text(encoding="utf-8"))
    for r in records:
        key = f"{r.get('tender_id','')}|{r.get('winner','')}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        pe = r.get("procuring_entity", "")
        r["agency_target"] = extract_agency_id(pe)
        r["award_amount_bdt"] = r.get("amount_bdt", 0)
        r["amount_bdt"] = r.get("amount_bdt", 0)
        all_awards.append(r)

logger.info(f"Loaded {len(all_awards)} unique eContracts awards")

app_dir = KNOWLEDGE / "app"
app_records = []
seen_tids = set()

for fp in sorted(app_dir.glob("*.json")):
    if fp.name.startswith("offices_") or fp.name == "dept_tree.json":
        continue
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    for r in records:
        if not isinstance(r, dict):
            continue
        tid = normalize_tender_id(r.get("tender_id", "") or "")
        if tid and tid in seen_tids:
            continue
        if tid:
            seen_tids.add(tid)
        app_records.append(r)

logger.info(f"Loaded {len(app_records)} APP records")

# Build indexes: ONLY by package_no
app_by_pkg = {}
app_by_norm_pkg = {}
app_by_tid = {}

for app in app_records:
    raw_pkg = (app.get("package_no") or "").strip()
    if raw_pkg:
        app_by_pkg[raw_pkg.upper()] = app
    norm_pkg = normalize_package_no(raw_pkg)
    if norm_pkg and norm_pkg != raw_pkg.upper():
        app_by_norm_pkg.setdefault(norm_pkg, []).append(app)
    title_pkg = extract_pkg_from_title(app.get("title", "")).upper()
    if title_pkg and title_pkg not in app_by_pkg:
        app_by_pkg[title_pkg] = app
    tid = normalize_tender_id(app.get("tender_id", "") or "")
    if tid:
        app_by_tid[tid] = app

logger.info(f"APP indexes: {len(app_by_pkg)} pkg | {len(app_by_norm_pkg)} norm | {len(app_by_tid)} tid")

# ── Matching (PACKAGE_NO ONLY) ──
matches = []
match_counts = defaultdict(int)

for award in all_awards:
    aid = award["tender_id"]
    awinner = award.get("winner", "")
    award_title = award.get("title", "")
    award_pkg_raw = (award.get("package_no") or "").strip().upper()
    award_agency = award.get("agency_target", "OTHER")

    best_app = None
    match_strategy = "none"

    if not award_pkg_raw:
        continue

    if award_pkg_raw in app_by_pkg:
        best_app = app_by_pkg[award_pkg_raw]
        match_strategy = "package_exact"
    else:
        norm_pkg = normalize_package_no(award_pkg_raw)
        if norm_pkg and norm_pkg in app_by_norm_pkg:
            candidates = app_by_norm_pkg[norm_pkg]
            if candidates:
                best_app = candidates[0]
                match_strategy = "package_normalized"
        if not best_app:
            title_pkg = extract_pkg_from_title(award_title).upper()
            if title_pkg and title_pkg in app_by_pkg:
                best_app = app_by_pkg[title_pkg]
                match_strategy = "package_title_fallback"
        if not best_app:
            norm_aid = normalize_tender_id(aid)
            if norm_aid and norm_aid in app_by_tid:
                best_app = app_by_tid[norm_aid]
                match_strategy = "tender_id_exact"

    estimated = float(best_app.get("estimated_amount_bdt", 0) or 0) if best_app else 0
    award_amt = float(award.get("award_amount_bdt", award.get("amount_bdt", 0)) or 0)

    npp = 0.0
    discount_pct = 0.0
    if estimated > 0 and award_amt > 0:
        npp = round((estimated - award_amt) / estimated, 6)
        discount_pct = round(npp * 100, 2)

    year = 0
    ad = award.get("award_date", "")
    m = re.search(r"(\d{4})", ad)
    if m:
        year = int(m.group(1))

    matches.append({
        "tender_id": aid,
        "package_no_award": award_pkg_raw,
        "package_no_app": best_app.get("package_no", "") if best_app else "",
        "winner": awinner,
        "award_amount_bdt": award_amt,
        "estimated_amount_bdt": estimated,
        "npp": npp,
        "discount_pct": discount_pct,
        "title": award_title[:300] if award_title else "",
        "agency": award_agency,
        "procuring_entity": award.get("procuring_entity", ""),
        "award_date": ad,
        "year": year,
        "match_strategy": match_strategy,
        "procurement_nature": award.get("procurement_nature", "Works"),
        "procurement_method": award.get("procurement_method", ""),
    })
    match_counts[match_strategy] += 1

logger.info(f"Match results: {dict(match_counts)}")
total_real = match_counts.get("package_exact", 0) + match_counts.get("package_normalized", 0)
total_tid = match_counts.get("tender_id_exact", 0)
logger.info(f"Real package matches: {total_real} | Tender ID matches: {total_tid} | Total: {len(matches)}")

# ── Synthetic estimates ──
agency_npp = defaultdict(list)
for m in matches:
    if m["npp"] != 0:
        agency_npp[m["agency"]].append(m["npp"])
agency_avg_npp = {ag: sum(v)/len(v) for ag, v in agency_npp.items()}

synthetic_count = 0
for m in matches:
    if m["match_strategy"] not in ("none",):
        continue
    if m["estimated_amount_bdt"] > 0:
        continue
    amt = m["award_amount_bdt"]
    if amt <= 0:
        continue
    avg_npp = agency_avg_npp.get(m["agency"], 0.074)
    if abs(avg_npp) > 0.2:
        avg_npp = 0.074
    estimated = round(amt / (1 - avg_npp), 2)
    m["estimated_amount_bdt"] = estimated
    m["npp"] = round((estimated - amt) / estimated, 6)
    m["discount_pct"] = round(m["npp"] * 100, 2)
    m["match_strategy"] = "synthetic"
    synthetic_count += 1

matched_final = sum(1 for m in matches if m["match_strategy"] not in ("none", "synthetic"))
logger.info(f"Final: {matched_final} real + {synthetic_count} synthetic = {len(matches)} total")

profiles = build_contractor_dna(matches)
npp_trends = build_agency_npp_trends(matches)
rate_analysis = build_rate_analysis(matches)
write_output(profiles, npp_trends, rate_analysis, matches, rebuild=True)

logger.info(f"=== DONE: {len(profiles)} contractors, {len(matches)} awards ===")
