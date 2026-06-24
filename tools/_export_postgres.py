"""
ETL: Export JSON knowledge base → PostgreSQL INSERT SQL.
Generates backend/database/seed.sql for direct psql import.
"""
from __future__ import annotations

import json, logging, re
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("export_pg")

KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"
OUTPUT = Path(__file__).resolve().parent.parent / "backend" / "database" / "seed.sql"

BANGLADESH_DISTRICTS = [
    "bagerhat","bandarban","barguna","barisal","bhola","bogra","brahmanbaria",
    "chandpur","chapainawabganj","chittagong","chuadanga","comilla","cox's bazar",
    "dhaka","dinajpur","faridpur","feni","gaibandha","gazipur","gopalganj",
    "habiganj","jamalpur","jessore","jhalokati","jhenaidah","joypurhat",
    "khagrachhari","khulna","kishoreganj","kurigram","kushtia","lakshmipur",
    "lalmonirhat","madaripur","magura","manikganj","maulvibazar","meherpur",
    "munshiganj","mymensingh","naogaon","narail","narayanganj","narsingdi",
    "natore","netrokona","nilphamari","noakhali","pabna","panchagarh",
    "patuakhali","pirojpur","rajbari","rajshahi","rangamati","rangpur",
    "sathkhira","shariatpur","sherpur","sirajganj","sunamganj","sylhet",
    "tangail","thakurgaon",
]

BANGLADESH_DIVISIONS = {
    "dhaka": ["dhaka","faridpur","gazipur","gopalganj","kishoreganj","madaripur","manikganj","munshiganj","narayanganj","narsingdi","rajbari","shariatpur","tangail"],
    "chittagong": ["bandarban","brahmanbaria","chandpur","chittagong","comilla","cox's bazar","feni","khagrachhari","lakshmipur","noakhali","rangamati"],
    "rajshahi": ["bogra","chapainawabganj","joypurhat","naogaon","natore","pabna","rajshahi","sirajganj"],
    "khulna": ["bagerhat","chuadanga","jessore","jhenaidah","khulna","kushtia","magura","meherpur","narail","sathkhira"],
    "barisal": ["barguna","barisal","bhola","jhalokati","patuakhali","pirojpur"],
    "sylhet": ["habiganj","maulvibazar","sunamganj","sylhet"],
    "rangpur": ["dinajpur","gaibandha","kurigram","lalmonirhat","nilphamari","panchagarh","rangpur","thakurgaon"],
    "mymensingh": ["jamalpur","mymensingh","netrokona","sherpur"],
}

BANGLADESH_DIVISION_NAMES = list(BANGLADESH_DIVISIONS.keys())

def detect_district(text: str) -> str:
    t = re.sub(r'[^a-zA-Z\s]', ' ', text).lower()
    for d in BANGLADESH_DISTRICTS:
        if d in t:
            return d.title()
    return ""

def fmt(val):
    if val is None:
        return "NULL"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    return "'" + str(val).replace("'", "''") + "'"

def fmt_date(val):
    if not val:
        return "NULL"
    val = str(val).strip()
    for fmt in ["%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"]:
        try:
            return "'" + datetime.strptime(val, fmt).strftime("%Y-%m-%d") + "'"
        except Exception:
            pass
    return "NULL"

def esc(text):
    if not text:
        return ""
    return str(text).replace("'", "''")


class SQLBuilder:
    def __init__(self):
        self.lines = []
        self._ensure_header()

    def _ensure_header(self):
        self.lines.append("-- ProcureFlow Seed Data")
        self.lines.append("-- Generated: %s" % datetime.now().isoformat())
        self.lines.append("--")
        self.lines.append("BEGIN;")
        self.lines.append("")

    def add(self, sql):
        self.lines.append(sql)

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines), encoding="utf-8")
        logger.info("Wrote %s (%d lines)", path, len(self.lines))

sql = SQLBuilder()


# ── Step 1: Agencies ───────────────────────────────────────────────────

