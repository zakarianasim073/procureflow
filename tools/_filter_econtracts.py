"""
Filter eContracts to target agencies, amount > 3cr, structured output.
"""
import json, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"

MINISTRY_MAP = {
    "BWDB": "Ministry of Water Resources",
    "LGED": "Ministry of Local Government, Rural Development and Co-operatives",
    "PWD": "Ministry of Housing and Public Works",
    "RHD": "Ministry of Road Transport and Bridges",
    "BBA": "Ministry of Road Transport and Bridges",
    "EDUCATION": "Ministry of Education",
    "BIWTA": "Ministry of Shipping",
    "BADC": "Ministry of Agriculture",
    "DISASTER": "Ministry of Disaster Management and Relief",
    "POWER": "Ministry of Power, Energy and Mineral Resources",
}

TARGET_AGENCIES = set(MINISTRY_MAP.keys())

def detect_agency(pe: str) -> str:
    pe_lower = pe.lower()
    if "bwdb" in pe_lower or "water development" in pe_lower:
        return "BWDB"
    if "lged" in pe_lower or "local government engineering" in pe_lower:
        return "LGED"
    if "pwd" in pe_lower or "public works" in pe_lower:
        return "PWD"
    if "rhd" in pe_lower or "roads and highways" in pe_lower or "road transport" in pe_lower:
        return "RHD"
    if "bba" in pe_lower or "bridge authority" in pe_lower:
        return "BBA"
    if "education" in pe_lower or "eed" in pe_lower or "school" in pe_lower or "college" in pe_lower:
        return "EDUCATION"
    if "biwta" in pe_lower:
        return "BIWTA"
    if "badc" in pe_lower:
        return "BADC"
    if "disaster" in pe_lower or "relief" in pe_lower or "drm" in pe_lower:
        return "DISASTER"
    if "power" in pe_lower or "electric" in pe_lower or "nesco" in pe_lower or "pgcb" in pe_lower or "reb" in pe_lower or "palli" in pe_lower:
        return "POWER"
    return "OTHER"

def parse_pe(pe: str):
    """Parse procuring_entity into structured parts."""
    if not pe:
        return {"pe_office": "", "district": "", "location": ""}
    parts = [p.strip() for p in pe.split(",")]
    pe_office = parts[0] if parts else ""
    dist_list = parts[1:] if len(parts) > 1 else []
    district = ""
    location = ""
    bangla_districts = [
        "dhaka", "chittagong", "rajshahi", "khulna", "barisal", "sylhet",
        "rangpur", "mymensingh", "dinajpur", "bogra", "comilla", "bhola",
        "noakhali", "sirajganj", "pabna", "kushtia", "jessore", "sherpur",
        "tangail", "munshiganj", "gazipur", "narayanganj", "narsingdi",
        "manikganj", "faridpur", "rajbari", "gopalganj", "shariatpur",
        "madaripur", "chandpur", "lakshmipur", "feni", "brahmanbaria",
        "kishoreganj", "habiganj", "maulvibazar", "sunamganj", "netrokona",
        "jamalpur", "panchagarh", "thakurgaon", "nilphamari", "lalmonirhat",
        "kurigram", "gaibandha", "joypurhat", "naogaon", "natore",
        "chapainawabganj", "meherpur", "chuadanga", "jhenaidah",
        "magura", "narail", "bagerhat", "sathkhira", "khagrachhari",
        "rangamati", "bandarban", "cox's bazar", "patuakhali", "barguna",
        "jhalokati", "pirojpur",
    ]
    for p in reversed(parts):
        p_clean = re.sub(r'[^a-zA-Z\s]', '', p).strip().lower()
        if p_clean in bangla_districts:
            district = p_clean.title()
            break
    if not pe_office:
        pe_office = parts[0] if parts else ""
    return {"pe_office": pe_office, "district": district, "location": ", ".join(parts[1:]) if len(parts) > 1 else ""}

