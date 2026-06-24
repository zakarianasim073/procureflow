"""Live server test — runs against running uvicorn instance."""
import urllib.request, urllib.error, json, sys, time

BASE = "http://localhost:8000"

def req(method, path, data=None):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=15)
        code = resp.status
        text = resp.read().decode()
    except urllib.error.HTTPError as e:
        code = e.code
        text = e.read().decode()
    except Exception as e:
        return None, str(e)
    try:
        return code, json.loads(text)
    except:
        return code, text[:200]

# Wait for server
for i in range(30):
    try:
        c, _ = req("GET", "/api/health")
        if c == 200:
            print(f"Server ready (attempt {i+1})")
            break
    except:
        pass
    time.sleep(2)
else:
    print("Server not responding after 60s")
    sys.exit(1)

results = []
def test(label, method, path, **kwargs):
    code, body = req(method, path, kwargs.get("data"))
    results.append((label, code, body))

# ── CORE SYSTEM ──
test("GET  /api/health", "GET", "/api/health")
test("GET  /api/stats", "GET", "/api/stats")
test("GET  / (SPA)", "GET", "/")

# ── BRAIN ──
test("GET  /api/brain/status", "GET", "/api/brain/status")
test("POST /api/brain/message", "POST", "/api/brain/message", data={"recipient": "agent-001-tender-radar", "subject": "test", "body": {}})
test("POST /api/brain/broadcast", "POST", "/api/brain/broadcast", data={"subject": "broadcast test", "body": {}})
test("POST /api/brain/query", "POST", "/api/brain/query", data={})
test("POST /api/brain/store", "POST", "/api/brain/store", data={"entry_type": "note", "data": {"k": "v"}, "summary": "test"})
test("GET  /api/brain/memory", "GET", "/api/brain/memory")
test("POST /api/brain/workflow", "POST", "/api/brain/workflow", data={"workflow": [], "context": {}})
test("GET  /api/brain/knowledge", "GET", "/api/brain/knowledge?type=report&limit=5")

# ── AGENTS ──
test("GET  /api/agents", "GET", "/api/agents")
test("GET  /api/agents?limit=2", "GET", "/api/agents")

# ── THOUGHT ENGINE ──
test("GET  /api/thoughts/pending", "GET", "/api/thoughts/pending")
test("GET  /api/thoughts/history", "GET", "/api/thoughts/history?status=approved&limit=5")
test("POST /api/thoughts/propose", "POST", "/api/thoughts/propose", data={"agent_id": "test", "title": "test thought", "description": "desc"})
test("GET  /api/thoughts/stats", "GET", "/api/thoughts/stats")

# ── KNOWLEDGE GRAPH ──
test("GET  /api/knowledge-graph/stats", "GET", "/api/knowledge-graph/stats")
test("GET  /api/knowledge-graph/agency/BWDB", "GET", "/api/knowledge-graph/agency/BWDB")
test("GET  /api/knowledge-graph/agency/LGED", "GET", "/api/knowledge-graph/agency/LGED")
test("GET  /api/knowledge-graph/contractor/Abdul%20Monem", "GET", "/api/knowledge-graph/contractor/Abdul%20Monem")
test("GET  /api/knowledge-graph/syndicate-patterns", "GET", "/api/knowledge-graph/syndicate-patterns")

# ── WATCHDOG ──
test("GET  /api/watchdog/health", "GET", "/api/watchdog/health")
test("GET  /api/watchdog/dashboard", "GET", "/api/watchdog/dashboard")
test("POST /api/watchdog/analyze", "POST", "/api/watchdog/analyze", data={"source": "test", "error_message": "something broke", "error_type": "RuntimeError"})
test("GET  /api/watchdog/errors", "GET", "/api/watchdog/errors?limit=5")
test("GET  /api/watchdog/sessions", "GET", "/api/watchdog/sessions?limit=5")

# ── ENGINEER ──
test("GET  /api/engineer/status", "GET", "/api/engineer/status")
test("POST /api/engineer/diagnose", "POST", "/api/engineer/diagnose", data={"source": "test", "error_message": "err", "error_type": "manual"})
test("GET  /api/engineer/components/agent", "GET", "/api/engineer/components/agent")
test("GET  /api/engineer/fixes/database", "GET", "/api/engineer/fixes/database")