AGENCY_CONFIG = {
    "BWDB": {"name": "Bangladesh Water Development Board", "ministry": "Ministry of Water Resources", "keyword": "BWDB"},
    "LGED": {"name": "Local Government Engineering Department", "ministry": "Ministry of Local Government, Rural Development and Co-operatives", "keyword": "LGED"},
    "PWD": {"name": "Public Works Department", "ministry": "Ministry of Housing and Public Works", "keyword": "PWD"},
    "RHD": {"name": "Roads and Highways Department", "ministry": "Ministry of Road Transport and Bridges", "keyword": "RHD"},
    "BBA": {"name": "Bangladesh Bridge Authority", "ministry": "Ministry of Road Transport and Bridges", "keyword": "BBA"},
    "EDUCATION": {"name": "Education Engineering Directorate", "ministry": "Ministry of Education", "keyword": "Education Engineering"},
    "BIWTA": {"name": "Bangladesh Inland Water Transport Authority", "ministry": "Ministry of Shipping", "keyword": "BIWTA"},
    "BADC": {"name": "Bangladesh Agricultural Development Corporation", "ministry": "Ministry of Agriculture", "keyword": "BADC"},
    "DISASTER": {"name": "Disaster Management Department", "ministry": "Ministry of Disaster Management and Relief", "keyword": "Disaster"},
    "POWER": {"name": "Power Grid Company of Bangladesh", "ministry": "Ministry of Power, Energy and Mineral Resources", "keyword": "PGCB"},
}

sql.add("-- Agencies")
for code, cfg in AGENCY_CONFIG.items():
    sql.add("INSERT INTO agencies (agency_code, agency_name, ministry, keyword) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING;" % (
        fmt(code), fmt(cfg["name"]), fmt(cfg["ministry"]), fmt(cfg["keyword"])))
sql.add("")


# ── Step 2: Zones ──────────────────────────────────────────────────────

zone_id_map = {}  # district_name → id
next_zone_id = 1

sql.add("-- Zones (divisions + districts)")

# Insert divisions first
for div_name in BANGLADESH_DIVISION_NAMES:
    sql.add("INSERT INTO zones (zone_id, zone_name, zone_type) VALUES (%d, %s, 'division') ON CONFLICT DO NOTHING;" % (next_zone_id, fmt(div_name.title())))
    zone_id_map[div_name.title()] = next_zone_id
    next_zone_id += 1

# Insert districts with parent division
for div_name, districts in BANGLADESH_DIVISIONS.items():
    parent_id = zone_id_map[div_name.title()]
    for dist_name in districts:
        sql.add("INSERT INTO zones (zone_id, zone_name, zone_type, parent_zone_id) VALUES (%d, %s, 'district', %d) ON CONFLICT DO NOTHING;" % (
            next_zone_id, fmt(dist_name.title()), parent_id))
        zone_id_map[dist_name.title()] = next_zone_id
        next_zone_id += 1

# Also discover unknown zones from data later
sql.add("")


# ── Step 3: Load data files ────────────────────────────────────────────

logger.info("Loading data files...")

# eContracts flat
ec_flat_path = KNOWLEDGE / "econtracts" / "flat.json"
ec_flat = json.loads(ec_flat_path.read_text(encoding="utf-8")) if ec_flat_path.exists() else []
logger.info("  eContracts: %d records", len(ec_flat))

# APP flat
app_flat_path = KNOWLEDGE / "app" / "flat.json"
app_flat = json.loads(app_flat_path.read_text(encoding="utf-8")) if app_flat_path.exists() else []
logger.info("  APP flat: %d records", len(app_flat))

# Matches
matches_path = KNOWLEDGE / "matches" / "all_matches.json"
matches = json.loads(matches_path.read_text(encoding="utf-8")) if matches_path.exists() else []
logger.info("  Matches: %d records", len(matches))

# Contractors DNA
contractors_path = KNOWLEDGE / "contractordna" / "contractors.json"
contractors_data = json.loads(contractors_path.read_text(encoding="utf-8")) if contractors_path.exists() else []
logger.info("  Contractors: %d records", len(contractors_data))

