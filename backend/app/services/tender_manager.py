"""
Tender Manager - Structured folder system for tender documents
Creates: tenders/{tender_id}/{notice_id,tds_id,tds_2_id,boq_id}.pdf
Auto-extracts variable data from Notice & TDS on upload
"""

import os, re, json, shutil, uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .tender_extractor import extract_tender_data


class TenderManager:
    """Manages structured tender folders with auto-extraction."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            from app.core.config import settings
            base_dir = str(Path(settings.BASE_DIR) / "tenders")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _tender_dir(self, tender_id: str) -> Path:
        p = (self.base_dir / tender_id).resolve()
        if not str(p).startswith(str(self.base_dir.resolve())):
            raise ValueError(f"Path traversal detected in tender_id: {tender_id!r}")
        p.mkdir(parents=True, exist_ok=True)
        return p

    def store_document(self, tender_id: str, doc_type: str, file_path: str) -> Dict:
        """
        Store a document in the tender folder.
        doc_type: 'notice', 'tds', 'tds_2', 'boq'
        Returns metadata about the stored document.
        """
        valid_types = {'notice', 'tds', 'tds_2', 'boq'}
        if doc_type not in valid_types:
            raise ValueError(f"doc_type must be one of: {valid_types}")

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        tdir = self._tender_dir(tender_id)
        ext = src.suffix.lower() or '.pdf'
        dest = tdir / f"{doc_type}{ext}"

        # Copy file
        shutil.copy2(str(src), str(dest))

        doc_info = {
            'tender_id': tender_id,
            'doc_type': doc_type,
            'filename': dest.name,
            'path': str(dest),
            'size_bytes': dest.stat().st_size,
            'uploaded_at': datetime.now().isoformat(),
        }
        return doc_info

    def has_document(self, tender_id: str, doc_type: str) -> bool:
        """Check if a document type exists for this tender."""
        tdir = self._tender_dir(tender_id)
        for f in tdir.iterdir():
            if f.stem == doc_type:
                return True
        return False

    def get_document_path(self, tender_id: str, doc_type: str) -> Optional[str]:
        """Get path to a specific document type."""
        tdir = self._tender_dir(tender_id)
        for f in tdir.iterdir():
            if f.stem == doc_type:
                return str(f)
        return None

    def extract_variables(self, tender_id: str) -> Dict[str, Any]:
        """
        Auto-extract variable data from Notice & TDS PDFs in the tender folder.
        Returns structured data and saves to variables.json in the tender folder.
        """
        notice_path = self.get_document_path(tender_id, 'notice')
        tds_path = self.get_document_path(tender_id, 'tds')
        tds_2_path = self.get_document_path(tender_id, 'tds_2')

        if not notice_path and not tds_path and not tds_2_path:
            return {}

        data = extract_tender_data(notice_path, tds_path, tds_2_path)

        # Save to variables.json
        tdir = self._tender_dir(tender_id)
        var_path = tdir / 'variables.json'
        with open(var_path, 'w') as f:
            json.dump(data, f, indent=2)

        return data

    def get_variables(self, tender_id: str) -> Dict[str, Any]:
        """Get previously extracted variables."""
        var_path = self._tender_dir(tender_id) / 'variables.json'
        if var_path.exists():
            with open(var_path) as f:
                return json.load(f)
        return {}

    def list_tenders(self) -> List[Dict]:
        """List all tenders with their document status."""
        tenders = []
        if not self.base_dir.exists():
            return tenders

        for d in sorted(self.base_dir.iterdir()):
            if d.is_dir():
                docs = {f.stem: f.name for f in d.iterdir() if f.suffix == '.pdf'}
                var_path = d / 'variables.json'
                variables = {}
                if var_path.exists():
                    with open(var_path) as f:
                        variables = json.load(f)

                tenders.append({
                    'tender_id': d.name,
                    'documents': docs,
                    'has_variables': var_path.exists(),
                    'title': variables.get('title', ''),
                    'procuring_entity': variables.get('procuring_entity', ''),
                    'estimated_cost': variables.get('estimated_cost', ''),
                })

        return tenders

    def delete_tender(self, tender_id: str) -> bool:
        """Delete a tender folder and all its documents."""
        tdir = self._tender_dir(tender_id)
        if tdir.exists():
            shutil.rmtree(str(tdir))
            return True
        return False

    def create_from_upload(self, upload_dir: str, tender_id: str = None) -> Dict:
        """
        Scan upload directory for tender documents and organize them.
        Expected naming: Notice_*.pdf, TDS_*.pdf, TDS_2_*.pdf, BOQ_*.pdf, 3.BOQ_*.pdf
        """
        upload_path = Path(upload_dir)
        if not upload_path.exists():
            return {'error': 'Upload directory not found'}

        # Auto-detect tender_id from filenames if not provided
        if not tender_id:
            for f in upload_path.iterdir():
                m = re.search(r'[_-](\d{5,})', f.stem)
                if m:
                    tender_id = m.group(1)
                    break

        if not tender_id:
            return {'error': 'Could not detect tender ID'}

        # Map files to doc types
        doc_map = {}
        for f in upload_path.iterdir():
            if f.suffix.lower() not in ('.pdf', '.xlsx', '.xls'):
                continue
            name = f.stem.lower()
            if 'notice' in name or '1.' in name[:5]:
                doc_map['notice'] = str(f)
            elif 'tds_2' in name or 'tds2' in name:
                doc_map['tds_2'] = str(f)
            elif 'tds' in name or '2.' in name[:5]:
                doc_map['tds'] = str(f)
            elif 'boq' in name or '3.' in name[:5]:
                doc_map['boq'] = str(f)

        result = {'tender_id': tender_id, 'stored': [], 'extracted': {}}

        for doc_type, src_path in doc_map.items():
            info = self.store_document(tender_id, doc_type, src_path)
            result['stored'].append(info)

        # Auto-extract
        if 'notice' in doc_map or 'tds' in doc_map:
            result['extracted'] = self.extract_variables(tender_id)

        return result


tender_manager = TenderManager()
