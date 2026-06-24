"""Extract ZIP and find BOQ"""
import zipfile, os

zip_path = "uploads/1290886/all_documents.zip"
out_dir = "uploads/1290886/docs"

with zipfile.ZipFile(zip_path, "r") as zf:
    zf.extractall(out_dir)
    print(f"ZIP contains {len(zf.namelist())} files:")
    total = 0
    for name in zf.namelist():
        info = zf.getinfo(name)
        size = info.file_size
        total += size
        print(f"  {name} ({size:,} bytes)")
    print(f"Total: {total:,} bytes")

print()
print("Files containing 'boq' or 'bill' or 'quantity' or 'section6':")
for root, dirs, files in os.walk(out_dir):
    for f in files:
        lower = f.lower()
        if any(k in lower for k in ["boq", "bill", "quantit", "section6"]):
            fpath = os.path.join(root, f)
            print(f"  {fpath} ({os.path.getsize(fpath):,} bytes)")