# Synthetic
synth_path = KNOWLEDGE / "matches" / "synthetic_estimates.json"
synthetic = json.loads(synth_path.read_text(encoding="utf-8")) if synth_path.exists() else []
logger.info("  Synthetic: %d records", len(synthetic))

# Unmatched APP
unmatched_path = KNOWLEDGE / "app" / "unmatched.json"
unmatched_app = json.loads(unmatched_path.read_text(encoding="utf-8")) if unmatched_path.exists() else []
logger.info("  Unmatched APP: %d records", len(unmatched_app))


# ── Step 4: Build tender_id mapping ────────────────────────────────────

# package_no (lowercase) → tender_id (serial)
tender_ids = {}
next_tender_id = 1

def get_tender_id(pkg):
    global next_tender_id
    key = (pkg or "").strip().lower()
    if key and key not in tender_ids:
        tender_ids[key] = next_tender_id
        next_tender_id += 1
    return tender_ids.get(key, 0)

# Register all package_nos from matches, ec_flat, app_flat
for m in matches:
    get_tender_id(m.get("package_no", ""))
for r in ec_flat:
    get_tender_id(r.get("package_no", ""))
for r in app_flat:
    get_tender_id(r.get("package_no", ""))
for r in synthetic:
    get_tender_id(r.get("package_no", ""))

logger.info("  Unique package_nos (tenders): %d", len(tender_ids))


# ── Step 5: Match package_nos to agency + zone ─────────────────────────

# Build package_no → agency mapping from eContracts
pkg_agency = {}
pkg_zone = {}
pkg_pe = {}
pkg_method = {}
pkg_title = {}

for r in ec_flat:
    pkg = (r.get("package_no") or "").strip().lower()
    if pkg:
        pkg_agency.setdefault(pkg, r.get("agency_code", ""))
        pkg_zone.setdefault(pkg, r.get("district", ""))
        pkg_pe.setdefault(pkg, r.get("pe_office", ""))
        if r.get("procurement_method"):
            pkg_method.setdefault(pkg, r["procurement_method"])
        if not pkg_title.get(pkg):
            pkg_title[pkg] = (r.get("title") or "")[:300]

# Also from APP for unmatched
for r in app_flat:
    pkg = (r.get("package_no") or "").strip().lower()
    if pkg:
        if pkg not in pkg_agency:
            pkg_agency[pkg] = ""
        if pkg not in pkg_pe:
            pkg_pe[pkg] = r.get("pe_office", "")
        if not pkg_title.get(pkg):
            pkg_title[pkg] = (r.get("title") or "")[:300]


# ── Helper: map agency from procuring_entity if unknown ─────────────────

MINISTRY_TO_AGENCY = {
    "ministry of water resources": "BWDB",
    "ministry of local government": "LGED",
    "ministry of housing and public works": "PWD",
    "ministry of road transport and bridges": "RHD",
    "ministry of education": "EDUCATION",
    "ministry of shipping": "BIWTA",
    "ministry of agriculture": "BADC",
    "ministry of disaster management": "DISASTER",
    "ministry of power": "POWER",
    "ministry of energy": "POWER",
    "water development board": "BWDB",
    "local government engineering": "LGED",
    "public works department": "PWD",
    "roads and highways": "RHD",
    "bridge authority": "BBA",
    "education engineering": "EDUCATION",
    "inland water transport": "BIWTA",
    "agricultural development": "BADC",
    "disaster management": "DISASTER",
    "power grid": "POWER",
    "rural electrification": "POWER",
}


# ── Step 6: Inserts ────────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- TENDERS")
sql.add("-- ============================================================")
sql.add("")

def get_agency_for_pkg(pkg_lower, fallback_text=""):
    a = pkg_agency.get(pkg_lower, "")
    if a and a in AGENCY_CONFIG:
        return a
    # Try to infer from ministry mapping
    ft = (fallback_text or "").lower()
    for key, ac in MINISTRY_TO_AGENCY.items():
        if key in ft:
            return ac
    return "UNKNOWN"

