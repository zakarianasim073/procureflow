"""
Package the complete Procurement Flow project into a clean ZIP.
"""
import os, zipfile, time

ROOT = os.path.dirname(__file__)
ZIP_NAME = f"ProcurementFlow_Complete_{time.strftime('%Y%m%d')}.zip"
ZIP_PATH = os.path.join(ROOT, ZIP_NAME)

EXCLUDE_DIR_NAMES = {
    "__pycache__", ".venv", "venv", "env", "node_modules", ".git", ".idea", ".vscode",
    ".pytest_cache", "dist", "build", "htmlcov", ".mypy_cache", ".ruff_cache",
    "scraped_tenders", ".git.bak", "runtime_outputs",
}
EXCLUDE_FILE_NAMES = {
    ".env.local", ".env.prod", ".env.windows", "package_project.py",
    "check_agents.py", "list_tenders.py", "check_unknown.py", "package_all_bwdb.py",
    "find_bwdb_works.py", "search_bwdb_direct.py", "show_results.py",
}

RUNTIME_INCLUDE = {
    "backend/runtime/data_intel/bwdb_all_tenders.json",
    "backend/runtime/data_intel/bwdb_works_summary.txt",
    "backend/runtime/data_intel/BWDB_Works_65_Tenders.zip",
    "backend/runtime/data_intel/BWDB_All_113_Tenders_20260611.zip",
    "backend/runtime/data_intel/bwdb_live_tenders.json",
    "backend/runtime/data_intel/dedup_index.json",
    "backend/runtime/data_intel/collection_log.json",
}

total = skipped = 0
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir == ".":
            rel_dir = ""

        # Skip entire runtime/ dir (will add specific files later)
        if rel_dir == "runtime" or rel_dir.startswith("runtime\\") or rel_dir.startswith("runtime/"):
            dirnames.clear()
            continue
        if "\\runtime\\" in rel_dir or "/runtime/" in rel_dir:
            dirnames.clear()
            continue

        # Skip excluded dirs
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIR_NAMES
                       and not d.endswith(".egg-info")
                       and not d.endswith(".dist-info")]

        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in {".pyc", ".pyo", ".db", ".sqlite3", ".log", ".swp", ".swo", ".pdf", ".zip"}:
                skipped += 1
                continue
            if fn in EXCLUDE_FILE_NAMES:
                skipped += 1
                continue
            fp = os.path.join(dirpath, fn)
            arcname = os.path.join(rel_dir, fn) if rel_dir else fn
            zf.write(fp, arcname)
            total += 1

    # Add specific runtime data_intel files
    for rt_rel in RUNTIME_INCLUDE:
        fp = os.path.join(ROOT, rt_rel.replace("/", os.sep))
        if os.path.isfile(fp):
            zf.write(fp, rt_rel)
            total += 1

size_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
print(f"OK: {ZIP_NAME}")
print(f"  Size:   {size_mb:.1f} MB")
print(f"  Files:  {total}")
print(f"  Skipped: {skipped}")
print(f"  Path:   {ZIP_PATH}")