# Load eContracts
all_recs = []
seen = set()
for fp in sorted((KNOWLEDGE / "econtracts_raw").glob("page_*.json")):
    for r in json.loads(fp.read_text(encoding="utf-8")):
        key = f"{r.get('tender_id','')}|{r.get('winner','')}"
        if key in seen: continue
        seen.add(key)
        all_recs.append(r)

print(f"Loaded {len(all_recs)} total eContracts")

# Filter by agency + amount > 3cr
filtered = []
for r in all_recs:
    pe = r.get("procuring_entity", "") or ""
    agency = detect_agency(pe)
    if agency not in TARGET_AGENCIES:
        continue
    amt = float(r.get("amount_bdt", 0) or 0)
    if amt < 30_000_000:
        continue
    r["agency"] = agency
    r["ministry"] = MINISTRY_MAP[agency]
    pe_info = parse_pe(pe)
    r["pe_office"] = pe_info["pe_office"]
    r["district"] = pe_info["district"]
    r["location"] = pe_info["location"]
    filtered.append(r)

print(f"After agency+amount filter: {len(filtered)} records")

# Structure hierarchically
hierarchy = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))

for r in filtered:
    m = r["ministry"]
    a = r["agency"]
    pe = r["pe_office"]
    dist = r["district"] or "Unknown"
    hierarchy[m][a][pe][dist].append(r)

# Sort by amount descending within each district
for m in hierarchy:
    for a in hierarchy[m]:
        for pe in hierarchy[m][a]:
            for dist in hierarchy[m][a][pe]:
                hierarchy[m][a][pe][dist].sort(key=lambda x: float(x.get("amount_bdt", 0) or 0), reverse=True)

# Build structured output
output = []
total_amt = 0
for m in sorted(hierarchy.keys()):
    ministry_entry = {"ministry": m, "agencies": []}
    for a in sorted(hierarchy[m].keys()):
        agency_entry = {"agency": a, "pe_offices": []}
        for pe in sorted(hierarchy[m][a].keys()):
            pe_entry = {"pe_office": pe, "districts": []}
            for dist in sorted(hierarchy[m][a][pe].keys()):
                recs_list = hierarchy[m][a][pe][dist]
                total = sum(float(r.get("amount_bdt", 0) or 0) for r in recs_list)
                total_amt += total
                dist_entry = {
                    "district": dist,
                    "total_contracts": len(recs_list),
                    "total_amount_bdt": round(total, 2),
                    "contracts": [
                        {
                            "tender_id": r.get("tender_id", ""),
                            "package_no": r.get("package_no", ""),
                            "contractor": r.get("winner", ""),
                            "work_name": (r.get("title", "") or "")[:200],
                            "quoted_amount_bdt": round(float(r.get("amount_bdt", 0) or 0), 2),
                            "contract_signing_date": r.get("award_date", ""),
                            "procurement_method": r.get("procurement_method", ""),
                            "procurement_nature": r.get("procurement_nature", ""),
                        }
                        for r in recs_list
                    ]
                }
                pe_entry["districts"].append(dist_entry)
            agency_entry["pe_offices"].append(pe_entry)
        ministry_entry["agencies"].append(agency_entry)
    output.append(ministry_entry)

result = {
    "generated_at": datetime.now().isoformat(),
    "total_records": len(filtered),
    "total_amount_bdt": round(total_amt, 2),
    "filter_criteria": {
        "agencies": list(TARGET_AGENCIES),
        "min_amount_bdt": 30_000_000,
        "source": "eContracts (up to Aug 2025)",
    },
    "data": output,
}

out = KNOWLEDGE / "econtracts_filtered.json"
out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Written to {out}")
print(f"\nSummary: {len(filtered)} contracts across {len(output)} ministries")
print(f"Total amount: BDT {total_amt:,.2f}")

# Per-agency counts
for m in output:
    for a in m["agencies"]:
        cnt = sum(len(d["contracts"]) for pe in a["pe_offices"] for d in pe["districts"])
        amt = sum(d["total_amount_bdt"] for pe in a["pe_offices"] for d in pe["districts"])
        print(f"  {a['agency']}: {cnt} contracts, BDT {amt:,.2f}")