# Tend from matches (matched)
match_pkgs = set()
for m in matches:
    pkg = (m.get("package_no") or "").strip().lower()
    if not pkg:
        continue
    match_pkgs.add(pkg)
    agency = get_agency_for_pkg(pkg, m.get("app_title", "") + " " + m.get("econtract_title", ""))
    zone = detect_district(m.get("district", "") + " " + m.get("app_title", "") + " " + m.get("econtract_title", "")) or pkg_zone.get(pkg, "")
    pe = m.get("pe_office", "") or pkg_pe.get(pkg, "")
    method = m.get("procurement_method", "") or pkg_method.get(pkg, "")
    title = (m.get("app_title") or m.get("econtract_title") or "")[:300]

    tid = get_tender_id(pkg)
    zone_id = zone_id_map.get(zone.title(), "NULL") if zone else "NULL"

    sql.add("INSERT INTO tenders (tender_id, package_no, title, agency_code, zone_id, pe_office, procurement_method, match_type) VALUES (%d, %s, %s, %s, %s, %s, %s, 'package_exact');" % (
        tid, fmt(pkg), fmt(title[:300]), fmt(agency), zone_id, fmt(pe[:200]), fmt(method[:100])))

# APP-only tenders
for r in unmatched_app:
    pkg = (r.get("package_no") or "").strip().lower()
    if not pkg or pkg in match_pkgs:
        continue
    tid = get_tender_id(pkg)
    pe = r.get("pe_office", "")
    zone = detect_district(r.get("title", "") + " " + pe)
    agency = get_agency_for_pkg(pkg, r.get("title", "") + " " + r.get("ministry", ""))
    method = r.get("procurement_method", "")
    title = (r.get("title") or "")[:300]
    zone_id = zone_id_map.get(zone.title(), "NULL") if zone else "NULL"

    sql.add("INSERT INTO tenders (tender_id, package_no, title, agency_code, zone_id, pe_office, procurement_method, match_type) VALUES (%d, %s, %s, %s, %s, %s, %s, 'unmatched_app');" % (
        tid, fmt(pkg), fmt(title[:300]), fmt(agency), zone_id, fmt(pe[:200]), fmt(method[:100])))

# EC-only tenders (not matched to any APP)
matched_ec_pkgs = set(m["package_no"].strip().lower() for m in matches if m.get("package_no"))
for r in ec_flat:
    pkg = (r.get("package_no") or "").strip().lower()
    if not pkg or pkg in match_pkgs or pkg in matched_ec_pkgs:
        continue
    # Already included above if in match_pkgs
    if pkg in set(x.strip().lower() for x in [m.get("package_no","") for m in matches]):
        continue
    tid = get_tender_id(pkg)
    agency = r.get("agency_code", "")
    zone = r.get("district", "")
    pe = r.get("pe_office", "")
    method = r.get("procurement_method", "")
    title = (r.get("title") or "")[:300]
    zone_id = zone_id_map.get(zone.title(), "NULL") if zone else "NULL"

    sql.add("INSERT INTO tenders (tender_id, package_no, title, agency_code, zone_id, pe_office, procurement_method, match_type) VALUES (%d, %s, %s, %s, %s, %s, %s, 'unmatched_ec');" % (
        tid, fmt(pkg), fmt(title[:300]), fmt(agency), zone_id, fmt(pe[:200]), fmt(method[:100])))

sql.add("")


# ── Step 7: APP Records ─────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- APP RECORDS")
sql.add("-- ============================================================")
sql.add("")

for r in app_flat:
    pkg = (r.get("package_no") or "").strip().lower()
    tid = tender_ids.get(pkg)
    if not tid:
        continue
    est = float(r.get("estimated_cost_bdt", 0) or 0)
    title = (r.get("title") or "")[:300]
    status = (r.get("status") or "")[:50]
    fy = (r.get("financial_year") or "")[:20]

    sql.add("INSERT INTO app_records (tender_id, title, estimated_cost_bdt, status, published_date, deadline, financial_year) VALUES (%d, %s, %s, %s, %s, %s, %s) ON CONFLICT (tender_id) DO NOTHING;" % (
        tid, fmt(title), fmt(est), fmt(status),
        fmt_date(r.get("published_date")),
        fmt_date(r.get("deadline")), fmt(fy)))

