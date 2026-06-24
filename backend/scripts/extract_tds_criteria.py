"""Extract financial qualification criteria from TDS PDF"""
import pdfplumber, re, json, sys, os

def extract_tds_criteria(boq_path: str, tender_id: str) -> dict:
    """Extract financial criteria from TDS PDF for a tender."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(boq_path)))
    tds_dir = os.path.join(base, "uploads", tender_id, "docs", "Section2_Tender Data Sheet")
    tds_pdf = None
    if os.path.isdir(tds_dir):
        for f in os.listdir(tds_dir):
            if f.endswith(".pdf"):
                tds_pdf = os.path.join(tds_dir, f)
                break
    
    if not tds_pdf or not os.path.isfile(tds_pdf):
        print(f"TDS PDF not found at {tds_dir}")
        return {}
    
    with pdfplumber.open(tds_pdf) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    
    criteria = {}
    
    # General Experience
    m = re.search(r"minimum number of years of General Experience.*?shall be\s+(\d+)", text, re.I | re.S)
    if m:
        criteria["general_experience"] = f"{m.group(1)} years"
    
    # Specific Experience (value)
    m = re.search(r"each with a value of at least Tk\.?\s*([\d,]+\.?\d*)\s*Lakh", text, re.I | re.S)
    if m:
        criteria["specific_experience_value"] = f"Tk. {m.group(1)} Lakh"
    
    # Specific Experience (contracts count)
    m = re.search(r"at least\s+(\d+)\s*\(?\w*\)?\s*(?:one|contract)", text, re.I | re.S)
    if not m:
        m = re.search(r"minimum Specific Experience.*?(\d+)\s+\(?\w*\)?\s*contract", text, re.I | re.S)
    if m:
        criteria["specific_experience_count"] = m.group(1)
    
    # Avg Annual Turnover
    m = re.search(r"average annual construction turnover.*?greater than Tk\.?\s*([\d,]+\.?\d*)\s*Lakh", text, re.I | re.S)
    if m:
        criteria["avg_annual_turnover"] = f"Tk. {m.group(1)} Lakh"
    
    # Liquid Assets
    m = re.search(r"financial resources.*?shall be Tk\s*([\d,]+\.?\d*)\s*Lakh", text, re.I | re.S)
    if m:
        criteria["liquid_assets"] = f"Tk. {m.group(1)} Lakh"
    
    # Min Tender Capacity
    m = re.search(r"minimum tender capacity shall be:\s*([\d,]+\.?\d*)\s*Lakh", text, re.I | re.S)
    if m:
        criteria["min_tender_capacity"] = f"Tk. {m.group(1)} Lakh"
    
    # Tender Security
    m = re.search(r"Tender Security shall be Tk\.?\s*([\d,]+\.?\d*)\s*Lakh", text, re.I | re.S)
    if m:
        criteria["tender_security"] = f"Tk. {m.group(1)} Lakh"
    
    # Performance Security %
    m = re.search(r"at the rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent.*?Performance Security", text, re.I | re.S)
    if not m:
        m = re.search(r"rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent", text, re.I | re.S)
    if m:
        criteria["performance_security"] = f"{m.group(1)}%"
    
    # Retention Money %
    m = re.search(r"rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent.*?Retention Money", text, re.I | re.S)
    if not m:
        m = re.search(r"deduct at the rate of\s*(?:five|5)\s*\(?(\d+)\)?\s*percent", text, re.I | re.S)
    if m:
        criteria["retention_money"] = f"{m.group(1)}%"
    
    return criteria

if __name__ == "__main__":
    boq_path = r"D:\A1\procurementflow_final_v3\procurementflow\backend\uploads\57c20c63.pdf"
    result = extract_tds_criteria(boq_path, "1290886")
    print(json.dumps(result, indent=2))
