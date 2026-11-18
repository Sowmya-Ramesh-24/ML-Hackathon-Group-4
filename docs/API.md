# PathSnap - API Reference

Base URL: `http://<host>:8000`. Interactive docs: `/docs` (Swagger UI).
All coordinates are `[lat, lon]`.

## GET /api/health
Service and pipeline status.
```json
{ "status": "ok", "mode": "mock", "pipeline": "mock-synthetic-grid (...)", "version": "1.0.0" }
```
`status` is `degraded` when real mode is selected but the teammates' module
failed validation; `pipeline` then names the problem.

## GET /api/trips
List selectable trips. Metadata only - never ground truth.
```json
{ "mode": "mock", "count": 10,
  "trips": [ {"trip_id": "trip_01", "num_observations": 66, "description": "..."} ] }
```
Errors: 503 when the pipeline is unavailable.

## POST /api/match
Body: `{ "trip_id": "trip_01" }`
Runs the full pipeline (model scoring + HMM/Viterbi decode) and returns:
```json
{
  "trip_id": "trip_01", "mode": "mock", "mock": true,
  "pipeline": "mock-synthetic-grid (...)",
  "num_observations": 66,
  "observations": [ {"index": 0, "lat": 12.97, "lon": 77.59, "timestamp": "..."} ],
  "stretches": [ {"stretch_id": 0, "arc_ids": ["h_2_1", "h_2_2"],
                  "reconstructed_arc_ids": [], "from_obs": 0, "to_obs": 5,
                  "geometry": [[12.97, 77.59], ...]} ],
  "unmatched_observations": [30, 31],
  "gaps": [ {"after_obs": 29, "before_obs": 32, "description": "..."} ],
  "processing_time_ms": 12.4,
  "note": "MOCK pipeline output - ..."
}
```
Each stretch is a separate polyline; stretches never span a GPS gap.
Errors: 404 unknown trip, 422 malformed body, 503 pipeline unavailable.

## GET /api/match/{trip_id}
Returns the cached last prediction for the trip.
Errors: 409 when no prediction has been run yet.

## POST /api/evaluate
Body: `{ "trip_id": "trip_01" }`
**Prediction must exist first** (409 otherwise) - ground truth is never
exposed before prediction. Metrics are computed server-side:
```json
{ "trip_id": "trip_01", "mode": "mock", "mock": true,
  "metrics": { "top1_accuracy": 0.95, "candidate_recall": 1.0,
               "matched_fraction": 0.97, "num_predicted_stretches": 3,
               "num_reference_stretches": 1, "continuity_ratio": 0.333,
               "processing_time_ms": 12.4 },
  "reference_geometry": [[12.97, 77.59], ...],
  "note": "Metrics computed server-side against server-side reference data." }
```
`reference_geometry` is present only when `PATHSNAP_RETURN_REFERENCE_GEOMETRY=true`
and a reference exists. Metrics that cannot be computed from available data
are returned as `null`, never invented.

## GET /api/trips/{trip_id}/map
Standalone Folium HTML map of the last prediction (GPS points, per-stretch
polylines, gap markers). Errors: 409 before prediction.
