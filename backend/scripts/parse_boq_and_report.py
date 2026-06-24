"""Parse the BOQ PDF and generate Excel report"""
import sys, json
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from pathlib import Path

BOQ_PDF = Path("uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf")
NOTICE_PDF = Path("uploads/1290886/docs/Section1_Instructions to Tenderer/Section1_Instructions to Tenderer.pdf")
TDS_PDF = Path("uploads/1290886/docs/Section2_Tender Data Sheet/Section2_Tender Data Sheet.pdf")
OUTPUT_DIR = Path("uploads/1290886")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Step 1: Parse BOQ PDF
print("=== Step 1: Parse BOQ PDF ===")
import PyPDF2

def extract_pdf_text(pdf_path):
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            text += f"\n--- Page {i+1} ---\n{t}"
        return text, len(reader.pages)

boq_text, boq_pages = extract_pdf_text(BOQ_PDF)
print(f"BOQ PDF: {boq_pages} pages, {len(boq_text)} chars")
print(boq_text[:2000])

# Save raw text
with open(OUTPUT_DIR / "boq_text.txt", "w", encoding="utf-8") as f:
    f.write(boq_text)

# Step 2: Parse TDS for tender info
print("\n=== Step 2: Parse TDS for zone info ===")
tds_text, tds_pages = extract_pdf_text(TDS_PDF)
print(f"TDS PDF: {tds_pages} pages, {len(tds_text)} chars")
print(tds_text[:1000])
with open(OUTPUT_DIR / "tds_text.txt", "w", encoding="utf-8") as f:
    f.write(tds_text)

# Step 3: Upload through the API pipeline
print("\n=== Step 3: Run pipeline ===")
import httpx
import asyncio

async def run_pipeline():
    # First, upload the tender documents
    api_base = "http://localhost:8000/api"
    
    async with httpx.AsyncClient() as client:
        # Upload tender
        with open(BOQ_PDF, "rb") as boq_f, open(NOTICE_PDF, "rb") as notice_f:
            files = {
                "notice": ("notice.pdf", notice_f, "application/pdf"),
                "boq": ("boq.pdf", boq_f, "application/pdf"),
            }
            resp = await client.post(
                f"{api_base}/tender/upload",
                params={"tender_id": "1290886"},
                files=files,
                timeout=120,
            )
            print(f"Upload response: {resp.status_code}")
            try:
                print(json.dumps(resp.json(), indent=2)[:1000])
            except:
                print(resp.text[:500])
        
        # Get tender details
        resp = await client.get(f"{api_base}/tender/1290886")
        print(f"\nTender details: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2)[:500])
        
        # Try to run BOQ comparison
        resp = await client.post(
            f"{api_base}/boq/compare",
            params={"tender_id": "1290886", "agency": "BWDB"},
            timeout=120,
        )
        print(f"\nBOQ compare: {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2)[:1000])
        except:
            print(resp.text[:500])

asyncio.run(run_pipeline())
