"""PathSnap FastAPI application entrypoint."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import evaluate, health, mapview, match, trips

app = FastAPI(
    title="PathSnap - Intelligent GPS Map Matching",
    description=(
        "GPS-to-road map matching: ML candidate scoring + HMM/Viterbi decoding, "
        "served as an API. Person 4 integration layer."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(match.router, prefix="/api")
app.include_router(evaluate.router, prefix="/api")
app.include_router(mapview.router, prefix="/api")

# Serve the frontend (built with plain HTML/JS + Leaflet) at / when present.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
