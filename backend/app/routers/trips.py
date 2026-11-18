"""Trip listing - metadata only, never ground truth."""
from fastapi import APIRouter, HTTPException

from ..pipeline import service
from ..pipeline.base import PipelineUnavailable
from ..schemas import TripListResponse, TripMeta

router = APIRouter(tags=["trips"])


@router.get("/trips", response_model=TripListResponse)
def list_trips() -> TripListResponse:
    try:
        pipeline = service.get_pipeline()
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    trips = [TripMeta(**t) for t in pipeline.list_trips()]
    return TripListResponse(mode=service.settings.mode, count=len(trips), trips=trips)
