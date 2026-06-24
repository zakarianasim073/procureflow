"""SOR Service - Rate lookup from PostgreSQL or CSV files"""

import csv
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import pdfplumber
from PyPDF2 import PdfReader

BASE_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


@dataclass
class SorRate:
    agency: str
    code: str
    description: str
    unit: str
    zone_a: float
    zone_b: float
    zone_c: float
    zone_d: float

    def get_rate(self, zone: Optional[str] = None) -> float:
        z = (zone or 'A').upper()
        return {
            'A': self.zone_a, 'B': self.zone_b,
            'C': self.zone_c, 'D': self.zone_d,
        }.get(z, self.zone_a)


def _norm(code: str) -> str:
    """Normalize: remove spaces, hyphens, dots, &, lowercase"""
    return code.replace(' ', '').replace('-', '').replace('.', '').replace('&', '').lower()


class SORService:
    def __init__(self):
        self._rates: Dict[str, List[SorRate]] = {'BWDB': [], 'PWD': [], 'LGED': []}
        self._idx: Dict[str, Dict[str, SorRate]] = {'BWDB': {}, 'PWD': {}, 'LGED': {}}
        self._loaded = False

    def load_all(self, prefer_db: bool = True):
        if prefer_db and self._load_from_db():
            self._loaded = True
            total = sum(len(v) for v in self._rates.values())
            logger.info("SOR: %d rates loaded from PostgreSQL (BWDB: %d, PWD: %d, LGED: %d)",
                        total, len(self._rates['BWDB']), len(self._rates['PWD']), len(self._rates['LGED']))
            return
        for agency in ['BWDB', 'PWD', 'LGED']:
            csv_path = BASE_DIR / agency.lower() / "rates.csv"
            if csv_path.exists():
                self._load_csv(agency, csv_path)
        self._loaded = True
        total = sum(len(v) for v in self._rates.values())
        logger.info("SOR: %d rates loaded from CSV (BWDB: %d, PWD: %d, LGED: %d)",
                    total, len(self._rates['BWDB']), len(self._rates['PWD']), len(self._rates['LGED']))

    def _load_csv(self, agency: str, csv_path: Path):
        with open(csv_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            for row in csv.DictReader(f):
                try:
                    code = row.get('code', '').strip()
                    rate = SorRate(
                        agency=agency, code=code,
                        description=row.get('description', '').strip(),
                        unit=row.get('unit', '').strip().lower(),
                        zone_a=float(row.get('zone_a', 0) or 0),
                        zone_b=float(row.get('zone_b', 0) or 0),
                        zone_c=float(row.get('zone_c', 0) or 0),
                        zone_d=float(row.get('zone_d', 0) or 0),
                    )
                    self._rates[agency].append(rate)
                    if code:
                        self._idx[agency][_norm(code)] = rate
                except (ValueError, KeyError):
                    continue

    def _load_from_db(self) -> bool:
        try:
            from app.db.database import get_sync_engine
            from sqlalchemy import inspect, select
            from sqlalchemy.orm import Session
            from app.models.sor_rate import SorRate as DBSorRate

            engine = get_sync_engine()
            inspector = inspect(engine)
            if "sor_rates" not in inspector.get_table_names():
                return False

            with Session(engine) as session:
                rates = session.execute(
                    select(DBSorRate).where(DBSorRate.is_active == True)
                ).scalars().all()

            if not rates:
                return False

            for db_rate in rates:
                agency = db_rate.agency.value
                sr = SorRate(
                    agency=agency, code=db_rate.code,
                    description=db_rate.description, unit=db_rate.unit,
                    zone_a=db_rate.zone_a, zone_b=db_rate.zone_b,
                    zone_c=db_rate.zone_c, zone_d=db_rate.zone_d,
                )
                self._rates[agency].append(sr)
                if db_rate.code:
                    self._idx[agency][_norm(db_rate.code)] = sr
                    if db_rate.normalized_code and db_rate.normalized_code != _norm(db_rate.code):
                        self._idx[agency][db_rate.normalized_code] = sr
            return True
        except Exception as e:
            logger.warning("SOR DB load failed, falling back to CSV: %s", e)
            return False

    def load_from_pdf(self, agency: str, pdf_path: str, zone: Optional[str] = None) -> int:
        """
        Best-effort PDF loader for SOR documents.
        Returns number of rate rows parsed. Existing CSV-backed rates remain available.
        """
        agency = agency.upper()
        if agency not in self._rates:
            self._rates[agency] = []
            self._idx[agency] = {}

        pdf = Path(pdf_path)
        if not pdf.exists():
            return 0

        rows = self._parse_pdf_rows(pdf, agency)
        loaded = 0
        for row in rows:
            code = row.get("code", "").strip()
            desc = row.get("description", "").strip()
            unit = row.get("unit", "").strip().lower()
            zone_a = float(row.get("zone_a", 0) or 0)
            zone_b = float(row.get("zone_b", 0) or 0)
            zone_c = float(row.get("zone_c", 0) or 0)
            zone_d = float(row.get("zone_d", 0) or 0)
            if not code:
                continue
            rate = SorRate(
                agency=agency,
                code=code,
                description=desc,
                unit=unit,
                zone_a=zone_a,
                zone_b=zone_b,
                zone_c=zone_c,
                zone_d=zone_d,
            )
            self._rates[agency].append(rate)
            self._idx[agency][_norm(code)] = rate
            loaded += 1

        return loaded

    def _parse_pdf_rows(self, pdf_path: Path, agency: str) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        seen = set()

        def add(row: Optional[Dict[str, str]]):
            if not row:
                return
            code = row.get("code", "").strip()
            if not code:
                return
            key = _norm(code)
            if key in seen:
                return
            seen.add(key)
            rows.append(row)

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables() or []:
                        for cells in table:
                            add(self._parse_sor_cells(cells, agency))

                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    lines = text.splitlines()
                    for idx, line in enumerate(lines):
                        row = self._parse_sor_line(line, agency)
                        if not row and self._find_sor_code(line, agency):
                            row = self._parse_sor_line(" ".join(lines[idx:idx + 4]), agency)
                        add(row)
        except Exception:
            reader = PdfReader(str(pdf_path))
            for page in reader.pages:
                text = page.extract_text() or ""
                lines = text.splitlines()
                for idx, line in enumerate(lines):
                    row = self._parse_sor_line(line, agency)
                    if not row and self._find_sor_code(line, agency):
                        row = self._parse_sor_line(" ".join(lines[idx:idx + 4]), agency)
                    add(row)

        return rows

    def _parse_sor_cells(self, cells: List[object], agency: str) -> Optional[Dict[str, str]]:
        cleaned = [self._clean_cell(cell) for cell in cells if self._clean_cell(cell)]
        if len(cleaned) < 4:
            return None

        joined = " ".join(cleaned)
        if self._is_sor_header(joined):
            return None

        code = self._find_sor_code(joined, agency)
        if not code:
            return None

        rate_positions = [
            idx for idx, cell in enumerate(cleaned)
            if re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?", cell)
        ]
        if len(rate_positions) < 4:
            return self._parse_sor_line(joined, agency)

        rate_positions = rate_positions[-4:]
        rates = [self._money_to_float(cleaned[idx]) for idx in rate_positions]
        first_rate_idx = rate_positions[0]
        unit = self._extract_unit(" ".join(cleaned[:first_rate_idx]))
        description_cells = []
        for idx, cell in enumerate(cleaned[:first_rate_idx]):
            if self._find_sor_code(cell, agency) == code:
                continue
            if unit and cell.lower() == unit:
                continue
            description_cells.append(cell)

        description = " ".join(description_cells)
        description = self._remove_code(description, code).strip(" -:;,")
        return self._sor_row(code, description, unit, rates)

    def _parse_sor_line(self, line: str, agency: str) -> Optional[Dict[str, str]]:
        line = self._clean_cell(line)
        if len(line) < 12 or self._is_sor_header(line):
            return None

        code = self._find_sor_code(line, agency)
        if not code:
            return None

        rates = [self._money_to_float(value) for value in re.findall(
            r"(?<![-.\w])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![-.\w])\d{1,6}\.\d{2}(?![-.\w])",
            line,
        )]
        if len(rates) < 4:
            return None
        rates = rates[-4:]

        rate_match = list(re.finditer(
            r"(?<![-.\w])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![-.\w])\d{1,6}\.\d{2}(?![-.\w])",
            line,
        ))[-4]
        before_rates = line[:rate_match.start()].strip()
        unit = self._extract_unit(before_rates)
        description = self._remove_code(before_rates, code)
        if unit:
            description = re.sub(rf"\b{re.escape(unit)}\b\s*$", "", description, flags=re.I)
        description = re.sub(r"^\d+\(?\d*\)?\s*", "", description).strip(" -:;,")
        return self._sor_row(code, description, unit, rates)

    def _sor_row(self, code: str, description: str, unit: str, rates: List[float]) -> Dict[str, str]:
        while len(rates) < 4:
            rates.insert(0, rates[0] if rates else 0.0)
        return {
            "code": code,
            "description": re.sub(r"\s+", " ", description).strip()[:500],
            "unit": unit.strip().lower(),
            "zone_a": str(rates[-4]),
            "zone_b": str(rates[-3]),
            "zone_c": str(rates[-2]),
            "zone_d": str(rates[-1]),
        }

    def _find_sor_code(self, text: str, agency: str) -> str:
        text = self._clean_cell(text)
        agency = agency.upper()

        if agency == "BWDB":
            patterns = [
                r"\b\d{2}\s*-\s*\d{3}\s*-\s*\d{2}\b",
                r"\b\d{2}\s*-\s*\d{3}\s+\d{2}\b",
                r"\b\d{2}\s*-\s*\d{3}\b",
            ]
        elif agency == "PWD":
            patterns = [
                r"\bPWD\s+EM\s+\d+(?:\.\d+){1,6}\b",
                r"\b\d{2}\.\d+(?:\.\d+){0,6}\b",
                r"\b\d{2}\s*-\s*\d{3}\s*-\s*\d{2}\b",
            ]
        else:
            patterns = [
                r"\b\d{1,2}\.\d+(?:\.\d+){0,6}\b",
                r"\b\d{2}\s*-\s*\d{3}\s*-\s*\d{2}\b",
            ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return self._normalize_sor_code(match.group(0), agency)
        return ""

    def _normalize_sor_code(self, code: str, agency: str) -> str:
        code = self._clean_cell(code).upper()
        if code.startswith("PWD EM"):
            return re.sub(r"\s+", " ", code)
        if "-" in code:
            parts = re.findall(r"\d+", code)
            if len(parts) >= 3:
                return f"{int(parts[0]):02d}-{int(parts[1]):03d}-{int(parts[2]):02d}"
            if len(parts) == 2:
                return f"{int(parts[0]):02d}-{int(parts[1]):03d}"
        return code

    def _extract_unit(self, text: str) -> str:
        known_units = [
            "cum/km", "cum/ km", "sqm", "sq.m", "sqft", "cft", "cum", "each",
            "nos", "no", "set", "job", "day", "month", "kg", "mt", "ton",
            "mtr", "meter", "m", "rft", "hr", "hour", "kwp", "lump sum",
        ]
        tail = self._clean_cell(text).lower()
        for unit in known_units:
            if re.search(rf"(?:^|\s){re.escape(unit)}\s*$", tail, flags=re.I):
                return unit.replace("sq.m", "sqm").replace("cum/ km", "cum/km")
        words = tail.split()
        return words[-1] if words and len(words[-1]) <= 12 and not re.search(r"\d", words[-1]) else ""

    def _remove_code(self, text: str, code: str) -> str:
        escaped = re.escape(code)
        relaxed = escaped.replace(r"\-", r"\s*-\s*").replace(r"\ ", r"\s+")
        text = re.sub(relaxed, " ", text, flags=re.I)
        if "-" in code:
            parts = re.findall(r"\d+", code)
            if len(parts) >= 3:
                text = re.sub(rf"\b{parts[0]}\s*-\s*{parts[1]}\s+{parts[2]}\b", " ", text)
        return re.sub(r"\s+", " ", text)

    def _money_to_float(self, value: str) -> float:
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return 0.0

    def _clean_cell(self, value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()

    def _is_sor_header(self, text: str) -> bool:
        lower = text.lower()
        return any(token in lower for token in [
            "item code", "item no", "description", "zone-a", "zone a",
            "schedule of rates", "government of", "page no",
        ])

    def find_rate(
        self, code: str, description: str = '',
        agency: str = 'BWDB', zone: Optional[str] = None,
    ) -> Tuple[Optional[float], Optional[SorRate]]:
        if not self._loaded:
            self.load_all()

        # Parse compound code "A&B" → use B as actual item code
        actual = code.split('&', 1)[1] if '&' in code else code

        # Detect agency from suffix
        detected = agency
        cu = actual.upper()
        if '(PWD)' in cu:
            detected = 'PWD'
        elif '(LGED)' in cu:
            detected = 'LGED'
        elif '(BWDB)' in cu:
            detected = 'BWDB'

        # Clean parenthesized suffix for matching
        match_code = re.sub(r'\([\w]+\)', '', actual).strip()
        ncode = _norm(match_code)
        idx = self._idx.get(detected, {})

        # 1. Exact match
        if ncode in idx:
            r = idx[ncode]
            return r.get_rate(zone), r

        # 2. Prefix match: requested code might be a group (e.g. "40-300")
        # while SOR has sub-items ("40-300-10", "40-300-20")
        # Only match if the shorter code has meaningful length (>=3 chars
        # after normalization) to avoid single-digit garbage matches.
        matches = []
        for c, r in idx.items():
            nc = _norm(c)
            if nc.startswith(ncode):
                matches.append((len(c), r))
            elif ncode.startswith(nc) and len(nc) >= 3:
                matches.append((len(c), r))
        if matches:
            # Prefer shortest match (the closest group-level code)
            matches.sort(key=lambda x: x[0])
            best = matches[0][1]
            return best.get_rate(zone), best

        # 3. Suffix match: with (PWD) removed, try the original code
        if match_code != actual:
            ncode_orig = _norm(actual)
            if ncode_orig in idx:
                r = idx[ncode_orig]
                return r.get_rate(zone), r

        # 4. Try matching without parenthesized suffix at all
        # Handle "03.5.1" from "03.5.1(PWD)"
        base = re.sub(r'\(.*?\)', '', actual).strip()
        nbase = _norm(base)
        if nbase and nbase in idx:
            return idx[nbase].get_rate(zone), idx[nbase]

        # 5. Try the full compound code "A&B" as-is
        if '&' in code:
            nfull = _norm(code)
            if nfull in idx:
                return idx[nfull].get_rate(zone), idx[nfull]

        # 6. Fuzzy by description (last resort)
        if description:
            from difflib import SequenceMatcher
            ndesc = description.lower()
            best = None
            best_score = 0.0
            for r in self._rates[detected]:
                score = SequenceMatcher(None, ndesc[:60], r.description.lower()[:60]).ratio()
                if score > best_score and score > 0.55:
                    best_score = score
                    best = r
            if best:
                return best.get_rate(zone), best

        return None, None

    def list_agencies(self) -> List[str]:
        return [a for a in ['BWDB', 'PWD', 'LGED'] if self._rates[a]]

    def get_stats(self, agency: str) -> Dict:
        return {
            'agency': agency,
            'total_rates': len(self._rates.get(agency, [])),
            'has_csv': (BASE_DIR / agency.lower() / "rates.csv").exists(),
        }


sor_service = SORService()
