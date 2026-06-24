"""
Seed data import script — reads backend/database/seed.sql (PostgreSQL)
and imports all rows into the SQLAlchemy ORM tables (SQLite).

Handles:
  - UUID primary keys (ORM uses UUIDs, seed uses SERIAL)
  - Table name differences (tenders→procurement_tenders, award_records→award_records_v2)
  - PostgreSQL-specific syntax (ON CONFLICT, SERIAL, ::type casts)
  - Foreign key mapping (old INT IDs → new UUIDs)
"""
import sys, os, re, json, uuid
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session
from app.models.base import Base as ModelsBase
from app.models.intelligence import (
    Agency, Zone, ProcurementTender, APPRecord, AwardRecordV2,
    Contractor, ProcurementLifecycle, ContractorDNA,
    AgencyIntelligence, ZoneIntelligence, DiscountPattern,
    AwardIntelligence,
)

DB_PATH = Path(__file__).resolve().parent / "runtime" / "db" / "procureflow.db"
SEED_PATH = Path(__file__).resolve().parent / "backend" / "database" / "seed.sql"
BATCH_SIZE = 1000

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}")
event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA journal_mode=WAL"))
event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA synchronous=OFF"))

print(f"Creating ORM tables at {DB_PATH}...")
# Only create intelligence-model tables (skip tender.py's "tenders" which has conflicting indexes)
MODELS = [
    Agency, Zone, ProcurementTender, APPRecord, AwardRecordV2,
    Contractor, ProcurementLifecycle, ContractorDNA,
    AgencyIntelligence, ZoneIntelligence, DiscountPattern, AwardIntelligence,
]
for m in MODELS:
    m.__table__.create(engine, checkfirst=True)

print("Reading seed.sql...")
with open(SEED_PATH, encoding="utf-8") as f:
    raw = f.read()

_not_quoted_cache = {}
def _not_quoted(text: str, pos: int) -> bool:
    key = (id(text), pos)
    if key in _not_quoted_cache:
        return _not_quoted_cache[key]
    in_q = False
    for i in range(pos):
        if text[i] == "'":
            in_q = not in_q
    result = not in_q
    _not_quoted_cache[key] = result
    return result

def strip_pg(line: str) -> str:
    """Remove PostgreSQL-specific suffixes and casts."""
    line = re.sub(r"::\w+(?:\[\])?", "", line)           # ::text, ::numeric, ::text[], etc.
    line = re.sub(r" ON CONFLICT DO NOTHING", "", line)  # PostgreSQL upsert
    line = re.sub(r" ON CONFLICT \([^)]+\) DO NOTHING", "", line)
    line = re.sub(r" ON CONFLICT \([^)]+\) DO UPDATE SET .*", ";", line)  # strip ON CONFLICT DO UPDATE
    line = re.sub(r"'(\d{4}-\d{2}-\d{2})'::date", r"'\1'", line)
    line = re.sub(r"'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[+-]\d+)?)'::timestamptz", r"'\1'", line)
    line = re.sub(r"DEFAULT NOW\(\)", "'2026-01-01 00:00:00+00'", line)
    line = re.sub(r"TRUE", "1", line, flags=re.IGNORECASE)
    line = re.sub(r"FALSE", "0", line, flags=re.IGNORECASE)
    line = re.sub(r"'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})'", r"'\1 \2'", line)
    return line.strip()

def split_vals(text: str) -> list:
    """Split comma-separated value string into individual values, respecting quotes and nesting."""
    vals = []
    cur = []
    depth = 0
    in_q = False
    for ch in text:
        if ch == "'":
            in_q = not in_q
            cur.append(ch)
        elif not in_q:
            if ch == "(":
                depth += 1
                cur.append(ch)
            elif ch == ")":
                depth -= 1
                cur.append(ch)
            elif ch == "," and depth == 0:
                vals.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        else:
            cur.append(ch)
    if cur:
        vals.append("".join(cur).strip())
    return vals

