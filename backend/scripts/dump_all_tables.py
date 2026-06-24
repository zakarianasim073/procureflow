"""Dump ALL pdfplumber tables to understand structure"""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from pathlib import Path
import pdfplumber

BOQ_PDF = Path("uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf")

with pdfplumber.open(BOQ_PDF) as pdf:
    for pi, page in enumerate(pdf.pages):
        tables = page.extract_tables() or []
        if not tables:
            continue
        for ti, table in enumerate(tables):
            print(f"\n=== Page {pi+1}, Table {ti+1}: {len(table)} rows ===")
            for ri, row in enumerate(table[:10]):  # First 10 rows
                cells = [str(c or "").strip().replace("\n", " | ")[:80] for c in row]
                print(f"  R{ri}: {cells}")
            if len(table) > 10:
                print(f"  ... ({len(table)-10} more rows)")
