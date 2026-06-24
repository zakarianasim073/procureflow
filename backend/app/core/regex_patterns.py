class EGPPatterns:
    PATTERNS = {
        "tender_id": r"Tender\s*(?:ID|No\.?|Number)\s*[:\-]\s*(\S+)",
        "title": r"(?:Project|Work)\s*Title\s*[:\-]\s*(.+)",
        "closing_date": r"Closing\s*Date\s*[:\-]\s*(.+)",
        "opening_date": r"Opening\s*Date\s*[:\-]\s*(.+)",
        "agency": r"(?:Procuring|Client)\s*(?:Entity|Agency)\s*[:\-]\s*(.+)",
        "district": r"District\s*[:\-]\s*(\S+)",
        "estimated_cost": r"Estimated\s*(?:Cost|Amount)\s*[:\-]\s*([\d,\.]+)",
    }

    PATTERNS_BN = {
        "tender_id": r"টেন্ডার\s*(?:আইডি|নং)\s*[:\-]\s*(\S+)",
        "title": r"প্রকল্পের\s*শিরোনাম\s*[:\-]\s*(.+)",
        "closing_date": r"জমাদানের\s*শেষ\s*তারিখ\s*[:\-]\s*(.+)",
        "opening_date": r"খোলার\s*তারিখ\s*[:\-]\s*(.+)",
        "agency": r"ক্রয়কারী\s*সত্তা\s*[:\-]\s*(.+)",
        "district": r"জেলা\s*[:\-]\s*(\S+)",
    }