def parse_values(text: str) -> list:
    """Parse value tuples like (v1,v2,...) (v3,v4,...) into list of value-lists."""
    text = text.strip().rstrip(";")
    if not text.startswith("("):
        return []
    results = []
    i = 0
    while i < len(text):
        if text[i] == "(":
            depth = 1
            j = i + 1
            while j < len(text) and depth > 0:
                if text[j] == "(" and _not_quoted(text, j):
                    depth += 1
                elif text[j] == ")" and _not_quoted(text, j):
                    depth -= 1
                j += 1
            if depth == 0:
                inner = text[i+1:j-1]
                results.append(split_vals(inner))
                i = j
            else:
                break
        else:
            i += 1
    if not results:
        if text.startswith("("):
            return [split_vals(text[1:].strip().rstrip(")"))]
    return results

def parse_insert(line: str):
    """Parse an INSERT INTO line. Returns (table_name, parsed_dict)."""
    m = re.match(r"INSERT INTO (\w+)\s*\(([^)]+)\)\s*", line, re.IGNORECASE)
    if not m:
        return None, []
    table = m.group(1)
    cols = [c.strip().strip('"') for c in m.group(2).split(",")]
    # Everything after column list should contain VALUES (...)
    rest = line[m.end():].strip()
    if not rest.upper().startswith("VALUES"):
        return table, []
    # Extract the value tuples from rest
    m2 = re.search(r"VALUES\s*", rest)
    if not m2:
        return table, []
    vals_text = rest[m2.end():].strip()
    rows = parse_values(vals_text)
    if not rows:
        return table, []
    return table, {"columns": cols, "rows": rows}

def split_simple_vals(text: str) -> list:
    """Split comma-separated values respecting quotes and parens."""
    parts = []
    cur = []
    depth = 0
    in_q = False
    for ch in text:
        if ch == "'":
            in_q = not in_q
            cur.append(ch)
        elif not in_q:
            if ch == "(":
                depth += 1; cur.append(ch)
            elif ch == ")":
                depth -= 1; cur.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts

def clean_val(v: str):
    """Clean a SQL value string → Python object."""
    v = v.strip()
    if v.upper() == "NULL" or v == "":
        return None
    if v.startswith("'") and v.endswith("'"):
        inner = v[1:-1]
        inner = inner.replace("''", "'").replace('\\"', '"').replace("\\\\", "\\")
        return inner
    if v.upper() == "TRUE":
        return True
    if v.upper() == "FALSE":
        return False
    try:
        if "." in v:
            return float(v)
        return int(v)
    except:
        return v

def mk_uuid() -> str:
    return uuid.uuid4().hex

# ============================================================
# MAIN IMPORT
# ============================================================

# 1) agencies — simple, PK = agency_code (same in both schemas)
print("Importing agencies...")
agencies_imported = 0
with Session(engine) as session:
    # Read all agencies from seed
    agency_data = {}
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO agencies "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        code = d.get("agency_code")
                        if code:
                            agency_data[code] = d

    for code, d in agency_data.items():
        existing = session.query(Agency).filter_by(agency_code=code).first()
        if not existing:
            agency = Agency(
                id=mk_uuid(),
                agency_code=code,
                agency_name=d.get("agency_name", ""),
                ministry=d.get("ministry", ""),
                keyword=d.get("keyword"),
            )
            session.add(agency)
            agencies_imported += 1
    session.commit()
print(f"  {agencies_imported} agencies imported")

# 2) zones — need ID mapping (SERIAL INT → UUID)
print("Importing zones...")
zone_id_map = {}  # int → str (uuid)
zones_imported = 0
with Session(engine) as session:
    zone_rows = []
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO zones "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        zone_rows.append(d)

    for d in zone_rows:
        old_id = d.get("zone_id")
        name = d.get("zone_name", "")
        existing = session.query(Zone).filter_by(zone_name=name).first()
        if not existing:
            nd = Zone(
                id=mk_uuid(),
                zone_name=name,
                zone_type=d.get("zone_type", "district"),
                parent_zone_id=None,  # resolved in second pass
            )
            session.add(nd)
            session.flush()
            if old_id:
                zone_id_map[int(old_id)] = nd.id
        else:
            if old_id:
                zone_id_map[int(old_id)] = existing.id
        zones_imported += 1

    # Second pass: resolve parent_zone_id
    for d in zone_rows:
        parent_int = d.get("parent_zone_id")
        if parent_int is not None:
            name = d.get("zone_name", "")
            zone = session.query(Zone).filter_by(zone_name=name).first()
            if zone and int(parent_int) in zone_id_map:
                zone.parent_zone_id = zone_id_map[int(parent_int)]
    session.commit()
