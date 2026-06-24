"""Test API endpoints in detail."""
import urllib.request, json

endpoints = [
    '/api/brain/status',
    '/api/brain/memory',
    '/api/intel/contractors/stats',
    '/api/intel/contractors?limit=1',
    '/api/tenders?limit=1',
    '/api/awards?limit=1',
    '/api/contractors?limit=1',
    '/api/agents',
]

for path in endpoints:
    try:
        r = urllib.request.urlopen(f'http://localhost:8000{path}', timeout=10)
        data = r.read().decode()
        if data:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                # Check for error key
                if 'error' in parsed or 'detail' in parsed:
                    print(f'[ERR] {path}: {parsed.get("error", parsed.get("detail", str(parsed)))[:200]}')
                else:
                    print(f'[OK] {path}: keys={list(parsed.keys())[:5]}')
            else:
                print(f'[OK] {path}: {str(parsed)[:100]}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'[HTTP {e.code}] {path}: {body[:200]}')
    except Exception as e:
        print(f'[FAIL] {path}: {e}')
