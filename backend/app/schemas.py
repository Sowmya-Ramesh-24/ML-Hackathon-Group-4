"""Pydantic schemas for the PathSnap API.

Coordinate convention everywhere: [lat, lon] pairs (Leaflet/Folium order).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    mode: str = Field(description="'mock' or 'real'")
    pipeline: str = Field(description="Human-readable pipeline source label")
    version: str


class TripMeta(BaseModel):
    trip_id: str
    num_observations: int
    description: str = ""


class TripListResponse(BaseModel):
    mode: str
    count: int
    trips: list[TripMeta]


class Observation(BaseModel):
    index: int
    lat: float
    lon: float
    timestamp: str


class Stretch(BaseModel):
    """One continuous run of the predicted route.

    Each stretch is drawn as its own polyline. Stretches are never joined
    across a GPS gap, so the map never shows a misleading straight line
    through missing coverage.
    """

    stretch_id: int
    arc_ids: list[str]
    reconstructed_arc_ids: list[str] = Field(
        default_factory=list,
        description="Intermediate arcs reconstructed by the decoder between matched observations",
    )
    from_obs: int
    to_obs: int
    geometry: list[list[float]] = Field(description="Ordered [lat, lon] polyline")


class Gap(BaseModel):
    after_obs: int
    before_obs: int
    description: str = "Unmatched observations - no route drawn across this gap"


class MatchRequest(BaseModel):
    trip_id: str


class MatchResponse(BaseModel):
    trip_id: str
    mode: str
    mock: bool = Field(description="True when results come from the labelled mock pipeline")
    pipeline: str
    num_observations: int
    observations: list[Observation]
    stretches: list[Stretch]
    unmatched_observations: list[int]
    gaps: list[Gap]
    processing_time_ms: float
    note: str = ""


class EvaluateRequest(BaseModel):
    trip_id: str


class EvaluationMetrics(BaseModel):
    top1_accuracy: Optional[float] = None
    candidate_recall: Optional[float] = None
    matched_fraction: float
    num_predicted_stretches: int
    num_reference_stretches: Optional[int] = None
    continuity_ratio: Optional[float] = None
    processing_time_ms: float


class EvaluateResponse(BaseModel):
    trip_id: str
    mode: str
    mock: bool
    metrics: EvaluationMetrics
    reference_geometry: Optional[list[list[float]]] = Field(
        default=None,
        description="Reference route polyline. Only present after prediction, when permitted.",
    )
    note: str = ""


class ErrorResponse(BaseModel):
    detail: str
