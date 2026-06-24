"""
[DEPRECATED] SQLite-based contractor DNA update.
All data now goes directly to PostgreSQL via ETL pipelines.
Keeping for reference only — do not run.
"""
import json, os, re
from datetime import datetime
from collections import defaultdict

raise RuntimeError("DEPRECATED: Use PostgreSQL ETL pipelines instead. See backend/scripts/")

def clean_name(name):
    if not name:
        return ''
    return re.sub(r'\s*\(.*?\).*', '', name).strip().upper()
def normalize_name(name):
    return re.sub(r'[^A-Z0-9]', '', clean_name(name))

print('=== Loading Award Data ===')
award_by_tid_pkg = {}
award_by_tid = {}
for fname in os.listdir(AWARD_DIR):
    if not fname.endswith('.json') or fname == '_checkpoint.json':
        continue
    with open(os.path.join(AWARD_DIR, fname), encoding='utf-8') as f:
        data = json.load(f)
    records = data if isinstance(data, list) else []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        tid = rec.get('tender_id', '').strip()
        pkg = rec.get('package_no', '').strip()
        name = rec.get('contractor_name', '').strip().upper()
        try:
            raw_amt = float(str(rec.get('amount_bdt', 0)).replace(',', ''))
        except:
            raw_amt = 0.0
        rec['_raw_amount'] = raw_amt
        rec['_clean_contractor'] = clean_name(name)
        rec['_normalized_contractor'] = normalize_name(name)
        if tid:
            key = (tid, pkg)
            if key not in award_by_tid_pkg:
                award_by_tid_pkg[key] = rec
            if tid not in award_by_tid:
                award_by_tid[tid] = rec

print(f'  {len(award_by_tid)} by tender_id, {len(award_by_tid_pkg)} by (tender_id, package_no)')

print('\n=== Loading APP Data ===')
app_by_pkg = {}
for fname in os.listdir(APP_DIR):
    if not fname.endswith('.json') or fname == '_checkpoint.json':
        continue
    with open(os.path.join(APP_DIR, fname), encoding='utf-8') as f:
        data = json.load(f)
    records = data if isinstance(data, list) else []
    for rec in records:
        pkg = rec.get('package_no', '').strip()
        if pkg:
            app_by_pkg[pkg] = rec
print(f'  {len(app_by_pkg)} APP records')

print('\n=== Processing Opening Reports ===')
json_dir = os.path.join(OUTPUT_DIR, 'JSON')

win_count = defaultdict(int)
bid_count = defaultdict(int)
win_amount = defaultdict(float)
bid_amount = defaultdict(float)
discounts = defaultdict(list)
agencies = defaultdict(set)
zones = defaultdict(set)
districts = defaultdict(set)
first_date = {}
last_date = {}

def find_winner_in_price_bids(price_bids, award_contractor_normalized):
    if not price_bids or not award_contractor_normalized:
        return None
    for bid in price_bids:
        bid_name_norm = normalize_name(bid.get('name', ''))
        if bid_name_norm == award_contractor_normalized:
            try:
                quoted = float(str(bid.get('quoted_amount', '0')).replace(',', ''))
            except:
                quoted = 0.0
            try:
                disc = float(str(bid.get('discount_pct', '0')).replace(',', ''))
            except:
                disc = 0.0
            return {'name': bid.get('name',''), 'quoted': quoted, 'discount': disc}
        # Also try partial match
        if award_contractor_normalized and len(award_contractor_normalized) > 8:
            if bid_name_norm and (bid_name_norm in award_contractor_normalized or award_contractor_normalized in bid_name_norm):
                try:
                    quoted = float(str(bid.get('quoted_amount', '0')).replace(',', ''))
                except:
                    quoted = 0.0
                return {'name': bid.get('name',''), 'quoted': quoted, 'discount': 0}
    return None