# ── CLIENTS ──
test("GET  /api/clients", "GET", "/api/clients")
test("POST /api/multi-client/evaluate", "POST", "/api/multi-client/evaluate", data={"clients": [{"id":"t","name":"T","tender_value":100000}]})

# ── INTELLIGENCE ──
test("POST /api/intelligence/ppr-dashboard", "POST", "/api/intelligence/ppr-dashboard", data={"action": "dashboard", "tender_id": "test"})

# ── PIPELINE ──
test("GET  /api/pipeline/definition", "GET", "/api/pipeline/definition")
test("POST /api/feedback/outcome", "POST", "/api/feedback/outcome", data={"agent_id": "test", "tender_id": "test", "predicted": {}, "actual": {}})

# ── SOR ──
test("GET  /api/sor/zones?agency=BWDB", "GET", "/api/sor/zones?agency=BWDB")
test("GET  /api/sor/status", "GET", "/api/sor/status")

# ── DATA ──
test("GET  /api/tenders?limit=3", "GET", "/api/tenders?limit=3")
test("GET  /api/awards?limit=3", "GET", "/api/awards?limit=3")
test("GET  /api/contractors?limit=3", "GET", "/api/contractors?limit=3")
test("GET  /api/agencies", "GET", "/api/agencies")

# ── EXISTING v1 ROUTES (sample) ──
test("GET  /api/tender/list?limit=2", "GET", "/api/tender/list?limit=2")
test("GET  /api/dashboard/stats", "GET", "/api/dashboard/stats")
test("GET  /api/ppr2025/overview", "GET", "/api/ppr2025/overview")
test("GET  /api/ppr2025/model/status", "GET", "/api/ppr2025/model/status")
test("POST /api/ppr2025/model/explain", "POST", "/api/ppr2025/model/explain", data={
    "estimated_cost": 5000000,
    "bid_price": 4300000,
    "bidder_count": 4,
    "agency": "BWDB",
    "tender_open_date": "2026-06-23",
    "bidder_name": "Smoke Test Bidder",
})
test("GET  /api/analytics/overview", "GET", "/api/analytics/overview")
test("GET  /api/executive/overview", "GET", "/api/executive/overview")
test("GET  /api/executive/report", "GET", "/api/executive/report")

# ── 404 HANDLING ──
test("GET  /api/nonexistent (expect 404)", "GET", "/api/nonexistent")

# ── REPORT ──
print("\n" + "=" * 110)
print(f"  {'ENDPOINT':<55} {'CODE':<6} {'STATUS'}")
print("=" * 110)
pass_count = 0
fail_count = 0
for label, code, body in results:
    if code is None:
        fail_count += 1
        print(f"  [ERR] {label:<53} CONN   {body}")
    elif code == 200 or code == 201:
        pass_count += 1
        snippet = ""
        if isinstance(body, dict):
            if "status" in body: snippet = "status=%s" % body["status"]
            elif "count" in body: snippet = "count=%s" % body["count"]
            elif "error" in body: snippet = "error=%s" % str(body["error"])[:60]
            else:
                ks = list(body.keys())[:2]
                snippet = "keys=%s" % ",".join(ks)
        else:
            snippet = str(body)[:80]
        print(f"  [OK]  {label:<53} {code:<6} {snippet}")
    elif code == 404 and "nonexistent" in label:
        pass_count += 1
        print(f"  [OK]  {label:<53} {code:<6} Expected 404")
    elif code == 500:
        fail_count += 1
        snippet = str(body)[:100] if isinstance(body, dict) else str(body)[:100]
        print(f"  [XX]  {label:<53} {code:<6} {snippet}")
    else:
        fail_count += 1
        snippet = str(body)[:100] if isinstance(body, dict) else str(body)[:100]
        print(f"  [XX]  {label:<53} {code:<6} {snippet}")

print("=" * 110)
print(f"  PASS: {pass_count}  |  FAIL: {fail_count}  |  TOTAL: {pass_count + fail_count}")
print("=" * 110)
