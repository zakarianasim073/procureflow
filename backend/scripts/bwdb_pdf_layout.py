"""Analyze BWDB PDF layout for better extraction"""
import pdfplumber
import re

pdf_path = r"C:\Users\znasi\Downloads\Documents\BWDB Revised Rate Schedule2023.pdf"

with pdfplumber.open(pdf_path) as pdf:
    for pg in range(min(5, len(pdf.pages))):
        page = pdf.pages[pg]
        words = page.extract_words(x_tolerance=3, y_tolerance=3)
        print(f"\n=== Page {pg}: {len(words)} words ===")
        # Group words by y position (row)
        rows = {}
        for w in words:
            y_key = round(w["top"], 0)
            if y_key not in rows:
                rows[y_key] = []
            rows[y_key].append((w["x0"], w["text"]))
        for y_key in sorted(rows.keys()):
            row_text = " ".join(t[1] for t in sorted(rows[y_key], key=lambda x: x[0]))
            if any(c.isdigit() for c in row_text):
                print(f"  y={y_key:5.0f}: {row_text[:150]}")