sql.add("")


# ── Step 8: Award Records ──────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- AWARD RECORDS")
sql.add("-- ============================================================")
sql.add("")

award_id = 1
for r in ec_flat:
    pkg = (r.get("package_no") or "").strip().lower()
    tid = tender_ids.get(pkg)
    if not tid:
        continue
    amt = float(r.get("amount_bdt", 0) or 0)
    title = (r.get("title") or "")[:300]
    winner = (r.get("winner") or "")[:200]
    method = r.get("procurement_method", "")
    url = (r.get("detail_url") or "")[:500]

    sql.add("INSERT INTO award_records (award_id, tender_id, source_tender_id, package_no, title, contractor_name, amount_bdt, procurement_method, award_date, detail_url) VALUES (%d, %d, %s, %s, %s, %s, %s, %s, %s, %s);" % (
        award_id, tid,
        fmt(r.get("tender_id", "")),
        fmt(r.get("package_no", "")),
        fmt(title), fmt(winner), fmt(amt),
        fmt(method[:100]),
        fmt_date(r.get("award_date")),
        fmt(url)))
    award_id += 1

sql.add("")


# ── Step 9: Contractors ─────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- CONTRACTORS")
sql.add("-- ============================================================")
sql.add("")

for c in contractors_data:
    name = (c.get("contractor_name") or "").strip()
    if not name:
        continue
    agencies_list = c.get("agencies", [])
    districts_list = c.get("districts", [])

    sql.add("INSERT INTO contractors (contractor_name, total_contracts, total_amount_bdt, agencies_worked, districts_worked, avg_npp, first_award_date, last_award_date) VALUES (%s, %d, %s, %s, %s, %s, %s, %s) ON CONFLICT (contractor_name) DO NOTHING;" % (
        fmt(name),
        c.get("total_contracts", 0),
        fmt(c.get("total_amount_bdt", 0)),
        fmt("{" + ",".join(esc(a) for a in agencies_list) + "}"),
        fmt("{" + ",".join(esc(d) for d in districts_list) + "}"),
        fmt(c.get("avg_npp", 0)),
        fmt_date(c.get("earliest_contract_date")),
        fmt_date(c.get("latest_contract_date"))))

sql.add("")


# ── Step 10: Procurement Lifecycle ──────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- PROCUREMENT LIFECYCLE (unified view)")
sql.add("-- ============================================================")
sql.add("")

lifecycle_id = 1

# Matched tenders
for m in matches:
    pkg = (m.get("package_no") or "").strip().lower()
    tid = tender_ids.get(pkg)
    if not tid:
        continue
    zone = m.get("district", "")
    zone_name = zone.title() if zone and zone.title() in zone_id_map else ""
    if not zone_name:
        zone_name = detect_district(m.get("app_title","") + " " + m.get("econtract_title","")) or "Unknown"

    est = float(m.get("estimated_cost_bdt", 0) or 0)
    award = float(m.get("contract_amount_bdt", 0) or 0)
    npp = m.get("npp_ratio", 0) if 0.5 <= float(m.get("npp_ratio", 0)) <= 2.0 else 0

    sql.add("INSERT INTO procurement_lifecycle (lifecycle_id, tender_id, package_no, agency_code, zone_name, title, estimated_cost_bdt, award_amount_bdt, npp_ratio, winner, award_date, procurement_method, pe_office, match_type, data_source) VALUES (%d, %d, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'package_exact', 'matched');" % (
        lifecycle_id, tid,
        fmt(pkg),
        fmt(m.get("agency_code", "")),
        fmt(zone_name),
        fmt((m.get("app_title") or "")[:300]),
        fmt(est), fmt(award), fmt(npp),
        fmt((m.get("contractor") or "")[:200]),
        fmt_date(m.get("award_date")),
        fmt((m.get("procurement_method") or "")[:100]),
        fmt((m.get("pe_office") or "")[:200])))
    lifecycle_id += 1

