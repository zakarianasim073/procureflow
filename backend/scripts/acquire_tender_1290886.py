"""Acquire tender 1290886 from e-GP and run pipeline"""
import sys, json, os, asyncio
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from app.agents.egp_client import eGPClient
from app.agents.discovery.tender_acquisition import TenderAcquisitionAgent
from app.services.tender_bundle import TenderBundleProcessor
from pathlib import Path

TENDER_ID = "1290886"
EMAIL = "hbsrjv@gmail.com"
PASSWORD = "hbsrjv2017"

async def main():
    print("=== Step 1: Login to e-GP ===")
    client = eGPClient(email=EMAIL, password=PASSWORD)
    if client.login():
        print("Login successful!")
    else:
        print("Login failed - trying public access")
    
    print("\n=== Step 2: Search for tender ===")
    tender = client.get_tender_by_id(TENDER_ID)
    if tender:
        print(f"Found tender:")
        for k, v in dict(tender._asdict()).items():
            print(f"  {k}: {v}")
    else:
        print(f"Tender {TENDER_ID} not found via public search")
        # Try public search
        results = client.search_tender_public(TENDER_ID)
        print(f"Public search found {len(results)} results")
        for r in results:
            print(f"  {r.tender_id}: {r.title}")
    
    print("\n=== Step 3: Get tender documents ===")
    docs = client.get_tender_documents(TENDER_ID)
    print(f"Documents found:")
    for key, val in docs.items():
        if isinstance(val, list):
            print(f"  {key}: {len(val)} items")
            for v in val[:3]:
                print(f"    - {v.get('filename', v.get('title', v))}")
        elif isinstance(val, dict):
            print(f"  {key}: {len(val)} fields")
            for k2, v2 in list(val.items())[:5]:
                print(f"    {k2}: {str(v2)[:80]}")
        else:
            print(f"  {key}: {str(val)[:80]}")
    
    print("\n=== Step 4: Download documents ===")
    save_dir = Path("uploads") / TENDER_ID
    save_dir.mkdir(parents=True, exist_ok=True)
    
    for doc_type in ["NIT", "BOQ", "TDS", "DRAWINGS", "SPECIFICATIONS"]:
        data = client.download_document(TENDER_ID, doc_type)
        if data:
            ext = ".pdf"
            if isinstance(data, bytes) and len(data) > 100:
                fpath = save_dir / f"{doc_type.lower()}{ext}"
                with open(fpath, "wb") as f:
                    f.write(data if isinstance(data, bytes) else data.encode())
                print(f"  Downloaded {doc_type}: {fpath} ({len(data)} bytes)")
        else:
            print(f"  No {doc_type} available")
    
    print("\n=== Step 5: Run Tender Acquisition Agent ===")
    agent = TenderAcquisitionAgent()
    result = await agent.execute({
        "tender_id": TENDER_ID,
        "email": EMAIL,
        "password": PASSWORD,
        "trigger_downstream": True,
    })
    print(f"Acquisition result keys: {list(result.keys()) if isinstance(result, dict) else result}")
    
    print("\n=== Done ===")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
