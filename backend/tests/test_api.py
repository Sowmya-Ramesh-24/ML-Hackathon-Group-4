"""Backend API tests - executed with pytest against the real FastAPI app.

Run from backend/:
    python -m pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PATHSNAP_MODE"] = "mock"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"


def test_list_trips_has_ten():
    r = client.get("/api/trips")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    assert len(body["trips"]) == 10
    for trip in body["trips"]:
        assert "trip_id" in trip and "num_observations" in trip
        # Ground truth must never leak through the trip listing.
        assert "reference" not in str(trip).lower()


def test_match_valid_trip():
    r = client.post("/api/match", json={"trip_id": "trip_01"})
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] is True
    assert body["num_observations"] > 0
    assert len(body["observations"]) == body["num_observations"]
    assert len(body["stretches"]) >= 1
    for st in body["stretches"]:
        assert len(st["geometry"]) >= 2
    # No reference/ground-truth geometry in the prediction response.
    assert "reference_geometry" not in body
    assert "reference" not in str(body["stretches"]).lower()


def test_match_unknown_trip_404():
    r = client.post("/api/match", json={"trip_id": "trip_99"})
    assert r.status_code == 404


def test_match_malformed_request_422():
    r = client.post("/api/match", json={"trip": 1})
    assert r.status_code == 422


def test_evaluate_before_prediction_409():
    r = client.post("/api/evaluate", json={"trip_id": "trip_05"})
    assert r.status_code == 409


def test_evaluate_after_prediction():
    assert client.post("/api/match", json={"trip_id": "trip_02"}).status_code == 200
    r = client.post("/api/evaluate", json={"trip_id": "trip_02"})
    assert r.status_code == 200
    body = r.json()
    m = body["metrics"]
    assert 0.0 <= m["top1_accuracy"] <= 1.0
    assert 0.0 <= m["candidate_recall"] <= 1.0
    assert 0.0 <= m["matched_fraction"] <= 1.0
    assert m["processing_time_ms"] >= 0
    assert body["reference_geometry"]  # present only AFTER prediction


def test_all_ten_trips_match_and_evaluate():
    trips = client.get("/api/trips").json()["trips"]
    assert len(trips) == 10
    for trip in trips:
        tid = trip["trip_id"]
        assert client.post("/api/match", json={"trip_id": tid}).status_code == 200, tid
        assert client.post("/api/evaluate", json={"trip_id": tid}).status_code == 200, tid


def test_gps_gap_trips_split_stretches():
    """Trips with a simulated GPS gap must produce a gap record and never a
    single polyline across the missing stretch."""
    found_gap = False
    for tid in ("trip_02", "trip_05", "trip_08"):
        body = client.post("/api/match", json={"trip_id": tid}).json()
        if body["gaps"]:
            found_gap = True
            assert len(body["stretches"]) >= 2
            assert body["unmatched_observations"]
            g = body["gaps"][0]
            assert g["before_obs"] > g["after_obs"]
    assert found_gap, "expected at least one mock trip with a GPS gap"


def test_folium_map_requires_prediction():
    # Fresh trip id not yet run in this session ordering; run then fetch.
    assert client.post("/api/match", json={"trip_id": "trip_03"}).status_code == 200
    r = client.get("/api/trips/trip_03/map")
    assert r.status_code == 200
    assert "folium" in r.text.lower()


def test_cors_header_present():
    r = client.options(
        "/api/health",
        headers={
            "Origin": "http://192.168.1.20:8000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "*"


def test_real_mode_without_module_reports_unavailable():
    """Real mode must fail loudly, never fabricate predictions."""
    from app.pipeline.real_pipeline import RealPipeline
    from app.pipeline.base import PipelineUnavailable

    try:
        RealPipeline("")
    except PipelineUnavailable as exc:
        assert "PATHSNAP_TEAMMATES_MODULE" in str(exc)
    else:
        raise AssertionError("RealPipeline('') should raise PipelineUnavailable")

    try:
        RealPipeline("module_that_does_not_exist_xyz")
    except PipelineUnavailable:
        pass
    else:
        raise AssertionError("Import of a missing module should raise PipelineUnavailable")
