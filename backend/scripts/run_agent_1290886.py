"""Run TenderAcquisitionAgent for tender 1290886 and generate BOQ report"""
import sys, asyncio, logging
sys.path.insert(0, ".")
sys.path.insert(0, "app")

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("agent_run")

TENDER_ID = "1290886"

async def main():
    logger.info("Initializing TenderAcquisitionAgent...")
    from app.agents.discovery.tender_acquisition import TenderAcquisitionAgent
    agent = TenderAcquisitionAgent()
    
    logger.info("Executing acquisition for tender %s...", TENDER_ID)
    result = await agent.execute({"tender_id": TENDER_ID})
    
    logger.info("Result status: %s", result.status)
    output = result.output if hasattr(result, 'output') else result
    
    if isinstance(output, dict):
        for k, v in output.items():
            if isinstance(v, dict):
                logger.info("  %s: {%s}", k, ", ".join(list(v.keys())[:8]))
            elif isinstance(v, list):
                logger.info("  %s: [%d items]", k, len(v))
                if v and isinstance(v[0], dict):
                    logger.info("    sample: %s", str(list(v[0].keys())[:5]))
            else:
                logger.info("  %s: %s", k, str(v)[:200])
        
        # Check for downloaded files
        runtime_dir = Path(f"runtime/tender_acquisition/{TENDER_ID}")
        if runtime_dir.exists():
            logger.info("\nDownloaded files:")
            for f in sorted(runtime_dir.rglob("*")):
                if f.is_file():
                    logger.info("  %s (%d bytes)", f.relative_to(runtime_dir), f.stat().st_size)
    
    logger.info("\n=== Acquisition complete ===")

if __name__ == "__main__":
    from pathlib import Path
    asyncio.run(main())
