"""Dump pdfplumber table contents to see BOQ items"""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from pathlib import Path
import pdfplumber
import json

BOQ_PDF = Path("uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf")

with pdfplumber.open(BOQ_PDF) as pdf:
    all_items = []
    for pi, page in enumerate(pdf.pages):
        tables = page.extract_tables() or []
        for ti, table in enumerate(tables):
            for ri, row in enumerate(table):
                if not row or not any(row):
                    continue
                cells = [str(c or "").strip().replace("\n", " ") for c in row]
                # Skip Lot Detail header table
                if "Lot Detail" in cells[0] or "Lot No." in cells[0]:
                    continue
                # Skip header rows
                if any("Item" in c and "no." in str(row[ri-1] if ri>0 else "") for c in cells):
                    continue
                if "Item no." in cells[0].lower():
                    continue
                
                # Check if first cell looks like an item number
                first = cells[0].strip()
                if first.isdigit() and int(first) <= 200:
                    all_items.append({
                        "page": pi + 1,
                        "table": ti,
                        "row": ri,
                        "cells": cells[:6],  # First 6 cols
                    })
    
    print(f"Found {len(all_items)} potential BOQ items:")
    for item in all_items[:20]:
        print(f"  P{item['page']}T{item['table']}R{item['row']}: {item['cells']}")
    if len(all_items) > 20:
        print(f"  ... and {len(all_items) - 20} more")

print(f"\nTotal items found: {len(all_items)}")
