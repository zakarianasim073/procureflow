"""
[DEPRECATED] SQLite-based opening report ingestion.
All data now goes directly to PostgreSQL via ETL pipelines.
Keeping for reference only — do not run.
"""
import json, os, sys, logging, re
from datetime import datetime
log = logging.getLogger(__name__)

raise RuntimeError("DEPRECATED: Use PostgreSQL ETL pipelines instead. See backend/scripts/")

    stats = {'new_contractors': 0, 'new_tenders': 0, 'with_bidders': 0, 'with_price': 0}

    for fname in files:
        if not fname.endswith('.json'):
            continue
        with open(os.path.join(json_dir, fname), encoding='utf-8') as f:
            meta = json.load(f)

        tender_id = meta.get('tender_id', fname.replace('.json', ''))
        package_no = meta.get('package_no', '')
        zone = meta.get('zone', '')
        opening_date = meta.get('opening_date', '') or meta.get('closing_date', '')

        estimated_cost = None
        if package_no and package_no in app_by_pkg:
            estimated_cost = app_by_pkg[package_no].get('estimated_cost_bdt')

        bidders = meta.get('bidders', [])
        price_bids = meta.get('price_bids', [])

        if not bidders and not price_bids:
            continue
        stats['with_bidders'] += 1
        if price_bids:
            stats['with_price'] += 1

        bids_to_process = price_bids if price_bids else bidders
        for bid in bids_to_process:
            name = bid.get('name', '').strip().upper()
            if not name:
                continue
            clean_name = re.sub(r'\s*\(.*?\).*', '', name).strip()
            if not clean_name:
                clean_name = name

            quoted = bid.get('quoted_amount', '0')
            try:
                quoted_val = float(quoted.replace(',', ''))
            except (ValueError, AttributeError):
                quoted_val = 0.0

            discount_pct = bid.get('discount_pct', '0')
            try:
                discount_val = float(discount_pct)
            except (ValueError, AttributeError):
                discount_val = 0.0

            now = datetime.now().isoformat()
            c.execute('SELECT id, total_contracts, total_amount_bdt FROM contractors WHERE contractor_name = ?',
                      (clean_name,))
            existing = c.fetchone()
            if existing:
                cid, t_count, t_amount = existing
                c.execute('''UPDATE contractors SET
                    total_contracts = total_contracts + 1,
                    total_amount_bdt = total_amount_bdt + ?,
                    avg_npp = (total_amount_bdt + ?) / (total_contracts + 1),
                    last_award_date = COALESCE(?, last_award_date, ?),
                    updated_at = ?
                    WHERE contractor_name = ?''',
                    (quoted_val, quoted_val, opening_date, opening_date, now, clean_name))
                c.execute('''UPDATE contractor_dna SET
                    total_contracts = total_contracts + 1,
                    total_amount_bdt = total_amount_bdt + ?,
                    avg_award_bdt = (total_amount_bdt + ?) / (total_contracts + 1),
                    avg_discount_pct = CASE WHEN avg_discount_pct IS NOT NULL
                        THEN (avg_discount_pct + ?) / 2 ELSE ? END,
                    avg_npp = (total_amount_bdt + ?) / (total_contracts + 1),
                    updated_at = ?
                    WHERE contractor_id = ?''',
                    (quoted_val, quoted_val, discount_val, discount_val, quoted_val, now, cid))
            else:
                cid = f'C{clean_name[:20]}{tender_id[:6]}'
                c.execute('''INSERT INTO contractors
                    (contractor_name, total_contracts, total_amount_bdt, avg_npp,
                     first_award_date, last_award_date, created_at, updated_at, id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (clean_name, 1, quoted_val, quoted_val,
                     opening_date, opening_date, now, now, cid))
                dna_id = f'DNA{cid}'
                c.execute('''INSERT INTO contractor_dna
                    (contractor_id, total_contracts, total_amount_bdt, avg_award_bdt,
                     agencies_worked, districts_worked, avg_npp, npp_volatility,
                     win_rate, avg_discount_pct, first_award_date, last_award_date,
                     created_at, updated_at, id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (cid, 1, quoted_val, quoted_val,
                     1, 1 if zone else 0, quoted_val, 0.0,
                     0.5, discount_val, opening_date, opening_date,
                     now, now, dna_id))
                stats['new_contractors'] += 1

    conn.commit()
    log.info(f'\n=== Done ===')
    log.info(f'New contractors: {stats["new_contractors"]}')
    log.info(f'Tenders with bidders: {stats["with_bidders"]}')
    log.info(f'Tenders with price bids: {stats["with_price"]}')
    conn.close()


if __name__ == '__main__':
    ingest()
