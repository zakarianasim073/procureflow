"""Download all tender documents from TenderDocView.jsp for tender 1290886"""
import sys, re
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from app.agents.credentials import get_credentials
from app.agents.egp_client import eGPClient, BASE_URL
from pathlib import Path

TENDER_ID = "1290886"
OUTPUT_DIR = Path("uploads") / TENDER_ID
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

creds = get_credentials()
client = eGPClient(email=creds.egp.email, password=creds.egp.password)
client.login()

# Fetch TenderDocView.jsp
print("Fetching TenderDocView.jsp...")
doc_url = f"{BASE_URL}/tenderer/TenderDocView.jsp?tenderId={TENDER_ID}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"{BASE_URL}/resources/common/ViewTender.jsp?id={TENDER_ID}",
}
resp = client.client.get(doc_url, headers=headers, timeout=120)
html = resp.text

# Find all download links
dl_links = re.findall(
    r'/TenderSecUploadServlet\?[^"\' ]+',
    html
)
print(f"Found {len(dl_links)} download links")

# Download each link
for i, dl_path in enumerate(dl_links):
    try:
        dl_url = f"{BASE_URL}{dl_path}"
        # Extract filename from docName parameter
        doc_name_match = re.search(r'docName=([^&]+)', dl_path)
        if doc_name_match:
            filename = doc_name_match.group(1)
            # URL decode
            filename = filename.replace('%20', ' ').replace('%28', '(').replace('%29', ')')
        else:
            filename = f"document_{i}"
        
        if 'zipdownload' in dl_path:
            filename = "all_documents.zip"
        
        print(f"  Downloading [{i+1}/{len(dl_links)}]: {filename}")
        
        dl_resp = client.client.get(dl_url, headers=headers, timeout=120, follow_redirects=True)
        
        if dl_resp.status_code == 200 and len(dl_resp.content) > 100:
            # Determine extension
            content = dl_resp.content
            if content[:4] == b'%PDF':
                ext = ".pdf"
            elif content[:2] == b'PK':
                ext = ".docx" if '.docx' in filename.lower() else ".zip"
            else:
                ext = ".bin"
            
            if not filename.lower().endswith(('.pdf', '.docx', '.zip', '.xlsx')):
                filename = filename + ext
            
            fpath = OUTPUT_DIR / filename
            fpath.write_bytes(content)
            print(f"    Saved: {fpath} ({len(content)} bytes)")
        else:
            print(f"    Failed: status={dl_resp.status_code}, size={len(dl_resp.content)}")
    except Exception as e:
        print(f"    Error downloading {dl_path}: {e}")

# List all downloaded files
print(f"\nAll files in {OUTPUT_DIR}:")
total_size = 0
for f in sorted(OUTPUT_DIR.glob("*")):
    print(f"  {f.name} ({f.stat().st_size:,} bytes)")
    total_size += f.stat().st_size
print(f"Total: {total_size:,} bytes")

client.close()
print("\nDone!")
