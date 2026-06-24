"""Start backend, capture stderr, test analytics/npp-trends."""
import subprocess, sys, time, urllib.request, json, os

os.environ['PYTHONPATH'] = 'D:\\A1\\procurementflow_final_v3\\procurementflow\\backend'

proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', '8000', '--host', '0.0.0.0'],
    cwd='D:\\A1\\procurementflow_final_v3\\procurementflow',
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env={**os.environ, 'PYTHONPATH': 'D:\\A1\\procurementflow_final_v3\\procurementflow\\backend'}
)

time.sleep(8)

# Check if process is still alive
if proc.poll() is not None:
    stdout, stderr = proc.communicate()
    print("SERVER DIED!")
    print("STDOUT:", stdout.decode()[-1000:])
    print("STDERR:", stderr.decode()[-2000:])
    sys.exit(1)

try:
    resp = urllib.request.urlopen('http://localhost:8000/api/analytics/npp-trends?months=12', timeout=10)
    print('SUCCESS:', resp.read().decode()[:500])
except urllib.error.HTTPError as e:
    print(f'HTTP {e.code}:', e.read().decode()[:500])
except Exception as e:
    print(f'ERROR: {e}')

time.sleep(1)
proc.terminate()
stdout, stderr = proc.communicate(timeout=5)
print("\n=== STDERR (last 3000 chars) ===")
print(stderr.decode()[-3000:])