print(f"  {zones_imported} zones imported ({len(zone_id_map)} mapped)")

# 3) tenders → procurement_tenders
print("Importing tenders → procurement_tenders...")
tender_id_map = {}  # int → uuid
tenders_imported = 0
with Session(engine) as session:
    tender_rows = []
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO tenders "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        tender_rows.append(d)

    for d in tender_rows:
        old_id = d.get("tender_id")
        pkg = d.get("package_no", "")
        if not pkg:
            continue
        existing = session.query(ProcurementTender).filter_by(package_no=pkg).first()
        if not existing:
            zone_old = d.get("zone_id")
            zone_uuid = zone_id_map.get(int(zone_old)) if zone_old is not None else None
            nt = ProcurementTender(
                id=mk_uuid(),
                package_no=pkg,
                title=d.get("title"),
                agency_code=d.get("agency_code"),
                zone_id=zone_uuid,
                pe_office=d.get("pe_office"),
                procurement_method=d.get("procurement_method"),
                match_type=d.get("match_type", "unmatched_app"),
            )
            session.add(nt)
            session.flush()
            if old_id:
                tender_id_map[int(old_id)] = nt.id
            tenders_imported += 1
        else:
            if old_id:
                tender_id_map[int(old_id)] = existing.id
            tenders_imported += 1

        if tenders_imported % 10000 == 0:
            session.commit()
            print(f"    {tenders_imported} tenders processed...")

    session.commit()
print(f"  {tenders_imported} tenders processed ({len(tender_id_map)} mapped)")

# 4) app_records
print("Importing app_records...")
app_imported = 0
with Session(engine) as session:
    app_rows = []
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO app_records "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        app_rows.append(d)

    for d in app_rows:
        old_tid = d.get("tender_id")
        tender_uuid = tender_id_map.get(int(old_tid)) if old_tid is not None else None
        if not tender_uuid:
            continue
        existing = session.query(APPRecord).filter_by(procurement_tender_id=tender_uuid).first()
        if existing:
            continue
        na = APPRecord(
            id=mk_uuid(),
            procurement_tender_id=tender_uuid,
            source_tender_id=str(d.get("source_tender_id", "")),
            title=d.get("title"),
            estimated_cost_bdt=float(d.get("estimated_cost_bdt", 0) or 0),
            status=d.get("status"),
            published_date=d.get("published_date"),
            deadline=d.get("deadline"),
            financial_year=d.get("financial_year"),
            app_code=d.get("app_code"),
            category=d.get("category"),
        )
        session.add(na)
        app_imported += 1
        if app_imported % 10000 == 0:
            session.commit()
            print(f"    {app_imported} app_records...")
    session.commit()
print(f"  {app_imported} app_records imported")

# 5) award_records → award_records_v2
print("Importing award_records → award_records_v2...")
award_imported = 0
with Session(engine) as session:
    award_rows = []
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO award_records "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        award_rows.append(d)

    for d in award_rows:
        old_tid = d.get("tender_id")
        tender_uuid = tender_id_map.get(int(old_tid)) if old_tid is not None else None
        if not tender_uuid:
            continue
        pkg = d.get("package_no", "")
        cname = d.get("contractor_name", "")
        if existing := session.query(AwardRecordV2).filter_by(
            procurement_tender_id=tender_uuid, contractor_name=cname
        ).first():
            continue
        na = AwardRecordV2(
            id=mk_uuid(),
            procurement_tender_id=tender_uuid,
            source_tender_id=str(d.get("source_tender_id", "")),
            package_no=pkg,
            title=d.get("title"),
            contractor_name=cname,
            amount_bdt=float(d.get("amount_bdt", 0) or 0),
            procurement_method=d.get("procurement_method"),
            award_date=d.get("award_date"),
            detail_url=d.get("detail_url"),
            agency_code=d.get("agency_code"),
            district=d.get("district"),
            pe_office=d.get("pe_office"),
        )
        session.add(na)
        award_imported += 1
        if award_imported % 10000 == 0:
            session.commit()
            print(f"    {award_imported} award_records...")
    session.commit()
print(f"  {award_imported} award_records imported")

