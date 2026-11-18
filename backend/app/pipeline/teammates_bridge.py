"""PathSnap integration bridge - wires the team's actual artifacts into the
integration contract (docs/INTEGRATION_CONTRACT.md).

Nothing in this module re-implements a teammate's responsibility; it only
CONNECTS their work:

- Person 1 (data):   data/student_test/<trip>/<trip>.{track,nodes,arcs,route}
                     and data/candidates/student_test_candidates.csv /
                     student_test_references.csv (their generated candidates).
- Person 2 (model):  models/selected_pipeline.joblib - their tuned
                     HistGradientBoosting pipeline (see models/06 notebook).
                     Loaded once at first use, never retrained.
- Person 3 (HMM):    src/decoder.py - their Viterbi decoder, imported
                     verbatim and called with their expected inputs.

Activate with:
    PATHSNAP_MODE=real
    PATHSNAP_TEAMMATES_MODULE=app.pipeline.teammates_bridge
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "student_test"
CANDIDATES_CSV = REPO_ROOT / "data" / "candidates" / "student_test_candidates.csv"
REFERENCES_CSV = REPO_ROOT / "data" / "candidates" / "student_test_references.csv"
MODEL_PATH = REPO_ROOT / "models" / "selected_pipeline.joblib"
DECODER_PATH = REPO_ROOT / "src" / "decoder.py"

# Person 1's feature list (src/pathsnap_candidates.py FEATURES), the exact
# column order Person 2's model was trained on.
FEATURES = [
    "dist_m", "dist_min_m", "dist_rel_m", "rank_dist", "n_cands", "proj_frac",
    "arc_len_m", "dist_end_m", "head_diff_deg", "head_cos", "speed_mps",
    "moving", "dt_prev_s", "dist_prev_pt_m", "dist_next_pt_m", "has_reverse",
    "deg_from", "deg_to",
]

# trip_id -> raw arrays/frames needed by scoring and decoding.
_trip_cache: dict[str, dict] = {}


def _decoder_module():
    spec = importlib.util.spec_from_file_location("pathsnap_decoder", DECODER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import Person 3 decoder from {DECODER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _model():
    """Person 2's trained pipeline, loaded exactly once."""
    return joblib.load(MODEL_PATH)


@lru_cache(maxsize=1)
def _candidates_frame() -> pd.DataFrame:
    return pd.read_csv(CANDIDATES_CSV, dtype={"trip_id": str})


@lru_cache(maxsize=1)
def _references_frame() -> pd.DataFrame:
    return pd.read_csv(REFERENCES_CSV, dtype={"trip_id": str})


def _haversine_m(lon1, lat1, lon2, lat2) -> float:
    r = 6_371_008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def _load_raw(trip_id: str) -> dict:
    if trip_id in _trip_cache:
        return _trip_cache[trip_id]
    folder = DATA_DIR / trip_id
    track_path = folder / f"{trip_id}.track"
    if not track_path.exists():
        raise KeyError(trip_id)
    read = lambda suffix, dt: pd.read_csv(
        folder / f"{trip_id}.{suffix}", sep=r"\s+", header=None, dtype=dt
    ).to_numpy()
    track = read("track", np.float64)          # lon, lat, t(seconds)
    nodes = read("nodes", np.float64)          # lon, lat ; row = node_id
    arcs = read("arcs", np.int64)              # from_node, to_node ; row = arc_id
    route = read("route", np.int64).ravel()    # ordered reference arc_ids
    cand = _candidates_frame()
    cand = cand[cand.trip_id == trip_id].reset_index(drop=True)
    refs = _references_frame()
    refs = refs[refs.trip_id == trip_id]
    raw = {
        "track": track, "nodes": nodes, "arcs": arcs, "route": route,
        "candidates_df": cand, "references_df": refs,
    }
    _trip_cache[trip_id] = raw
    return raw


# -- Contract function 1 (Person 1 data) ------------------------------------

