"""Analyze the 'comma' BWDB PDF (139p) for SOR data"""
import PyPDF2, re

path = r"C:\Users\znasi\Downloads\Documents\BWDB Revised Rate Schedule,2023.pdf"
with open(path, "rb") as f:
    reader = PyPDF2.PdfReader(f)
    print(f"Total pages: {len(reader.pages)}")

    # Extract pages 3-10 (after title/committee/general instructions)
    sample_text = ""
    for i in range(3, min(15, len(reader.pages))):
        t = reader.pages[i].extract_text() or ""
        sample_text += t + "\n---PAGE BREAK---\n"

    print("\n=== Pages 3-14 ===")
    print(sample_text[:3000])

    # Count item codes
    all_text = ""
    for pg in reader.pages:
        all_text += pg.extract_text() or ""

    codes = re.findall(r"\d{2}-\d{3}-\d{2}", all_text)
    print(f"\nItem codes (pattern XX-XXX-XX): {len(set(codes))} unique")

    # Look for rates pattern: 4 numbers with commas
    rate_lines = re.findall(r".*?([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2}).*?", all_text)
    print(f"Lines with 4 rates: {len(rate_lines)}")

    # Check zones mentioned
    zones = re.findall(r"Zone\s*[A-D]", all_text)
    print(f"Zone mentions: {set(zones)}")
