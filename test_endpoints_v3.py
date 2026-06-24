"""
ProcureFlow BD — Comprehensive Endpoint Verification Script
Tests all critical API routes that the frontend depends on.
"""
import sys
import requests
import json

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
SKIP = []

def test(method: str, path: str, expect: int = 200, label: str = ""):
    global PASS, FAIL
    url = f"{BASE}{path}"
    name = label or f"{method} {path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=10)
        elif method == "POST":
            r = requests.post(url, json={}, timeout=10)
        else:
            r = requests.request(method, url, timeout=10)
        if r.status_code == expect:
            PASS += 1
            print(f"  ✓ {name}")
        else:
            FAIL += 1
            print(f"  ✗ {name} — got {r.status_code}, expected {expect}")
    except requests.ConnectionError:
        SKIP.append(name)
        print(f"  ? {name} — Connection refused")
    except Exception as e:
        FAIL += 1
        print(f"  ✗ {name} — {e}")

def section(title: str):
    print(f"\n── {title} ─{'─' * min(60, max(0, 60 - len(title)))}")

# ── Run Tests ──────────────────────────────────────────────────────────────

section("System")

test("GET", "/api/health", label="Health check")
test("GET", "/api/stats", label="System stats")
test("GET", "/api/system/status", label="System status")
test("GET", "/api/", label="API root")

section("Agents & Brain")

test("GET", "/api/agents", label="List agents")
test("GET", "/api/agents/agent-001-tender-radar", label="Get agent detail")
test("GET", "/api/pipeline/phases", label="Pipeline phases")
test("GET", "/api/pipeline/definition", label="Pipeline definition")
test("POST", "/api/pipeline/run", label="Run pipeline")
test("GET", "/api/brain/status", label="Brain status")
test("POST", "/api/brain/message", label="Brain message")

section("Auth")

test("POST", "/api/auth/login", expect=422, label="Login (expected 422 - no body)")
test("POST", "/api/auth/register", expect=422, label="Register (expected 422 - no body)")

section("Tenders")

test("GET", "/api/tenders", label="List tenders")
test("GET", "/api/tenders?limit=3", label="List tenders (limit 3)")
test("GET", "/api/tender/list", label="List tenders (alt)")
test("POST", "/api/tender/db", expect=422, label="Tender DB create (empty body)")

section("Awards")

test("GET", "/api/awards", label="List awards")
test("GET", "/api/awards?limit=3", label="List awards (limit 3)")
test("GET", "/api/awards/stats", label="Award stats")

section("Contractors")

test("GET", "/api/contractors", label="List contractors")
test("GET", "/api/contractors?limit=3", label="List contractors (limit 3)")

section("Knowledge Graph")

test("GET", "/api/knowledge-graph/stats", label="KG stats")
test("GET", "/api/knowledge-graph/syndicate-patterns", label="Syndicate patterns")

section("Dashboard & Analytics")

test("GET", "/api/dashboard/stats", label="Dashboard stats")
test("GET", "/api/dashboard/analytics", label="Dashboard analytics")
test("GET", "/api/analytics/overview", label="Analytics overview")
test("GET", "/api/analytics/contractor-leaderboard", label="Contractor leaderboard")

section("PPR2025")

test("GET", "/api/ppr2025/overview", label="PPR2025 overview")
test("GET", "/api/ppr2025/contractors", label="PPR2025 contractors")
test("GET", "/api/ppr2025/award-stats", label="PPR2025 award stats")

section("Intel")

test("GET", "/api/intel/contractors", label="Intel contractors")
test("GET", "/api/intel/contractors/stats", label="Intel contractors stats")
test("GET", "/api/intel/import/status", label="Intel import status")

section("Predictions & Executive")

test("GET", "/api/predict/npp/stats", label="NPP stats")
test("GET", "/api/predict/bid/stats", label="Bid stats")
test("GET", "/api/executive/overview", label="Executive overview")

section("SOR")

test("GET", "/api/sor/agencies", label="SOR agencies")
test("GET", "/api/sor/zones", label="SOR zones")

section("Market & Deptree")

test("GET", "/api/market/rates", label="Market rates")
test("GET", "/api/market/indices", label="Market indices")
test("GET", "/api/deptree/ministries", label="Deptree ministries")
test("GET", "/api/deptree/targets", label="Deptree targets")

section("Watchdog & Engineer")

test("GET", "/api/watchdog/health", label="Watchdog health")
test("GET", "/api/watchdog/dashboard", label="Watchdog dashboard")
test("GET", "/api/engineer/status", label="Engineer status")

section("Chat & Embeds")

test("POST", "/api/chat", expect=422, label="Chat (empty body)")
test("POST", "/api/embeddings/search", expect=422, label="Embed search (empty body)")

section("Opening Reports")

test("GET", "/api/opening-reports", label="List opening reports")

section("Clents & Multi-Client")

test("GET", "/api/clients", label="List clients")
test("POST", "/api/clients/create", expect=422, label="Create client (empty body)")

section("Thought Engine")

test("GET", "/api/thoughts/pending", label="Pending thoughts")
test("GET", "/api/thoughts/stats", label="Thought stats")

# ── Summary ────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"  RESULTS: {PASS} PASS  |  {FAIL} FAIL  |  {len(SKIP)} SKIP")
print(f"  Total: {PASS + FAIL + len(SKIP)} endpoints tested")
print(f"{'='*60}")

sys.exit(0 if FAIL == 0 else 1)
