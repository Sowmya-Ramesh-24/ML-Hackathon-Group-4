"""Pipeline interfaces - the integration contract between Person 4 and the
teammates' code (Persons 1, 2 and 3).

The backend talks to the route-matching pipeline ONLY through the
`MatchingPipeline` abstract class below. Two implementations exist:

- mock_pipeline.MockPipeline  - clearly labelled synthetic pipeline so the
  backend and frontend can be built and demonstrated in parallel while the
  teammates finish their parts.
- real_pipeline.RealPipeline  - thin adapter that imports the actual
  teammates' Python module at startup and calls their real functions.

docs/INTEGRATION_CONTRACT.md describes the exact functions the teammates'
module must expose for real mode.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class TripData:
    """Everything the pipeline knows about one trip.

    Persons 1+2 own the contents; Person 4 only passes them through.
    `reference_geometry` is server-side ground truth and must never be sent
    to the browser before a prediction has been produced.
    """

    trip_id: str
    observations: list[dict]  # [{index, lat, lon, timestamp}]
    arcs: dict[str, dict]  # arc_id -> {arc_id, geometry: [[lat, lon], ...], length_m}
    candidates: dict[int, list[str]]  # obs index -> candidate arc_ids
    scores: dict[int, list[dict]]  # obs index -> [{arc_id, p_match}]
    reference_geometry: list[list[float]] | None = None
    reference_arc_ids: list[str] = field(default_factory=list)
    #: Optional server-side mapping obs index -> true arc_id (evaluation only,
    #: never sent to the browser before prediction).
    obs_true_arcs: dict[int, str] = field(default_factory=dict)


@dataclass
class DecodeResult:
    """Person 3's output: the decoded route for one trip."""

    predictions: dict[int, str | None]  # obs index -> arc_id or None (unmatched)
    processing_time_ms: float = 0.0


class PipelineUnavailable(RuntimeError):
    """Raised when the requested pipeline cannot serve requests (e.g. real
    mode selected but the teammates' module is missing or incomplete)."""


class MatchingPipeline(abc.ABC):
    """The single seam between the FastAPI backend and the matching stack."""

    #: Short label surfaced through the API so demos can prove their source.
    label: str = "abstract"
    #: True only for the labelled mock pipeline.
    is_mock: bool = True

    @abc.abstractmethod
    def list_trips(self) -> list[dict]:
        """Return trip metadata (no ground truth) for the trip picker."""

    @abc.abstractmethod
    def load_trip(self, trip_id: str) -> TripData:
        """Load observations, candidates, scores and road geometry.

        Raises KeyError for an unknown trip_id.
        """

    @abc.abstractmethod
    def decode(self, trip: TripData) -> DecodeResult:
        """Run the actual model + HMM/Viterbi decode for a loaded trip."""
