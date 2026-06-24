import os
import sys
sys.path.insert(0, 'backend')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://procurementflow:procurementflow@localhost:5432/procurementflow'
os.environ['SYNC_DATABASE_URL'] = 'postgresql+psycopg2://procurementflow:procurementflow@localhost:5432/procurementflow'

from app.db.database import get_sync_engine
from sqlalchemy import text

eng = get_sync_engine()
with eng.connect() as conn:
    # Distribution
    r = conn.execute(text('''
        SELECT 
            CASE 
                WHEN health_score >= 0.8 THEN 'A (0.8-1.0)'
                WHEN health_score >= 0.6 THEN 'B (0.6-0.8)'
                WHEN health_score >= 0.4 THEN 'C (0.4-0.6)'
                WHEN health_score >= 0.2 THEN 'D (0.2-0.4)'
                ELSE 'F (0.0-0.2)'
            END as grade,
            COUNT(*) as count
        FROM contractor_dna
        WHERE health_score IS NOT NULL
        GROUP BY grade
        ORDER BY grade
    '''))
    print('Health score distribution:')
    for row in r:
        print(f'  {row.grade}: {row.count}')
    
    # Top 10
    r = conn.execute(text('''
        SELECT contractor_id, health_score, total_contracts, total_amount_bdt, completion_rate, on_time_rate
        FROM contractor_dna
        WHERE health_score IS NOT NULL
        ORDER BY health_score DESC
        LIMIT 10
    '''))
    print('\nTop 10 by health_score:')
    for row in r:
        print(f'  {row.contractor_id}: score={row.health_score:.3f}, contracts={row.total_contracts}, total={row.total_amount_bdt:,.0f}, completion={row.completion_rate:.1f}%, on_time={row.on_time_rate:.1f}%')
    
    # Stats
    r = conn.execute(text('''
        SELECT 
            MIN(health_score) as min_score,
            MAX(health_score) as max_score,
            AVG(health_score) as avg_score,
            COUNT(*) as total
        FROM contractor_dna
        WHERE health_score IS NOT NULL
    '''))
    row = r.fetchone()
    print(f'\nStats: min={row.min_score:.3f}, max={row.max_score:.3f}, avg={row.avg_score:.3f}, total={row.total}')