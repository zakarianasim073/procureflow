"""
🐕 Watchdog Intelligence — System Health Monitor & Error Reporter.
Monitors all agents, DB, API, pipeline. Persists errors. Generates health reports.
Provides error intelligence engine with solution recommendations.
"""
from __future__ import annotations
import os, sys, json, time, logging, traceback, uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.agents.core.engineer import get_engineer
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Paths
BASE = os.environ.get("PROCUREFLOW_BASE", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ERROR_LOG_DIR = f"{BASE}/runtime/logs"
HEALTH_LOG = f"{ERROR_LOG_DIR}/system/health.jsonl"
ERROR_LOG = f"{ERROR_LOG_DIR}/system/errors.jsonl"
SESSION_LOG = f"{ERROR_LOG_DIR}/sessions/session_{int(time.time())}.jsonl"

@dataclass
class ErrorRecord:
    id: str = ""
    timestamp: str = ""
    source: str = ""
    error_type: str = ""
    error_message: str = ""
    traceback: str = ""
    context: dict = field(default_factory=dict)
    severity: str = "error"
    resolved: bool = False

class AgentWatchdog:
    """Central watchdog. Tracks errors, monitors agents, generates health reports."""
    
    def __init__(self, brain=None):
        self.brain = brain
        self._errors: List[ErrorRecord] = []
        self._agent_health: Dict[str, str] = {}
        self._pipeline_stats = {"runs":0,"ok":0,"fail":0,"by_stage":{}}
        self._start = time.time()
        os.makedirs(ERROR_LOG_DIR, exist_ok=True)
        os.makedirs(f"{ERROR_LOG_DIR}/system", exist_ok=True)
        os.makedirs(f"{ERROR_LOG_DIR}/sessions", exist_ok=True)
        os.makedirs(f"{ERROR_LOG_DIR}/agents", exist_ok=True)
        os.makedirs(f"{ERROR_LOG_DIR}/pipeline", exist_ok=True)
        # Write session start
        self._log("session", "start", {"watchdog_initialized": True})
        logger.info(f"🐕 Watchdog initialized — logging to {ERROR_LOG_DIR}")

    def _log(self, log_type: str, action: str, data: dict):
        """Write to appropriate log file."""
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "type": log_type, "action": action, **data}
        try:
            if log_type == "error":
                with open(ERROR_LOG, "a") as f: f.write(json.dumps(entry) + "\n")
            elif log_type == "session":
                with open(SESSION_LOG, "a") as f: f.write(json.dumps(entry) + "\n")
            else:
                with open(HEALTH_LOG, "a") as f: f.write(json.dumps(entry) + "\n")
        except Exception:
            import sys as _sys
            print(f"[watchdog] log write failed: {log_type}/{action}", file=_sys.stderr)

    def capture_error(self, source: str, error: Exception, context: dict = None, severity: str = "error") -> ErrorRecord:
        """Capture error with full context, persist to log."""
        tb = traceback.format_exc()
        rec = ErrorRecord(
            id=f"err-{int(time.time())}-{len(self._errors)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source, error_type=type(error).__name__,
            error_message=str(error)[:1000], traceback=tb[:3000],
            context=context or {}, severity=severity,
        )
        self._errors.append(rec)
        self._log("error", "captured", {
            "id": rec.id, "source": source, "type": rec.error_type,
            "severity": severity, "message": str(error)[:200],
        })
        # Also write agent-specific log
        try:
            safe_source = source.replace("/", "_").replace("\\", "_").replace("..", "_").replace(".", "_")
            with open(f"{ERROR_LOG_DIR}/agents/{safe_source}.log", "a") as f:
                f.write(json.dumps({"ts":rec.timestamp,"error":str(error)[:500],"traceback":tb[:2000]}) + "\n")
        except Exception:
            import sys as _sys; print(f"[watchdog] agent log write failed: {source}", file=_sys.stderr)
        logger.warning(f"🐕 [{severity}] {source}: {str(error)[:100]}")
        # Auto-diagnose with Intelligence Engineer
        try:
            engineer = get_engineer()
            diag = engineer.diagnose(source, str(error)[:500], type(error).__name__, context)
            self._log("engineer_diagnosis", "auto", {
                "source": source, "diagnosis": diag.get("root_cause_analysis", "")[:200],
                "fix_steps": len(diag.get("fix_steps", [])),
                "confidence": diag.get("confidence", "low"),
            })
            rec._diagnosis = diag
        except Exception as e:
            logger.warning(f"Engineer diagnosis failed: {e}")
        return rec

    def record_pipeline(self, stage: str, ok: bool, ms: int):
        self._pipeline_stats["runs"] += 1
        if ok: self._pipeline_stats["ok"] += 1
        else: 
            self._pipeline_stats["fail"] += 1
            self._pipeline_stats["by_stage"][stage] = self._pipeline_stats["by_stage"].get(stage, 0) + 1
        self._log("pipeline", "run", {"stage": stage, "ok": ok, "ms": ms})

    async def check_all_agents(self) -> dict:
        """Check health of all registered agents."""
        result = {"healthy": 0, "degraded": 0, "down": 0, "details": {}}
        if not self.brain: return result
        for agent_id, cap in self.brain._agents.items():
            inst = self.brain._agent_instances.get(agent_id)
            if inst and getattr(cap, "is_available", True):
                result["healthy"] += 1
                result["details"][agent_id] = "healthy"
                self._agent_health[agent_id] = "healthy"
            elif not inst:
                result["down"] += 1
                result["details"][agent_id] = "missing_instance"
                self._agent_health[agent_id] = "down"
            else:
                result["degraded"] += 1
                result["details"][agent_id] = "unavailable"
                self._agent_health[agent_id] = "degraded"
        self._log("health", "agent_check", {"total": len(self.brain._agents), **result})
        return result
    
    def check_db(self) -> dict:
        """Check database integrity."""
        r = {"status": "ok", "size_mb": 0, "issues": []}
        try:
            from app.db.database import get_database_backend, get_database_summary, get_sync_engine
            backend = get_database_backend()
            r["backend"] = backend
            r["connection"] = get_database_summary()

            engine = get_sync_engine()
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
                db_name = r["connection"].get("database")
                if db_name:
                    size_bytes = conn.exec_driver_sql(
                        "SELECT pg_database_size(current_database())"
                    ).scalar()
                    if size_bytes is not None:
                        r["size_mb"] = round(float(size_bytes) / (1024 * 1024), 1)
        except Exception as e:
            r["status"] = "error"
            r["issues"].append(str(e)[:200])
        self._log("health", "db_check", r)
        return r

    async def generate_report(self) -> dict:
        """Generate full health report."""
        agents = await self.check_all_agents()
        db = self.check_db()
        report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "uptime_s": int(time.time() - self._start),
            "status": "critical" if agents["down"] > 0 else "degraded" if agents["degraded"] > 0 or db["status"] != "ok" else "healthy",
            "agents": agents,
            "database": db,
            "pipeline": {
                "total": self._pipeline_stats["runs"],
                "success_rate": round((self._pipeline_stats["ok"] / max(self._pipeline_stats["runs"],1)) * 100, 1),
                "failures": self._pipeline_stats["fail"],
                "by_stage": self._pipeline_stats["by_stage"],
            },
            "recent_errors": [{"id":e.id,"source":e.source,"type":e.error_type,"severity":e.severity,"message":e.error_message[:200]} for e in self._errors[-10:]],
            "error_count": len(self._errors),
            "recommendations": [],
        }
        if agents["down"] > 0: report["recommendations"].append(f"🔴 {agents['down']} agent(s) down")
        if db["status"] != "ok": report["recommendations"].append(f"🗄️ DB issue: {db.get('issues',['unknown'])[0]}")
        self._log("health", "report", {"status": report["status"], "errors": len(self._errors)})
        return report

    def get_recent_errors(self, limit=20) -> list:
        return [{"id":e.id,"ts":e.timestamp,"src":e.source,"type":e.error_type,"sev":e.severity,"msg":e.error_message[:200]} for e in self._errors[-limit:]]

    def analyze_error(self, source: str, error_msg: str, error_type: str = "Unknown") -> dict:
        """Error Intelligence Engine — provides exact solution for any error."""
        msg = error_msg.lower()
        solution = {
            "source": source, "error_type": error_type,
            "message": error_msg[:500], "analysis": "",
            "root_cause": "", "steps": [], "prevention": "",
            "confidence": "medium", "auto_fixable": False,
        }
        # ── Pattern-based error analysis ─────────────────────────────
        if error_type in ("OperationalError", "DatabaseError", "IntegrityError"):
            if "no such column" in msg:
                col = msg.split("no such column:")[-1].strip().split()[0] if "no such column:" in msg else "?"
                solution["root_cause"] = f"Missing DB column: {col}"
                solution["analysis"] = "Schema mismatch — model updated but migration not run."
                solution["steps"] = [f"Run: ALTER TABLE ... ADD COLUMN {col}", "Run init_db() to recreate schema"]
            elif "no such table" in msg:
                tbl = msg.split("no such table:")[-1].strip().split()[0] if "no such table:" in msg else "?"
                solution["root_cause"] = f"Missing table: {tbl}"
                solution["steps"] = [f"Run init_db() to create table {tbl}"]
            elif "database is locked" in msg:
                solution["root_cause"] = "Concurrent write lock"
                solution["steps"] = ["Check for long-running transactions", "Reduce concurrent writes", "Check PostgreSQL locks: SELECT * FROM pg_locks WHERE NOT granted"]
            elif "unable to open" in msg:
                solution["root_cause"] = "DB file path invalid"
                solution["steps"] = [f"Check DB path in database.py", "Ensure data/ directory exists"]
            solution["confidence"] = "high"

        elif error_type in ("ModuleNotFoundError", "ImportError"):
            pkgs = [p for p in msg.split("'") if p.strip() and not p.isspace() and len(p) > 1]
            missing = pkgs[0] if pkgs else "?"
            solution["root_cause"] = f"Missing package: {missing}"
            solution["steps"] = [f"pip install {missing}"]
            solution["confidence"] = "high"

        elif error_type in ("ConnectionError", "TimeoutError", "HTTPError"):
            solution["root_cause"] = "Network/API unavailable"
            solution["steps"] = ["Check network", "Verify endpoint", "Add retry with backoff", "Implement circuit breaker"]
            solution["confidence"] = "medium"

        elif error_type == "RuntimeWarning" and "coroutine" in msg:
            fn = msg.split("'")[1] if "'" in msg else "?"
            solution["root_cause"] = f"Async coroutine '{fn}' never awaited"
            solution["steps"] = [f"Add 'await {fn}()' in {source}"]
            solution["confidence"] = "high"
            solution["auto_fixable"] = True

        elif error_type in ("AttributeError", "KeyError", "TypeError", "ValueError"):
            solution["root_cause"] = f"Data format error in {source}"
            solution["analysis"] = "Agent received unexpected data format."
            solution["steps"] = [f"Validate input schema for {source}", "Add Pydantic validation", "Check upstream agent output"]
            solution["confidence"] = "medium"

        elif error_type in ("FileNotFoundError", "PermissionError"):
            paths = [p for p in msg.split("'") if "/" in p]
            path = paths[0] if paths else "?"
            solution["root_cause"] = f"File access error: {path}"
            solution["steps"] = [f"Check path: {path}", "Verify permissions", "Create directory if needed"]
            solution["confidence"] = "high"

        elif error_type == "MemoryError":
            solution["root_cause"] = "Memory exhausted"
            solution["steps"] = ["Reduce batch sizes", "Add pagination", "Check RAM/swap", "Optimize queries"]
            solution["confidence"] = "medium"

        else:
            solution["analysis"] = f"Unknown error pattern: {error_type}"
            solution["steps"] = [f"Check full traceback in logs/{source}.log", f"Test {source} in isolation", "Review recent changes"]
            solution["confidence"] = "low"

        # Attach traceback reference
        recent = [e for e in self._errors if e.source == source and e.error_type == error_type]
        if recent:
            solution["traceback_preview"] = recent[-1].traceback[:500]
        
        return solution

    def get_dashboard(self) -> dict:
        """Get dashboard data for frontend."""
        return {
            "status": "active",
            "uptime_s": int(time.time() - self._start),
            "error_count": len(self._errors),
            "pipeline_runs": self._pipeline_stats["runs"],
            "pipeline_ok": self._pipeline_stats["ok"],
            "pipeline_fail": self._pipeline_stats["fail"],
            "agent_health": self._agent_health,
            "log_paths": {"errors": ERROR_LOG, "health": HEALTH_LOG, "sessions": SESSION_LOG},
        }

# Singleton
_instance = None
def get_watchdog(brain=None):
    global _instance
    if _instance is None: _instance = AgentWatchdog(brain)
    elif brain and not _instance.brain: _instance.brain = brain
    return _instance
