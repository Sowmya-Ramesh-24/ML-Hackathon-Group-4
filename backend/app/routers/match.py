"""Run GPS-to-road matching for a selected trip."""
from fastapi import APIRouter, HTTPException

from ..pipeline import service
from ..pipeline.base import PipelineUnavailable
from ..schemas import Gap, MatchRequest, MatchResponse, Observation, Stretch

router = APIRouter(tags=["matching"])


def _run_to_response(trip_id: str, run: dict) -> MatchResponse:
    pipeline = service.get_pipeline()
    trip = run["trip"]
    result = run["result"]
    return MatchResponse(
        trip_id=trip_id,
        mode=service.settings.mode,
        mock=pipeline.is_mock,
        pipeline=pipeline.label,
        num_observations=len(trip.observations),
        observations=[Observation(**ob) for ob in trip.observations],
        stretches=[Stretch(**st) for st in run["stretches"]],
        unmatched_observations=run["unmatched"],
        gaps=[Gap(**g) for g in run["gaps"]],
        processing_time_ms=result.processing_time_ms,
        note=(
            "MOCK pipeline output - synthetic data, not teammate model predictions."
            if pipeline.is_mock
            else "Predictions from the teammates' pipeline."
        ),
    )


@router.post("/match", response_model=MatchResponse)
def run_match(req: MatchRequest) -> MatchResponse:
    try:
        run = service.run_match(req.trip_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown trip_id {req.trip_id!r}")
    except PipelineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _run_to_response(req.trip_id, run)


@router.get("/match/{trip_id}", response_model=MatchResponse)
def get_match(trip_id: str) -> MatchResponse:
    run = service.get_run(trip_id)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail=f"No prediction has been run for {trip_id!r} yet. POST /api/match first.",
        )
    return _run_to_response(trip_id, run)
