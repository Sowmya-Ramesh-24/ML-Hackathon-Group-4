"""Health endpoint - also reports pipeline mode so the UI can badge MOCK."""
from fastapi import APIRouter

from ..pipeline import service
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    mode, label, error = service.pipeline_status()
    return HealthResponse(
        status="ok" if error is None else "degraded",
        mode=mode,
        pipeline=label if error is None else f"unavailable: {error}",
        version=VERSION,
    )
