import os
import sys
sys.path.insert(0, 'backend')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://procurementflow:procurementflow@localhost:5432/procurementflow'
os.environ['SYNC_DATABASE_URL'] = 'postgresql+psycopg2://procurementflow:procurementflow@localhost:5432/procurementflow'

from app.db.database import get_sync_engine
from sqlalchemy import text

eng = get_sync_engine()
with eng.connect() as conn:
    r = conn.execute(text('SELECT COUNT(*) FROM contractor_dna'))
    print(f'Total contractor_dna: {r.scalar()}')
    r = conn.execute(text('SELECT COUNT(*) FROM contractor_dna WHERE health_score IS NOT NULL'))
    print(f'With health_score: {r.scalar()}')
    r = conn.execute(text('SELECT health_score FROM contractor_dna LIMIT 10'))
    for row in r:
        print(f'  {row.health_score}')