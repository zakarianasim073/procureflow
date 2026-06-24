"""
Subprocess downloader for e-GP tender documents.
Bypasses in-process httpx connectivity issues by running in a clean subprocess.
Usage: python _sub_dl.py <tender_id> <docs_dir> <uploads_dir>
Outputs JSON array of downloaded file metadata on the last stdout line.
"""
import sys, httpx, re, zipfile, shutil, json
from pathlib import Path

# Add backend paths: script is at backend/app/agents/discovery/_sub_dl.py
SCRIPT_DIR = Path(__file__).resolve().parent  # discovery/
BACKEND = SCRIPT_DIR.parent.parent.parent  # backend/
sys.path.insert(0, str(BACKEND / "app"))
sys.path.insert(0, str(BACKEND))

from app.agents.credentials import get_credentials
from app.agents.egp_client import eGPClient, BASE_URL

TENDER_ID = sys.argv[1]
DOCS_DIR = Path(sys.argv[2])
UPLOADS_DIR = Path(sys.argv[3])
DOCS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

try:
    creds = get_credentials()
    client = eGPClient(email=creds.egp.email, password=creds.egp.password, timeout=120)
    client.login()
    print(f"Sub dl: logged in as {creds.egp.email}", flush=True)
except Exception as exc:
    print(f"Sub dl: login failed: {exc}", flush=True)
    print("[]", flush=True)
    sys.exit(0)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"{BASE_URL}/resources/common/ViewTender.jsp?id={TENDER_ID}",
}

results = []

# 1) Notice PDF (public, correct URL format)
notice_url = (
    f"{BASE_URL}/GeneratePdf"
    f"?reqURL=http://www.eprocure.gov.bd/resources/common/ViewTender.jsp"
    f"&reqQuery=id={TENDER_ID}&folderName=TenderNotice&id={TENDER_ID}"
)
try:
    nr = client.client.get(notice_url, headers=headers, timeout=120)
    if nr.status_code == 200 and len(nr.content) > 500:
        p = DOCS_DIR / "notice.pdf"
        p.write_bytes(nr.content)
        results.append({"doc_type": "NIT", "path": str(p), "size_bytes": len(nr.content), "source": "egp_direct", "url": notice_url})
        shutil.copy2(str(p), str(UPLOADS_DIR / "notice.pdf"))
        print(f"Sub dl: Notice PDF {len(nr.content):,}B", flush=True)
except Exception as exc:
    print(f"Sub dl: Notice failed: {exc}", flush=True)

# 2) All-documents ZIP
zip_url = f"{BASE_URL}/TenderSecUploadServlet?tenderId={TENDER_ID}&folderArchId=1&lotNo=Package&funName=zipdownload"
try:
    zr = client.client.get(zip_url, headers=headers, timeout=120)
    if zr.status_code == 200 and len(zr.content) > 1000:
        zp = DOCS_DIR / "all_documents.zip"
        zp.write_bytes(zr.content)
        results.append({"doc_type": "ZIP", "path": str(zp), "size_bytes": len(zr.content), "source": "egp_direct", "url": zip_url})
        shutil.copy2(str(zp), str(UPLOADS_DIR / "all_documents.zip"))
        try:
            with zipfile.ZipFile(zp) as zf:
                zf.extractall(str(UPLOADS_DIR))
            for fp in sorted(UPLOADS_DIR.rglob("*")):
                if fp.is_file() and fp.name not in ("all_documents.zip", "notice.pdf"):
                    results.append({"doc_type": "extracted", "path": str(fp), "size_bytes": fp.stat().st_size, "source": "zip_extract"})
            print(f"Sub dl: ZIP {len(zr.content):,}B extracted", flush=True)
        except Exception as exc:
            print(f"Sub dl: ZIP extract failed: {exc}", flush=True)
except Exception as exc:
    print(f"Sub dl: ZIP failed: {exc}", flush=True)

# 3) TenderDocView.jsp individual sections
tdv_url = f"{BASE_URL}/tenderer/TenderDocView.jsp?tenderId={TENDER_ID}"
try:
    tr = client.client.get(tdv_url, headers=headers, timeout=120)
    if tr.status_code == 200 and len(tr.text) > 1000:
        (DOCS_DIR / "TenderDocView.html").write_text(tr.text, encoding="utf-8")
        dl_links = re.findall(r'/TenderSecUploadServlet\?[^"\' ]+', tr.text)
        for dl_path in dl_links:
            if "zipdownload" in dl_path:
                continue
            dl_url = f"{BASE_URL}{dl_path}"
            dm = re.search(r'docName=([^&]+)', dl_path)
            fn = dm.group(1) if dm else "document"
            fn = fn.replace("%20", " ").replace("%28", "(").replace("%29", ")")
            try:
                dr = client.client.get(dl_url, headers=headers, timeout=120)
                if dr.status_code == 200 and len(dr.content) > 200:
                    ext = ".pdf"
                    if dr.content[:2] == b'PK':
                        ext = ".docx" if ".docx" in fn.lower() else ".bin"
                    elif dr.content[:4] != b'%PDF':
                        ext = ".bin"
                    if not fn.lower().endswith((".pdf", ".docx", ".zip", ".xlsx")):
                        fn += ext
                    fp = DOCS_DIR / fn
                    fp.write_bytes(dr.content)
                    results.append({"doc_type": "section", "path": str(fp), "size_bytes": len(dr.content), "source": "TenderDocView", "url": dl_url})
                    shutil.copy2(str(fp), str(UPLOADS_DIR / fn))
                    print(f"Sub dl: Section {fn} ({len(dr.content):,}B)", flush=True)
            except Exception:
                pass
except Exception as exc:
    print(f"Sub dl: TenderDocView failed: {exc}", flush=True)

client.close()
print(json.dumps(results), flush=True)