# 6) contractors
print("Importing contractors...")
contractor_id_map = {}
contractors_imported = 0
with Session(engine) as session:
    c_rows = []
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO contractors "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        c_rows.append(d)

    for d in c_rows:
        old_id = d.get("contractor_id")
        name = d.get("contractor_name", "")
        if not name:
            continue
        existing = session.query(Contractor).filter_by(contractor_name=name).first()
        if not existing:
            nc = Contractor(
                id=mk_uuid(),
                contractor_name=name,
                total_contracts=int(d.get("total_contracts", 0) or 0),
                total_amount_bdt=float(d.get("total_amount_bdt", 0) or 0),
                agencies_worked=d.get("agencies_worked"),  # TEXT[] from PG, stored as JSON
                districts_worked=d.get("districts_worked"),
                avg_npp=float(d.get("avg_npp", 0) or 0),
                first_award_date=d.get("first_award_date"),
                last_award_date=d.get("last_award_date"),
            )
            session.add(nc)
            session.flush()
            if old_id:
                contractor_id_map[int(old_id)] = nc.id
        else:
            if old_id:
                contractor_id_map[int(old_id)] = existing.id
        contractors_imported += 1
    session.commit()
print(f"  {contractors_imported} contractors ({len(contractor_id_map)} mapped)")

# 7) procurement_lifecycle
print("Importing procurement_lifecycle...")
pl_imported = 0
with Session(engine) as session:
    pl_rows = []
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO procurement_lifecycle "):
                line_s = strip_pg(line)
                tbl, parsed = parse_insert(line_s)
                if parsed:
                    for row in parsed["rows"]:
                        d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                        pl_rows.append(d)

    for d in pl_rows:
        pkg = d.get("package_no", "")
        if not pkg:
            continue
        existing = session.query(ProcurementLifecycle).filter_by(package_no=pkg).first()
        if existing:
            continue
        npl = ProcurementLifecycle(
            id=mk_uuid(),
            package_no=pkg,
            agency_code=d.get("agency_code"),
            zone_name=d.get("zone_name"),
            title=d.get("title"),
            estimated_cost_bdt=float(d.get("estimated_cost_bdt", 0) or 0),
            award_amount_bdt=float(d.get("award_amount_bdt", 0) or 0),
            npp_ratio=float(d.get("npp_ratio", 0) or 0),
            winner=d.get("winner"),
            award_date=d.get("award_date"),
            procurement_method=d.get("procurement_method"),
            pe_office=d.get("pe_office"),
            match_type=d.get("match_type", "unmatched_app"),
            data_source=d.get("data_source", "app_only"),
        )
        session.add(npl)
        pl_imported += 1
        if pl_imported % 10000 == 0:
            session.commit()
            print(f"    {pl_imported} lifecycle...")
    session.commit()
print(f"  {pl_imported} lifecycle records imported")

