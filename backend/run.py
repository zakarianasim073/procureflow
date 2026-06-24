"""Procurement Flow Specialist BD — Local launcher"""
import os, sys
from pathlib import Path

# Ensure we can import app
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("PROCUREFLOW_HOST", "0.0.0.0")
    port = int(os.getenv("PROCUREFLOW_PORT", "8000"))
    debug = os.getenv("PROCUREFLOW_DEBUG", "true").lower() in ("true", "1")
    
    print(f"Procurement Flow Specialist BD starting on {host}:{port}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info",
    )
