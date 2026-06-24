"""Start backend and test all endpoints."""
import subprocess, sys, time, urllib.request, json, os, signal

os.environ['PYTHONPATH'] = 'D:\\A1\\procurementflow_final_v3\\procurementflow\\backend'

proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', '8000', '--host', '0.0.0.0'],
    cwd='D:\\A1\\procurementflow_final_v3\\procurementflow',
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env={**os.environ, 'PYTHONPATH': 'D:\\A1\\procurementflow_final_v3\\procurementflow\\backend'}
)

time.sleep(8)

if proc.poll() is not None:
    _, stderr = proc.communicate()
    print("Server died:", stderr.decode()[-1000:])
    sys.exit(1)

ENDPOINTS = [
    '/api/ppr2025/overview',
    '/api/ppr2025/npp-trends?months=12',
    '/api/ppr2025/contractors?limit=3',
    '/api/ppr2025/award-stats',
    '/api/ppr2025/document-checklist?tender_type=works',
    '/api/analytics/overview',
    '/api/analytics/npp-trends?months=12',
    '/api/analytics/agency-comparison',
    '/api/analytics/contractor-leaderboard?limit=3',
    '/api/analytics/win-rate',
    '/api/analytics/discount-distribution',
    '/api/deptree/ministries',
    '/api/deptree/targets',
    '/api/predict/npp/stats',
    '/api/predict/bid/stats',
    '/api/predict/bid/cross-check/auto',
    '/api/executive/overview',
    '/api/intel/contractors?limit=3',
    '/api/intel/npp-trends',
]

BASE = 'http://localhost:8000'
all_ok = True
for ep in ENDPOINTS:
    url = BASE + ep
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        data = json.loads(resp.read())
        ok = True
        if isinstance(data, dict):
            ok = 'error' not in data
            if 'success' in data:
                ok = data['success']
        print(f'[{"OK" if ok else "FAIL"}] {ep}')
        if not ok:
            print(f'  Response: {str(data)[:200]}')
        all_ok = all_ok and ok
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        print(f'[ERR]  {ep} (HTTP {e.code}): {body}')
        all_ok = False
    except Exception as e:
        print(f'[ERR]  {ep}: {e}')
        all_ok = False

proc.terminate()
time.sleep(1)
try:
    _, stderr = proc.communicate(timeout=5)
except:
    proc.kill()
    _, stderr = proc.communicate(timeout=3)
print("\n=== STDERR (last 2000) ===")
print((stderr or b"").decode()[-2000:])
print()
if all_ok:
    print('ALL ENDPOINTS PASSED!')
else:
    print('Some endpoints failed.')
    sys.exit(1)
