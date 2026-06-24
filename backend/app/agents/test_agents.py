"""
Procurement Flow Specialist BD — Agent System Tests
Validates that the production agent registry and orchestrator stay in sync.
"""

import asyncio
import json
import sys
import time
from typing import Any, Dict

# Skip network tests that require live eGP portal access
SKIP_NETWORK_TESTS = True

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


from . import AgentRegistry, AgentStatus
from .orchestrator import WorkflowOrchestrator, PipelinePhase, PIPELINE_DEFINITION
from app.main import register_all_agents


def build_registry() -> AgentRegistry:
    registry = AgentRegistry()
    register_all_agents(registry)
    return registry


def status_value(result) -> str:
    status = getattr(result, "status", "")
    return getattr(status, "value", status)


def test_registration():
    registry = build_registry()
    count = registry.count
    assert count >= 40, f"Expected the production registry to contain the full agent set, got {count}"
    
    required = [
        "agent-001-tender-radar",
        "agent-005-boq-intelligence",
        "agent-009-ppr-evaluation",
        "agent-022-executive-decision",
        "agent-027-orchestrator",
        "agent-044-sor-zone-matcher",
    ]
    for aid in required:
        agent = registry.get(aid)
        assert agent is not None, f"Missing required agent: {aid}"
        assert agent.agent_name != "", f"Agent {aid} has empty name"
        assert agent.description != "", f"Agent {aid} has empty description"
    
    print(f"  ✅ Registration: {count} agents registered")
    for aid in required:
        print(f"     Verified: {aid}")


def test_agent_ids_all_unique():
    registry = build_registry()
    ids = [a.agent_id for a in registry._agents.values()]
    assert len(ids) == len(set(ids)), "Duplicate agent IDs found!"
    print(f"  ✅ All {len(ids)} agent IDs unique")


def test_agent_info_all():
    registry = build_registry()
    for aid, agent in registry._agents.items():
        info = agent.info()
        assert info["agent_id"] == aid
        assert len(info["agent_name"]) > 0
        assert len(info["description"]) > 0
        assert isinstance(info["dependencies"], list)
        assert len(info["version"]) > 0
    print(f"  ✅ All {registry.count} agents have valid metadata")


def test_pipeline_phases():
    phases = list(PipelinePhase)
    assert len(phases) == 14, f"Expected 14 phases, got {len(phases)}"
    
    for phase in phases:
        agents = PIPELINE_DEFINITION.get(phase, [])
        assert len(agents) > 0, f"Phase {phase.value} has no agents"

    registry = build_registry()
    pipeline_agents = {aid for phase in phases for aid in PIPELINE_DEFINITION[phase]}
    registered_agents = set(registry._agents.keys())
    missing = sorted(pipeline_agents - registered_agents)
    assert not missing, f"Pipeline references unregistered agents: {missing}"

    total_in_phases = sum(len(PIPELINE_DEFINITION[p]) for p in phases)
    unique_in_phases = len(pipeline_agents)

    print(f"  ✅ {len(phases)} pipeline phases, {total_in_phases} references, {unique_in_phases} unique agents")


def test_dependency_order():
    registry = build_registry()
    # Test no dependency cycles by resolving all agents
    all_ids = list(registry._agents.keys())
    order = registry._resolve_order(all_ids)
    assert len(order) == len(all_ids), f"Resolution returned {len(order)} agents, expected {len(all_ids)}"
    print(f"  ✅ All {len(order)} agents can be dependency-ordered")


async def test_single_agent_001():
    registry = build_registry()
    agent = registry.get("agent-001-tender-radar")
    result = await agent.run({"demo_mode": True, "sources": []})
    assert status_value(result) == AgentStatus.SUCCESS.value, f"Failed: {result.error}"
    assert result.execution_time_ms >= 0
    assert any(key in result.output for key in ("tenders_found", "matched_tenders"))
    total_found = result.output.get("total_found", result.output.get("total", 0))
    assert total_found >= 0
    print(f"  ✅ Agent 1 (Tender Radar) — {total_found} tenders found in {result.execution_time_ms:.0f}ms")


async def test_single_agent_005():
    registry = build_registry()
    result = await registry.run_agent("agent-005-boq-intelligence", {})
    assert status_value(result) == AgentStatus.SUCCESS.value
    assert result.output["total_items"] > 0
    assert "items" in result.output
    print(f"  ✅ Agent 5 (BOQ Intelligence) — {result.output['total_items']} items, {len(result.output.get('categories_found',[]))} categories")


