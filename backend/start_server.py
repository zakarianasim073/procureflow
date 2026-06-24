"""Start backend server without reload."""
import os, sys
backend_dir = r"D:\A1\procurementflow_final_v3\procurementflow\backend"
sys.path.insert(0, backend_dir)
os.environ.setdefault("BOQ_BASE_DIR", r"D:\A1\procurementflow_final_v3\procurementflow\runtime")
os.environ.setdefault("EGP_EMAIL", "hbsrjv@gmail.com")
os.environ.setdefault("EGP_PASSWORD", "hbsrjv2017")
import uvicorn
uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
