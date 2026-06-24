"""Test endpoints against running server."""
import urllib.request, json

tests = [
    ('/api/health', 'health'),
    ('/api/stats', 'stats'),
    ('/api/agents', 'agents'),
    ('/api/brain/status', 'brain'),
    ('/api/thoughts/stats', 'thoughts'),
    ('/api/clients', 'clients'),
    ('/api/tenders?limit=1', 'tenders'),
    ('/api/awards?limit=1', 'awards'),
    ('/api/contractors?limit=1', 'contractors'),
    ('/api/agencies', 'agencies'),
    ('/api/pipeline/phases', 'pipeline'),
    ('/api/engineer/status', 'engineer'),
    ('/api/watchdog/health', 'watchdog'),
    ('/api/sor/zones', 'sor'),
    ('/api/intel/contractors?limit=1', 'intel'),
    ('/api/ppr2025/evaluations?limit=1', 'ppr'),
    ('/api/brain/knowledge', 'knowledge'),
    ('/api/sor/status', 'sor-status'),
    ('/api/knowledge-graph/stats', 'kg'),
]

passed = 0
failed = 0
for path, name in tests:
    try:
        r = urllib.request.urlopen(f'http://localhost:8001{path}', timeout=15)
        if r.status == 200:
            passed += 1
        else:
            print(f'  [{r.status}] {name}: {path}')
            failed += 1
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 500 and ('operation' in body or 'does not exist' in body):
            print(f'  [SCHEMA] {name}: {body[:80]}...')
        else:
            print(f'  [{e.code}] {name}: {body[:80]}')
        failed += 1
    except Exception as e:
        print(f'  [FAIL] {name}: {e}')
        failed += 1

print(f'\nPassed: {passed}/{len(tests)}, Failed: {failed}/{len(tests)}')
