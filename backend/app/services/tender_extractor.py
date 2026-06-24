"""
Tender Data Extractor v3 - Clean extraction from e-GP Notice & TDS PDFs
"""

import re
from typing import Dict, Any, List, Optional
from pathlib import Path
import PyPDF2


class TenderExtractor:
    def extract_all(self, notice_path: str = None, tds_path: str = None, tds_2_path: str = None) -> Dict[str, Any]:
        data = {
            'tender_id': '', 'invitation_ref': '', 'title': '',
            'work_name': '', 'ministry': '', 'organization': '', 'procuring_entity': '',
            'procuring_entity_district': '', 'division': '', 'procurement_method': '',
            'package_no': '', 'project_code': '', 'project_name': '',
            'closing_date': '', 'opening_date': '', 'publication_date': '',
            'last_selling_date': '', 'estimated_cost': '', 'tender_security': '',
            'work_period_start': '', 'work_period_end': '',
            'financial': {}, 'eligibility': {}, 'officials': {},
        }
        if notice_path and Path(notice_path).exists():
            data.update(self._extract_notice(notice_path))
        if tds_path and Path(tds_path).exists():
            td = self._extract_tds(tds_path)
            data['financial'] = td.get('financial', {})
            data['eligibility'] = td.get('eligibility', {})
        if tds_2_path and Path(tds_2_path).exists():
            td2 = self._extract_tds(tds_2_path)
            data['financial'] = {**data.get('financial', {}), **td2.get('financial', {})}
            data['eligibility'] = {**data.get('eligibility', {}), **td2.get('eligibility', {})}
        if data.get('title') and not data.get('work_name'):
            data['work_name'] = data['title']
        if data.get('project_name') and not data.get('work_name'):
            data['work_name'] = data['project_name']
        return data

    def _read_pdf(self, path: str) -> str:
        try:
            import fitz
            doc = fitz.open(path)
            text = "\n".join(page.get_text() or "" for page in doc)
            doc.close()
            if text.strip():
                return text
        except Exception:
            pass

        text = ""
        with open(path, 'rb') as f:
            for page in PyPDF2.PdfReader(f).pages:
                text += (page.extract_text() or "") + "\n"
        return text

    def _lines(self, text: str) -> List[str]:
        return [ln.replace("\xa0", " ").strip() for ln in text.splitlines() if ln.replace("\xa0", " ").strip()]

    def _cln(self, val: str) -> str:
        """Clean extracted value."""
        val = val.strip().replace('\n', ' ')
        val = re.sub(r'\s+', ' ', val).strip()
        val = val.rstrip(':').strip()
        return val

    def _after_label(self, lines: List[str], label: str, max_ahead: int = 5) -> str:
        label_low = label.lower()
        for i, line in enumerate(lines):
            if label_low not in line.lower():
                continue
            if ":" in line and line.split(":", 1)[1].strip():
                return self._cln(line.split(":", 1)[1])
            for j in range(i + 1, min(i + max_ahead, len(lines))):
                candidate = lines[j].strip()
                if candidate and candidate != ":" and not candidate.endswith(":"):
                    return self._cln(candidate)
        return ""

    def _collect_after(self, lines: List[str], label: str, stop_labels: List[str], max_lines: int = 10) -> str:
        start = None
        for i, line in enumerate(lines):
            if label.lower() in line.lower():
                start = i + 1
                break
        if start is None:
            return ""
        pieces = []
        for line in lines[start:start + max_lines]:
            if any(stop.lower() in line.lower() for stop in stop_labels):
                break
            if line != ":":
                pieces.append(line)
        return self._cln(" ".join(pieces))

    def _date_after_label(self, lines: List[str], label: str) -> str:
        label_low = label.lower()
        date_re = re.compile(r"\d{2}[-/][A-Za-z]{3}[-/]\d{4}(?:\s+\d{2}:\d{2})?|\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?")
        for i, line in enumerate(lines):
            if label_low in line.lower():
                for j in range(i, min(i + 8, len(lines))):
                    match = date_re.search(lines[j])
                    if match:
                        return self._cln(match.group(0))
        return ""

    def _extract_package_and_work(self, lines: List[str]) -> tuple[str, str]:
        for i, line in enumerate(lines):
            context = " ".join(lines[max(0, i - 3):i + 1]).lower()
            if "description" not in line.lower() or "package" not in context:
                continue
            package_no = ""
            work_parts = []
            if ":" in line and line.split(":", 1)[1].strip():
                package_no = line.split(":", 1)[1].strip()
                cursor = i + 1
            else:
                cursor = i + 1
                while cursor < len(lines) and lines[cursor] == ":":
                    cursor += 1
                if cursor < len(lines):
                    package_no = lines[cursor].strip()
                    cursor += 1
            while cursor < len(lines):
                current = lines[cursor]
                if current.lower().startswith(("category", "scheduled tender", "evaluation type")):
                    break
                work_parts.append(current)
                cursor += 1
            return self._cln(package_no), self._cln(" ".join(work_parts))
        return "", ""

    def _extract_lot_details(self, lines: List[str]) -> Dict[str, Any]:
        date_re = re.compile(r"\d{2}-[A-Za-z]{3}-\d{4}")
        for i in range(len(lines)):
            line = lines[i]
            match = re.search(r"([A-Za-z][A-Za-z\s]+?)(\d{5,})\s+(\d{2}-[A-Za-z]{3}-\d{4})\s+(\d{2}-[A-Za-z]{3}-\d{4})", line)
            if match:
                return {
                    "location": self._cln(match.group(1)),
                    "tender_security": match.group(2),
                    "work_period_start": match.group(3),
                    "work_period_end": match.group(4),
                }
            if re.fullmatch(r"\d{5,}", line) and i + 2 < len(lines) and date_re.fullmatch(lines[i + 1]) and date_re.fullmatch(lines[i + 2]):
                return {
                    "location": lines[i - 1] if i > 0 else "",
                    "tender_security": line,
                    "work_period_start": lines[i + 1],
                    "work_period_end": lines[i + 2],
                }
        return {}

    def _extract_notice(self, path: str) -> Dict[str, Any]:
        text = self._read_pdf(path)
        lines = self._lines(text)
        d = {}

        # Tender ID
        m = re.search(r'Tender/Proposal\s*ID\s*:\s*(\d+)', text)
        if m: d['tender_id'] = m.group(1)

        # Invitation Reference (stop at Tender/Proposal Status)
        m = re.search(r'Invitation\s*Reference\s*No\.?\s*:\s*([^\n]+)', text)
        if m:
            ref = m.group(1)
            idx = ref.find('Tender/Proposal Status')
            d['invitation_ref'] = self._cln(ref[:idx] if idx > 0 else ref)

        # Ministry
        m = re.search(r'Ministry\s*:\s*([^\n]+?)(?:\s*Division\s*:|\s*Organization\s*:|$)', text)
        if m: d['ministry'] = self._cln(m.group(1))
        else:
            value = self._after_label(lines, "Ministry")
            if value:
                d['ministry'] = value

        # Organization
        m = re.search(r'Organization\s*:\s*([^\n]+)', text)
        if m: d['organization'] = self._cln(m.group(1))

        # Procuring Entity
        m = re.search(r'Procuring\s*Entity\s*Name\s*:\s*([^\n]+)', text)
        if m: d['procuring_entity'] = self._cln(m.group(1))
        else:
            d['procuring_entity'] = self._after_label(lines, "Procuring Entity Name")

        m = re.search(r'Procuring\s*Entity\s*District\s*:\s*([^\n]+)', text)
        if m: d['procuring_entity_district'] = self._cln(m.group(1))
        else:
            m = re.search(r'Procuring\s*Entity\s*Code\s*:\s*Procuring\s*Entity\s*District\s*:\s*([^\n]+)', text, re.IGNORECASE)
            if m:
                d['procuring_entity_district'] = self._cln(m.group(1))

        m = re.search(r'\bDivision\s*:\s*([^\n]+?)(?:\s*Organization\s*:|\n|$)', text)
        if m:
            value = self._cln(m.group(1))
            if value and "organization" not in value.lower():
                d['division'] = value

        # Procurement Method (stop at Budget Type)
        m = re.search(r'Procurement\s*Method\s*:\s*([^\n]+)', text)
        if m:
            pm = m.group(1)
            idx = pm.find('Budget')
            d['procurement_method'] = self._cln(pm[:idx] if idx > 0 else pm)

        # Package No
        m = re.search(r'Package\s*No\.?\s*(?:and\s*Description)?\s*:\s*([^\n]+)', text)
        if m: d['package_no'] = self._cln(m.group(1))
        package_no, work_name = self._extract_package_and_work(lines)
        if package_no:
            d['package_no'] = package_no
        if work_name:
            d['title'] = work_name
            d['work_name'] = work_name

        # Project Code
        m = re.search(r'Project\s*Code\s*:\s*(\d+)', text)
        if m: d['project_code'] = m.group(1)

        # Project Name (grab until next field)
        m = re.search(r'Project\s*Name\s*:\s*(.+?)(?:\n\s*(?:Tender|Category|Scheduled|$))', text, re.DOTALL)
        if m: d['project_name'] = self._cln(m.group(1).replace('\n', ' '))
        if not d.get('project_name'):
            project_name = self._collect_after(lines, "Project Name", ["Tender/Proposal Package No", "Tender/Proposal Package No. and", "Description"], 8)
            if project_name:
                d['project_name'] = project_name

        # Title / Brief - stop at "Evaluation Type", "Eligibility", "Category", "Scheduled", "Tender/Proposal", "Document"
        m = re.search(
            r'Brief\s*(?:Description\s*of\s*[Ww]orks?)?\s*:\s*(.+?)'
            r'(?=\s*(?:Evaluation\s+Type|Eligibility|Category|Scheduled|Tender/Proposal|Document))',
            text, re.DOTALL | re.IGNORECASE
        )
        if m:
            title = m.group(1)
            title = re.sub(r'\s+', ' ', title.replace('\n', ' ')).strip()
            title = title.rstrip('. ')
            d['title'] = title
            d['work_name'] = title

        # Dates (multiple formats)
        m = re.search(r'(?:Closing\s*Date\s*(?:and|&)?\s*Time|Closing Date)\s*:?\s*((?:\d{2}/){2}\d{4}\s*\d{2}:\d{2})', text)
        if m: d['closing_date'] = self._cln(m.group(1))
        if not d.get('closing_date'):
            d['closing_date'] = self._date_after_label(lines, "Tender/Proposal Closing")

        m = re.search(r'(?:Opening\s*Date\s*(?:and|&)?\s*Time|Opening Date)\s*:?\s*((?:\d{2}/){2}\d{4}\s*\d{2}:\d{2})', text)
        if m: d['opening_date'] = self._cln(m.group(1))
        if not d.get('opening_date'):
            d['opening_date'] = self._date_after_label(lines, "Tender/Proposal Opening")

        # Publication date - try with time first, then without
        m = re.search(r'Publication\s*Date\s*(?:and|&)?\s*Time?\s*:?\s*((?:\d{2}/){2}\d{4}\s*(?:\d{2}:\d{2})?|(?:\d{2}-[A-Z][a-z]{2}-\d{4}\s*(?:\d{2}:\d{2})?))', text)
        if m:
            d['publication_date'] = self._cln(m.group(1))
        else:
            m = re.search(r'(?:Published|Publication)\s*Date\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})', text, re.IGNORECASE)
            if m: d['publication_date'] = self._cln(m.group(1))
        if not d.get('publication_date'):
            d['publication_date'] = self._date_after_label(lines, "Scheduled Tender/Proposal Publication")

        # Last selling date - try with time first, then without
        m = re.search(r'(?:Document\s*last\s*selling|last\s*selling|Last\s*Selling)\s*[^:]*:\s*((?:\d{2}/){2}\d{4}\s*(?:\d{2}:\d{2})?|\d{2}-[A-Z][a-z]{2}-\d{4}\s*(?:\d{2}:\d{2})?)', text, re.IGNORECASE)
        if m:
            d['last_selling_date'] = self._cln(m.group(1))
        else:
            m = re.search(r'Last\s*Selling\s*Date\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})', text, re.IGNORECASE)
            if m: d['last_selling_date'] = self._cln(m.group(1))

        # Estimated cost - try "Estimated Cost Tk:" format first
        m = re.search(r'Estimated\s*Cost\s*\(?Tk\)?\.?\s*:?\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
        if m:
            d['estimated_cost'] = m.group(1).replace(',', '')
        else:
            # Fallback: infer from line like "Shariatpur7500000 01-Jul-2024 30-Jun-2026"
            m = re.search(r'([A-Z][a-z]+)(\d{5,}\.?\d*)\s+(\d{2}-[A-Z][a-z]{2}-\d{4})\s+(\d{2}-[A-Z][a-z]{2}-\d{4})', text)
            if m:
                d['estimated_cost'] = m.group(2)
                d['work_period_start'] = m.group(3)
                d['work_period_end'] = m.group(4)

        m = re.search(r'Tender\s*Security\s*(?:Amount)?\s*(?:Tk\.?)?\s*:?\s*([\d,]+\.?\d*(?:\s*[A-Za-z]+)?)', text, re.IGNORECASE)
        if m:
            d['tender_security'] = self._cln(m.group(1))

        lot = self._extract_lot_details(lines)
        for key in ["location", "tender_security", "work_period_start", "work_period_end"]:
            if lot.get(key) and not d.get(key):
                d[key] = lot[key]

        # Official contact details - name stops at "Designation"
        m = re.search(r'Name\s*of\s*Official\s*Inviting[^:]*:\s*(.+?)(?=\s*Designation|$)', text, re.DOTALL | re.IGNORECASE)
        if m: d.setdefault('officials', {})['name'] = self._cln(m.group(1))
        m = re.search(r'Designation\s*of\s*Official[^:]*:\s*([^\n]+)', text)
        if m: d.setdefault('officials', {})['designation'] = self._cln(m.group(1))
        m = re.search(r'Phone\s*(?:No|Number)\s*:\s*([^\n]+)', text)
        if m: d.setdefault('officials', {})['phone'] = self._cln(m.group(1))

        return d

    def _extract_tds(self, path: str) -> Dict[str, Any]:
        text = self._read_pdf(path)
        d = {'financial': {}, 'eligibility': {}}

        m = re.search(r'general\s+experience[\s\S]{0,500}?shall\s+be\s*(\d+)\s*(?:\([^)]*\)\s*)?years', text, re.IGNORECASE)
        if m: d['eligibility']['min_general_experience_years'] = m.group(1)

        m = re.search(r'specific\s+experience[\s\S]{0,500}?at\s+least\s*(\d+|[Oo]ne)\s*(?:\([^)]*\))?\s*contract', text, re.IGNORECASE)
        if m:
            value = m.group(1)
            d['eligibility']['min_specific_contracts'] = "1" if value.lower() == "one" else value

        m = re.search(r'(?:minimum\s+value|value\s+of\s+at\s+least|total\s+value)[\s\S]{0,160}?Tk\.?\s*([\d,]+\.?\d*)\s*Lakh', text, re.IGNORECASE)
        if m: d['eligibility']['min_contract_value_lakh'] = m.group(1).replace(',', '')

        m = re.search(r'annual\s+construction\s+turnover[\s\S]{0,250}?Tk\.?\s*([\d,]+\.?\d*)\s*lakh', text, re.IGNORECASE)
        if m: d['financial']['min_annual_turnover_lakh'] = m.group(1).replace(',', '')

        m = re.search(r'(?:liquid\s+assets?|financial\s+resources|credit\s+line)[\s\S]{0,320}?Tk\.?\s*([\d,]+\.?\d*)\s*lakh', text, re.IGNORECASE)
        if m: d['financial']['min_liquid_assets_lakh'] = m.group(1).replace(',', '')

        m = re.search(r'(?:Minimum\s*(?:Tender|tender)\s*Capacity|minimum\s+capacity)[\s\S]{0,120}?Tk\.?\s*([\d,]+\.?\d*)\s*Lakh', text, re.IGNORECASE)
        if m: d['financial']['min_tender_capacity_lakh'] = m.group(1).replace(',', '')

        m = re.search(r'non-judicial\s+stamp[^.]*?Tk\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
        if m: d['financial']['jv_stamp_value'] = m.group(1).replace(',', '')

        m = re.search(r'Nominated\s*Subcontractor[^.]*?:\s*([^\n]+)', text, re.IGNORECASE)
        if m: d['eligibility']['nominated_subcontractors'] = self._cln(m.group(1))

        # Personnel
        lines = self._lines(text)
        personnel = self._parse_manpower_lines(lines)
        if not personnel:
            for line in text.split('\n'):
                m = re.search(r'(\d+)\.\s*(.+?):\s*(\d+)(?:No|Nos)?\s+(\d+)\s*Years\s+(\d+)\s*Years', line)
                if m:
                    personnel.append({
                        'sl_no': len(personnel) + 1,
                        'role': m.group(2).strip(),
                        'qualification': '',
                        'count': int(m.group(3)),
                        'total_experience_years': int(m.group(4)),
                        'similar_experience_years': int(m.group(5)),
                    })
        if personnel:
            d['eligibility']['personnel'] = personnel

        equipment = self._parse_equipment_lines(lines)
        if equipment:
            d['eligibility']['equipment'] = equipment

        return d

    def _parse_manpower_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        start = next((i for i, line in enumerate(lines) if line.lower().strip() == "position" and "experience" in " ".join(lines[i:i + 8]).lower()), None)
        if start is None:
            start = next((i for i, line in enumerate(lines) if "key personnel" in line.lower()), None)
        if start is None:
            return []

        end = next((i for i in range(start + 1, len(lines)) if any(token in lines[i].lower() for token in ["equipment type", "last login", "joint venture", "plant and equipment"])), min(start + 140, len(lines)))
        block = lines[start:end]
        items: List[Dict[str, Any]] = []
        i = 0
        while i < len(block):
            if not re.fullmatch(r"\d{1,2}", block[i].strip()):
                i += 1
                continue
            sl_no = int(block[i])
            i += 1
            text_parts = []
            while i < len(block) and not re.fullmatch(r"\d+\s*Years?", block[i], re.IGNORECASE):
                if re.fullmatch(r"\d{1,2}", block[i].strip()) and text_parts:
                    break
                if not self._is_tds_header_noise(block[i]):
                    text_parts.append(block[i])
                i += 1
            if i >= len(block):
                break
            total_exp_text = block[i]
            similar_exp_text = block[i + 1] if i + 1 < len(block) and "year" in block[i + 1].lower() else ""
            i += 2

            combined = self._cln(" ".join(text_parts))
            role, qualification = self._split_role_qualification(combined)
            count_text = self._extract_person_count(combined)
            items.append({
                "sl_no": sl_no,
                "role": role,
                "qualification": qualification,
                "count_text": count_text,
                "count": self._count_from_text(count_text),
                "total_experience": total_exp_text,
                "similar_experience": similar_exp_text,
                "total_experience_years": self._first_int(total_exp_text),
                "similar_experience_years": self._first_int(similar_exp_text),
            })
        return items

    def _parse_equipment_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        starts = [i for i, line in enumerate(lines) if "equipment type and characteristics" in line.lower() or "plant and equipment" in line.lower() or "equipment type" in line.lower()]
        if not starts:
            return []
        start = starts[-1]
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("19.") or "joint venture" in lines[i].lower()), min(start + 120, len(lines)))
        block = lines[start:end]
        items: List[Dict[str, Any]] = []
        i = 0
        while i < len(block):
            if not re.fullmatch(r"\d{1,2}", block[i].strip()):
                i += 1
                continue
            sl_no = int(block[i])
            i += 1
            desc_parts = []
            qty = ""
            while i < len(block):
                line = block[i]
                if re.fullmatch(r"\d{1,2}", line.strip()):
                    break
                if "documentary evidence" in line.lower():
                    break
                if re.fullmatch(r"\d+\s*(nos?|sets?|each|no)\.?", line.strip(), re.IGNORECASE):
                    qty = line.strip()
                    i += 1
                    break
                if not self._is_tds_header_noise(line):
                    desc_parts.append(line)
                i += 1
            description = self._cln(" ".join(desc_parts))
            if description:
                items.append({
                    "sl_no": sl_no,
                    "description": description,
                    "quantity": qty or "As required",
                    "count": self._count_from_text(qty),
                })
        return items

    def _is_tds_header_noise(self, line: str) -> bool:
        low = line.lower().strip()
        return low in {"no", "position", "minimum number", "required", "works", "experience", "(years)", "qualification"} or "equipment type" in low

    def _split_role_qualification(self, text: str) -> tuple[str, str]:
        if ":" in text:
            role, rest = text.split(":", 1)
            qualification = re.sub(r"\([^)]*person[^)]*\)", "", rest, flags=re.IGNORECASE).strip()
            return role.strip(), qualification or "N/A"
        cleaned = re.sub(r"\([^)]*person[^)]*\)", "", text, flags=re.IGNORECASE).strip()
        return cleaned, "N/A"

    def _extract_person_count(self, text: str) -> str:
        m = re.search(r"\((\d+)\s*person\)", text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} Person"
        m = re.search(r"\b(\d+)\s*(?:persons?|nos?|no)\b", text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} Person"
        return "As required" if "as required" in text.lower() else "1 Person"

    def _count_from_text(self, text: str) -> int:
        m = re.search(r"\d+", str(text or ""))
        return int(m.group(0)) if m else 1

    def _first_int(self, text: str) -> int:
        m = re.search(r"\d+", str(text or ""))
        return int(m.group(0)) if m else 0


def extract_tender_data(notice_path: str = None, tds_path: str = None, tds_2_path: str = None) -> Dict[str, Any]:
    return TenderExtractor().extract_all(notice_path, tds_path, tds_2_path)
