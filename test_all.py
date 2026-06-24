"""Comprehensive API route test using TestClient."""
import os, sys
sys.path.insert(0, 'backend')
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://procurementflow:procurementflow@localhost:5432/procurementflow'
os.environ['SYNC_DATABASE_URL'] = 'postgresql+psycopg2://procurementflow:procurementflow@localhost:5432/procurementflow'

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

tests = [
    ('GET', '/api/health'),
    ('GET', '/api/stats'),
    ('GET', '/api/agents'),
    ('GET', '/api/brain/status'),
    ('GET', '/api/thoughts/stats'),
    ('GET', '/api/clients'),
    ('GET', '/api/tenders?limit=1'),
    ('GET', '/api/awards?limit=1'),
    ('GET', '/api/contractors?limit=1'),
    ('GET', '/api/agencies'),
    ('GET', '/api/pipeline/phases'),
    ('GET', '/api/engineer/status'),
    ('GET', '/api/watchdog/health'),
    ('GET', '/api/sor/zones'),
    ('GET', '/api/intel/contractors?limit=1'),
    ('GET', '/api/ppr2025/evaluations?limit=1'),
    ('GET', '/api/brain/knowledge'),
    ('GET', '/api/sor/status'),
    ('GET', '/api/knowledge-graph/stats'),
]

passed = 0
failed = 0
for method, path in tests:
    try:
        r = client.request(method, path)
        if r.status_code == 200:
            passed += 1
            # Check for error in response body
            try:
                data = r.json()
                if isinstance(data, dict):
                    if data.get('error') or data.get('detail'):
                        err = data.get('error') or data.get('detail')
                        if 'does not exist' in str(err) or 'UndefinedColumn' in str(err):
                            print(f'  [SCHEMA] {path}: {str(err)[:80]}')
                            failed += 1
                            passed -= 1
            except Exception:
                pass
        elif r.status_code == 404:
            print(f'  [404] {path}')
            failed += 1
        else:
            print(f'  [{r.status_code}] {path}: {r.text[:100]}')
            failed += 1
    except Exception as e:
        print(f'  [FAIL] {path}: {e}')
        failed += 1

print(f'\nPassed: {passed}/{len(tests)}, Failed: {failed}/{len(tests)}')
