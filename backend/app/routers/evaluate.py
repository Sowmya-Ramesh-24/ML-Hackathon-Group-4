"""Evaluation endpoint.

Rules enforced here (see the project brief's security requirement):
- Evaluation is only possible AFTER a prediction exists for the trip
  (409 otherwise). Ground truth is never exposed before prediction.
- Metrics are computed server-side from server-side reference data.
- Reference geometry is returned only when the server config permits it
  (PATHSNAP_RETURN_REFERENCE_GEOMETRY) and only in this post-prediction
  response. It is never part of /api/trips or /api/match.
"""
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..pipeline import service
from ..schemas import EvaluateRequest, EvaluateResponse, EvaluationMetrics

router = APIRouter(tags=["evaluation"])


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    run = service.get_run(req.trip_id)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No prediction exists for {req.trip_id!r}. Run POST /api/match "
                "first - evaluation never precedes prediction."
            ),
        )
    pipeline = service.get_pipeline()
    trip = run["trip"]
    result = run["result"]
    predictions = result.predictions

    matched = {i: a for i, a in predictions.items() if a}
    metrics = EvaluationMetrics(
        matched_fraction=round(len(matched) / max(len(trip.observations), 1), 4),
        num_predicted_stretches=len(run["stretches"]),
        processing_time_ms=result.processing_time_ms,
    )

    reference_available = bool(trip.obs_true_arcs)
    if reference_available:
        # Server-side scoring against the server-side per-observation truth.
        true_by_obs = trip.obs_true_arcs
        scored = [i for i in matched if i in true_by_obs]
        correct = sum(1 for i in scored if matched[i] == true_by_obs[i])
        metrics.top1_accuracy = round(correct / max(len(scored), 1), 4)

        # Candidate recall: fraction of observations whose candidate set
        # contained the true arc.
        in_cand = sum(
            1
            for ob in trip.observations
            if true_by_obs.get(ob["index"]) in trip.candidates.get(ob["index"], [])
        )
        metrics.candidate_recall = round(in_cand / max(len(trip.observations), 1), 4)

        # Continuity: reference traversed as one stretch vs predicted pieces.
        metrics.num_reference_stretches = 1
        metrics.continuity_ratio = round(
            1.0 / max(len(run["stretches"]), 1), 4
        )
        note = "Metrics computed server-side against server-side reference data."
    else:
        note = "No reference route available server-side; returning prediction statistics only."

    reference_geometry = None
    if settings.return_reference_geometry and trip.reference_geometry:
        reference_geometry = trip.reference_geometry

    return EvaluateResponse(
        trip_id=req.trip_id,
        mode=settings.mode,
        mock=pipeline.is_mock,
        metrics=metrics,
        reference_geometry=reference_geometry,
        note=note,
    )
