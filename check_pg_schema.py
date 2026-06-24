"""Check actual PG column names for key tables."""
import psycopg2
c = psycopg2.connect('postgresql://procurementflow:procurementflow@localhost:5432/procurementflow')
cur = c.cursor()

tables = ['procurement_tenders', 'award_records_v2', 'contractor_dna', 'contractors']
for t in tables:
    cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{t}' ORDER BY ordinal_position")
    cols = cur.fetchall()
    print(f'{t} ({len(cols)} cols):')
    for col in cols:
        print(f'  {col[0]}: {col[1]}')
    print()

c.close()
