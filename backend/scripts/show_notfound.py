"""Show full descriptions for all 13 SOR NOT FOUND items"""
import sys, asyncio, re
sys.path.insert(0, '.')
from app.sor.sor_service import SORService
from app.services.boq_processor import BOQProcessor

# Get raw PDF text for full descriptions
from PyPDF2 import PdfReader
reader = PdfReader('uploads/1290886/BOQ.pdf')
raw_text = ""
for page in reader.pages:
    raw_text += page.extract_text() + "\n"

async def main():
    sor = SORService()
    sor.load_all()
    
    from app.services.pdf_parser import PDFParser
    parser = PDFParser()
    items = await parser.extract_boq_items('uploads/1290886/BOQ.pdf')

    # Build item_no -> raw description map from raw text
    # Each item starts with item_no followed by group/code
    item_raw_desc = {}
    for item in items:
        ino = item.get('item_no', '')
        code = item.get('code', '')
        # Find in raw text by item number pattern
        m = re.search(rf'^{ino}\s+\d+\s+{re.escape(code)}', raw_text, re.M)
        if m:
            # Collect everything from this line to the next item number
            start = m.start()
            next_m = re.search(rf'^{int(ino)+1}\s+\d+\s+', raw_text, re.M)
            end = next_m.start() if next_m else len(raw_text)
            item_raw_desc[ino] = raw_text[start:end].strip()
        if not item_raw_desc.get(ino):
            # Fallback: use parser description
            item_raw_desc[ino] = item.get('description', '')

    proc = BOQProcessor()
    result = await proc.compare(
        'uploads/1290886/BOQ.pdf', 'BWDB',
        zone={'BWDB': 'B', 'PWD': 'B', 'LGED': 'B'},
        sor_service=sor,
        tender_info={'tender_id': '1290886', 'title': 'Test'}
    )
    
    data = result.get('data', [])
    for r in data:
        if r['flag'] == 'SOR NOT FOUND':
            code = r['code']
            ino = r['item_no']
            desc = item_raw_desc.get(ino, r['desc'])
            print(f"{'='*80}")
            print(f"Item #{ino}  Code: {code}  Agency: {r['agency']}")
            print(f"SOR source: {r['sor_source']}  SOR rate: {r['sor_rate']}")
            print(f"{'='*80}")
            print(desc)
            print()

asyncio.run(main())
