"""
AgentBrain initialization test — registers all agents, starts message bus.
Usage: python init_brain.py
"""
import os, sys, json, logging
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///D:/A1/procurementflow_final_v3/procurementflow/backend/data/procureflow_v3.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///D:/A1/procurementflow_final_v3/procurementflow/backend/data/procureflow_v3.db"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

logging.basicConfig(level=logging.INFO)

import asyncio
from app.agents.core.brain import AgentBrain, BrainMessage, MessageType
from app.main import register_all_agents, AgentRegistry

async def main():
    print("=== AgentBrain Initialization ===\n")

    # 1. Create AgentBrain with SQLite session
    brain = AgentBrain()
    print("[OK] AgentBrain created")

    # 2. Register all agents via the registry
    registry = AgentRegistry()
    registry = register_all_agents(registry)
    print(f"[OK] Registry has {registry.count} agents\n")

    # 3. Register agents with the brain
    for agent_id, agent in sorted(registry._agents.items()):
        brain.register_agent(
            agent_id=agent_id,
            instance=agent,
            name=getattr(agent, "agent_name", agent_id),
            description=getattr(agent, "description", ""),
        )
    print(f"\n[OK] {len(brain._agent_instances)} agents registered with Brain")

    # 4. Start the brain
    await brain.start()
    print("[OK] Brain started (message processing loop active)\n")

    # 5. Test: Send a broadcast message
    print("--- Test Broadcast ---")
    delivered = await brain.broadcast(
        sender_id="agent-027-orchestrator",
        subject="system.health_check",
        body={"check": "all", "timestamp": "2026-06-23T00:00:00Z"}
    )
    print(f"  Broadcast delivered to {len(delivered)} agents")

    # 6. Test: Send a direct request to TenderRadar
    print("\n--- Test Direct Request ---")
    result = await brain.request(
        sender_id="agent-027-orchestrator",
        recipient_id="agent-001-tender-radar",
        subject="tender.list",
        body={"limit": 3, "tender_id": ""},
        timeout=15.0
    )
    if result and "error" not in result:
        print(f"  Response received: {json.dumps(result, default=str)[:300]}")
    else:
        print(f"  (Expected if no data:) {result}")

    # 7. Check DB for persisted messages
    print("\n--- DB Persistence Check ---")
    async with brain.db() as session:
        from app.db import AgentBrainMessage
        from sqlalchemy import select, func
        count_result = await session.execute(select(func.count()).select_from(AgentBrainMessage))
        msg_count = count_result.scalar()
        print(f"  Messages persisted in DB: {msg_count}")

    # 8. Knowledge share test
    print("\n--- Test Knowledge Share ---")
    entry_id = await brain.store_knowledge(
        agent_id="agent-001-tender-radar",
        entry_type="tender_discovery",
        tender_id="test-001",
        data={"title": "Test Tender", "estimated_value": 5000000},
        summary="Test entry for AgentBrain initialization",
        tags=["test", "initialization"]
    )
    print(f"  Knowledge entry stored: {entry_id}")

    # 9. Query knowledge
    entries = await brain.query_knowledge(entry_type="tender_discovery")
    print(f"  Knowledge entries found: {len(entries)}")

    # 10. Stop the brain
    await brain.stop()
    print("\n[OK] Brain stopped cleanly")

    print("\n=== AgentBrain Initialization Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
