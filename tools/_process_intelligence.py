"""
Build APP structured output, match APP ↔ eContracts, derive contractor DNA & NPP trends.
"""
from __future__ import annotations

import json, logging, re, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("process_intel")

KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"

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

def detect_district(text: str) -> str:
    t = re.sub(r'[^a-zA-Z\s]', ' ', text).lower()
    for d in BANGLADESH_DISTRICTS:
        if d in t:
            return d.title()
    return ""

def parse_procuring_entity(pe: str) -> dict:
    if not pe:
        return {"ministry": "", "agency": "", "pe_office": "", "district": ""}
    parts = [p.strip() for p in re.split(r",,+", pe)]  # split on 2+ commas
    ministry = parts[0] if len(parts) > 0 else ""
    agency = parts[1] if len(parts) > 1 else ""
    pe_office = parts[2] if len(parts) > 2 else parts[0]
    district = detect_district(pe)
    return {"ministry": ministry, "agency": agency, "pe_office": pe_office, "district": district}


# ── Step 1: APP Structured Output ──────────────────────────────────────

def build_app_structure():
    """Read ALL.json, build Ministry→PE→Package hierarchy."""
    fp = KNOWLEDGE / "app" / "ALL.json"
    data = json.loads(fp.read_text(encoding="utf-8"))
    tenders = [r for r in data if r.get("tender_id")]
    logger.info("APP: %d tender records out of %d total", len(tenders), len(data))

    hierarchy: dict = {}
    total_est = 0.0
    with_pkg = 0

    for r in tenders:
        pkg = (r.get("package_no") or "").strip()
        if pkg:
            with_pkg += 1

        pe = r.get("procuring_entity") or ""
        parsed = parse_procuring_entity(pe)
        ministry = parsed["ministry"] or (r.get("_department") or "Unknown Ministry")
        pe_office = parsed["pe_office"] or r.get("_office_name") or pe.split(",")[0].strip()
        district = parsed["district"] or detect_district(pe + " " + (r.get("title") or ""))
        est = float(r.get("estimated_amount_bdt") or r.get("estimated_value_bdt") or 0)
        total_est += est

        key = (ministry, pe_office)
        hierarchy.setdefault(ministry, {})
        hierarchy[ministry].setdefault(pe_office, {"packages": [], "total_estimated_bdt": 0.0})
        pinfo = hierarchy[ministry][pe_office]
        pinfo["packages"].append({
            "package_no": pkg or r.get("app_code", ""),
            "title": (r.get("title") or "")[:200],
            "estimated_cost_bdt": round(est, 2),
            "district": district,
            "tender_id": r.get("tender_id", ""),
            "status": r.get("status", ""),
            "published_date": r.get("published_date", ""),
            "deadline": r.get("deadline", ""),
            "procurement_method": r.get("procurement_method", ""),
            "category": r.get("category", ""),
        })
        pinfo["total_estimated_bdt"] += est

    # Convert to list hierarchy
    output_ministries = []
    for m_name in sorted(hierarchy.keys()):
        pe_list = []
        for pe_name in sorted(hierarchy[m_name].keys()):
            pinfo = hierarchy[m_name][pe_name]
            pe_list.append({
                "pe_office": pe_name,
                "total_estimated_bdt": round(pinfo["total_estimated_bdt"], 2),
                "package_count": len(pinfo["packages"]),
                "packages": sorted(pinfo["packages"], key=lambda x: x.get("package_no", "")),
            })
        d = {"ministry": m_name, "pe_offices": pe_list}
        if any(any(a.lower() in m_name.lower() for a in ["ministry"]) for _ in [0]):
            pass
        output_ministries.append(d)

    output = {
        "generated_at": datetime.now().isoformat(),
        "total_packages": len(tenders),
        "with_package_no": with_pkg,
        "total_estimated_bdt": round(total_est, 2),
        "ministries": output_ministries,
    }

    out_fp = KNOWLEDGE / "app" / "structure.json"
    out_fp.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also create flat list for quick matching
    flat = []
    for m in output_ministries:
        for pe in m["pe_offices"]:
            for p in pe["packages"]:
                flat.append({
                    "package_no": p["package_no"],
                    "title": p["title"],
                    "estimated_cost_bdt": p["estimated_cost_bdt"],
                    "district": p["district"],
                    "pe_office": pe["pe_office"],
                    "ministry": m["ministry"],
                    "tender_id": p["tender_id"],
                    "status": p["status"],
                    "source": "APP",
                })
    flat_fp = KNOWLEDGE / "app" / "flat.json"
    flat_fp.write_text(json.dumps(flat, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("APP structure: %d packages, %d ministries, BDT %.2f total",
                output["total_packages"], len(output_ministries), output["total_estimated_bdt"])
    for m in output_ministries:
        pc = sum(pe["package_count"] for pe in m["pe_offices"])
        logger.info("  %s: %d packages", m["ministry"], pc)
    return flat


# ── Step 2: Matching ───────────────────────────────────────────────────

def run_matching(app_flat: list):
    """Match APP ↔ eContracts by package_no (exact case-insensitive)."""
    ec_fp = KNOWLEDGE / "econtracts" / "flat.json"
    if not ec_fp.exists():
        logger.error("eContracts flat.json not found - run crawl first")
        return [], []
    ec_data = json.loads(ec_fp.read_text(encoding="utf-8"))
    logger.info("Matching: %d APP packages vs %d eContracts", len(app_flat), len(ec_data))

    # Build lookup by package_no (lowercase)
    app_by_pkg = defaultdict(list)
    app_no_pkg = 0
    for r in app_flat:
        pkg = (r.get("package_no") or "").strip().lower()
        if pkg:
            app_by_pkg[pkg].append(r)
        else:
            app_no_pkg += 1

    ec_by_pkg = defaultdict(list)
    ec_no_pkg = 0
    for r in ec_data:
        pkg = (r.get("package_no") or "").strip().lower()
        if pkg:
            ec_by_pkg[pkg].append(r)
        else:
            ec_no_pkg += 1

    logger.info("  APP: %d with package_no, %d without", len(app_by_pkg), app_no_pkg)
    logger.info("  eContracts: %d with package_no, %d without", len(ec_by_pkg), ec_no_pkg)

    # Find matches
    matches = []
    matched_pkgs = app_by_pkg.keys() & ec_by_pkg.keys()
    for pkg in sorted(matched_pkgs):
        for app_r in app_by_pkg[pkg]:
            for ec_r in ec_by_pkg[pkg]:
                est = float(app_r.get("estimated_cost_bdt") or 0)
                contract_amt = float(ec_r.get("amount_bdt") or 0)
                npp = round(contract_amt / est, 4) if est > 0 else 0
                matches.append({
                    "package_no": pkg,
                    "match_type": "package_exact",
                    "app_title": app_r.get("title", "")[:200],
                    "econtract_title": ec_r.get("title", "")[:200],
                    "ministry": ec_r.get("ministry", app_r.get("ministry", "")),
                    "agency_code": ec_r.get("agency_code", ""),
                    "pe_office": ec_r.get("pe_office", app_r.get("pe_office", "")),
                    "district": ec_r.get("district", app_r.get("district", "")),
                    "contractor": ec_r.get("winner", ""),
                    "estimated_cost_bdt": est,
                    "contract_amount_bdt": contract_amt,
                    "npp_ratio": npp if 0.5 <= npp <= 2.0 else 0,
                    "npp_raw": npp,
                    "app_tender_id": app_r.get("tender_id", ""),
                    "econtract_tender_id": ec_r.get("tender_id", ""),
                    "procurement_method": ec_r.get("procurement_method", app_r.get("procurement_method", "")),
                    "award_date": ec_r.get("award_date", ""),
                })

    # Save matches
    out = KNOWLEDGE / "matches" / "all_matches.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matches, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Matches: %d package_exact from %d unique package_nos",
                len(matches), len(matched_pkgs))

    # Save unmatched APP
    unmatched_pkgs = app_by_pkg.keys() - ec_by_pkg.keys()
    unmatched_app = []
    for pkg in sorted(unmatched_pkgs):
        for r in app_by_pkg[pkg]:
            unmatched_app.append(r)

    # Also save matched eContracts
    matched_ec_pkgs = app_by_pkg.keys() & ec_by_pkg.keys()
    matched_ec = []
    for pkg in sorted(matched_ec_pkgs):
        for r in ec_by_pkg[pkg]:
            matched_ec.append(r)

    # Create synthetic matches for unmatched APP (agency-average NPP)
    unmatched_out = KNOWLEDGE / "app" / "unmatched.json"
    unmatched_out.write_text(json.dumps(unmatched_app, indent=2, ensure_ascii=False), encoding="utf-8")

    return matches, unmatched_app


# ── Step 3: Contractor DNA ─────────────────────────────────────────────

def build_contractor_dna(matches: list):
    """Per-contractor analysis from matched records."""
    contractors = defaultdict(lambda: {
        "contractor_name": "",
        "total_contracts": 0,
        "total_amount_bdt": 0.0,
        "agencies": set(),
        "ministries": set(),
        "districts": set(),
        "pe_offices": set(),
        "package_nos": [],
        "latest_contract_date": "",
        "earliest_contract_date": "",
        "avg_npp": 0.0,
        "npp_values": [],
    })

    for m in matches:
        name = (m.get("contractor") or "Unknown").strip()
        if not name:
            continue
        c = contractors[name]
        c["contractor_name"] = name
        c["total_contracts"] += 1
        c["total_amount_bdt"] += float(m.get("contract_amount_bdt") or 0)
        if m.get("agency_code"):
            c["agencies"].add(m["agency_code"])
        if m.get("ministry"):
            c["ministries"].add(m["ministry"])
        if m.get("district"):
            c["districts"].add(m["district"])
        if m.get("pe_office"):
            c["pe_offices"].add(m["pe_office"])
        if m.get("package_no"):
            c["package_nos"].append(m["package_no"])
        if m.get("award_date"):
            d = m["award_date"]
            if not c["latest_contract_date"] or d > c["latest_contract_date"]:
                c["latest_contract_date"] = d
            if not c["earliest_contract_date"] or d < c["earliest_contract_date"]:
                c["earliest_contract_date"] = d
        npp = m.get("npp_ratio", 0)
        if npp > 0:
            c["npp_values"].append(npp)

    # Convert sets to lists and calculate averages
    result = []
    for name in sorted(contractors.keys()):
        c = contractors[name]
        avg_npp = round(sum(c["npp_values"]) / len(c["npp_values"]), 4) if c["npp_values"] else 0
        result.append({
            "contractor_name": name,
            "total_contracts": c["total_contracts"],
            "total_amount_bdt": round(c["total_amount_bdt"], 2),
            "agencies": sorted(c["agencies"]),
            "ministries": sorted(c["ministries"]),
            "districts": sorted(c["districts"]),
            "pe_offices": sorted(c["pe_offices"]),
            "package_nos": sorted(set(c["package_nos"])),
            "latest_contract_date": c["latest_contract_date"],
            "earliest_contract_date": c["earliest_contract_date"],
            "avg_npp": avg_npp,
            "npp_sample_size": len(c["npp_values"]),
        })

    out = KNOWLEDGE / "contractordna" / "contractors.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Contractor DNA: %d unique contractors", len(result))
    if result:
        logger.info("  Top: %s (%d contracts, BDT %.2f)",
                    result[0]["contractor_name"], result[0]["total_contracts"], result[0]["total_amount_bdt"])
    return result


