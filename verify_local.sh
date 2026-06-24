#!/usr/bin/env bash
# ── Procurement Flow Specialist BD — Local Verification Script ──────────────
# Checks Docker, Postgres, FastAPI, Celery, Agents, and Frontend health.
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

check() {
    TOTAL=$((TOTAL+1))
    if eval "$1" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✅ PASS${NC} $2"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}❌ FAIL${NC} $2"
        [ -n "$3" ] && echo -e "     ${YELLOW}Fix: $3${NC}"
        FAIL=$((FAIL+1))
    fi
}

echo -e "\n${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}   Procurement Flow Specialist BD — Local Verification${NC}"
echo -e "${CYAN}   $(date)${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}\n"

# ── 1. Docker Infrastructure ──────────────────────────────────────────────
echo -e "${YELLOW}[1/8] Docker Infrastructure${NC}"
check "docker ps --format '{{.Names}}' | grep -q procurementflow-postgres" "PostgreSQL container running" "Run: docker-compose up -d postgres"
check "docker ps --format '{{.Names}}' | grep -q procurementflow-redis" "Redis container running" "Run: docker-compose up -d redis"
check "docker ps --format '{{.Names}}' | grep -q procurementflow-minio" "MinIO container running" "Run: docker-compose up -d minio"

# ── 2. PostgreSQL Database ───────────────────────────────────────────────
echo -e "\n${YELLOW}[2/8] PostgreSQL Database${NC}"
check "docker exec procurementflow-postgres pg_isready -U procurementflow" "PostgreSQL accepting connections"
check "docker exec procurementflow-postgres psql -U procurementflow -d procurementflow -c 'SELECT 1' >/dev/null 2>&1" "Database reachable"

# ── 3. FastAPI Backend ────────────────────────────────────────────────────
echo -e "\n${YELLOW}[3/8] FastAPI Backend${NC}"
check "curl -sf http://localhost:8000/api/health >/dev/null 2>&1" "Health endpoint /api/health" "Start: cd backend && uvicorn app.main:app --reload"
check "curl -sf http://localhost:8000/api/health 2>/dev/null | grep -q healthy" "Health returns healthy"

# ── 4. Agent CLI ──────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[4/8] Agent CLI${NC}"
check "cd backend && python -m app.agents.runner list 2>/dev/null | grep -q '27 agents registered'" "27 agents registered" "Activate venv and cd backend"
check "cd backend && python -m app.agents.runner phases 2>/dev/null | grep -q 'DISCOVERY'" "Pipeline phases defined"

# ── 5. Celery Worker ──────────────────────────────────────────────────────
echo -e "\n${YELLOW}[5/8] Celery Worker${NC}"
REDIS_RUNNING=$(docker ps --format '{{.Names}}' | grep -c procurementflow-redis || true)
if [ "$REDIS_RUNNING" -gt 0 ]; then
    check "celery -A app.celery_app status 2>/dev/null | grep -q 'online'" "Celery worker online" "Start: celery -A app.celery_app worker --loglevel=info"
    check "celery -A app.celery_app inspect registered 2>/dev/null | grep -q pipeline_discovery" "Celery tasks registered"
else
    echo -e "  ${YELLOW}⚠ SKIP${NC} Celery check (Redis not available)"
    TOTAL=$((TOTAL-2)); FAIL=$((FAIL-2))
fi

# ── 6. API Endpoints ──────────────────────────────────────────────────────
echo -e "\n${YELLOW}[6/8] API Endpoints${NC}"
check "curl -sf http://localhost:8000/api/sor/agencies >/dev/null 2>&1" "SOR agencies endpoint"
check "curl -sf http://localhost:8000/api/dashboard/stats >/dev/null 2>&1" "Dashboard stats endpoint"
check "curl -sf -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"test@demo.com\",\"password\":\"test123\"}' 2>/dev/null | grep -q 'access_token'" "Auth login works"
check "curl -sf http://localhost:8000/api/payments/plans >/dev/null 2>&1" "Payment plans endpoint"

# ── 7. Frontend ───────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[7/8] Frontend${NC}"
check "curl -sf http://localhost:5173 >/dev/null 2>&1" "Vite dev server responding" "Start: cd frontend && npm run dev"
check "curl -sf http://localhost:5173 2>/dev/null | grep -q 'root'" "React app serving HTML"

# ── 8. Database Schema ────────────────────────────────────────────────────
echo -e "\n${YELLOW}[8/8] Database Schema${NC}"
check "docker exec procurementflow-postgres psql -U procurementflow -d procurementflow -c '\dt' 2>/dev/null | grep -q 'users'" "Users table exists"
check "docker exec procurementflow-postgres psql -U procurementflow -d procurementflow -c '\dt' 2>/dev/null | grep -q 'tenders'" "Tenders table exists"
check "docker exec procurementflow-postgres psql -U procurementflow -d procurementflow -c '\dt' 2>/dev/null | grep -q 'boq_items'" "BOQ items table exists"

# ── Summary ───────────────────────────────────────────────────────────────
echo -e "\n${CYAN}══════════════════════════════════════════════════════════════${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e " ${GREEN}✅ ALL SYSTEMS OPERATIONAL  (${PASS}/${TOTAL} passed)${NC}"
    echo -e " ${GREEN}   Procurement Flow Specialist BD is production-ready!${NC}"
else
    echo -e " ${RED}⚠  ${FAIL} check(s) failed  (${PASS}/${TOTAL} passed)${NC}"
    echo -e " ${YELLOW}   Fix the issues above before pushing to production.${NC}"
fi
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}\n"

# ── Exit with code ────────────────────────────────────────────────────────
[ "$FAIL" -eq 0 ]