def list_trips() -> list[dict]:
    trips = []
    for folder in sorted(DATA_DIR.iterdir()):
        if not folder.is_dir():
            continue
        track = folder / f"{folder.name}.track"
        if not track.exists():
            continue
        n = sum(1 for _ in open(track))
        trips.append({
            "trip_id": folder.name,
            "num_observations": n,
            "description": f"Student-test trip {folder.name} (real data, team pipeline)",
        })
    return trips


# -- Contract function 2 (Person 1 data) ------------------------------------

def load_trip(trip_id: str) -> dict | None:
    try:
        raw = _load_raw(trip_id)
    except KeyError:
        return None
    track, nodes, arcs, route = raw["track"], raw["nodes"], raw["arcs"], raw["route"]

    observations = [
        {"index": i, "lat": float(row[1]), "lon": float(row[0]),
         "timestamp": f"{row[2]:.0f}s"}
        for i, row in enumerate(track)
    ]

    arc_map: dict[str, dict] = {}
    for arc_id, (fr, to) in enumerate(arcs):
        lon1, lat1 = nodes[fr]
        lon2, lat2 = nodes[to]
        arc_map[str(arc_id)] = {
            "arc_id": str(arc_id),
            "nodes": (int(fr), int(to)),
            "geometry": [[float(lat1), float(lon1)], [float(lat2), float(lon2)]],
            "length_m": _haversine_m(lon1, lat1, lon2, lat2),
        }

    cand = raw["candidates_df"]
    candidates = {
        int(obs): [str(a) for a in grp.arc_id]
        for obs, grp in cand.groupby("observation_index")
    }

    # Reference route geometry (server-side only; never leaves before prediction).
    reference_geometry: list[list[float]] = []
    for arc_id in route:
        fr, to = arcs[arc_id]
        start = [float(nodes[fr][1]), float(nodes[fr][0])]
        end = [float(nodes[to][1]), float(nodes[to][0])]
        if not reference_geometry or reference_geometry[-1] != start:
            reference_geometry.append(start)
        reference_geometry.append(end)

    obs_true_arcs = {
        int(r.observation_index): str(int(r.reference_arc_id))
        for r in raw["references_df"].itertuples()
        if pd.notna(r.reference_arc_id)
    }

    return {
        "trip_id": trip_id,
        "observations": observations,
        "arcs": arc_map,
        "candidates": candidates,
        "reference_geometry": reference_geometry,
        "reference_arc_ids": [str(a) for a in route],
        "obs_true_arcs": obs_true_arcs,
    }


# -- Contract function 3 (Person 2 model, real inference) -------------------

def score_candidates(raw_trip: dict) -> dict[int, list[dict]]:
    trip_id = raw_trip["trip_id"]
    cand = _load_raw(trip_id)["candidates_df"]
    if cand.empty:
        return {}
    model = _model()
    proba = model.predict_proba(cand[FEATURES])
    classes = list(model.classes_)
    p_match = proba[:, classes.index(1)] if 1 in classes else proba[:, -1]
    scored = cand.assign(p_match=p_match)
    return {
        int(obs): [
            {"arc_id": str(r.arc_id), "p_match": float(r.p_match)}
            for r in grp.itertuples()
        ]
        for obs, grp in scored.groupby("observation_index")
    }


# -- Contract function 4 (Person 3 decoder, called verbatim) -----------------

def decode(payload: dict, scores: dict[int, list[dict]]) -> dict[int, str | None]:
    trip_id = payload["trip_id"]
    raw = _load_raw(trip_id)
    rows = [
        {"observation_index": int(obs), "arc_id": int(s["arc_id"]),
         "p_match": float(s["p_match"])}
        for obs, cand_list in scores.items()
        for s in cand_list
    ]
    candidates = pd.DataFrame(rows, columns=["observation_index", "arc_id", "p_match"])
    result = _decoder_module().decode_trip(
        raw["track"], raw["nodes"], raw["arcs"], candidates
    )
    return {
        int(m["observation_index"]): (str(m["arc_id"]) if m["arc_id"] is not None else None)
        for m in result["matches"]
    }
