"""
BWDB SOR Extractor - FINAL VERSION
- Uses first line only for rate detection (covers 95%+ of items)
- For multi-line items, checks last line of block
- Hyphen-only code pattern prevents rate-as-code confusion
Usage: python extract_bwdb.py
"""

import re, csv
from pathlib import Path
SOR_DIR = Path(__file__).parent

UNITS = ['cum', 'sqm', 'each', 'no', 'nos', 'kg', 'm', 'day', 'lump', '%', 'rmt', 'mt', 'ton', 'pkt', 'lot', 'set', 'job']

def get_floats(text: str) -> list:
    """Extract all valid numbers from text as floats."""
    nums = re.findall(r'[\d,]+\.?\d*', text)
    floats = []
    for n in nums:
        n = n.strip().replace('|', '').replace('}', '').replace(']', '').replace('[', '')
        n = n.replace('(', '').replace(')', '').strip()
        if not n or n in ('-', '--', '–', '-'):
            continue
        if ',' in n:
            if '.' in n:
                n = n.replace(',', '')
            elif len(n.split(',')[-1]) <= 2:
                n = n.replace(',', '.')
            else:
                n = n.replace(',', '')
        try:
            v = float(n)
            if v > 1.0 and not (2020 <= v <= 2030):
                floats.append(v)
        except Exception:
            continue
    return floats

def find_rates(text: str) -> list:
    """Find 4 zone rates. Returns [a,b,c,d] or empty."""
    floats = get_floats(text)
    if len(floats) < 4:
        return []
    # Forward: find first 4 with max/min < 2.0
    for i in range(len(floats) - 3):
        c4 = floats[i:i+4]
        if min(c4) > 0 and max(c4) / min(c4) < 2.0:
            return c4
    # Backward: find 4 with max/min < 3.0
    for i in range(len(floats) - 4, -1, -1):
        c4 = floats[i:i+4]
        if min(c4) > 0 and max(c4) / min(c4) < 3.0:
            return c4
    return floats[-4:]

def extract_bwdb_rates():
    import PyPDF2
    pdf = SOR_DIR / "bwdb" / "BWDB_SOR_2022_pdfcoffee.pdf"
    reader = PyPDF2.PdfReader(str(pdf))
    
    all_lines = []
    for i in range(31, len(reader.pages)):
        for line in reader.pages[i].extract_text().split('\n'):
            l = line.strip()
            if l:
                all_lines.append(l)
    
    print(f"Lines from p32-137: {len(all_lines)}")
    
    # Hyphen-only BWDB code: XX-XXX-XX or X-XXX-XX
    code_pat = r'\d{1,2}-\d{2,3}(?:-\d{1,2})?(?:\([\w]+\))?'
    item_pat = re.compile(
        r'^(\d+(?:\([\d]+\))?)\s*[|}\[\]\(\)_\s]*\s*(' + code_pat + r')'
    )
    
    starts = [(i, m.group(1), m.group(2)) for i, line in enumerate(all_lines)
              if (m := item_pat.match(line)) and re.match(r'^\d{1,2}-\d{2,3}', m.group(2))]
    print(f"Items: {len(starts)}")
    
    code_index = {s[2] for s in starts}
    
    items = []
    for idx, (start_i, sl_no, code) in enumerate(starts):
        end_i = starts[idx+1][0] if idx+1 < len(starts) else len(all_lines)
        blk = all_lines[start_i:end_i]
        first = blk[0]
        
        # Clean first line: remove SL.No + Code prefix
        clean = re.sub(
            r'^\d+(?:\([\d]+\))?\s*[|}\[\]\(\)_\s]*\s*' + re.escape(code) + r'(?:\s*[|}\[\]\(\)_\s]*\s*)?',
            ' ', first
        ).strip()
        
        rates = find_rates(clean)
        
        if not rates:
            # Check last non-empty line for multi-line items
            for li in range(len(blk)-1, -1, -1):
                lr = find_rates(blk[li])
                if lr:
                    rates = lr
                    break
        
        if not rates:
            continue
        
        # Build description
        desc = clean
        if len(blk) > 1:
            rest = ' '.join(l for l in blk[1:] if not item_pat.match(l))
            desc = clean + ' ' + rest if rest else clean
        
        # Strip rates from desc
        for rv in reversed(rates):
            for rs in reversed(re.findall(r'[\d,]+\.?\d*', desc)):
                try:
                    if abs(float(rs.replace(',','')) - rv) < 0.01:
                        desc = desc.rsplit(rs, 1)[0].strip()
                        break
                except Exception: pass

        desc = re.sub(r'\s+', ' ', desc).strip().strip('|').strip(',').strip('}').strip(']').strip(')').strip('.').strip()
        
        # Find unit
        unit = ''
        words = desc.split()
        for i in range(len(words)-1, -1, -1):
            w = words[i].strip('.,;:)}]').lower()
            if w in UNITS:
                if w == 'no' and i > 0 and words[i-1].lower() in ('if','or','of','and','when'):
                    continue
                unit = w
                desc = ' '.join(words[:i])
                break
        
        desc = re.sub(r'\s+', ' ', desc).strip()
        
        # OCR fixes
        desc = re.sub(r'(\d+)cem', r'\1cm', desc)
        desc = re.sub(r'(\d+)em(?![a-zA-Z])', r'\1cm', desc)
        desc = re.sub(r'\$(\d)', r'5\1', desc)
        for o, n in {'B10ck':'Block','b10ck':'block','inc1uding':'including','rem0ving':'removing',
                     '1and':'land','d1rection':'direction','w0rk':'work','a11':'all',
                     'Kes':'Kg','n0 ':'no ','n°':'no'}.items():
            desc = desc.replace(o, n)
        
        if rates and len(desc) > 2:
            items.append({
                'agency':'BWDB','code':code,'description':desc[:250],'unit':unit,
                'zone_a':rates[0],'zone_b':rates[1],'zone_c':rates[2],'zone_d':rates[3],
            })
    
    # Deduplicate
    seen = {}
    for item in items:
        if item['code'] not in seen or (item['unit'] and not seen[item['code']]['unit']):
            seen[item['code']] = item
    items = list(seen.values())
    print(f"Extracted: {len(items)}")
    return items

def save_rates_csv(rates, fp=None):
    fp = fp or SOR_DIR / "bwdb" / "rates.csv"
    rates.sort(key=lambda r: r['code'])
    with open(fp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['agency','code','description','unit','zone_a','zone_b','zone_c','zone_d'])
        w.writeheader()
        w.writerows(rates)
    print(f"Saved {len(rates)} to {fp}")

if __name__ == '__main__':
    print("=== BWDB SOR Extraction ===\n")
    save_rates_csv(extract_bwdb_rates())
    print("\nDone!")