# 8) contractor_dna — contains subqueries like (SELECT contractor_id FROM contractors WHERE contractor_name = '...')
print("Importing contractor_dna...")
dna_imported = 0
from sqlalchemy import text as sql_text
with Session(engine) as session:
    with open(SEED_PATH, encoding="utf-8") as f:
        for line in f:
            if line.startswith("INSERT INTO contractor_dna "):
                # Extract contractor_name from subquery
                m_name = re.search(r"contractor_name\s*=\s*'([^']+)'", line)
                if not m_name:
                    continue
                cname = m_name.group(1)
                # Map to our UUID-based contractor_id
                contractor = session.query(Contractor).filter_by(contractor_name=cname).first()
                if not contractor:
                    continue
                contractor_uuid = contractor.id
                # Parse column list (excluding contractor_id which has subquery)
                m_cols = re.search(r"\(([^)]+)\)\s*VALUES", line)
                if not m_cols:
                    continue
                cols = [c.strip() for c in m_cols.group(1).split(",")]
                # Remove ON CONFLICT suffix
                clean = re.sub(r" ON CONFLICT \([^)]+\) DO UPDATE SET .*", "", line)
                clean = clean.strip().rstrip(";")
                # Find the outer value parens manually (need to handle subquery inside)
                vi = clean.rfind("VALUES")
                if vi < 0:
                    continue
                after_vals = clean[vi + 6:].strip()
                if not after_vals.startswith("("):
                    continue
                # Find matching close paren
                depth = 0
                close = -1
                for k, ch in enumerate(after_vals):
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            close = k
                            break
                if close < 0:
                    continue
                inner = after_vals[1:close]
                # Split inner by comma respecting nesting
                vals = []
                cur = []
                dq = 0
                sq = False
                for ch in inner:
                    if ch == "'" and not sq:
                        sq = True; cur.append(ch); continue
                    if ch == "'" and sq:
                        sq = False; cur.append(ch); continue
                    if sq:
                        cur.append(ch); continue
                    if ch == "(":
                        dq += 1; cur.append(ch); continue
                    if ch == ")":
                        dq -= 1; cur.append(ch); continue
                    if ch == "," and dq == 0:
                        vals.append("".join(cur).strip()); cur = []; continue
                    cur.append(ch)
                if cur:
                    vals.append("".join(cur).strip())
                # Build dict from cols ignoring contractor_id (first col, has subquery)
                if len(vals) > 1:
                    d = dict(zip(cols[1:], [clean_val(v) for v in vals[1:]]))
                else:
                    d = {}
                existing = session.query(ContractorDNA).filter_by(contractor_id=contractor_uuid).first()
                if existing:
                    continue
                nd = ContractorDNA(
                    id=mk_uuid(),
                    contractor_id=contractor_uuid,
                    total_contracts=int(d.get("total_contracts", 0) or 0),
                    total_amount_bdt=float(d.get("total_amount_bdt", 0) or 0),
                    avg_award_bdt=float(d.get("avg_award_bdt", 0) or 0),
                    agencies_worked=int(d.get("agencies_worked", 0) or 0),
                    districts_worked=int(d.get("districts_worked", 0) or 0),
                    preferred_agency=d.get("preferred_agency"),
                    preferred_zone=d.get("preferred_zone"),
                    avg_npp=float(d.get("avg_npp", 0) or 0),
                    npp_volatility=float(d.get("npp_volatility", 0) or 0),
                    win_rate=float(d.get("win_rate", 0) or 0),
                    avg_discount_pct=float(d.get("avg_discount_pct", 0) or 0),
                    first_award_date=d.get("first_award_date"),
                    last_award_date=d.get("last_award_date"),
                )
                session.add(nd)
                dna_imported += 1
                if dna_imported % 500 == 0:
                    session.commit()
    session.commit()
print(f"  {dna_imported} contractor_dna records imported")

# 9-12: Intelligence tables
def import_intel_table(table_name, orm_class, id_field, fkey_map=None):
    count = 0
    # Get ORM column names (excluding auto-managed)
    orm_cols = set(c.name for c in orm_class.__table__.columns)
    orm_cols.discard("id")
    orm_cols.discard("created_at")
    orm_cols.discard("updated_at")
    with Session(engine) as session:
        rows = []
        with open(SEED_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith(f"INSERT INTO {table_name} "):
                    line_s = strip_pg(line)
                    tbl, parsed = parse_insert(line_s)
                    if parsed:
                        for row in parsed["rows"]:
                            d = dict(zip(parsed["columns"], [clean_val(v) for v in row]))
                            rows.append(d)

        for d in rows:
            # Skip columns not in ORM model
            kwargs = {"id": mk_uuid()}
            for col, val in d.items():
                if col == id_field:
                    continue
                if col in orm_cols:
                    kwargs[col] = val
            instance = orm_class(**kwargs)
            session.add(instance)
            count += 1
            if count % 1000 == 0:
                session.commit()
                print(f"    {count} {table_name}...")
        session.commit()
    print(f"  {count} {table_name} records imported")
    return count

import_intel_table("agency_intelligence", AgencyIntelligence, "intelligence_id")
import_intel_table("zone_intelligence", ZoneIntelligence, "intelligence_id")
import_intel_table("discount_patterns", DiscountPattern, "pattern_id")
import_intel_table("award_intelligence", AwardIntelligence, "intelligence_id")

print("\n=== SEED IMPORT COMPLETE ===")
print(f"Database: {DB_PATH}")

# Print summary
summary = dict(
    agencies=agencies_imported,
    zones=zones_imported,
    tenders=tenders_imported,
    app_records=app_imported,
    award_records=award_imported,
    contractors=contractors_imported,
    procurement_lifecycle=pl_imported,
    contractor_dna=dna_imported,
)
for tbl, cnt in summary.items():
    print(f"  {tbl}: {cnt}")
