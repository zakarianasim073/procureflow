"""Parse BOQ items directly from pdfplumber tables"""
import sys, re
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from pathlib import Path
import pdfplumber
import asyncio

BOQ_PDF = Path("uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf")

UNITS = ['cum', 'sqm', 'each', 'no', 'nos', 'kg', 'm', 'day', 'lump', '%', 'rmt', 'mt', 'ton',
         'meter', 'points', 'point', 'sq', 'cft', 'rft', 'lump sum', 'ls', 'job', 'set',
         'hours', 'm. ton', 'ps/ km', 'each', 'm.', 'Cum/ Km', 'Cum', 'Sqm', 'Kg', 'Point',
         'Nos', 'No', 'hour', 'ps/km']

async def extract_boq_from_tables(pdf_path):
    """Extract BOQ items from e-GP table format"""
    items = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            tables = page.extract_tables() or []
            for ti, table in enumerate(tables):
                for ri, row in enumerate(table):
                    if not row or not any(row):
                        continue
                    
                    cells = [str(c or "").strip() for c in row]
                    
                    # Skip empty and header rows
                    if not any(c.isdigit() for c in cells[:5]):
                        continue
                    
                    # Check if this row has an item number in column 2 (index 2)
                    # The structure is: ['', '', item_no, group, code_with_newlines, desc, unit, qty, ...]
                    item_no = cells[2] if len(cells) > 2 and cells[2].strip().isdigit() else ""
                    if not item_no:
                        continue
                    
                    item_num = int(item_no)
                    if item_num > 200:
                        continue
                    
                    # Code is in column 4 (index 4), merge newline-separated parts
                    code_text = cells[4] if len(cells) > 4 else ""
                    code_text = code_text.replace("\n", " ").replace(" | ", " ")
                    # Extract code (remove "(BWDB)", "(PWD)", "(LGED)" suffixes)
                    code = ""
                    code_match = re.search(r'([\d]+[\s-][\d]+[\s-]?[\d]*)', code_text)
                    if code_match:
                        code = re.sub(r'\s+', '', code_match.group(1))
                    else:
                        # Try dotted code like "01.1" or "4.07.03"
                        code_match = re.search(r'(\d+(?:\.\d+){1,4})', code_text)
                        if code_match:
                            code = code_match.group(1)
                    
                    # Description in column 5 (index 5)
                    desc = cells[5] if len(cells) > 5 else ""
                    desc = desc.replace("\n", " ").strip()
                    desc = re.sub(r'\s+', ' ', desc)
                    
                    # Unit in column 6 (index 6)
                    unit = cells[6] if len(cells) > 6 else ""
                    unit = unit.lower().strip()
                    
                    # Quantity in column 7 (index 7)
                    qty_str = cells[7] if len(cells) > 7 else "0"
                    qty_str = qty_str.replace(",", "").strip()
                    qty = 0.0
                    try:
                        qty = float(qty_str) if qty_str else 0.0
                    except ValueError:
                        qty = 0.0
                    
                    items.append({
                        'item_no': item_no,
                        'code': code,
                        'description': desc[:500],
                        'unit': unit,
                        'quantity': qty,
                        'rate': None,
                    })
    
    # Deduplicate by item_no
    seen = set()
    unique_items = []
    for item in items:
        if item['item_no'] not in seen:
            seen.add(item['item_no'])
            unique_items.append(item)
    
    # Sort by item number
    unique_items.sort(key=lambda x: int(x['item_no']))
    return unique_items

items = asyncio.run(extract_boq_from_tables(str(BOQ_PDF)))
print(f"Extracted {len(items)} items:")
print()

for item in items:
    code_display = item['code'] if item['code'] else "(no code)"
    print(f"  #{item['item_no']:>3}  {code_display:<20}  {item['unit']:<10}  {str(item['quantity']):<12}  {item['description'][:60]}")

print(f"\nTotal items: {len(items)}")
print(f"Codes by agency:")
agencies = {}
for item in items:
    code = item['code']
    if code.endswith('(BWDB)') or '(BWDB)' in code:
        agencies['BWDB'] = agencies.get('BWDB', 0) + 1
    elif code.endswith('(PWD)') or '(PWD)' in code:
        agencies['PWD'] = agencies.get('PWD', 0) + 1
    elif code.endswith('(LGED)') or '(LGED)' in code:
        agencies['LGED'] = agencies.get('LGED', 0) + 1
    else:
        agencies['UNKNOWN'] = agencies.get('UNKNOWN', 0) + 1
for agency, count in sorted(agencies.items()):
    print(f"  {agency}: {count}")
