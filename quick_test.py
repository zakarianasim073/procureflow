"""Quick endpoint verification for ProcureFlow BD V3"""
import sys, requests

BASE = "http://127.0.0.1:8000"
TIMEOUT = 8
pass_count = fail_count = 0

def test(method, path, expect=200):
    global pass_count, fail_count
    url = f"{BASE}{path}"
    label = f"{method} {path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=TIMEOUT)
        else:
            r = requests.post(url, json={}, timeout=TIMEOUT)
        ok = r.status_code == expect
        print(f"  {'OK' if ok else 'FAIL'} {label} -> {r.status_code}" + ("" if ok else f" (expected {expect})"))
        if ok: pass_count += 1
        else: fail_count += 1
    except Exception as e:
        print(f"  FAIL {label} -> {e}")
        fail_count += 1

# Core system
test("GET", "/api/health")
test("GET", "/api/stats")
test("GET", "/api/agents")
test("GET", "/api/pipeline/phases")
test("GET", "/api/")

# Data endpoints
test("GET", "/api/tenders?limit=2")
test("GET", "/api/awards?limit=2")
test("GET", "/api/awards/stats")
test("GET", "/api/contractors?limit=2")
test("GET", "/api/opening-reports?limit=2")

# Knowledge graph
test("GET", "/api/knowledge-graph/stats")
test("GET", "/api/knowledge-graph/syndicate-patterns")

# Analytics
test("GET", "/api/analytics/overview")
test("GET", "/api/analytics/contractor-leaderboard?limit=3")
test("GET", "/api/dashboard/stats")

# Auth
test("POST", "/api/auth/login", expect=422)

# PPR2025
test("GET", "/api/ppr2025/overview")
test("GET", "/api/ppr2025/contractors?limit=3")
test("GET", "/api/ppr2025/award-stats")

# Intel
test("GET", "/api/intel/contractors?limit=2")
test("GET", "/api/intel/import/status")

# Predictions
test("GET", "/api/predict/npp/stats")
test("GET", "/api/predict/bid/stats")

# Executive
test("GET", "/api/executive/overview")

# SOR
test("GET", "/api/sor/agencies")
test("GET", "/api/sor/zones")

# Market
test("GET", "/api/market/rates")
test("GET", "/api/market/indices")

# Deptree
test("GET", "/api/deptree/ministries")
test("GET", "/api/deptree/targets")

# Watchdog & Engineer
test("GET", "/api/watchdog/health")
test("GET", "/api/watchdog/dashboard")
test("GET", "/api/engineer/status")

# Thoughts & Brain
test("GET", "/api/thoughts/stats")
test("GET", "/api/brain/status")

# Summary
total = pass_count + fail_count
print(f"\n{'='*50}")
print(f"  {pass_count} PASS / {fail_count} FAIL / {total} TOTAL")
print(f"{'='*50}")
sys.exit(0 if fail_count == 0 else 1)