# ── Step 4: NPP Trends + Rate Analysis ─────────────────────────────────

def build_npp_trends(matches: list):
    """Aggregate NPP trends by agency, district, procurement method."""
    # Aggregate by agency
    by_agency = defaultdict(lambda: {"npp_values": [], "amounts": [], "count": 0})
    by_district = defaultdict(lambda: {"npp_values": [], "amounts": [], "count": 0})
    by_method = defaultdict(lambda: {"npp_values": [], "amounts": [], "count": 0})
    by_agency_district = defaultdict(lambda: {"npp_values": [], "amounts": [], "count": 0})

    for m in matches:
        npp = m.get("npp_ratio", 0)
        if npp <= 0:
            continue
        amt = float(m.get("contract_amount_bdt") or 0)
        agency = (m.get("agency_code") or "Unknown").upper()
        district = m.get("district") or "Unknown"
        method = m.get("procurement_method") or "Unknown"
        agency_dist = "%s / %s" % (agency, district)

        by_agency[agency]["npp_values"].append(npp)
        by_agency[agency]["amounts"].append(amt)
        by_agency[agency]["count"] += 1

        by_district[district]["npp_values"].append(npp)
        by_district[district]["amounts"].append(amt)
        by_district[district]["count"] += 1

        by_method[method]["npp_values"].append(npp)
        by_method[method]["amounts"].append(amt)
        by_method[method]["count"] += 1

        by_agency_district[agency_dist]["npp_values"].append(npp)
        by_agency_district[agency_dist]["amounts"].append(amt)
        by_agency_district[agency_dist]["count"] += 1

    def stats(values, amounts):
        if not values:
            return {"count": 0, "avg_npp": 0, "min_npp": 0, "max_npp": 0, "total_amount": 0}
        return {
            "count": len(values),
            "avg_npp": round(sum(values) / len(values), 4),
            "min_npp": round(min(values), 4),
            "max_npp": round(max(values), 4),
            "median_npp": round(sorted(values)[len(values) // 2], 4),
            "total_amount": round(sum(amounts), 2),
        }

    npp_data = {
        "generated_at": datetime.now().isoformat(),
        "total_matches": len(matches),
        "by_agency": {k: stats(v["npp_values"], v["amounts"]) for k, v in sorted(by_agency.items())},
        "by_district": {k: stats(v["npp_values"], v["amounts"]) for k, v in sorted(by_district.items())},
        "by_procurement_method": {k: stats(v["npp_values"], v["amounts"]) for k, v in sorted(by_method.items())},
        "by_agency_district": {k: stats(v["npp_values"], v["amounts"]) for k, v in sorted(by_agency_district.items())},
    }

    out = KNOWLEDGE / "npp" / "npp_trends.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(npp_data, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("NPP trends: %d agencies, %d districts, %d methods analyzed",
                len(npp_data["by_agency"]), len(npp_data["by_district"]), len(npp_data["by_procurement_method"]))
    for a, s in sorted(npp_data["by_agency"].items()):
        logger.info("  %s: avg_npp=%.2f, n=%d, total=BDT %.2f",
                    a, s["avg_npp"], s["count"], s["total_amount"])

    # Also build per-agency NPP for synthetic estimation
    agency_avg_npp = {}
    for a, s in npp_data["by_agency"].items():
        agency_avg_npp[a] = s["avg_npp"]
    npp_avg_out = KNOWLEDGE / "npp" / "agency_avg_npp.json"
    npp_avg_out.write_text(json.dumps(agency_avg_npp, indent=2), encoding="utf-8")

    return npp_data


def build_synthetic_estimates(app_flat: list, matches: list, unmatched_app: list):
    """Generate synthetic estimates for unmatched APP using agency-average NPP."""
    # Calculate agency-average NPP from matches
    npp_by_agency = defaultdict(list)
    for m in matches:
        agency = (m.get("agency_code") or "").upper()
        npp = m.get("npp_ratio", 0)
        if agency and npp > 0:
            npp_by_agency[agency].append(npp)

    agency_avg_npp = {}
    for agency, values in npp_by_agency.items():
        agency_avg_npp[agency] = round(sum(values) / len(values), 4)

    # Map APP ministry/department to agency for synthetic estimation
    ministry_to_agency = {
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
    }

    # Generate synthetic estimates
    synthetic = []
    for r in unmatched_app:
        ministry = (r.get("ministry") or "").lower()
        pkg = r.get("package_no", "")
        est = float(r.get("estimated_cost_bdt") or 0)

        # Determine agency
        agency = "UNKNOWN"
        for m_key, a_code in ministry_to_agency.items():
            if m_key in ministry:
                agency = a_code
                break

        avg_npp = agency_avg_npp.get(agency, 0)
        synthetic_amt = round(est * avg_npp, 2) if avg_npp > 0 and est > 0 else 0
        synthetic.append({
            "package_no": pkg,
            "title": (r.get("title") or "")[:200],
            "estimated_cost_bdt": est,
            "ministry": r.get("ministry", ""),
            "pe_office": r.get("pe_office", ""),
            "district": r.get("district", ""),
            "agency_code": agency,
            "avg_npp": avg_npp,
            "synthetic_contract_amount": synthetic_amt,
            "source": "synthetic_agency_avg",
        })

    out = KNOWLEDGE / "matches" / "synthetic_estimates.json"
    out.write_text(json.dumps(synthetic, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build combined rates
    rates = KNOWLEDGE / "rates"
    rates.mkdir(parents=True, exist_ok=True)

    real_rates = []
    for m in matches:
        if m.get("npp_ratio", 0) > 0:
            real_rates.append({
                "package_no": m["package_no"],
                "agency": m.get("agency_code", ""),
                "district": m.get("district", ""),
                "pe_office": m.get("pe_office", ""),
                "estimated": m.get("estimated_cost_bdt", 0),
                "contract": m.get("contract_amount_bdt", 0),
                "npp": m["npp_ratio"],
                "type": "real",
            })
    for s in synthetic:
        if s.get("synthetic_contract_amount", 0) > 0:
            real_rates.append({
                "package_no": s["package_no"],
                "agency": s.get("agency_code", ""),
                "district": s.get("district", ""),
                "pe_office": s.get("pe_office", ""),
                "estimated": s.get("estimated_cost_bdt", 0),
                "contract": s.get("synthetic_contract_amount", 0),
                "npp": s.get("avg_npp", 0),
                "type": "synthetic",
            })

    rates_fp = rates / "all_rates.json"
    rates_fp.write_text(json.dumps(real_rates, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Synthetic estimates: %d generated from %d unmatched APP records",
                len(synthetic), len(unmatched_app))
    logger.info("Combined rates: %d records (real=%d, synthetic=%d)",
                len(real_rates), len(matches), len(synthetic))

    return synthetic


# ── Main ───────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("Step 1: Building APP Structured Output")
    logger.info("=" * 60)
    app_flat = build_app_structure()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 2: Matching APP ↔ eContracts")
    logger.info("=" * 60)
    matches, unmatched_app = run_matching(app_flat)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 3: Building Contractor DNA")
    logger.info("=" * 60)
    contractors = build_contractor_dna(matches)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 4: NPP Trends + Rate Analysis")
    logger.info("=" * 60)
    npp_trends = build_npp_trends(matches)
    synthetic = build_synthetic_estimates(app_flat, matches, unmatched_app)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    logger.info("APP packages: %d", len(app_flat))
    logger.info("Real matches: %d", len(matches))
    logger.info("Unmatched APP: %d", len(unmatched_app))
    logger.info("Synthetic estimates: %d", len(synthetic))
    logger.info("Unique contractors: %d", len(contractors))
    logger.info("NPP by agencies: %d", len(npp_trends["by_agency"]))
    logger.info("All outputs saved to knowledge/")

if __name__ == "__main__":
    main()