# Synthetic tenders
for s in synthetic:
    pkg = (s.get("package_no") or "").strip().lower()
    tid = tender_ids.get(pkg)
    if not tid:
        continue
    est = float(s.get("estimated_cost_bdt", 0) or 0)
    award = float(s.get("synthetic_contract_amount", 0) or 0)
    npp = float(s.get("avg_npp", 0) or 0)
    zone = detect_district(s.get("title", "") + " " + s.get("district", "")) or "Unknown"
    agency = s.get("agency_code", "")

    sql.add("INSERT INTO procurement_lifecycle (lifecycle_id, tender_id, package_no, agency_code, zone_name, title, estimated_cost_bdt, award_amount_bdt, npp_ratio, procurement_method, pe_office, match_type, data_source) VALUES (%d, %d, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'synthetic', 'synthetic');" % (
        lifecycle_id, tid,
        fmt(pkg), fmt(agency), fmt(zone),
        fmt((s.get("title") or "")[:300]),
        fmt(est), fmt(award), fmt(npp),
        fmt((s.get("procurement_method") or "")[:100]),
        fmt((s.get("pe_office") or "")[:200])))
    lifecycle_id += 1

sql.add("")


# ── Step 11: Intelligence Tables ────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- CONTRACTOR DNA")
sql.add("-- ============================================================")
sql.add("")

for c in contractors_data:
    name = (c.get("contractor_name") or "").strip()
    if not name:
        continue
    total_amt = float(c.get("total_amount_bdt", 0) or 0)
    total_ct = c.get("total_contracts", 0) or 0
    avg_award = round(total_amt / total_ct, 2) if total_ct > 0 else 0
    npp = c.get("avg_npp", 0) or 0
    discount = round((1 - npp) * 100, 2) if npp > 0 else 0
    agencies_list = c.get("agencies", [])
    districts_list = c.get("districts", [])
    pref_agency = agencies_list[0] if agencies_list else ""
    pref_zone = districts_list[0] if districts_list else ""
    first = c.get("earliest_contract_date", "")
    last = c.get("latest_contract_date", "")
    specialization = c.get("package_nos", [])
    spec_str = specialization[0] if specialization else ""

    sql.add("INSERT INTO contractor_dna (contractor_id, total_contracts, total_amount_bdt, avg_award_bdt, agencies_worked, districts_worked, preferred_agency, preferred_zone, avg_npp, avg_discount_pct, first_award_date, last_award_date) VALUES ((SELECT contractor_id FROM contractors WHERE contractor_name = %s), %d, %s, %s, %d, %d, %s, %s, %s, %s, %s, %s) ON CONFLICT (contractor_id) DO UPDATE SET total_contracts = EXCLUDED.total_contracts, total_amount_bdt = EXCLUDED.total_amount_bdt, avg_award_bdt = EXCLUDED.avg_award_bdt, updated_at = NOW();" % (
        fmt(name), total_ct, fmt(total_amt), fmt(avg_award),
        len(agencies_list), len(districts_list),
        fmt(pref_agency), fmt(pref_zone),
        fmt(npp), fmt(discount),
        fmt_date(first), fmt_date(last)))

sql.add("")

# ── Agency Intelligence ─────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- AGENCY INTELLIGENCE")
sql.add("-- ============================================================")
sql.add("")

# Compute from procurement_lifecycle
agency_stats = defaultdict(lambda: {"total": 0, "amount": 0.0, "npp": [], "contractors": Counter(), "zones": Counter(), "methods": Counter()})

for m in matches:
    agency = (m.get("agency_code") or "").upper()
    if not agency or agency == "UNKNOWN":
        continue
    s = agency_stats[agency]
    s["total"] += 1
    s["amount"] += float(m.get("contract_amount_bdt", 0) or 0)
    npp = m.get("npp_ratio", 0)
    if 0.5 <= float(npp) <= 2.0:
        s["npp"].append(float(npp))
    if m.get("contractor"):
        s["contractors"][m["contractor"]] += 1
    if m.get("district"):
        s["zones"][m["district"]] += 1
    if m.get("procurement_method"):
        s["methods"][m["procurement_method"]] += 1

