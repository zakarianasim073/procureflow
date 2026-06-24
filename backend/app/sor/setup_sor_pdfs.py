"""Copy SOR PDFs from upload directory to sor data directories.
Run after uploading PDFs through the system.

Usage:
    python setup_sor_pdfs.py /path/to/uploaded/pdfs/
    
Or copy files manually:
    cp <LGED_SOR.pdf> app/sor/lged/LGED_Revised_Rate_Schedule_2023.pdf
    cp <PWD_SOR.pdf> app/sor/pwd/PWD_SoR_2022_Revised.pdf
    cp <BWDB_SOR.pdf> app/sor/bwdb/BWDB_Revised_Rate_Schedule_2023.pdf
"""

import shutil, sys, os
from pathlib import Path

SOR_DIR = Path(__file__).parent

MAPPING = {
    "LGED": "LGED_Revised_Rate_Schedule_2023.pdf",
    "PWD": "PWD_SoR_2022_Revised.pdf",
    "BWDB": "BWDB_Revised_Rate_Schedule_2023.pdf",
}

def setup(upload_dir=None):
    if upload_dir:
        upload_dir = Path(upload_dir)
        for agency, fname in MAPPING.items():
            src = upload_dir / fname
            if src.exists():
                dst = SOR_DIR / agency.lower() / fname
                shutil.copy2(src, dst)
                print(f"✅ {agency}: {fname} ({os.path.getsize(dst)/1024:.0f} KB)")
            else:
                # Try to find any matching PDF
                candidates = list(upload_dir.glob(f"*{agency}*")) + list(upload_dir.glob(f"*{agency.lower()}*"))
                if candidates:
                    shutil.copy2(candidates[0], SOR_DIR / agency.lower() / fname)
                    print(f"✅ {agency}: {candidates[0].name} → {fname}")
                else:
                    print(f"❌ {agency}: No PDF found in {upload_dir}")
    else:
        # Check if PDFs already exist
        for agency, fname in MAPPING.items():
            pdf = SOR_DIR / agency.lower() / fname
            if pdf.exists():
                size = os.path.getsize(pdf)
                print(f"✅ {agency}: {fname} ({size/1024/1024:.1f} MB)")
            else:
                print(f"❌ {agency}: PDF not found at {pdf}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        setup(sys.argv[1])
    else:
        setup()
