"""
SOR PDF Extractor — Extracts item rates from LGED, PWD, BWDB SOR PDFs
Uses PyPDF2 for speed + regex for multi-line item parsing.

Output: rates.csv + rates.json for each agency, with improved descriptions.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

SOR_DIR = Path(__file__).parent

# All known units in Bangladeshi SOR
UNITS = [
    "cum", "sqm", "each", "no", "nos", "kg", "m", "day", "lump", "percent",
    "rmt", "mt", "ton", "pkt", "lot", "set", "job", "sqm.", "m.", "kg.",
    "mm", "cm", "week", "month", "hour", "pair", "litre", "gallon",
]

def _norm_code(code: str) -> str:
    """Normalize item code for matching."""
    return code.strip().replace(" ", "").replace("-", "").replace(".", "").lower()

def _clean_rate(val: str) -> Optional[float]:
    """Parse a rate value string to float."""
    if not val:
        return None
    val = val.strip().replace(",", "").replace("|", "").replace("}", "").replace("]", "")
    val = val.replace("(", "").replace(")", "").replace("_", "")
    if not val or val in ("-", "--", "–", "."):
        return None
    try:
        v = float(val)
        if 0 <= v < 99999999:
            return v
    except ValueError:
        pass
    return None


def _rate_or_fallback(primary: Optional[float], fallback: Optional[float]) -> Optional[float]:
    return fallback if primary is None else primary

def _find_unit(text: str) -> Tuple[str, str]:
    """Find unit in text, return (text_without_unit, unit)."""
    words = text.split()
    for i in range(len(words) - 1, -1, -1):
        w = words[i].strip(".,;:)}]").lower()
        if w in UNITS:
            # Verify it's actually a unit (not part of description)
            if w == "no" and i > 0 and words[i - 1].lower() in ("if", "or", "of", "and", "when", "for"):
                continue
            if w == "m" and i > 0 and words[i - 1].lower() in ("2", "3"):
                continue  # sqm, cum already captured
            unit = words[i].strip(".,;:)}]")
            desc = " ".join(words[:i])
            return desc, unit
    return text, ""


class SORExtractor:
    """Extract SOR rates from PDF files."""

    def extract_all(self) -> Dict[str, List[Dict]]:
        """Extract rates from all three SOR PDFs."""
        results = {}
        for agency in ["LGED", "PWD", "BWDB"]:
            try:
                rates = self.extract(agency)
                results[agency] = rates
                logger.info(f"{agency}: {len(rates)} items extracted")
                self._save(agency, rates)
            except Exception as e:
                logger.error(f"{agency} extraction failed: {e}")
                results[agency] = []
        return results

    def extract(self, agency: str) -> List[Dict]:
        """Extract rates for a specific agency."""
        pdf_path = self._get_pdf_path(agency)
        if not pdf_path or not pdf_path.exists():
            logger.warning(f"SOR PDF not found for {agency}: {pdf_path}")
            return []
        
        logger.info(f"Extracting {agency} SOR from {pdf_path.name}...")
        reader = PdfReader(str(pdf_path))
        
        if agency == "LGED":
            return self._extract_lged(reader)
        elif agency == "PWD":
            return self._extract_pwd(reader)
        elif agency == "BWDB":
            return self._extract_bwdb(reader)
        return []

    def _get_pdf_path(self, agency: str) -> Path:
        """Get the PDF file path for an agency."""
        dir_path = SOR_DIR / agency.lower()
        if not dir_path.exists():
            return None
        
        # Look for the uploaded PDF or existing one
        candidates = list(dir_path.glob("*2023*.pdf")) + list(dir_path.glob("*2022*.pdf")) + list(dir_path.glob("*.pdf"))
        # Prefer the newly uploaded files
        for c in candidates:
            if "Revised" in c.name or "revised" in c.name:
                return c
        return candidates[0] if candidates else None

    def _extract_lged(self, reader: PdfReader) -> List[Dict]:
        """Extract LGED SOR rates."""
        items = []
        current_desc = ""
        current_code = ""
        
        # LGED regex: code then description then unit then 4 rates
        item_pattern = re.compile(
            r'^([\d]+\.[\d]+(?:\.[\d]+(?:\.[\d]+)?)?(?:\s*\([\w]+\))?)\s+'  # Item code
            r'(.+?)\s+'  # Description (non-greedy)
            r'(sqm|cum|each|no|nos|kg|m\.?|day|%|lump|set|job|rmt|mt|ton|pkt|lot|week|month|hour|pair|litre|gallon|mm|cm)\s+'  # Unit
            r'([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)'  # Zone A, B, C, D
            r'(?:\s+([\d,]+\.?\d*))?',  # Optional extra rate
            re.IGNORECASE
        )
        
        for page_num in range(len(reader.pages)):
            text = reader.pages[page_num].extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                # Skip headers
                if any(kw in line for kw in ["Item Code", "Zone-A", "Zone-B", "Schedule of Rates", "Chapter"]):
                    continue
                
                m = item_pattern.match(line)
                if m:
                    code = m.group(1).strip()
                    desc = m.group(2).strip()
                    unit = m.group(3).lower()
                    rate_a = _clean_rate(m.group(4))
                    rate_b = _clean_rate(m.group(5))
                    rate_c = _clean_rate(m.group(6))
                    rate_d = _clean_rate(m.group(7))
                    
                    # Clean description
                    desc = re.sub(r'\s+', ' ', desc).strip().rstrip(",").rstrip(".")
                    
                    if rate_a is not None and code:
                        items.append({
                            "agency": "LGED",
                            "code": code,
                            "description": desc[:300],
                            "unit": unit,
                            "zone_a": rate_a,
                            "zone_b": _rate_or_fallback(rate_b, rate_a),
                            "zone_c": _rate_or_fallback(rate_c, rate_a),
                            "zone_d": _rate_or_fallback(rate_d, rate_a),
                        })
        
        return items

    def _extract_pwd(self, reader: PdfReader) -> List[Dict]:
        """Extract PWD SOR rates."""
        items = []
        current_chapter = ""
        
        # PWD regex patterns
        item_pattern = re.compile(
            r'^([\d\.\-]+(?:\([\w]+\))?)\s+'  # Item No.
            r'(.+?)\s+'
            r'(sqm|cum|each|no|nos|kg|m\.?|day|%|lump|set|job|rmt|mt|ton|pkt|lot|week|month|hour|pair|litre|gallon|mm|cm)\s+'
            r'([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
            re.IGNORECASE
        )
        
        for page_num in range(len(reader.pages)):
            text = reader.pages[page_num].extract_text()
            if not text:
                continue
            
            # Detect chapter
            ch = re.search(r'CHAPTER\s+[\d]+[\s:].+', text, re.IGNORECASE)
            if ch:
                current_chapter = ch.group(0).strip()
            
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                
                # Skip headers
                if any(kw in line for kw in ["Item No.", "Description", "Unit Rate", "Page", "SoR 2022"]):
                    continue
                
                m = item_pattern.match(line)
                if m:
                    code = m.group(1).strip()
                    desc = m.group(2).strip()
                    unit = m.group(3).lower()
                    rate_a = _clean_rate(m.group(4))
                    rate_b = _clean_rate(m.group(5))
                    rate_c = _clean_rate(m.group(6))
                    rate_d = _clean_rate(m.group(7))
                    
                    desc = re.sub(r'\s+', ' ', desc).strip().rstrip(",").rstrip(".")
                    
                    if rate_a is not None and code:
                        items.append({
                            "agency": "PWD",
                            "code": code,
                            "description": desc[:300],
                            "unit": unit,
                            "zone_a": rate_a,
                            "zone_b": _rate_or_fallback(rate_b, rate_a),
                            "zone_c": _rate_or_fallback(rate_c, rate_a),
                            "zone_d": _rate_or_fallback(rate_d, rate_a),
                            "chapter": current_chapter,
                        })
        
        return items

    def _extract_bwdb(self, reader: PdfReader) -> List[Dict]:
        """Extract BWDB SOR rates - handles multi-line descriptions."""
        items = []
        
        # BWDB format: SL.No ItemCode Description Unit ZoneA ZoneB ZoneC ZoneD
        item_pattern = re.compile(
            r'^(\d+(?:\([\d]+\))?)\s+'  # SL.No
            r'([\d]{1,2}[\-–][\d]{2,3}(?:[\-–][\d]{1,2})?(?:\([\w]+\))?)\s+'  # Item Code
            r'(.+?)\s+'
            r'(sqm|cum|each|no|nos|kg|m\.?|day|%|lump|set|job|rmt|mt|ton|pkt|lot|week|month|hour|pair|litre|gallon|mm|cm)\s+'
            r'([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)',
            re.IGNORECASE
        )
        
        # For multi-line items
        all_lines = []
        for page_num in range(len(reader.pages)):
            text = reader.pages[page_num].extract_text()
            if text:
                for line in text.split('\n'):
                    l = line.strip()
                    if l and len(l) > 2:
                        all_lines.append(l)
        
        # Find all item start positions
        starts = []
        for i, line in enumerate(all_lines):
            m = item_pattern.match(line)
            if m:
                starts.append((i, m))
        
        # Extract each item with its description block
        for idx, (start_i, m) in enumerate(starts):
            end_i = starts[idx + 1][0] if idx + 1 < len(starts) else len(all_lines)
            
            code = m.group(2).strip().replace("–", "-")
            unit = m.group(4).lower()
            rate_a = _clean_rate(m.group(5))
            rate_b = _clean_rate(m.group(6))
            rate_c = _clean_rate(m.group(7))
            rate_d = _clean_rate(m.group(8))
            
            # Build description from start line + following lines in block
            first_desc = m.group(3).strip()
            block_lines = all_lines[start_i + 1:end_i]
            
            # Clean first line description (remove rates from end)
            desc = first_desc
            for r in [rate_a, rate_b, rate_c, rate_d]:
                if r:
                    r_str = f"{r:,.2f}".replace(",", "")
                    if r_str in desc:
                        desc = desc.replace(r_str, "").strip()
                    r_str2 = f"{r:,.2f}"
                    if r_str2 in desc:
                        desc = desc.replace(r_str2, "").strip()
            
            # Append continuation lines that don't start a new item
            for bl in block_lines:
                # Skip if it looks like a new item
                if re.match(r'^\d+\s+[\d\-]', bl):
                    continue
                # Clean rates from continuation
                clean_bl = bl.strip()
                for r in [rate_a, rate_b, rate_c, rate_d]:
                    if r:
                        r_str = f"{r:,.2f}".replace(",", "")
                        if r_str in clean_bl:
                            clean_bl = clean_bl.replace(r_str, "").strip()
                        r_str2 = f"{r:,.2f}"
                        if r_str2 in clean_bl:
                            clean_bl = clean_bl.replace(r_str2, "").strip()
                clean_bl = re.sub(r'[\d,]+\.\d{2}', '', clean_bl).strip()
                if clean_bl and len(clean_bl) > 3:
                    desc += " " + clean_bl
            
            desc = re.sub(r'\s+', ' ', desc).strip().rstrip(",").rstrip(".").rstrip("|")
            
            if rate_a is not None and code and len(desc) > 5:
                items.append({
                    "agency": "BWDB",
                    "code": code,
                    "description": desc[:300],
                    "unit": unit,
                    "zone_a": rate_a,
                    "zone_b": _rate_or_fallback(rate_b, rate_a),
                    "zone_c": _rate_or_fallback(rate_c, rate_a),
                    "zone_d": _rate_or_fallback(rate_d, rate_a),
                })
        
        # Deduplicate by code
        seen = {}
        for item in items:
            key = _norm_code(item["code"])
            if key not in seen or (item["unit"] and not seen[key]["unit"]):
                seen[key] = item
            elif key in seen and len(item["description"]) > len(seen[key]["description"]):
                seen[key] = item
        
        return list(seen.values())

    def _save(self, agency: str, rates: List[Dict]):
        """Save rates to CSV and JSON."""
        agency_dir = SOR_DIR / agency.lower()
        agency_dir.mkdir(parents=True, exist_ok=True)
        
        # Sort by code
        rates.sort(key=lambda r: r["code"])
        
        # CSV
        csv_path = agency_dir / "rates.csv"
        fieldnames = ["agency", "code", "description", "unit", "zone_a", "zone_b", "zone_c", "zone_d"]
        if agency == "PWD":
            fieldnames.append("chapter")
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rates:
                row = {k: r.get(k, "") for k in fieldnames}
                w.writerow(row)
        logger.info(f"Saved {len(rates)} rates to {csv_path}")
        
        # JSON
        json_path = agency_dir / "rates.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rates, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(rates)} rates to {json_path}")

    def load_rates(self, agency: str) -> List[Dict]:
        """Load rates from CSV (or JSON) for an agency.
        
        Prefers CSV over JSON because CSV is more reliable.
        Falls back to extraction only if no data file exists.
        """
        agency_dir = SOR_DIR / agency.lower()
        
        # Try CSV first (more reliable)
        csv_path = agency_dir / "rates.csv"
        if csv_path.exists():
            rates = []
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for key in ["zone_a", "zone_b", "zone_c", "zone_d"]:
                        try:
                            row[key] = float(row[key]) if row.get(key) else 0.0
                        except (ValueError, TypeError):
                            row[key] = 0.0
                    rates.append(row)
            if rates:
                return rates
        
        # Try JSON as fallback
        json_path = agency_dir / "rates.json"
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        
        return []


# Global singleton
_extractor: Optional[SORExtractor] = None

def get_extractor() -> SORExtractor:
    global _extractor
    if _extractor is None:
        _extractor = SORExtractor()
    return _extractor


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
    extractor = SORExtractor()
    results = extractor.extract_all()
    total = sum(len(v) for v in results.values())
    print(f"\n✅ Extracted {total} items total:")
    for agency, rates in results.items():
        print(f"   {agency}: {len(rates)} items")