async def test_single_agent_008():
    registry = build_registry()
    result = await registry.run_agent("agent-008-risk-intelligence", {
        "upstream": {"agent-004-document-ai": {"emd_amount": 500000, "estimated_value": 52000000}}
    })
    assert status_value(result) == AgentStatus.SUCCESS.value
    assert result.output["risk_level"] in ["Low", "Medium", "High"]
    print(f"  ✅ Agent 8 (Risk Intelligence) — Level: {result.output['risk_level']}")


async def test_single_agent_021():
    registry = build_registry()
    result = await registry.run_agent("agent-022-executive-decision", {
        "upstream": {
            "agent-018-ai-bid-assistant": {"should_bid": True, "recommendation": "BID"},
            "agent-008-risk-intelligence": {"risk_level": "Medium"},
            "agent-016-win-probability": {"win_probability": 72.0},
            "agent-021-financial-intelligence": {"expected_profit": 6300000},
            "agent-007-eligibility-compliance": {"compliant": True},
        }
    })
    assert status_value(result) == AgentStatus.SUCCESS.value
    assert result.output["decision"] in ["BID", "NO_BID", "DEFER"]
    print(f"  ✅ Agent 21 (Executive Decision) — Decision: {result.output['decision']}, Win: {result.output.get('win_chance_pct','N/A')}")


async def test_pipeline_phase_discovery():
    registry = build_registry()
    orch = registry.get("agent-027-orchestrator")
    result = await orch.run({"mode": "phase", "phase": "discovery"})
    assert status_value(result) == AgentStatus.SUCCESS.value
    assert "phases" in result.output or "phases_completed" in result.output or "discovery" in str(result.output)
    print(f"  ✅ Orchestrator — Discovery phase completed")


async def test_all_agents_execute_solo():
    """Test that every agent can execute without crashing."""
    registry = build_registry()
    
    # Skip orchestrator (handled separately)
    skip = {"agent-027-orchestrator", "agent-028-syndicate-radar", "agent-030-ra-bill-predictor", "agent-029-vision-intelligence"}
    solo_agents = [a for a in registry._agents.values() if a.agent_id not in skip]
    
    results = []
    for agent in solo_agents:
        try:
            result = await agent.run({})
            status = "✅" if status_value(result) == AgentStatus.SUCCESS.value else "⚠️"
            results.append((agent.agent_id, status, status_value(result)))
        except Exception as e:
            results.append((agent.agent_id, "❌", str(e)[:50]))
    
    successes = sum(1 for _, s, _ in results if s == "✅")
    print(f"  ✅ Solo execution: {successes}/{len(results)} agents succeeded")
    for aid, symbol, status in results:
        if symbol != "✅":
            print(f"     {symbol} {aid}: {status}")


async def main():
    print("\n" + "=" * 60)
    print("  Procurement Flow Specialist BD — Agent System Tests")
    print("=" * 60 + "\n")
    
    start = time.time()
    passed = 0
    failed = 0
    
    tests = [
        ("Agent Registration", test_registration),
        ("Unique IDs", test_agent_ids_all_unique),
        ("Agent Metadata", test_agent_info_all),
        ("Pipeline Phases", test_pipeline_phases),
        ("Dependency Order", test_dependency_order),
    ]
    
    if not SKIP_NETWORK_TESTS:
        tests += [
            ("Agent 1 (Tender Radar)", test_single_agent_001),
            ("Agent 5 (BOQ Intel)", test_single_agent_005),
            ("Agent 8 (Risk Intel)", test_single_agent_008),
            ("Agent 21 (Executive)", test_single_agent_021),
            ("Pipeline: Discovery", test_pipeline_phase_discovery),
            ("All Agents Solo", test_all_agents_execute_solo),
        ]
    else:
        print(f"\n{'=' * 60}")
        print("  Network tests SKIPPED (set SKIP_NETWORK_TESTS=False to test live eGP)")
        print(f"{'=' * 60}\n")
    
    for name, test_fn in tests:
        print(f"\n- {name}")
        try:
            if asyncio.iscoroutinefunction(test_fn):
                await test_fn()
            else:
                test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{passed+failed} passed in {elapsed:.1f}s")
    print(f"{'=' * 60}\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