for fname in os.listdir(json_dir):
    if not fname.endswith('.json'):
        continue
    with open(os.path.join(json_dir, fname), encoding='utf-8') as f:
        meta = json.load(f)
    
    tender_id = meta.get('tender_id', '')
    package_no = meta.get('package_no', '')
    opening_date = meta.get('opening_date', '') or meta.get('closing_date', '')
    zone = meta.get('zone', '')
    district = meta.get('district', zone)
    pe = meta.get('procuring_entity', '')
    price_bids = meta.get('price_bids', [])
    bidders_list = meta.get('bidders', [])
    original_est = meta.get('estimated_cost', None)
    
    # Match estimate from APP data (trust APP data over any prior value)
    est_cost = None
    if package_no and package_no in app_by_pkg:
        try:
            est_cost = float(str(app_by_pkg[package_no].get('estimated_cost_bdt', 0)).replace(',', ''))
        except:
            est_cost = None
    
    # Match award by tender_id + package_no, then fallback to tender_id only
    award_info = award_by_tid_pkg.get((tender_id, package_no))
    if not award_info:
        award_info = award_by_tid.get(tender_id)
    else:
        # We found exact match, prefer it
        pass
    
    # Scale award amount: if raw amount is suspiciously small compared to estimate, multiply by 100
    scaled_amount = 0.0
    if award_info and isinstance(award_info, dict):
        raw_amt = award_info.get('_raw_amount', 0)
        scaled_amount = raw_amt  # assume already correct for now
        if est_cost and raw_amt > 0 and raw_amt < est_cost / 5:
            scaled_amount = raw_amt * 100
        elif est_cost and raw_amt > 0 and raw_amt > est_cost * 10:
            scaled_amount = raw_amt / 100
    
    # Collect all bidders
    for bidder in bidders_list:
        bname = clean_name(bidder.get('name', ''))
        if bname:
            bid_count[bname] += 1
            if zone:
                zones[bname].add(zone)
            if district:
                districts[bname].add(district)
            if pe:
                agencies[bname].add(pe)
            if opening_date:
                if bname not in first_date or opening_date < first_date[bname]:
                    first_date[bname] = opening_date
                if bname not in last_date or opening_date > last_date[bname]:
                    last_date[bname] = opening_date
    
    # Track price bids
    for bid in price_bids:
        bname = clean_name(bid.get('name', ''))
        if not bname:
            continue
        try:
            quoted = float(str(bid.get('quoted_amount', '0')).replace(',', ''))
        except:
            quoted = 0.0
        bid_amount[bname] += quoted
        try:
            disc = float(str(bid.get('discount_pct', '0')).replace(',', ''))
        except:
            disc = 0.0
        if disc > 0:
            discounts[bname].append(disc)
    
    # Identify winner
    award_contractor_name = None
    if award_info and isinstance(award_info, dict):
        award_contractor_name = award_info.get('_clean_contractor', '')
    
    winner_name = None
    winner_quoted = 0.0
    winner_discount = 0.0
    
    if award_contractor_name:
        winner_name = award_contractor_name
        # Find this name's quoted amount in price_bids
        winner_match = find_winner_in_price_bids(price_bids, normalize_name(award_contractor_name))
        if winner_match:
            winner_quoted = winner_match['quoted']
            winner_discount = winner_match['discount']
        else:
            # Try matching by bidder_name in bidders list
            norm_winner = normalize_name(award_contractor_name)
            for b in bidders_list:
                bname_norm = normalize_name(b.get('name', ''))
                if bname_norm and (bname_norm == norm_winner or (norm_winner in bname_norm) or (bname_norm in norm_winner)):
                    winner_name = clean_name(b.get('name', ''))
                    break
    
    if winner_name:
        win_count[winner_name] += 1
        win_amount[winner_name] += scaled_amount
        if zone:
            zones[winner_name].add(zone)
        if district:
            districts[winner_name].add(district)
        if pe:
            agencies[winner_name].add(pe)
        if opening_date:
            if winner_name not in first_date or opening_date < first_date[winner_name]:
                first_date[winner_name] = opening_date
            if winner_name not in last_date or opening_date > last_date[winner_name]:
                last_date[winner_name] = opening_date
    
    # Update JSON metadata
    meta['estimated_cost'] = est_cost
    if award_info and isinstance(award_info, dict):
        aff = award_info.get('_clean_contractor', '')
        meta['award_winner'] = meta.get('award_winner', aff or award_info.get('contractor_name', ''))
        meta['award_amount'] = scaled_amount
        meta['winner_quoted'] = winner_quoted
        meta['winner_discount_pct'] = winner_discount
    
    with open(os.path.join(json_dir, fname), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, default=str)

