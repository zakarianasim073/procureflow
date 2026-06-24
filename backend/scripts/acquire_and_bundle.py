"""Acquire tender 1290886 from e-GP and generate BOQ Excel report"""
import sys, json, asyncio, logging
sys.path.insert(0, ".")
sys.path.insert(0, "app")

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("acquire")

from app.agents.egp_client import eGPClient
from app.agents.discovery.tender_acquisition import TenderAcquisitionAgent
from pathlib import Path

TENDER_ID = "1290886"

async def main():
    # Step 1: Try direct eGPClient first
    logger.info("=== Step 1: Login to e-GP ===")
    client = eGPClient()
    if client.login():
        logger.info("Login successful!")
    else:
        logger.warning("Login failed")
    
    # Step 2: Search
    logger.info("=== Step 2: Search tender ===")
    tender = client.get_tender_by_id(TENDER_ID)
    if tender:
        logger.info("Found tender via get_tender_by_id:")
        for k, v in dict(tender._asdict()).items():
            logger.info("  %s: %s", k, str(v)[:200])
    else:
        logger.info("Tender not found via get_tender_by_id, trying public search...")
        results = client.search_tender_public(TENDER_ID)
        logger.info("Public search: %d results", len(results))
        for r in results[:5]:
            logger.info("  %s: %s - %s", r.tender_id, r.title[:60], r.procuring_entity[:60] if r.procuring_entity else "")
    
    # Step 3: Get tender documents
    logger.info("=== Step 3: Get document links ===")
    docs = client.get_tender_documents(TENDER_ID)
    logger.info("Documents result keys: %s", list(docs.keys()))
    
    # Step 4: Download documents
    logger.info("=== Step 4: Download documents ===")
    save_dir = Path("uploads") / TENDER_ID
    save_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded = {}
    for doc_type in ["NIT", "BOQ", "TDS", "DRAWINGS", "SPECIFICATIONS", "CORRIGENDUM"]:
        data = client.download_document(TENDER_ID, doc_type)
        if data and len(data) > 100:
            ext = ".pdf"
            if isinstance(data, bytes):
                if data[:4] == b'%PDF':
                    ext = ".pdf"
                elif data[:2] == b'PK':
                    ext = ".xlsx"
            fpath = save_dir / f"{doc_type.lower()}{ext}"
            with open(fpath, "wb") as f:
                f.write(data if isinstance(data, bytes) else data.encode())
            downloaded[doc_type] = str(fpath)
            logger.info("  Downloaded %s: %s (%d bytes)", doc_type, fpath, len(data))
        else:
            logger.info("  No %s available", doc_type)
    
    # Step 5: Run acquisition agent
    logger.info("=== Step 5: Run TenderAcquisitionAgent ===")
    agent = TenderAcquisitionAgent()
    result = await agent.execute({"tender_id": TENDER_ID})
    logger.info("Agent result status: %s", result.status.value if hasattr(result.status, 'value') else result.status)
    if hasattr(result, 'output'):
        logger.info("Output keys: %s", list(result.output.keys()) if isinstance(result.output, dict) else "not dict")
    
    # Step 6: Run bundle processor
    logger.info("=== Step 6: Run bundle/pipeline ===")
    from app.services.tender_bundle import TenderBundleProcessor
    bundle = TenderBundleProcessor()
    
    notice_path = downloaded.get("NIT") or (save_dir / "nit.pdf")
    boq_path = downloaded.get("BOQ") or (save_dir / "boq.xlsx")
    
    # Check what files exist
    for f in save_dir.glob("*"):
        logger.info("  File: %s (%d bytes)", f.name, f.stat().st_size)
    
    # If we have downloaded files, try to run the pipeline
    if any(save_dir.iterdir()):
        logger.info("Documents downloaded. Ready for pipeline processing.")
        logger.info("Use the API: POST /api/tender/upload with files")
    
    client.close()
    logger.info("=== Done ===")

if __name__ == "__main__":
    asyncio.run(main())