for agency, s in sorted(agency_stats.items()):
    avg_npp = round(sum(s["npp"]) / len(s["npp"]), 4) if s["npp"] else 0
    top_contractors = json.dumps([{"name": n, "count": c} for n, c in s["contractors"].most_common(5)])
    top_zones = json.dumps([{"zone": z, "count": c} for z, c in s["zones"].most_common(5)])
    pref_method = s["methods"].most_common(1)[0][0] if s["methods"] else ""

    sql.add("INSERT INTO agency_intelligence (agency_code, total_contracts, total_amount_bdt, avg_npp, top_contractors, top_zones, preferred_method) VALUES (%s, %d, %s, %s, '%s', '%s', %s) ON CONFLICT (agency_code) DO UPDATE SET total_contracts = EXCLUDED.total_contracts, total_amount_bdt = EXCLUDED.total_amount_bdt, avg_npp = EXCLUDED.avg_npp, updated_at = NOW();" % (
        fmt(agency), s["total"], fmt(s["amount"]), fmt(avg_npp),
        esc(top_contractors), esc(top_zones), fmt(pref_method)))

sql.add("")


# ── Zone Intelligence ───────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- ZONE INTELLIGENCE")
sql.add("-- ============================================================")
sql.add("")

zone_stats = defaultdict(lambda: {"total": 0, "amount": 0.0, "agencies": set(), "npp": [], "contractors": Counter()})

for m in matches:
    zone = (m.get("district") or "").strip().title()
    if not zone or zone == "Unknown":
        continue
    s = zone_stats[zone]
    s["total"] += 1
    s["amount"] += float(m.get("contract_amount_bdt", 0) or 0)
    if m.get("agency_code"):
        s["agencies"].add(m["agency_code"])
    npp = m.get("npp_ratio", 0)
    if 0.5 <= float(npp) <= 2.0:
        s["npp"].append(float(npp))
    if m.get("contractor"):
        s["contractors"][m["contractor"]] += 1

for zone, s in sorted(zone_stats.items()):
    avg_npp = round(sum(s["npp"]) / len(s["npp"]), 4) if s["npp"] else 0
    top_agencies = json.dumps([{"agency": a} for a in sorted(s["agencies"])[:5]])
    top_contractors = json.dumps([{"name": n, "count": c} for n, c in s["contractors"].most_common(5)])

    sql.add("INSERT INTO zone_intelligence (zone_name, total_contracts, total_amount_bdt, active_agencies, top_agencies, top_contractors, avg_npp) VALUES (%s, %d, %s, %d, '%s', '%s', %s) ON CONFLICT (zone_name) DO UPDATE SET total_contracts = EXCLUDED.total_contracts, total_amount_bdt = EXCLUDED.total_amount_bdt, active_agencies = EXCLUDED.active_agencies, updated_at = NOW();" % (
        fmt(zone), s["total"], fmt(s["amount"]), len(s["agencies"]),
        esc(top_agencies), esc(top_contractors), fmt(avg_npp)))

sql.add("")


# ── Discount Patterns ──────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- DISCOUNT PATTERNS")
sql.add("-- ============================================================")
sql.add("")

pattern_key = lambda m: (m.get("agency_code", "UNKNOWN"), m.get("district", "Unknown"), m.get("procurement_method", "Unknown"))
pattern_groups = defaultdict(lambda: {"npp": [], "amounts": []})

for m in matches:
    npp = m.get("npp_ratio", 0)
    if not (0.5 <= float(npp) <= 2.0):
        continue
    key = pattern_key(m)
    pattern_groups[key]["npp"].append(float(npp))
    pattern_groups[key]["amounts"].append(float(m.get("contract_amount_bdt", 0) or 0))

