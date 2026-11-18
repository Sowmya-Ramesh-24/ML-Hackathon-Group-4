"""Start the PathSnap backend.

Usage:
    python run.py

Honours PATHSNAP_HOST / PATHSNAP_PORT (see .env.example). Binds 0.0.0.0 by
default so Laptop 2 can reach the API over the LAN during the demo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