print(f'  Awards matched: {len(win_count)} winners found')

print('\n=== Updating Database ===')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
now = datetime.now().isoformat()

all_names = set(list(bid_count.keys()) + list(win_count.keys()))
updated = 0
inserted = 0

for name in all_names:
    wins = win_count.get(name, 0)
    bids = bid_count.get(name, 0)
    win_amt = win_amount.get(name, 0)
    bid_amt = bid_amount.get(name, 0)
    ag_list = list(agencies.get(name, set()))
    zn_list = list(zones.get(name, set()))
    dist_list = list(districts.get(name, set()))
    disc_list = discounts.get(name, [])
    avg_disc = round(sum(disc_list) / len(disc_list), 2) if disc_list else 0.0
    fd = first_date.get(name, '')
    ld = last_date.get(name, '')
    wr = round(wins / bids, 4) if bids > 0 else 0.0
    avg_amt = round(win_amt / wins, 2) if wins > 0 else 0.0
    
    c.execute('SELECT id FROM contractors WHERE contractor_name = ?', (name,))
    existing = c.fetchone()
    
    if existing:
        cid = existing[0]
        c.execute('''UPDATE contractors SET
            total_contracts = ?, total_amount_bdt = ?, avg_npp = ?,
            agencies_worked = ?, districts_worked = ?,
            first_award_date = ?, last_award_date = ?,
            updated_at = ?
            WHERE contractor_name = ?''',
            (wins, win_amt, avg_amt,
             json.dumps(ag_list), json.dumps(dist_list),
             fd, ld, now, name))
        c.execute('''UPDATE contractor_dna SET
            total_contracts = ?, total_amount_bdt = ?,
            avg_award_bdt = ?, win_rate = ?,
            agencies_worked = ?, districts_worked = ?,
            avg_discount_pct = ?,
            first_award_date = ?, last_award_date = ?,
            updated_at = ?
            WHERE contractor_id = ?''',
            (wins, win_amt, avg_amt, wr,
             len(ag_list), len(dist_list), avg_disc,
             fd, ld, now, cid))
        updated += 1
    else:
        cid = f'C{name[:20]}{fd[:8] if fd else "00000000"}'
        c.execute('''INSERT INTO contractors
            (contractor_name, total_contracts, total_amount_bdt, avg_npp,
             agencies_worked, districts_worked, first_award_date, last_award_date,
             created_at, updated_at, id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, wins, win_amt, avg_amt,
             json.dumps(ag_list), json.dumps(dist_list),
             fd, ld, now, now, cid))
        dna_id = f'DNA{cid}'
        c.execute('''INSERT INTO contractor_dna
            (contractor_id, total_contracts, total_amount_bdt, avg_award_bdt,
             agencies_worked, districts_worked, avg_npp, npp_volatility,
             win_rate, avg_discount_pct, first_award_date, last_award_date,
             created_at, updated_at, id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (cid, wins, win_amt, avg_amt,
             len(ag_list), len(dist_list),
             avg_amt, 0.0,
             wr, avg_disc, fd, ld, now, now, dna_id))
        inserted += 1

conn.commit()
conn.close()

print(f'  Updated: {updated}, Inserted: {inserted}')
print(f'\n=== Final Contractor DNA Summary ===')
print(f'Total unique contractors: {len(all_names)}')
print(f'With award wins: {len(win_count)}')
print(f'With bid data: {len(bid_count)}')

if win_count:
    print(f'\nTop 10 by wins:')
    for name, cnt in sorted(win_count.items(), key=lambda x: -x[1])[:10]:
        amt = win_amount.get(name, 0)
        bids = bid_count.get(name, 0)
        wr = f'{cnt/bids*100:.1f}%' if bids > 0 else 'N/A'
        print(f'  {name[:40]:40s} wins={cnt:2d} bids={bids:3d} rate={wr:>7s} amount={amt:>15,.2f}')
    
    print(f'\nTop 10 by amount:')
    for name, amt in sorted(win_amount.items(), key=lambda x: -x[1])[:10]:
        cnt = win_count.get(name, 0)
        bids = bid_count.get(name, 0)
        print(f'  {name[:40]:40s} amount={amt:>15,.2f} wins={cnt:2d} bids={bids:3d}')
