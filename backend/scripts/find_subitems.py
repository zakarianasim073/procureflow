"""Find subitem codes in BOQ descriptions"""
import pdfplumber, re

boq_dir = r"D:\A1\procurementflow_final_v3\procurementflow\backend\uploads\1290886\docs\Section6_Bill of Quantities"
path = None
import os
for f in os.listdir(boq_dir):
    if f.endswith(".pdf"):
        path = os.path.join(boq_dir, f)
        break

with pdfplumber.open(path) as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        text = page.extract_text() or ""
        # Look for subitem patterns like 40-270-10 in text
        subitems = re.findall(r'\d{1,4}-\d{1,4}-\d{2,4}', text)
        if subitems:
            print(f"Page {i+1} codes in text: {subitems}")
        for ti, table in enumerate(tables):
            for row in table:
                if not row:
                    continue
                cells = [str(c or "").replace("\n", " ").strip() for c in row]
                # Check each cell for subitem codes
                for ci, cell in enumerate(cells):
                    codes = re.findall(r'\b(\d{1,4}-\d{1,4}-\d{2,4})\b', cell)
                    if codes:
                        print(f"  Page {i+1} T{ti} C{ci}: {codes} -> {cell[:100]}")
