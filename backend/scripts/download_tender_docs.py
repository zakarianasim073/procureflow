"""Download tender documents from e-GP using ViewTender.jsp and GeneratePdf"""
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

if not client.login():
    print("Login failed!")
    exit(1)
print("Login successful! Session:", client.session.is_authenticated)

# Download notice as PDF via GeneratePdf
print("\n=== Attempting to download NIT/Notice via GeneratePdf ===")
try:
    # Try the ViewTender.jsp as PDF
    gen_url = f"{BASE_URL}/GeneratePdf"
    params = {
        "reqURL": f"{BASE_URL}/resources/common/ViewTender.jsp",
        "reqQuery": f"id={TENDER_ID}&h=t",
        "folderName": "TenderNotice",
        "id": TENDER_ID,
    }
    resp = client.client.get(gen_url, params=params, timeout=60, follow_redirects=True)
    print(f"GeneratePdf response: status={resp.status_code}, len={len(resp.content)}")
    if len(resp.content) > 1000:
        fpath = OUTPUT_DIR / "notice.pdf"
        fpath.write_bytes(resp.content)
        print(f"Saved notice: {fpath} ({len(resp.content)} bytes)")
    else:
        print(f"Short response: {resp.text[:500]}")
except Exception as e:
    print(f"GeneratePdf error: {e}")

# Try accessing LotPckDocs.jsp 
print("\n=== Attempting LotPckDocs.jsp ===")
try:
    doc_url = f"{BASE_URL}/tenderer/LotPckDocs.jsp?tenderId={TENDER_ID}"
    print(f"Fetching: {doc_url}")
    resp = client.client.get(doc_url, timeout=60, follow_redirects=True)
    print(f"Response: status={resp.status_code}, len={len(resp.content)}")
    print(f"Final URL: {resp.url}")
    if resp.status_code == 200 and len(resp.text) > 500:
        with open(OUTPUT_DIR / "lotpckdocs.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("Saved HTML to", OUTPUT_DIR / "lotpckdocs.html")
        # Check for download links
        download_links = re.findall(r'href=["\']([^"\']*DownloadDocument[^"\']*)["\']', resp.text, re.IGNORECASE)
        print(f"Download links: {len(download_links)}")
        for dl in download_links:
            print(f"  {dl}")
        # Try to download each link
        for i, dl in enumerate(download_links[:10]):
            try:
                dl_url = dl if dl.startswith("http") else f"{BASE_URL}{dl}"
                dl_resp = client.client.get(dl_url, timeout=60, follow_redirects=True)
                print(f"  DL {i}: status={dl_resp.status_code}, len={len(dl_resp.content)}")
                if len(dl_resp.content) > 500:
                    ext = ".pdf" if dl_resp.content[:4] == b'%PDF' else ".bin"
                    fpath = OUTPUT_DIR / f"document_{i}{ext}"
                    fpath.write_bytes(dl_resp.content)
                    print(f"    Saved: {fpath}")
            except Exception as e:
                print(f"  DL {i} error: {e}")
    else:
        print(f"Response text: {resp.text[:500]}")
except Exception as e:
    print(f"LotPckDocs error: {e}")

# Try TenderDocView
print("\n=== Attempting TenderDocView.jsp ===")
try:
    doc_url = f"{BASE_URL}/tenderer/TenderDocView.jsp?tenderId={TENDER_ID}"
    resp = client.client.get(doc_url, timeout=60, follow_redirects=True)
    print(f"Response: status={resp.status_code}, len={len(resp.content)}")
    if resp.status_code == 200 and len(resp.text) > 500:
        with open(OUTPUT_DIR / "tenderdocview.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("Saved HTML")
except Exception as e:
    print(f"TenderDocView error: {e}")

# Try PDFServlet with POST
print("\n=== Attempting PDFServlet POST ===")
try:
    pdf_url = f"{BASE_URL}/PDFServlet"
    resp = client.client.post(pdf_url, timeout=60, follow_redirects=True)
    print(f"Response: status={resp.status_code}, len={len(resp.content)}")
except Exception as e:
    print(f"PDFServlet error: {e}")

# List all files downloaded
print("\n=== Downloaded files ===")
for f in sorted(OUTPUT_DIR.glob("*")):
    print(f"  {f.name} ({f.stat().st_size} bytes)")

client.close()
print("\nDone!")
