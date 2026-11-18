"""Pipeline selection and per-trip run state.

Ground-truth handling: reference geometry lives only inside TripData on the
server. It leaves the server solely through the evaluate endpoint, and only
after a prediction for that trip exists.
"""
from __future__ import annotations

import threading

from ..config import settings
from .base import DecodeResult, MatchingPipeline, PipelineUnavailable, TripData

_lock = threading.Lock()
_pipeline: MatchingPipeline | None = None
_pipeline_error: str | None = None
# trip_id -> (TripData, DecodeResult, stretches, unmatched, gaps)
_runs: dict[str, dict] = {}


def get_pipeline() -> MatchingPipeline:
    """Lazily build the configured pipeline. Real-mode failures are cached
    and re-raised so /api/health can report them without crashing startup."""
    global _pipeline, _pipeline_error
    with _lock:
        if _pipeline is not None:
            return _pipeline
        if _pipeline_error is not None:
            raise PipelineUnavailable(_pipeline_error)
        try:
            if settings.mode == "real":
                from .real_pipeline import RealPipeline

                _pipeline = RealPipeline(settings.teammates_module)
            else:
                from .mock_pipeline import MockPipeline

                _pipeline = MockPipeline()
        except PipelineUnavailable as exc:
            _pipeline_error = str(exc)
            raise
        return _pipeline


def pipeline_status() -> tuple[str, str, str | None]:
    """(mode, label, error) for the health endpoint; never raises."""
    try:
        p = get_pipeline()
        return settings.mode, p.label, None
    except PipelineUnavailable as exc:
        return settings.mode, "unavailable", str(exc)


def run_match(trip_id: str) -> dict:
    """Execute the full pipeline for one trip and cache the run server-side."""
    pipeline = get_pipeline()
    try:
        trip = pipeline.load_trip(trip_id)
    except KeyError:
        raise
    result = pipeline.decode(trip)
    stretches, unmatched, gaps = pipeline.build_stretches(trip, result.predictions)
    run = {
        "trip": trip,
        "result": result,
        "stretches": stretches,
        "unmatched": unmatched,
        "gaps": gaps,
    }
    _runs[trip_id] = run
    return run


def get_run(trip_id: str) -> dict | None:
    return _runs.get(trip_id)
