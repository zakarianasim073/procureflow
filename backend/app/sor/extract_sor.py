"""
SOR Rate Extractor - Extracts rates from BWDB, PWD, LGED SOR PDFs into CSV
Usage: python extract_sor.py
Output: sor/bwdb/rates.csv, sor/pwd/rates.csv, sor/lged/rates.csv
"""

import re, csv, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pathlib import Path

SOR_DIR = Path(__file__).parent


def extract_pwd_rates():
    """Extract PWD SOR item rates into CSV"""
    pdf_path = SOR_DIR / "pwd" / "PWD_SOR_2022_Revised.pdf"
    if not pdf_path.exists():
        print(f"PWD SOR not found at {pdf_path}")
        return []

    import PyPDF2
    reader = PyPDF2.PdfReader(str(pdf_path))
    
    rates = []
    in_table = False
    current_chapter = ""
    
    for page_num in range(len(reader.pages)):
        text = reader.pages[page_num].extract_text()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect chapter
            if line.startswith('CHAPTER') or 'Chapter' in line:
                current_chapter = line[:80]
                in_table = False
                continue
            
            # Detect table header
            if 'Item No' in line and 'Description' in line and 'Unit' in line:
                in_table = True
                continue
            
            if not in_table:
                continue
            
            # Parse item rows: "CODE Description of Item unit rate1 rate2 rate3 rate4"
            # Patterns like: "01.1.1", "02.1.2", "03.5.1(PWD)", "06-4-1"
            m = re.match(r'^([\d\.\-]+(?:\([\w]+\))?)\s+(.+?)\s+'
                        r'(per\s+)?(cum|sqm|each|no|nos|kg|mt|rmt|m|day|sqm\.|M\.ton|M\. Ton|%)\s+'
                        r'([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)', 
                        line, re.IGNORECASE)
            if m:
                code = m.group(1)
                desc = m.group(2).strip() + (' ' + m.group(3) if m.group(3) else '')
                unit = m.group(4).lower()
                rate_a = float(m.group(5).replace(',', ''))
                rate_b = float(m.group(6).replace(',', ''))
                rate_c = float(m.group(7).replace(',', ''))
                rate_d = float(m.group(8).replace(',', ''))
                
                rates.append({
                    'agency': 'PWD',
                    'code': code,
                    'description': re.sub(r'\s+', ' ', desc),
                    'unit': unit,
                    'zone_a': rate_a,
                    'zone_b': rate_b,
                    'zone_c': rate_c,
                    'zone_d': rate_d,
                    'chapter': current_chapter
                })
    
    # Save to CSV
    if rates:
        csv_path = SOR_DIR / "pwd" / "rates.csv"
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['agency','code','description','unit','zone_a','zone_b','zone_c','zone_d','chapter'])
            w.writeheader()
            w.writerows(rates)
        print(f"PWD: {len(rates)} rates extracted → {csv_path}")
    return rates


def extract_lged_rates():
    """Extract LGED SOR item rates into CSV"""
    pdf_path = SOR_DIR / "lged" / "LGED_SOR.pdf"
    if not pdf_path.exists():
        print(f"LGED SOR not found at {pdf_path}")
        return []

    import PyPDF2
    reader = PyPDF2.PdfReader(str(pdf_path))
    
    rates = []
    in_table = False
    
    for page_num in range(len(reader.pages)):
        text = reader.pages[page_num].extract_text()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect table header
            if 'Item Code' in line and 'Description' in line and 'Zone-A' in line:
                in_table = True
                continue
            if in_table and ('Schedule of Rates' in line or 'Chapter' in line):
                in_table = False
                continue
            
            if not in_table:
                continue
            
            # LGED format: "CODE Description unit rate_A rate_B rate_C rate_D rate"
            m = re.match(r'^([\w\-\.]+(?:\([\w]+\))?)\s+(.+?)\s+'
                        r'(cum|sqm|each|no|nos|kg|mt|rmt|m|day|sqm\.|%)\s+'
                        r'([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)'
                        r'(?:\s+([\d,]+\.?\d*))?',
                        line, re.IGNORECASE)
            if m:
                code = m.group(1)
                desc = m.group(2).strip()
                unit = m.group(3).lower()
                rate_a = float(m.group(4).replace(',', ''))
                rate_b = float(m.group(5).replace(',', ''))
                rate_c = float(m.group(6).replace(',', ''))
                rate_d = float(m.group(7).replace(',', ''))
                
                rates.append({
                    'agency': 'LGED',
                    'code': code,
                    'description': re.sub(r'\s+', ' ', desc),
                    'unit': unit,
                    'zone_a': rate_a,
                    'zone_b': rate_b,
                    'zone_c': rate_c,
                    'zone_d': rate_d,
                })
    
    if rates:
        csv_path = SOR_DIR / "lged" / "rates.csv"
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['agency','code','description','unit','zone_a','zone_b','zone_c','zone_d'])
            w.writeheader()
            w.writerows(rates)
        print(f"LGED: {len(rates)} rates extracted → {csv_path}")
    return rates


if __name__ == '__main__':
    print("=== SOR Rate Extraction ===\n")
    pwd = extract_pwd_rates()
    lged = extract_lged_rates()
    print(f"\nDone. PWD: {len(pwd)}, LGED: {len(lged)}")
    print("Note: BWDB SOR is scanned PDF - needs OCR processing")