pattern_id = 1
for key, data in sorted(pattern_groups.items()):
    agency, zone, method = key
    vals = data["npp"]
    amounts = data["amounts"]
    if not vals:
        continue
    avg_npp = round(sum(vals) / len(vals), 4)
    min_npp = round(min(vals), 4)
    max_npp = round(max(vals), 4)
    sorted_vals = sorted(vals)
    median_npp = sorted_vals[len(sorted_vals) // 2]
    variance = sum((v - avg_npp) ** 2 for v in vals) / len(vals)
    stddev_npp = round(variance ** 0.5, 4)

    sql.add("INSERT INTO discount_patterns (pattern_id, agency_code, zone_name, procurement_method, sample_size, avg_npp, min_npp, max_npp, median_npp, stddev_npp, total_amount_bdt) VALUES (%d, %s, %s, %s, %d, %s, %s, %s, %s, %s, %s);" % (
        pattern_id, fmt(agency), fmt(zone), fmt(method),
        len(vals), fmt(avg_npp), fmt(min_npp), fmt(max_npp),
        fmt(median_npp), fmt(stddev_npp), fmt(sum(amounts))))
    pattern_id += 1

sql.add("")


# ── Award Intelligence ──────────────────────────────────────────────────

sql.add("-- ============================================================")
sql.add("-- AWARD INTELLIGENCE")
sql.add("-- ============================================================")
sql.add("")

# Group by agency × fiscal_year × quarter
from datetime import datetime
intel_id = 1
intel_groups = defaultdict(lambda: {"amounts": [], "npp": [], "methods": Counter(), "contractors": Counter()})

for m in matches:
    d = m.get("award_date", "")
    if not d:
        continue
    for fmt_d in ["%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(d, fmt_d)
            break
        except Exception:
            dt = None
    if not dt:
        continue
    # Bangladesh FY: Jul–Jun
    fy = "FY%d-%d" % (dt.year - 1, dt.year) if dt.month < 7 else "FY%d-%d" % (dt.year, dt.year + 1)
    q = (dt.month - 1) // 3 + 1
    key = (m.get("agency_code", "UNKNOWN"), fy, q)
    g = intel_groups[key]
    g["amounts"].append(float(m.get("contract_amount_bdt", 0) or 0))
    npp = m.get("npp_ratio", 0)
    if 0.5 <= float(npp) <= 2.0:
        g["npp"].append(float(npp))
    if m.get("procurement_method"):
        g["methods"][m["procurement_method"]] += 1
    if m.get("contractor"):
        g["contractors"][m["contractor"]] += 1

for key, g in sorted(intel_groups.items()):
    agency, fy, q = key
    if not g["amounts"]:
        continue
    total_amt = round(sum(g["amounts"]), 2)
    avg_npp = round(sum(g["npp"]) / len(g["npp"]), 4) if g["npp"] else 0
    avg_amt = round(total_amt / len(g["amounts"]), 2)
    methods_json = json.dumps(dict(g["methods"].most_common(5)))
    top_ctr = json.dumps([{"name": n, "count": c} for n, c in g["contractors"].most_common(5)])

    sql.add("INSERT INTO award_intelligence (intelligence_id, agency_code, fiscal_year, quarter, total_contracts, total_amount_bdt, avg_npp, avg_contract_amount, contract_count_by_method, top_contractors) VALUES (%d, %s, %s, %d, %d, %s, %s, %s, '%s', '%s');" % (
        intel_id, fmt(agency), fmt(fy), q, len(g["amounts"]),
        fmt(total_amt), fmt(avg_npp), fmt(avg_amt),
        esc(methods_json), esc(top_ctr)))
    intel_id += 1

sql.add("")


# ── Finalize ────────────────────────────────────────────────────────────

sql.add("COMMIT;")
sql.write(OUTPUT)

logger.info("Done! Generated %d tenders, %d awards, %d contractors, %d lifecycle records",
            len(tender_ids), award_id - 1, len(contractors_data), lifecycle_id - 1)
logger.info("SQL file ready: %s", OUTPUT)
