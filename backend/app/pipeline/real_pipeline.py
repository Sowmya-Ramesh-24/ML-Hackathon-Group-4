"""REAL pipeline adapter - loads the teammates' actual Python module.

Activated with PATHSNAP_MODE=real and PATHSNAP_TEAMMATES_MODULE pointing at
the module the teammates hand over (import name or .py file path).

The module must expose the integration surface documented in
docs/INTEGRATION_CONTRACT.md:

    list_trips() -> list[dict]                      (Person 1)
    load_trip(trip_id) -> dict                      (Person 1)
        keys: observations, arcs, candidates, reference_geometry (optional),
              reference_arc_ids (optional)
    score_candidates(trip) -> dict[int, list[dict]] (Person 2)
        obs index -> [{arc_id, p_match}] - model inference only; the trained
        model must be loaded once by their module, never retrained per call.
    decode(trip, scores) -> dict[int, str | None]   (Person 3)
        obs index -> predicted arc_id (None = unmatched). HMM/Viterbi that
        picks a globally plausible sequence, not per-point argmax.

Optional keys in load_trip's dict: reference_geometry, reference_arc_ids,
obs_true_arcs (obs index -> true arc_id, used only for server-side
evaluation after prediction).

This adapter never fabricates output: any missing piece raises
PipelineUnavailable with an explicit message instead of returning invented
predictions.
"""
from __future__ import annotations

import importlib
import importlib.util
import time
from pathlib import Path

from .base import DecodeResult, MatchingPipeline, PipelineUnavailable, TripData

REQUIRED_FUNCTIONS = ("list_trips", "load_trip", "score_candidates", "decode")


class RealPipeline(MatchingPipeline):
    label = "real teammates pipeline (Persons 1-3 via adapter)"
    is_mock = False

    def __init__(self, module_ref: str) -> None:
        if not module_ref:
            raise PipelineUnavailable(
                "PATHSNAP_MODE=real but PATHSNAP_TEAMMATES_MODULE is not set. "
                "Point it at the teammates' integration module (see "
                "docs/INTEGRATION_CONTRACT.md) or run with PATHSNAP_MODE=mock."
            )
        self._module = self._import(module_ref)
        missing = [f for f in REQUIRED_FUNCTIONS if not callable(getattr(self._module, f, None))]
        if missing:
            raise PipelineUnavailable(
                f"Teammates module {module_ref!r} is missing required function(s): "
                f"{', '.join(missing)}. See docs/INTEGRATION_CONTRACT.md."
            )

    @staticmethod
    def _import(module_ref: str):
        path = Path(module_ref)
        if path.suffix == ".py" and path.exists():
            spec = importlib.util.spec_from_file_location("teammates_pipeline", path)
            if spec is None or spec.loader is None:
                raise PipelineUnavailable(f"Cannot import teammates module from {module_ref!r}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        try:
            return importlib.import_module(module_ref)
        except ImportError as exc:
            raise PipelineUnavailable(
                f"Cannot import teammates module {module_ref!r}: {exc}"
            ) from exc

    # -- MatchingPipeline API ---------------------------------------------

    def list_trips(self) -> list[dict]:
        trips = self._module.list_trips()
        return [
            {
                "trip_id": t["trip_id"],
                "num_observations": int(t.get("num_observations", 0)),
                "description": str(t.get("description", "")),
            }
            for t in trips
        ]

    def load_trip(self, trip_id: str) -> TripData:
        raw = self._module.load_trip(trip_id)
        if raw is None:
            raise KeyError(trip_id)
        for key in ("observations", "arcs", "candidates"):
            if key not in raw:
                raise PipelineUnavailable(
                    f"Teammates load_trip({trip_id!r}) result is missing key {key!r}. "
                    "See docs/INTEGRATION_CONTRACT.md."
                )
        candidates = {int(k): list(v) for k, v in raw["candidates"].items()}
        trip = TripData(
            trip_id=trip_id,
            observations=list(raw["observations"]),
            arcs=dict(raw["arcs"]),
            candidates=candidates,
            scores={},
            reference_geometry=raw.get("reference_geometry"),
            reference_arc_ids=list(raw.get("reference_arc_ids", [])),
            obs_true_arcs={int(k): v for k, v in raw.get("obs_true_arcs", {}).items()},
        )
        t0 = time.perf_counter()
        scored = self._module.score_candidates(raw)
        trip.scores = {int(k): list(v) for k, v in scored.items()}
        trip._score_time_ms = (time.perf_counter() - t0) * 1000  # type: ignore[attr-defined]
        return trip

    def decode(self, trip: TripData) -> DecodeResult:
        payload = {
            "trip_id": trip.trip_id,
            "observations": trip.observations,
            "arcs": trip.arcs,
            "candidates": trip.candidates,
        }
        t0 = time.perf_counter()
        predictions = self._module.decode(payload, trip.scores)
        elapsed = (time.perf_counter() - t0) * 1000
        if not isinstance(predictions, dict):
            raise PipelineUnavailable(
                "Teammates decode() must return dict[obs_index -> arc_id or None]. "
                "See docs/INTEGRATION_CONTRACT.md."
            )
        score_ms = getattr(trip, "_score_time_ms", 0.0)
        return DecodeResult(
            predictions={int(k): v for k, v in predictions.items()},
            processing_time_ms=round(score_ms + elapsed, 2),
        )

    # -- stretch assembly (same rules as the mock pipeline) ---------------

    def build_stretches(self, trip: TripData, predictions: dict[int, str | None]):
        from .mock_pipeline import MockPipeline

        helper = MockPipeline.__new__(MockPipeline)
        helper._arcs = trip.arcs
        return MockPipeline.build_stretches(helper, trip, predictions)
