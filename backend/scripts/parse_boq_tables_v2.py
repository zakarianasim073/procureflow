"""Parse BOQ items from pdfplumber tables - v2 with fixes"""
import sys, re, json
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from pathlib import Path
import pdfplumber
import asyncio

BOQ_PDF = Path("uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf")

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
                    
                    cells_raw = row
                    # Merge multi-line cell text
                    cells = []
                    for c in cells_raw:
                        txt = str(c or "").strip()
                        txt = txt.replace("\n", " ").replace("|", "")
                        txt = re.sub(r'\s+', ' ', txt).strip()
                        cells.append(txt)
                    
                    # Find item number: try col 0, then col 2
                    item_no = ""
                    if len(cells) > 0 and cells[0].strip().isdigit():
                        item_no = cells[0].strip()
                    elif len(cells) > 2 and cells[2].strip().isdigit():
                        item_no = cells[2].strip()
                    
                    if not item_no:
                        continue
                    
                    item_num = int(item_no)
                    if item_num > 200:
                        continue
                    
                    # Skip if already seen
                    if any(it['item_no'] == item_no for it in items):
                        continue
                    
                    # Code: find from any column that looks like a code
                    code = ""
                    for ci in range(min(len(cells), 8)):
                        c = cells[ci]
                        # Full code: 04-180-00 (BWDB) or 40-620-00
                        # The merge above removed | so "40-620- 00 (BWDB)" -> "40-620-00 (BWDB)"
                        m = re.search(r'(\d{1,4}-\d{1,4}-\d{1,4})(?:\s*\((\w+)\))?', c)
                        if m:
                            code = m.group(1)
                            break
                        # Dotted code: 4.07.03 or 01.1
                        m = re.search(r'(\d+(?:\.\d+){1,4})(?:\s*\((\w+)\))?', c)
                        if m:
                            code = m.group(1)
                            break
                        # Partial code ended with dash: "40-620-"
                        if re.search(r'\d+-\d+-$', c):
                            code = c.strip()
                            break
                    
                    # Description: find from first column after the code column
                    desc = ""
                    for ci in range(1, min(len(cells), 8)):
                        c = cells[ci]
                        if len(c) > 30 and not c.replace('.', '').replace(',', '').isdigit():
                            # This looks like a description
                            if not any(kw in c for kw in ['Item no', 'Group', 'Item Code', 'Description', 'Measurement', 'Unit Price', 'Total Price', 'Grand Total', 'Table', 'Name :', 'Discount', 'Provisional', 'Unconditional']):
                                desc = c
                                break
                    
                    # Unit and qty: scan for pattern "unit qty"
                    unit = ""
                    qty_str = ""
                    for ci in range(min(len(cells), 10)):
                        c = cells[ci]
                        # Check for "unit number" pattern
                        for u_pattern in ['sqm', 'cum', 'nos', 'no', 'kg', 'm', 'each', 'job', 'set', 'hour', 'point', 'm. ton', 'ps/ km', 'cum/ km', 'm of weld']:
                            pat = re.search(rf'\b{re.escape(u_pattern)}\b\s+([\d,]+\.?\d*)', c, re.IGNORECASE)
                            if pat:
                                unit = u_pattern.lower()
                                qty_str = pat.group(1).replace(',', '')
                                break
                            # Also "qty unit" or just "unit" alone in cell
                            pat2 = re.search(rf'\b([\d,]+\.?\d*)\s+{re.escape(u_pattern)}\b', c, re.IGNORECASE)
                            if pat2:
                                unit = u_pattern.lower()
                                qty_str = pat2.group(1).replace(',', '')
                                break
                        if unit:
                            break
                    
                    # If no unit found, try last columns as qty
                    if not qty_str:
                        for ci in [5, 6, 7, 4]:
                            if ci < len(cells):
                                c = cells[ci].replace(',', '').strip()
                                if re.match(r'^[\d]+\.?\d*$', c):
                                    qty_str = c
                                    break
                    
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
    
    # Sort by item number
    items.sort(key=lambda x: int(x['item_no']))
    return items

items = asyncio.run(extract_boq_from_tables(str(BOQ_PDF)))
print(f"Extracted {len(items)} items:")
print()

for item in items[:10]:
    code_display = item['code'] if item['code'] else "(no code)"
    print(f"  #{item['item_no']:>3}  {code_display:<20}  {item['unit']:<10}  {str(item['quantity']):<12}  {item['description'][:60]}")

print(f"\n... ({len(items)} total)")
print(f"\nAll items as JSON:")
print(json.dumps(items, indent=2))
