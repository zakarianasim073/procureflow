"""
BOQ Matcher — Matches tender BOQ items against SOR rate schedules
Supports fuzzy matching by item code, description similarity, or both.

Usage:
  from app.sor.boq_matcher import BOQMatcher
  
  matcher = BOQMatcher()
  matcher.load_all()  # Load SOR data for all agencies
  
  # Match a single item
  result = matcher.match_item(agency="LGED", code="1.10.01", zone="A")
  
  # Match an entire BOQ
  boq_items = [{"code": "1.10.01", "description": "...", "quantity": 100}, ...]
  results = matcher.match_boq(boq_items, agency="LGED", zone="A")
  
  # Generate comparison document
  doc = matcher.generate_comparison(boq_items, agency="LGED", zone="A")
"""

from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .sor_extractor import SORExtractor, _norm_code, _clean_rate

logger = logging.getLogger(__name__)

SOR_DIR = Path(__file__).parent


def _zone_rate(item: Dict[str, Any], zone: str) -> float:
    zone_key = f"zone_{(zone or 'A').lower()}"
    value = item.get(zone_key)
    if value is None:
        value = item.get("zone_a", 0)
    return value or 0.0


class BOQMatcher:
    """Match BOQ items against SOR rate schedules with fuzzy matching."""

    def __init__(self):
        self._sor_data: Dict[str, Dict] = {"LGED": {}, "PWD": {}, "BWDB": {}}
        self._sor_list: Dict[str, List[Dict]] = {"LGED": [], "PWD": [], "BWDB": []}
        self._loaded = False

    def load_all(self):
        """Load SOR data for all agencies."""
        extractor = SORExtractor()
        
        for agency in ["LGED", "PWD", "BWDB"]:
            rates = extractor.load_rates(agency)
            
            # If no rates loaded, try extraction
            if not rates:
                rates = extractor.extract(agency)
            
            self._sor_list[agency] = rates
            
            # Build lookup indexes
            idx = {}
            for r in rates:
                code = _norm_code(r["code"])
                if code not in idx:
                    idx[code] = r
            self._sor_data[agency] = idx
        
        self._loaded = True
        total = sum(len(v) for v in self._sor_list.values())
        logger.info(f"Loaded {total} SOR items across {len([k for k in self._sor_list if self._sor_list[k]])} agencies")

    def match_item(
        self,
        code: str = "",
        description: str = "",
        agency: str = "",
        zone: str = "A",
        threshold: float = 0.4,
    ) -> Dict[str, Any]:
        """Match a single BOQ item against SOR.
        
        Args:
            code: Item code from BOQ
            description: Item description from BOQ
            agency: SOR agency ("LGED", "PWD", "BWDB", or "" for all)
            zone: Zone for rate lookup ("A", "B", "C", "D")
            threshold: Fuzzy match threshold (0-1)
        
        Returns:
            Dict with match results
        """
        if not self._loaded:
            self.load_all()
        
        result = {
            "matched": False,
            "confidence": 0.0,
            "sor_item": None,
            "sor_rate": 0.0,
            "matched_by": "",
            "alternatives": [],
        }
        
        # Determine which agencies to search
        agencies = [agency] if agency else ["LGED", "PWD", "BWDB"]
        
        normalized_code = _norm_code(code) if code else ""
        
        best_match = None
        best_score = 0.0
        
        for ag in agencies:
            idx = self._sor_data.get(ag, {})
            items = self._sor_list.get(ag, [])
            
            # 1. Exact code match
            if normalized_code and normalized_code in idx:
                sor_item = idx[normalized_code]
                rate = _zone_rate(sor_item, zone)
                score = 1.0
                if score > best_score:
                    best_score = score
                    best_match = {
                        "matched": True,
                        "confidence": 1.0,
                        "sor_item": sor_item,
                        "sor_rate": rate,
                        "matched_by": "exact_code",
                        "agency": ag,
                        "alternatives": [],
                    }
            
            # 2. Partial code match (code substrings)
            if normalized_code and not best_match:
                for sor_code, sor_item in idx.items():
                    if normalized_code in sor_code or sor_code in normalized_code:
                        rate = _zone_rate(sor_item, zone)
                        score = min(len(normalized_code), len(sor_code)) / max(len(normalized_code), len(sor_code))
                        if score > 0.5 and score > best_score:
                            best_score = score
                            best_match = {
                                "matched": True,
                                "confidence": score,
                                "sor_item": sor_item,
                                "sor_rate": rate,
                                "matched_by": "partial_code",
                                "agency": ag,
                                "alternatives": [],
                            }
            
            # 3. Description fuzzy match
            if description and not best_match:
                desc_lower = description.lower()
                desc_words = set(desc_lower.split())
                
                for sor_item in items:
                    sor_desc = sor_item.get("description", "").lower()
                    
                    # Word overlap scoring
                    sor_words = set(sor_desc.split())
                    if not desc_words or not sor_words:
                        continue
                    
                    intersection = desc_words & sor_words
                    union = desc_words | sor_words
                    
                    if len(union) == 0:
                        continue
                    
                    jaccard = len(intersection) / len(union)
                    
                    # Boost for numeric matches (quantities, measurements)
                    desc_nums = set(re.findall(r'\d+\.?\d*', desc_lower))
                    sor_nums = set(re.findall(r'\d+\.?\d*', sor_desc))
                    num_score = len(desc_nums & sor_nums) / max(len(desc_nums | sor_nums), 1) if desc_nums or sor_nums else 0
                    
                    score = jaccard * 0.7 + num_score * 0.3
                    
                    if score > threshold and score > best_score:
                        best_score = score
                        rate = _zone_rate(sor_item, zone)
                        best_match = {
                            "matched": True,
                            "confidence": round(score, 3),
                            "sor_item": sor_item,
                            "sor_rate": rate,
                            "matched_by": "description_fuzzy",
                            "agency": ag,
                            "alternatives": [],
                        }
        
        if best_match:
            # Find alternatives
            if code and normalized_code:
                for ag in agencies:
                    for sor_code, sor_item in self._sor_data.get(ag, {}).items():
                        if sor_code != normalized_code and (normalized_code in sor_code or sor_code in normalized_code):
                            rate = _zone_rate(sor_item, zone)
                            best_match["alternatives"].append({
                                "code": sor_item["code"],
                                "description": sor_item.get("description", "")[:80],
                                "rate": rate,
                                "agency": ag,
                            })
            
            return best_match
        
        return result

    def match_boq(
        self,
        boq_items: List[Dict[str, Any]],
        agency: str = "",
        zone: str = "A",
        threshold: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """Match an entire BOQ against SOR.
        
        Args:
            boq_items: List of BOQ items with keys: code, description, quantity, unit
            agency: SOR agency
            zone: Zone for rate lookup
            threshold: Match threshold
        
        Returns:
            List of match results
        """
        if not self._loaded:
            self.load_all()
        
        results = []
        for item in boq_items:
            code = item.get("code", "")
            description = item.get("description", "")
            quantity = float(item.get("quantity", 0))
            
            match = self.match_item(
                code=code,
                description=description,
                agency=agency or item.get("agency", ""),
                zone=zone,
                threshold=threshold,
            )
            
            matched_rate = match.get("sor_rate", 0)
            sor_item = match.get("sor_item") or {}
            
            results.append({
                "boq_code": code,
                "boq_description": description[:100],
                "boq_unit": item.get("unit", ""),
                "boq_quantity": quantity,
                "matched": match["matched"],
                "confidence": match["confidence"],
                "matched_by": match["matched_by"],
                "sor_code": sor_item.get("code", ""),
                "sor_description": sor_item.get("description", "")[:100] if sor_item else "",
                "sor_unit": sor_item.get("unit", ""),
                "sor_rate": matched_rate,
                "total_amount": matched_rate * quantity,
                "agency": match.get("agency", agency),
                "zone": zone,
                "alternatives": match.get("alternatives", []),
            })
        
        return results

    def generate_comparison(
        self,
        boq_items: List[Dict[str, Any]],
        agency: str = "",
        zone: str = "A",
        threshold: float = 0.4,
    ) -> Dict[str, Any]:
        """Generate a comprehensive comparison document.
        
        Returns a dict with summary, matched and unmatched items,
        and total cost comparison.
        """
        matches = self.match_boq(boq_items, agency, zone, threshold)
        
        matched_items = [m for m in matches if m["matched"]]
        unmatched_items = [m for m in matches if not m["matched"]]
        
        total_sor = sum(m["total_amount"] for m in matched_items)
        total_boq = sum(
            (float(item.get("quantity", 0) or 0) * float(item.get("rate", 0) or 0))
            for item in boq_items
        )

        return {
            "summary": {
                "total_items": len(matches),
                "matched": len(matched_items),
                "unmatched": len(unmatched_items),
                "match_rate": round(len(matched_items) / max(len(matches), 1) * 100, 1),
                "total_sor_amount": round(total_sor, 2),
                "total_boq_amount": round(total_boq, 2),
                "agency": agency or "AUTO",
                "zone": zone,
            },
            "matched_items": matched_items,
            "unmatched_items": unmatched_items,
            "zone_rates": {
                "A": "Dhaka & Mymensingh (LGED) / Dhaka (PWD)",
                "B": "Chattogram & Sylhet (LGED) / Chattogram (PWD)",
                "C": "Rajshahi & Rangpur (LGED) / Khulna (PWD)",
                "D": "Khulna & Barishal (LGED) / Rajshahi (PWD)",
            },
        }


# BOQ Parser — parses BOQ from PDF or structured data

class BOQParser:
    """Parse BOQ data from PDF or text formats."""

    # Known measurement units in e-GP BOQ
    UNITS = {
        'sqm', 'sq.m', 'cum', 'cum/km', 'each', 'no', 'nos', 'kg', 'm',
        'day', '%', 'lump', 'set', 'job', 'rmt', 'mt', 'ton', 'pkt', 'lot',
        'week', 'month', 'hour', 'pair', 'litre', 'gallon', 'mm', 'cm',
        'kwp', 'kw', 'mtr', 'rft', 'cft', 'sqft', 'hr', 'km', 'l.s',
        'lumsum', 'lump sum', 'point', 'trip', 'mile', 'yard',
    }

    UNIT_MAP = {
        'sq.m': 'sqm', 'sq.m.': 'sqm', 'sq. m': 'sqm',
        'cum/km': 'cum/km', 'cum/ km': 'cum/km',
        'l.s': 'lump', 'lumsum': 'lump', 'lump sum': 'lump',
        'no': 'nos', 'no.': 'nos', 'nos.': 'nos',
        'm.': 'm', 'mtr': 'm', 'meter': 'm',
        'kg.': 'kg', 'mt': 'ton',
        'kw': 'kwp',
        'hr': 'hour',
    }

    # Regex for e-GP BOQ item code patterns
    CODE_PATTERN = r'(?:\d{2,3}[-]\d{1,3}(?:[-]\d+)?(?:\([\w]+\))?)'
    PWD_EM_CODE = r'(?:PWD\s*(?:EM)?\s*(?:\d+(?:\.\d+)*))'

    @staticmethod
    def _find_unit_qty(text):
        """Extract unit and quantity from text.
        
        Handles e-GP BOQ PDF format where unit+quantity appears before
        "Fill By" marker in patterns like:
          "...description.sqm 36000.00 Fill By"
          "...description each 1.00 Fill By"  
          "...descriptionCum/ Km 5178.74 Fill By"
          "...Nos 4380.00 Fill By"
        """
        # Build unit pattern (longest first)
        unit_list = sorted(BOQParser.UNITS, key=len, reverse=True)
        # Also add variants with / in them
        unit_list_ext = unit_list + ['cum/km', 'cum/ km', 'l.s', 'sq.m', 'nos', 'no']
        unit_list_ext = sorted(set(unit_list_ext), key=len, reverse=True)
        
        unit_pattern = '|'.join(re.escape(u) for u in unit_list_ext)
        
        # Find "Fill By" or "Fill Tenderer" position
        fill_match = re.search(r'Fills?\s+By', text, re.IGNORECASE)
        if fill_match:
            # Look backwards from "Fill By" for unit+qty pattern
            pre_fill = text[:fill_match.start()].strip()
            
            # Pattern: optional dot or space, then UNIT, then optional space, then QUANTITY
            # The unit might be attached to previous word with a dot (e.g., "charge.sqm")
            patterns = [
                # Unit separated by dot or space from description, then qty
                rf'(?:\.|\s|\b)({unit_pattern})\s+([\d,]+(?:\.\d+)?)\s*$',
                # Qty then unit (for "5 Kg" patterns)  
                rf'([\d,]+(?:\.\d+)?)\s+\b({unit_pattern})\s*$',
                # Unit directly at end (quantity might be embedded)
                rf'\b({unit_pattern})\s+([\d,]+(?:\.\d+)?)',
            ]
            
            for pat in patterns:
                m = re.search(pat, pre_fill, re.IGNORECASE)
                if m:
                    groups = m.groups()
                    if len(groups) == 2:
                        a, b = groups
                        # Determine which is unit and which is qty
                        a_str = a.strip()
                        b_str = b.strip()
                        a_is_unit = a_str.lower() in [u.lower() for u in unit_list_ext]
                        b_is_unit = b_str.lower() in [u.lower() for u in unit_list_ext]
                        a_is_qty = a_str.replace('.', '').replace(',', '').isdigit()
                        b_is_qty = b_str.replace('.', '').replace(',', '').isdigit()
                        
                        if a_is_unit and b_is_qty:
                            unit_raw = a_str.lower()
                            qty_str = b_str
                        elif a_is_qty and b_is_unit:
                            unit_raw = b_str.lower()
                            qty_str = a_str
                        else:
                            continue
                        
                        try:
                            # Remove commas (thousand separators) but keep dots (decimal points)
                            qty = float(qty_str.replace(',', '').strip())
                            norm_unit = BOQParser.UNIT_MAP.get(unit_raw, unit_raw)
                            # Normalize special units
                            norm_unit = norm_unit.replace('cum/', 'cum/').strip().lower()
                            return norm_unit, qty
                        except ValueError:
                            continue
        
        # Fallback: search entire text
        for pat in [
            rf'\b({unit_pattern})\s+([\d,]+(?:\.\d+)?)',
            rf'([\d,]+(?:\.\d+)?)\s+\b({unit_pattern})\b',
        ]:
            for m in re.finditer(pat, text, re.IGNORECASE):
                groups = m.groups()
                a, b = groups
                a_str = a.strip().lower()
                b_str = b.strip().lower()
                
                a_is_unit = a_str in [u.lower() for u in unit_list_ext]
                b_is_unit = b_str in [u.lower() for u in unit_list_ext]
                a_is_qty = a_str.replace('.', '').replace(',', '').replace('-', '').isdigit()
                b_is_qty = b_str.replace('.', '').replace(',', '').replace('-', '').isdigit()
                
                if a_is_unit and b_is_qty:
                    try:
                        return BOQParser.UNIT_MAP.get(a_str, a_str), float(b_str.replace(',', ''))
                    except ValueError:
                        continue
                elif a_is_qty and b_is_unit and not a_is_unit:
                    try:
                        return BOQParser.UNIT_MAP.get(b_str, b_str), float(a_str.replace(',', ''))
                    except ValueError:
                        continue
        
        return '', 0.0

    @staticmethod
    def _extract_code_from_text(text):
        """Extract item code from text, handling e-GP formats."""
        # Try standard code pattern
        m = re.search(BOQParser.CODE_PATTERN, text)
        if m:
            return m.group(0)
        
        # Try PWD EM code pattern  
        m = re.search(BOQParser.PWD_EM_CODE, text)
        if m:
            return m.group(0).strip()
        
        # Try partial code like "02-1"
        m = re.search(r'(\d{2,3}[-]\d{1,3})', text)
        if m:
            return m.group(0)
        
        return ''

    @staticmethod
    def from_pdf(pdf_path: str, use_excel_fallback: bool = True) -> list[dict]:
        """Parse BOQ from an e-GP generated PDF file.

        Handles the multi-column HTML table layout where item codes,
        descriptions, units and quantities span multiple lines.
        
        Args:
            pdf_path: Path to PDF file
            use_excel_fallback: If True, try to find matching Excel file for complete data
        
        Returns:
            List of BOQ item dicts
        """
        from PyPDF2 import PdfReader
        
        try:
            reader = PdfReader(pdf_path)
        except Exception as e:
            logger.error(f"Cannot read PDF {pdf_path}: {e}")
            return []

        # Extract all text lines
        raw_lines = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                for line in text.split('\n'):
                    stripped = line.strip()
                    if stripped:
                        raw_lines.append(stripped)

        # ── Step 1: Identify item blocks ──────────────────────────────
        # Each item in e-GP starts with a line matching "NUM AT_START"
        # But items 22-44 have format "NUM PWD" or "NUM 02-1" etc.
        # Items 1-21 have format "NUM CODE CODE Description"
        # Items 45-47 have format "NUM CODE CODE UNIT QTY Fill By" (inline)
        
        item_blocks = []  # list of (item_no, [lines])
        current_item = None
        current_lines = []
        
        for line in raw_lines:
            # Check if line starts with a potential item number
            m = re.match(r'^(\d{1,3})\s', line)
            if not m:
                if current_item is not None:
                    current_lines.append(line)
                continue
            
            num = int(m.group(1))
            
            # Skip if it's a false positive (like "855 Kg/m3" or "10 m lead")
            # Valid item numbers are 1-47 for this tender
            if num > 50:
                if current_item is not None:
                    current_lines.append(line)
                continue
            
            # If we were tracking a previous item, save it
            if current_item is not None and current_lines:
                # Check if this is really a new item or continuation
                # Items 22+ especially have continuation lines that start with codes
                
                # For items 22-44, the pattern is "NUM PWD" followed by detailed code lines
                # Check if the new line is actually a continuation of current item
                is_new_item = True
                
                if current_item is not None:
                    # Check if the next text after the number looks like a code
                    rest = line[m.end():].strip()
                    # If the rest is just "PWD" or "EM" or a partial code, 
                    # and we haven't found "Fill By" yet, it might be continuation
                    # But actually, numbers 1-47 at start of line ARE new items
                    pass
                
                item_blocks.append((current_item, current_lines))
                current_lines = []
            
            current_item = num
            current_lines = [line]
        
        # Don't forget last item
        if current_item is not None and current_lines:
            item_blocks.append((current_item, current_lines))

        # ── Step 2: Parse each item block ────────────────────────────
        items = []
        
        for item_no, block_lines in item_blocks:
            try:
                item = BOQParser._parse_item_block(item_no, block_lines)
                if item and item.get('description', '').strip():
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse item {item_no}: {e}")
                continue

        logger.info(f"BOQ PDF: extracted {len(items)} items")
        return items

    @staticmethod
    def _parse_item_block(item_no: int, lines: list) -> dict | None:
        """Parse a single item block from the BOQ."""
        if not lines:
            return None
        
        # Join everything for easier searching
        full_text = ' '.join(lines)
        first_line = lines[0]
        
        # Determine item type from first line pattern
        # Type A: "NUM CODE CODE Description"  (items 1, 3-21, 27-34)
        # Type B: "NUM PARTIAL_CODE" then next lines have details  (items 2, 22, 44)
        # Type C: "NUM PWD" then next lines have PWD code  (items 23-26, 29-43)
        # Type D: "NUM CODE CODE UNIT QTY Fill By" (items 45-47)
        
        m_a = re.match(r'^(\d{1,3})\s+([\d]{2,3}[-][\d]{1,3}(?:\([\w]+\))?|01\.1|03\.5|02-1|04-3|06-4|06-6|16-1-1|15-1-1|03\.1\.1|1\.02|3\.12\.06)\s+', first_line)
        
        m_c = re.match(r'^(\d{1,3})\s+(PWD)', first_line)
        
        m_b = re.match(r'^(\d{1,3})\s+([\d]{2,3}[-][\d]{1,3})', first_line)
        
        # Also check for items starting with just a partial code like "01.1", "02-1", "03.5"
        m_b2 = re.match(r'^(\d{1,3})\s+((?:01\.1|02-1|03\.5|04-3|06-4|06-6|16-1-1|15-1-1|03\.1\.1|1\.02|3\.12\.06))', first_line)
        
        # Determine item structure
        code = ''
        agency = 'BWDB'
        group_code = ''
        desc_lines = []
        
        if m_a:
            # Type A: Full code on first line
            rest = first_line[m_a.end():].strip()
            
            # Check if rest starts with another code
            code_match = re.search(BOQParser.CODE_PATTERN, rest)
            if code_match:
                code = code_match.group(0)
                desc_start = rest[code_match.end():].strip()
                group_code = m_a.group(2)
            else:
                # No second code, the first might be it
                code = m_a.group(2)
                desc_start = rest
            
            # Get description from first line + subsequent lines
            desc_parts = [desc_start]
            desc_parts.extend(lines[1:])
            desc_text = ' '.join(desc_parts)
            
        elif m_c:
            # Type C: "NUM PWD" - code on subsequent lines
            group_code = 'PWD'
            agency = 'PWD'
            desc_text = ' '.join(lines[1:])
            
            # Extract code from continuation text
            # Patterns for PWD EM items:
            #   "EM-\n1.18PWD EM-\n1.18.1.1.1Providing..." -> code = "EM-1.18.1.1.1"
            #   "EM-\n6.8.3PWD EM-\n6.8.3.1.1STREET..." -> code = "EM-6.8.3.1.1"
            #   "EM 4.4PWD EM-\n4.4.1.1CIRCUIT..." -> code = "EM-4.4.1.1"
            
            # Try to find combined EM code (with dashes and dots)
            em_code_match = re.search(
                r'EM[- ]?\s*(\d+(?:\.\d+(?:\.\d+(?:\.\d+(?:\.\d+)?)?)?)?)',
                desc_text
            )
            if em_code_match:
                # Check if the code continues on next lines
                base_code = em_code_match.group(1)
                full_desc = ' '.join(lines[2:])
                # Try to find continuation of code
                cont_match = re.search(r'^' + re.escape(base_code) + r'(\d+(?:\.\d+)*)', full_desc)
                if cont_match:
                    code = 'EM-' + base_code + cont_match.group(1)
                else:
                    code = 'EM-' + base_code
            else:
                code = BOQParser._extract_code_from_text(desc_text)
            
        elif m_b or m_b2:
            # Type B: Partial code, continue to next lines
            partial = m_b.group(2) if m_b else m_b2.group(2)
            group_code = partial
            desc_text = ' '.join(lines)
            
            # Full code should be extractable from full text
            code = BOQParser._extract_code_from_text(desc_text)
            if not code:
                code = partial
        else:
            # Fallback: take entire text
            desc_text = ' '.join(lines)
            code = BOQParser._extract_code_from_text(desc_text)
        
        # Clean description
        # Remove "Fill By Tenderer/Consultant - Money Positive..." parts
        desc_text = re.sub(
            r'Fill\s+By\s+Tenderer/Consultant\s*-?\s*Money\s+Positive\([^)]+\)',
            ' ', desc_text
        )
        desc_text = re.sub(r'Auto\s+Auto\s+Auto', ' ', desc_text)
        desc_text = re.sub(r'https?://\S+', '', desc_text)
        desc_text = re.sub(r'\d+/\d+', '', desc_text)
        
        # Remove item number and codes from description
        desc_clean = re.sub(r'^\d{1,3}\s+', '', desc_text)
        if code:
            desc_clean = re.sub(r'^' + re.escape(code), '', desc_clean)
        if group_code and group_code != code:
            desc_clean = re.sub(r'^' + re.escape(group_code), '', desc_clean)
        desc_clean = re.sub(r'\(PWD\)', '', desc_clean)
        desc_clean = re.sub(r'PWD\s*EM', '', desc_clean)
        
        # Clean extra whitespace
        desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
        
        # Detect agency
        if '(PWD)' in full_text or 'PWD' in first_line or 'PWD' in str(lines[1:3] if len(lines) > 2 else ''):
            agency = 'PWD'
        elif '(LGED)' in full_text:
            agency = 'LGED'
        
        # Extract unit and quantity
        unit, quantity = BOQParser._find_unit_qty(full_text)
        
        # If no unit found, try the description before "Fill By"
        fill_by_pos = full_text.find('Fill By')
        if not unit and fill_by_pos > 0:
            pre_fill = full_text[:fill_by_pos]
            unit, quantity = BOQParser._find_unit_qty(pre_fill)
        
        # Clean up PWD EM code format
        if agency == 'PWD' and code:
            # Normalize PWD EM codes like "PWD EM3.2.4" -> "PWD EM 3.2.4"
            code = re.sub(r'PWD\s*EM\s*', 'PWD EM', code)
            # Extract just the number part after PWD
            if not code.startswith('PWD') and 'PWD' in full_text:
                em_match = re.search(r'PWD\s*(?:EM\s*)?(\d+(?:\.\d+)*)', full_text)
                if em_match:
                    code = f'PWD EM{em_match.group(1)}'
        
        if not code:
            code = group_code or ''
        
        return {
            'item_no': item_no,
            'code': code,
            'group_code': group_code,
            'description': desc_clean[:300],
            'unit': unit,
            'quantity': quantity,
            'agency': agency,
        }
