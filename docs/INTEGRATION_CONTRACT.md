# PathSnap - Integration Contract (Persons 1-3 -> Person 4)

This document defines the **exact interface** the teammates' Python module must
expose so the FastAPI backend can run the real pipeline
(`PATHSNAP_MODE=real`). Nothing else in their code needs to change.

## Handoff: one Python module

Point the backend at it with `PATHSNAP_TEAMMATES_MODULE`:

```bash
export PATHSNAP_MODE=real
export PATHSNAP_TEAMMATES_MODULE=teammates_pipeline      # importable module name
# or: export PATHSNAP_TEAMMATES_MODULE=/path/to/teammates_pipeline.py
```

## Required functions

```python
def list_trips() -> list[dict]:
    """Person 1. Metadata for the trip picker. No ground truth.
    Each dict: {"trip_id": str, "num_observations": int, "description": str}"""

def load_trip(trip_id: str) -> dict:
    """Person 1. Everything needed to run matching for one trip.
    Returns None for an unknown trip_id.
    Keys:
      observations : list[{"index": int, "lat": float, "lon": float,
                           "timestamp": str}]  # timestamp order
      arcs         : dict[arc_id, {"arc_id": str,
                                   "geometry": [[lat, lon], ...],
                                   "length_m": float}]
      candidates   : dict[obs_index, list[arc_id]]   # per GPS observation
    Optional (server-side evaluation only, never sent pre-prediction):
      reference_geometry : [[lat, lon], ...]
      reference_arc_ids  : list[arc_id]
      obs_true_arcs      : dict[obs_index, arc_id]
    """

def score_candidates(trip: dict) -> dict[int, list[dict]]:
    """Person 2. Model inference over the loaded trip.
    Input: the same dict load_trip returned.
    Returns: dict[obs_index, [{"arc_id": str, "p_match": float}]]
    MUST include candidate alternatives, not just the argmax.
    The trained model/artifacts MUST be loaded once at module import or first
    call - never retrained per request."""

def decode(trip: dict, scores: dict[int, list[dict]]) -> dict[int, str | None]:
    """Person 3. HMM / Viterbi decoding.
    Inputs: the trip dict from load_trip, and Person 2's scores.
    Returns: dict[obs_index, predicted arc_id] - None means unmatched.
    Must choose a globally plausible sequence (handle disconnected roads),
    not the per-point highest-scoring candidate."""
```

## Conventions

- Coordinates are `[lat, lon]` everywhere (Leaflet/Folium order).
- Observation indexes are consecutive integers per trip, timestamp order.
- The backend assembles continuous route stretches from consecutive predicted
  arcs, inserts decoder-reconstructed intermediate arcs when two consecutive
  predicted arcs are not adjacent, and never draws across unmatched runs
  (GPS gaps).

## Current status

The adapter (`backend/app/pipeline/real_pipeline.py`) validates the module at
startup and fails loudly (HTTP 503 with the missing function names) instead of
fabricating output. Until this module is supplied, the system runs in labelled
**mock mode** (`PATHSNAP_MODE=mock`) with synthetic data.
