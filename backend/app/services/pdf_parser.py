"""PDF Parser - Extracts BOQ items from Bangladesh e-GP system PDFs (all formats)"""

import re
from typing import List, Dict, Optional
import PyPDF2
import pdfplumber

UNITS = ['cum', 'sqm', 'each', 'no', 'nos', 'kg', 'm', 'day', 'lump', '%', 'rmt', 'mt', 'ton',
         'meter', 'points', 'point', 'sq', 'cft', 'rft', 'lump sum', 'ls', 'job', 'set']


def _item_no_value(item_no: object) -> Optional[int]:
    text = str(item_no or "").strip()
    if not text:
        return None
    match = re.match(r"^(\d{1,3})$", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None

class PDFParser:
    """Parse BOQ data from e-GP tender PDFs - handles both new and old formats"""

    async def extract_boq_items(self, pdf_path: str) -> List[Dict]:
        # Try pdfplumber table extraction first (works for most formats)
        table_items = self._parse_bwdb_boq_tables(pdf_path)
        if table_items:
            # Post-process: extract sub-item codes from raw PDF text for dotted codes
            try:
                raw_text = ""
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        raw_text += page.extract_text() + "\n"
                for item in table_items:
                    code = item.get("code", "")
                    if re.fullmatch(r'\d+(?:\.\d+)+', code):
                        m = re.search(re.escape(code) + r'\.(\d+)', raw_text)
                        if m:
                            item["code"] = f"{code}.{m.group(1)}"
            except Exception:
                pass
            return table_items
        
        raw_lines = self._read_lines(pdf_path)
        
        # Detect format
        fmt = self._detect_format(raw_lines)
        print(f"  Detected format: {fmt}")
        
        if fmt == 'new_egp':
            return self._parse_new_egp(raw_lines)
        elif fmt == 'egp_tabular':
            return self._parse_egp_tabular(raw_lines)
        elif fmt == 'old_egp':
            return self._parse_old_egp(raw_lines)
        elif fmt == 'generic_numbers':
            return self._parse_generic(raw_lines)
        else:
            return self._parse_generic(raw_lines)

    def _read_lines(self, pdf_path: str) -> List[str]:
        lines = []
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                for line in page.extract_text().split('\n'):
                    l = line.strip()
                    if l:
                        lines.append(l)
        return lines

    def _parse_bwdb_boq_tables(self, pdf_path: str) -> List[Dict]:
        """Parse BOQ items directly from pdfplumber tables (handles BWDB/long format).
        
        Detects column layout automatically:
        - 10-col format: item_no|group|code|desc|unit|qty|rate|rate_words|total|total_words
        - 14-col format: empty|empty|item_no|group|code|desc|unit|qty|rate|rate_words|total|total_words|...
        """
        items = []
        seen_item_nos = set()

        def _clean(txt):
            t = str(txt or "").strip()
            t = t.replace("\n", " ")
            return re.sub(r'\s+', ' ', t).strip()

        def _is_code(val):
            return bool(re.search(r'\d{1,4}[-.]\d{1,4}', val))

        def _is_unit(val):
            return val.lower() in ('sqm', 'sqft', 'sft', 'no', 'nos', 'ls', 'job',
                                    'kg', 'ton', 'm3', 'cum', 'rm', 'm', 'km', 'lump sum',
                                    'each', 'set', 'pkt', 'bag', 'day', 'month', 'week')

        def _read_cells(row, col_offset):
            """Read code, desc, unit, qty from cells with given offset."""
            ci = col_offset
            # code from Item Code column
            code = ""
            code_col = cells[ci] if len(cells) > ci else ""
            parent_prefix = ""
            if code_col:
                cleaned = re.sub(r'\(.*?\)', '', code_col).strip()
                cleaned = cleaned.replace("|", "").strip()
                cleaned = re.sub(r'\s+', '', cleaned)
                for pat in [r'(\d{1,4}-\d{1,4}-\d{1,4})', r'(\d+(?:\.\d+){1,4})', r'(\d{1,4}-\d{1,4})']:
                    m = re.search(pat, cleaned)
                    if m:
                        code = m.group(1)
                        break
                # Get parent prefix for sub-item search (e.g., "40-620" from "40-620-00")
                pm = re.match(r'(\d{1,4}-\d{1,4})', code)
                if pm:
                    parent_prefix = pm.group(1)
                else:
                    pm = re.match(r'(\d+(?:\.\d+)+)', code)
                    if pm:
                        parent_prefix = pm.group(1)

                # Preserve agency suffix (PWD)/(LGED)/(BWDB) from raw code column
                ag_m = re.search(r'\((PWD|LGED|BWDB)\)', code_col, re.I)
                if ag_m:
                    code = f"{code} ({ag_m.group(1).upper()})"

            # description (may contain sub-item code like "40-620-20")
            desc = _clean(cells[ci + 1]) if len(cells) > ci + 1 else ""
            # skip header/boilerplate
            if not desc or any(kw in desc for kw in
                ['Item no', 'Group', 'Item Code', 'Description',
                 'Measurement', 'Unit Price', 'Total Price',
                 'Grand Total', 'Table', 'Name :', 'Discount',
                 'Provisional', 'Unconditional', 'Bill of Quantities',
                 'for approval', 'Lot Detail', 'Lot No']):
                return None

            # Check description for sub-item code
            if parent_prefix:
                if code.endswith("-00") or re.fullmatch(r'\d{1,4}-\d{1,4}', code):
                    # Dash format: 04-180-00 → search for 04-180-20 in desc
                    sub_rx = re.compile(re.escape(parent_prefix) + r'\s*-\s*(\d{2,4})\b')
                    sm = sub_rx.search(desc)
                    if sm:
                        sub_suffix = sm.group(1)
                        if code.endswith("-00") or not code.endswith(f"-{sub_suffix}"):
                            code = f"{parent_prefix}-{sub_suffix}"
                elif re.fullmatch(r'\d+(?:\.\d+)+', code):
                    # Dotted format: 01.1 → search for 01.1.3 in desc
                    sub_rx = re.compile(re.escape(parent_prefix) + r'\.(\d+)')
                    sm = sub_rx.search(desc)
                    if sm:
                        code = f"{parent_prefix}.{sm.group(1)}"

            # unit
            unit = cells[ci + 2].lower().strip() if len(cells) > ci + 2 else ""
            # quantity
            qty_str = cells[ci + 3].replace(",", "").strip() if len(cells) > ci + 3 else ""
            qty = 0.0
            try:
                qty = float(qty_str) if qty_str else 0.0
            except ValueError:
                qty = 0.0
            return {'code': code, 'desc': desc[:500], 'unit': unit, 'qty': qty}

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if not row or not any(row):
                            continue
                        cells = [_clean(c) for c in row]
                        ncols = len(cells)

                        # Find item number in col 0 or col 2
                        item_no = ""
                        if ncols > 0 and cells[0].isdigit():
                            item_no = cells[0]
                            # Detect format: if col 4 looks like a code, use offset 4; else use offset 2
                            col_offset = 2  # default: 10-col format (code in col 2)
                            if ncols > 4 and _is_code(cells[4]):
                                col_offset = 4  # 14-col format (code in col 4)
                            elif ncols > 2 and _is_code(cells[2]):
                                col_offset = 2
                        elif ncols > 2 and cells[2].isdigit():
                            item_no = cells[2]
                            col_offset = 4  # 14-col format
                        else:
                            continue

                        item_no_num = _item_no_value(item_no)
                        if item_no_num is None or item_no_num > 200:
                            continue
                        if item_no in seen_item_nos:
                            continue

                        parsed = _read_cells(cells, col_offset)
                        if parsed is None:
                            continue

                        seen_item_nos.add(item_no)
                        items.append({
                            'item_no': item_no,
                            'code': parsed['code'],
                            'description': parsed['desc'],
                            'unit': parsed['unit'],
                            'quantity': parsed['qty'],
                            'rate': None,
                        })

        if items:
            items.sort(key=lambda x: _item_no_value(x.get('item_no')) or 999999)
            print(f"  pdfplumber table extraction: {len(items)} items")
        return items

    def _detect_format(self, lines: List[str]) -> str:
        """Detect which BOQ format the PDF uses."""
        egp_old_count = 0
        egp_new_count = 0
        generic_count = 0
        tabular_count = 0
        fill_by_count = 0
        work_code_pattern = re.compile(r'Work\d+[\.\-]\d+')

        for line in lines[:200]:  # Check first 200 lines
            if re.match(r'^\d+\s+(Part-[A-D])\s+(N\.A|N\./A|[A-Z]?)\s+', line):
                egp_old_count += 1
                continue
            # Tabular e-GP: "1 04-180 04-180 Description..." or split code lines
            if re.match(r'^\d+\s+[A-Za-z0-9./()\-]+(?:\s+[A-Za-z0-9./()\-]+)?\s*', line):
                tabular_count += 1
                continue
            if 'Fill By' in line:
                fill_by_count += 1
            # Check for "Work" followed by code pattern (e.g., "Work04-180-00")
            if re.search(r'Work\d+[\.\-]\d+', line):
                egp_new_count += 1
                continue
            if re.match(r'^\d+\.\s+\w+', line):
                generic_count += 1

        if egp_old_count > 5:
            return 'old_egp'
        if tabular_count > 5 or (tabular_count > 2 and fill_by_count > 5):
            return 'egp_tabular'
        if egp_new_count > 3:
            return 'new_egp'
        if generic_count > 5:
            return 'generic_numbers'
        return 'old_egp'

    def _parse_egp_tabular_table(self, pdf_path: str) -> List[Dict]:
        items: List[Dict] = []
        seen_item_no = set()

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        cells = [re.sub(r'\s+', ' ', str(c or '')).strip() for c in row]
                        if not any(cells):
                            continue

                        item_no = self._extract_item_no(cells)
                        if not item_no:
                            continue
                        if item_no in seen_item_no:
                            continue

                        code = self._extract_code_from_row(cells)
                        desc = self._extract_description_from_cells(cells)
                        code = self._normalize_subitem_code(code, desc)
                        unit, qty = self._extract_unit_qty_from_row(cells)

                        if not code and not desc:
                            continue

                        items.append({
                            'item_no': item_no,
                            'code': code,
                            'description': desc[:500],
                            'unit': unit,
                            'quantity': qty,
                            'rate': None,
                        })
                        seen_item_no.add(item_no)

        text_items = self._parse_egp_tabular_text(pdf_path)
        for item in text_items:
            if item["item_no"] not in seen_item_no:
                items.append(item)
                seen_item_no.add(item["item_no"])

        # Keep stable ordering and only likely BOQ items.
        items = [x for x in items if _item_no_value(x.get('item_no')) is not None]
        items.sort(key=lambda x: _item_no_value(x.get('item_no')) or 999999)
        return items

    def _parse_egp_tabular_text(self, pdf_path: str) -> List[Dict]:
        text_lines: List[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text_lines.extend((page.extract_text() or "").splitlines())
        lines = [re.sub(r'\s+', ' ', ln).strip() for ln in text_lines if ln.strip()]
        items: List[Dict] = []
        for idx, line in enumerate(lines):
            m = re.match(
                r'^(\d{1,3})\s+(?:(PWD|LGED)\s+)?([A-Za-z0-9 .-]+?)\s+(.+?)\s+('
                + '|'.join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
                + r')\s+([\d,]+(?:\.\d+)?)\s+Fill By',
                line,
                flags=re.IGNORECASE,
            )
            if not m:
                continue
            item_no = m.group(1)
            code_part = m.group(3).strip()
            desc_part = m.group(4).strip()
            unit = m.group(5).lower()
            qty = float(m.group(6).replace(',', ''))
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ''
            follow = ' '.join(lines[idx + offset] for offset in range(1, min(4, len(lines) - idx)))
            code = self._extract_code_from_text(code_part + ' ' + follow)
            if not code:
                code = self._extract_code_from_text(code_part)
            if re.fullmatch(r'\d{1,4}-\d{1,4}', code or ''):
                suffix = self._suffix_from_following_lines(follow)
                if suffix:
                    code = f"{code}-{suffix}"
            code = self._normalize_subitem_code(code, code_part + ' ' + follow + ' ' + desc_part)
            items.append({
                'item_no': item_no,
                'code': code,
                'description': desc_part[:500],
                'unit': unit,
                'quantity': qty,
                'rate': None,
            })
        return items

    def _extract_item_no(self, cells: List[str]) -> str:
        for cell in cells[:3]:
            m = re.match(r'^(\d{1,3})$', cell)
            if m:
                return m.group(1)
            m2 = re.match(r'^(\d{1,3})\s+', cell)
            if m2:
                return m2.group(1)
        return ''

    def _extract_code(self, cells: List[str]) -> str:
        code_candidates = []
        for cell in cells:
            if not cell:
                continue
            # Prefer full BOQ item code patterns first (e.g., 40-360-10, 16-720-10/20).
            for m in re.finditer(r'(\d{1,4}-\d{1,4}-\d{1,4}(?:/\d{1,4})?)', cell):
                cand = m.group(1).strip()
                code_candidates.append(cand)

            # Typical item codes, including dotted and dashed forms.
            for m in re.finditer(r'([A-Za-z]?\d{1,4}(?:[.\-]\d{1,4}){1,5}(?:\([A-Z]+\))?)', cell):
                cand = m.group(1).strip()
                if re.match(r'^\d+\.\d{2}$', cand):
                    continue
                if '-' in cand or cand.count('.') >= 2 or '(PWD)' in cand or '(LGED)' in cand:
                    code_candidates.append(cand)
        if not code_candidates:
            return ''
        code_candidates = list(dict.fromkeys(code_candidates))
        # Rank: full dashed sub-item > slash sub-item > dotted sub-item > group/base.
        def score(code: str) -> tuple:
            dash_count = code.count('-')
            dot_count = code.count('.')
            has_slash = 1 if '/' in code else 0
            # Penalize short group-only dashed codes like 16-720.
            group_penalty = 1 if re.fullmatch(r'\d{1,4}-\d{1,4}', code) else 0
            return (dash_count, has_slash, dot_count, -group_penalty, len(code))

        code_candidates.sort(key=score, reverse=True)
        return code_candidates[0]

    def _extract_code_from_row(self, cells: List[str]) -> str:
        if len(cells) >= 3 and cells[2]:
            code = self._extract_code_from_text(cells[2])
            if code:
                return code
        if len(cells) >= 2 and cells[1]:
            code = self._extract_code_from_text(cells[1])
            if code:
                return code
        return self._extract_code(cells)

    def _extract_code_from_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text or '').strip()
        text = re.sub(r'\b(PWD\s+)?EM-\s+', r'\1EM- ', text, flags=re.IGNORECASE)
        em_matches = re.findall(r'\b((?:PWD\s+)?EM-?\s*\d+(?:\.\d+){1,4})\b', text, flags=re.IGNORECASE)
        if em_matches:
            em_matches.sort(key=len, reverse=True)
            best = re.sub(r'\s+', ' ', em_matches[0].replace('EM-', 'EM ')).strip()
            base_num = re.search(r'(\d+(?:\.\d+)*)$', best)
            if base_num:
                m_full = re.search(rf'\b({re.escape(base_num.group(1))}\.\d+(?:\.\d+)*)\b', text)
                if m_full:
                    prefix = re.sub(r'\d+(?:\.\d+)*$', '', best).strip()
                    return f"{prefix} {m_full.group(1)}".strip()
            return best
        m = re.search(r'\b(\d{1,4}-\d{1,4}-\s*\d{1,4}(?:\s*/\s*\d{1,4})?)\b', text)
        if m:
            return re.sub(r'\s+', '', m.group(1))
        m = re.search(r'\b(\d{1,4}(?:\.\d{1,4}){1,5})\b', text)
        if m:
            return m.group(1)
        m = re.search(r'\b(\d{1,4}-\d{1,4})\b', text)
        if m:
            return m.group(1)
        return ''

    def _suffix_from_following_lines(self, text: str) -> str:
        m = re.search(r'(?:^|\s)(\d{1,3})(?=\s+[A-Za-z(])', text)
        return m.group(1) if m else ''

    def _extract_description_from_cells(self, cells: List[str]) -> str:
        txt = ' '.join(cells)
        txt = re.sub(r'\s+', ' ', txt).strip()
        txt = re.sub(r'^(\d{1,3})\s+', '', txt)
        txt = re.sub(r'Fill By\s*Tenderer/Consultant.*$', '', txt, flags=re.IGNORECASE)
        txt = re.sub(r'- Money Positive.*$', '', txt, flags=re.IGNORECASE)
        return txt.strip()

    def _extract_unit_qty_from_cells(self, cells: List[str]) -> tuple:
        joined = ' '.join(cells)
        for u in sorted(UNITS, key=len, reverse=True):
            m = re.search(rf'\b{re.escape(u)}\b\s*([\d,]+(?:\.\d+)?)', joined, flags=re.IGNORECASE)
            if m:
                try:
                    return u.lower(), float(m.group(1).replace(',', ''))
                except Exception:
                    return u.lower(), 0.0
        # fallback: last decimal in row as qty if no explicit unit pattern found
        nums = re.findall(r'[\d,]+(?:\.\d+)?', joined)
        if nums:
            try:
                return '', float(nums[-1].replace(',', ''))
            except Exception:
                return '', 0.0
        return '', 0.0

    def _extract_unit_qty_from_row(self, cells: List[str]) -> tuple:
        if len(cells) >= 6:
            unit = (cells[4] or '').strip().lower()
            qty = (cells[5] or '').strip()
            if unit or qty:
                try:
                    return unit, float(qty.replace(',', ''))
                except Exception:
                    return unit, 0.0
        return self._extract_unit_qty_from_cells(cells)

    def _normalize_subitem_code(self, code: str, description: str) -> str:
        if not code:
            return code
        # Dash format: 40-620 → 40-620-20
        if re.fullmatch(r'\d{1,4}-\d{1,4}', code):
            m = re.search(rf'{re.escape(code)}-\s*(\d{{1,4}}(?:\s*/\s*\d{{1,4}})?)', description)
            if m:
                suffix = re.sub(r'\s+', '', m.group(1))
                return f"{code}-{suffix}"
        # Dotted format: 01.1 → 01.1.3, 02.1 → 02.1.1
        if re.fullmatch(r'\d+(?:\.\d+)+', code):
            m = re.search(rf'{re.escape(code)}\.(\d+)', description)
            if m:
                return f"{code}.{m.group(1)}"
        return code

    # ── Format 4: e-GP tabular export ───────────────────────────────────────
    # Lines: "1 04-180 04-180 Description..."
    def _parse_egp_tabular(self, lines: List[str]) -> List[Dict]:
        items = []
        cleaned = [ln for ln in lines if not self._is_noise_line(ln)]
        i = 0
        while i < len(cleaned):
            line = cleaned[i]
            m = re.match(r'^(\d{1,3})\s+([A-Za-z0-9./()\-]+)(?:\s+([A-Za-z0-9./()\-]+))?\s*(.*)$', line)
            if not m:
                i += 1
                continue
            token_a = (m.group(2) or '').strip()
            token_b = (m.group(3) or '').strip()
            if not (re.search(r'[.\-/()]', token_a) or re.search(r'[.\-/()]', token_b)):
                i += 1
                continue

            item_no = m.group(1)
            code = token_b or token_a
            tail = (m.group(4) or '').strip()
            block = [line]
            j = i + 1
            while j < len(cleaned):
                nxt = cleaned[j]
                if re.match(r'^\d{1,3}\s+[A-Za-z0-9./()\-]+(?:\s+[A-Za-z0-9./()\-]+)?\s*', nxt):
                    # New item start: stop current block unless the row is still clearly wrapped.
                    if any('Fill By' in b for b in block) or len(block) > 3:
                        break
                block.append(nxt)
                if 'Fill By' in nxt:
                    # Capture trailing lines after Fill By boilerplate and stop this item.
                    extra = 0
                    while j + 1 < len(cleaned) and extra < 3:
                        if re.match(r'^\d{1,3}\s+[A-Za-z0-9./()\-]+', cleaned[j + 1]):
                            break
                        block.append(cleaned[j + 1])
                        j += 1
                        extra += 1
                    break
                j += 1

            if code.endswith('-'):
                code = self._complete_dashed_code(code, block)
            code = self._improve_code_from_desc(code, tail)

            desc_lines = [tail] if tail else []
            skip_patterns = ['Tenderer/Consultant', 'Money Positive', 'digits after decimal', 'Auto Auto Auto', 'View Form', 'https://']
            for row in block[1:]:
                if any(kw in row for kw in skip_patterns):
                    continue
                desc_lines.append(row)

            unit, qty = self._find_unit_qty(block)
            desc = ' '.join(desc_lines)
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = re.sub(r'Fill By\s*Tenderer/Consultant.*?$', '', desc)
            desc = re.sub(r'- Money Positive.*$', '', desc)
            desc = re.sub(r'Auto\s*Auto\s*Auto', '', desc)
            desc = desc.strip()

            item_no_num = _item_no_value(item_no)
            if item_no_num is None or item_no_num > 200:
                i = j + 1
                continue

            items.append({
                'item_no': str(item_no),
                'code': code,
                'description': desc[:500],
                'unit': unit,
                'quantity': qty,
                'rate': None,
            })
            i = j + 1

        return items

    def _complete_dashed_code(self, code: str, block: List[str]) -> str:
        for row in block[1:4]:
            m = re.match(r'^(\d{1,3})(?=[A-Za-z]|\b)', row.strip())
            if m:
                suffix = m.group(1)
                # Avoid accidental capture from numeric description values (e.g., density 855).
                if len(suffix) <= 2:
                    return f"{code}{suffix}"
        return code

    def _improve_code_from_desc(self, code: str, tail: str) -> str:
        if not tail:
            return code
        m = re.search(r'\b(\d{1,3}(?:\.\d+){1,3})\b', tail)
        if m:
            candidate = m.group(1)
            if candidate.startswith(code):
                return candidate
            if code.endswith('.') and candidate.startswith(code[:-1]):
                return candidate
            if code.count('.') >= 1 and candidate.startswith(code.split('.')[0]):
                return candidate
        return code

    def _is_noise_line(self, line: str) -> bool:
        l = line.strip()
        if not l:
            return True
        noise_patterns = [
            r'^Home$',
            r'^Message Box$',
            r'^Tender$',
            r'^CMS$',
            r'^Doc\. Library$',
            r'^Tenderer Database$',
            r'^Administration$',
            r'^Debarment$',
            r'^My Account$',
            r'^Help$',
            r'^Go Back to Tender/Proposal',
            r'^Welcome,',
            r'^Logout$',
            r'^View All Notifications$',
            r'^Form View$',
            r'^https?://',
            r'^Page',
            r'^Copyright',
            r'^Best viewed',
            r'^18/05/20',
        ]
        for pattern in noise_patterns:
            if re.search(pattern, l, re.IGNORECASE):
                return True
        return False

    def _find_item_starts(self, lines: List[str], pattern) -> List:
        """Find item start lines matching a pattern."""
        starts = []
        for i, line in enumerate(lines):
            m = pattern(line)
            if m:
                starts.append((i, m))
        return starts

    def _extract_block(self, lines: List[str], start_idx: int, end_idx: int) -> List[str]:
        """Extract block of lines for an item."""
        return lines[start_idx:end_idx]

    def _find_unit_qty(self, block: List[str]) -> tuple:
        """Find unit and quantity from item block."""
        unit = ''
        qty = 0.0
        
        full_text = ' '.join(block)
        
        # Find Fill By or Auto Auto line - unit+qty is just before it
        for line in block:
            if 'Fill By' in line or 'Auto Auto' in line:
                before = line.split('Fill By')[0].split('Auto Auto')[0].strip()
                
                # Remove common trailing boilerplate
                for kw in ['digits after decimal', 'Money Positive', '- Money']:
                    idx = before.find(kw)
                    if idx > 0:
                        before = before[:idx].strip()
                
                # Try each unit pattern: unit followed by spaces then number
                for u in sorted(UNITS, key=len, reverse=True):
                    # Pattern: unit + space(s) + number
                    pat = re.escape(u) + r'\s+([\d,]+\.?\d*)'
                    m = re.search(pat, before, re.IGNORECASE)
                    if m:
                        unit = u.lower()
                        try:
                            qty = float(m.group(1).replace(',', ''))
                        except Exception:
                            qty = 0.0
                        break

                if unit:
                    break

        # Also check for unit at end of words (e.g., "...description.sqm 2")
        if not unit:
            for line in block:
                for u in sorted(UNITS, key=len, reverse=True):
                    # Word ends with unit then space then number
                    m = re.search(r'[a-zA-Z]' + re.escape(u) + r'\s+([\d,]+\.?\d*)', line, re.IGNORECASE)
                    if m:
                        unit = u.lower()
                        try:
                            qty = float(m.group(1).replace(',', ''))
                        except Exception:
                            qty = 0.0
                        break
                if unit:
                    break
        
        return unit, qty

    # ── Format 1: New e-GP (2024+) ──────────────────────────────────────
    # Lines: "1. Bank Protection Work04-180-00 Description..."
    def _parse_new_egp(self, lines: List[str]) -> List[Dict]:
        items = []
        item_starts = [(i, int(m.group(1))) for i, line in enumerate(lines)
                       if (m := re.match(r'^(\d+)\.\s', line))]

        for idx, (start_i, item_no) in enumerate(item_starts):
            end_i = item_starts[idx + 1][0] if idx + 1 < len(item_starts) else len(lines)
            block = lines[start_i:end_i]
            item = self._extract_new_egp_item(block, item_no)
            if item:
                items.append(item)
        return items

    def _extract_new_egp_item(self, block: List[str], item_no: int) -> Optional[Dict]:
        code = None
        desc_lines = []
        
        for line in block:
            m = re.search(r'Work((?:\d+[\.\-]\d+(?:[\.\-]\d+)?(?:\([\w]+\))?(?:\s*&\s*\d+[\.\-]\d+(?:[\.\-]\d+)?(?:\([\w]+\))?)?))', line)
            if m:
                code = m.group(1).strip()
                after_code = line[m.end():].strip()
                desc_lines.append(after_code)
            elif code is not None:
                if any(kw in line for kw in ['Tenderer/Consultant', 'Money Positive', 'digits after decimal', 'Auto Auto Auto']):
                    continue
                desc_lines.append(line)
        
        if not code:
            for line in block:
                m = re.match(r'^[A-Za-z]+((?:\d+[\.\-]\d+(?:[\.\-]\d+)?(?:\([\w]+\))?(?:\s*&\s*\d+[\.\-]\d+(?:[\.\-]\d+)?(?:\([\w]+\))?)?))', line)
                if m:
                    code = m.group(1).strip()
                    after_code = line[m.end():].strip()
                    desc_lines.append(after_code)
                    break
        
        if not code:
            return None
        
        unit, qty = self._find_unit_qty(block)
        
        desc = ' '.join(desc_lines)
        desc = re.sub(r'\s+', ' ', desc).strip()
        desc = re.sub(r'Fill By\s*Tenderer/Consultant.*?$', '', desc)
        desc = re.sub(r'- Money Positive.*$', '', desc)
        desc = re.sub(r'Auto\s*Auto\s*Auto', '', desc)
        desc = desc.strip()
        code = re.sub(r'\s*&\s*', '&', code).strip()
        
        return {
            'item_no': str(item_no),
            'code': code,
            'description': desc[:500],
            'unit': unit,
            'quantity': qty,
            'rate': None,
        }

    # ── Format 2: Old e-GP (2020) ───────────────────────────────────────
    # Lines: "1 Part-A N.A Description...Cum 8.943 Fill By"
    def _parse_old_egp(self, lines: List[str]) -> List[Dict]:
        items = []
        item_starts = []
        
        for i, line in enumerate(lines):
            m = re.match(r'^(\d+)\s+(Part-[A-D])\s+(N\.A|N\./A|[A-Z]?)\s+(.*)', line)
            if m:
                item_starts.append((i, int(m.group(1)), m.group(2), m.group(4)))
        
        for idx, (start_i, item_no, part, first_desc) in enumerate(item_starts):
            end_i = item_starts[idx + 1][0] if idx + 1 < len(item_starts) else len(lines)
            block = lines[start_i:end_i]
            
            # Description: start with the text after Part/N.A code
            desc_parts = [first_desc]
            skip_patterns = ['Tenderer/Consultant', 'Money Positive', 'digits after decimal', 'Auto Auto Auto']
            
            for line in block[1:]:
                # Skip the item start if it's a continuation (no new item number)
                if re.match(r'^\d+\s+Part-', line):
                    continue
                if any(kw in line for kw in skip_patterns):
                    continue
                desc_parts.append(line)
            
            unit, qty = self._find_unit_qty(block)
            
            desc = ' '.join(desc_parts)
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = re.sub(r'Fill By\s*Tenderer/Consultant.*?$', '', desc)
            desc = re.sub(r'- Money Positive.*$', '', desc)
            desc = re.sub(r'Auto\s*Auto\s*Auto', '', desc)
            desc = desc.strip()
            
            items.append({
                'item_no': str(item_no),
                'code': f"{part}/NA",
                'description': desc[:500],
                'unit': unit,
                'quantity': qty,
                'rate': None,
                'part': part,
            })
        
        return items

    # ── Format 3: Generic numbered items ─────────────────────────────────
    def _parse_generic(self, lines: List[str]) -> List[Dict]:
        items = []
        item_starts = [(i, int(m.group(1))) for i, line in enumerate(lines)
                       if (m := re.match(r'^(\d+)\.\s', line))]

        for idx, (start_i, item_no) in enumerate(item_starts):
            end_i = item_starts[idx + 1][0] if idx + 1 < len(item_starts) else len(lines)
            block = lines[start_i:end_i]
            
            desc_parts = []
            first = True
            for line in block:
                if first:
                    # Remove "1. " prefix
                    line = re.sub(r'^\d+\.\s+', '', line)
                    first = False
                if any(kw in line for kw in ['Tenderer/Consultant', 'Money Positive', 'digits after decimal', 'Auto Auto Auto', 'Fill By']):
                    continue
                desc_parts.append(line)
            
            unit, qty = self._find_unit_qty(block)
            
            desc = ' '.join(desc_parts)
            desc = re.sub(r'\s+', ' ', desc).strip()
            
            items.append({
                'item_no': str(item_no),
                'code': '',
                'description': desc[:500],
                'unit': unit,
                'quantity': qty,
                'rate': None,
            })
        
        return items
