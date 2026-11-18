"""MOCK pipeline - synthetic data only, clearly labelled.

This module exists so Person 4's backend/frontend can be built, tested and
demonstrated while Persons 1-3 finish their components. Every API response
produced from this pipeline carries mock=true and the UI shows a MOCK banner.

Nothing here is a real prediction: the "model" is a distance-based scoring
function with noise and the "decoder" is a small Viterbi over a synthetic
street grid. When the teammates' module is available, set PATHSNAP_MODE=real
and this file is bypassed entirely.
"""
from __future__ import annotations

import math
import random
import time
from collections import deque

from .base import DecodeResult, MatchingPipeline, TripData

# Synthetic grid around central Bengaluru (mock geography only).
BASE_LAT, BASE_LON = 12.9716, 77.5946
GRID = 6  # GRID x GRID intersections
STEP = 0.0022  # ~240 m between intersections
GPS_NOISE_DEG = 0.00012  # ~13 m of synthetic GPS noise
MATCH_THRESHOLD = 0.12  # below this emission score an observation is "unmatched"
NUM_TRIPS = 10


def _node(r: int, c: int) -> tuple[float, float]:
    return (BASE_LAT + r * STEP, BASE_LON + c * STEP)


def _build_arcs() -> dict[str, dict]:
    """Grid streets: horizontal arcs h_r_c and vertical arcs v_r_c."""
    arcs: dict[str, dict] = {}
    for r in range(GRID):
        for c in range(GRID):
            if c + 1 < GRID:
                a, b = _node(r, c), _node(r, c + 1)
                arcs[f"h_{r}_{c}"] = {
                    "arc_id": f"h_{r}_{c}",
                    "nodes": ((r, c), (r, c + 1)),
                    "geometry": [[a[0], a[1]], [b[0], b[1]]],
                    "length_m": STEP * 111_000,
                }
            if r + 1 < GRID:
                a, b = _node(r, c), _node(r + 1, c)
                arcs[f"v_{r}_{c}"] = {
                    "arc_id": f"v_{r}_{c}",
                    "nodes": ((r, c), (r + 1, c)),
                    "geometry": [[a[0], a[1]], [b[0], b[1]]],
                    "length_m": STEP * 111_000,
                }
    return arcs


def _point_seg_dist_m(p: tuple[float, float], a: list[float], b: list[float]) -> float:
    """Approximate point-to-segment distance in metres (equirectangular)."""
    lat_scale = 111_000.0
    lon_scale = 111_000.0 * math.cos(math.radians(BASE_LAT))
    px, py = p[1] * lon_scale, p[0] * lat_scale
    ax, ay = a[1] * lon_scale, a[0] * lat_scale
    bx, by = b[1] * lon_scale, b[0] * lat_scale
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _walk(rng: random.Random, length: int) -> list[tuple[int, int]]:
    """Random walk on the grid; returns the visited nodes (length edges)."""
    r = rng.randrange(1, GRID - 1)
    c = rng.randrange(1, GRID - 1)
    path = [(r, c)]
    for _ in range(length):
        moves = []
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < GRID and 0 <= nc < GRID and (nr, nc) != path[-1]:
                moves.append((nr, nc))
        if not moves:
            break
        r, c = rng.choice(moves)
        path.append((r, c))
    return path


def _arc_between(a: tuple[int, int], b: tuple[int, int]) -> str:
    if a[0] == b[0]:
        return f"h_{a[0]}_{min(a[1], b[1])}"
    return f"v_{min(a[0], b[0])}_{a[1]}"


def _neighbors(node: tuple[int, int]) -> list[tuple[int, int]]:
    r, c = node
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < GRID and 0 <= nc < GRID:
            out.append((nr, nc))
    return out


def _bfs_path(start, goal, neighbors=None) -> list | None:
    """BFS shortest path over an arbitrary node graph. `neighbors` defaults
    to the mock grid's 4-connectivity; the real pipeline passes an adjacency
    built from the trip's actual road-network arcs."""
    if neighbors is None:
        neighbors = _neighbors
    if start == goal:
        return [start]
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in neighbors(cur):
            if nxt not in prev:
                prev[nxt] = cur
                if nxt == goal:
                    path = [nxt]
                    while path[-1] is not None:
                        path.append(prev[path[-1]])
                    return [n for n in reversed(path[:-1])]
                q.append(nxt)
    return None


class MockPipeline(MatchingPipeline):
    """Labelled synthetic pipeline. NOT real model output."""

    label = "mock-synthetic-grid (Person 4 placeholder, not teammate output)"
    is_mock = True

    def __init__(self) -> None:
        self._arcs = _build_arcs()
        self._trips: dict[str, TripData] = {}
        for i in range(1, NUM_TRIPS + 1):
            trip_id = f"trip_{i:02d}"
            self._trips[trip_id] = self._generate(trip_id, seed=1000 + i)

    # -- data generation ------------------------------------------------

    def _generate(self, trip_id: str, seed: int) -> TripData:
        rng = random.Random(seed)
        path = _walk(rng, rng.randrange(18, 30))
        true_arcs = [_arc_between(path[i], path[i + 1]) for i in range(len(path) - 1)]

        observations: list[dict] = []
        obs_true_arc: list[str] = []
        idx = 0
        base_ts = 1_700_000_000
        for arc_id, (na, nb) in zip(true_arcs, zip(path, path[1:])):
            la, loa = _node(*na)
            lb, lob = _node(*nb)
            for k in range(3):  # 3 samples per edge
                t = (k + 0.5) / 3
                lat = la + (lb - la) * t + rng.gauss(0, GPS_NOISE_DEG)
                lon = loa + (lob - loa) * t + rng.gauss(0, GPS_NOISE_DEG)
                observations.append(
                    {
                        "index": idx,
                        "lat": lat,
                        "lon": lon,
                        "timestamp": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(base_ts + idx * 5)
                        ),
                    }
                )
                obs_true_arc.append(arc_id)
                idx += 1

        # Candidates + mock model scores for each observation.
        # Scores are unnormalized exp(-distance/25) * jitter: the nearest arc
        # typically scores 0.5-0.9, distant arcs approach 0 - this lets the
        # decoder flag low-confidence observations as unmatched.
        def score_candidates_for(ob):
            dists = []
            for arc_id, arc in self._arcs.items():
                d = _point_seg_dist_m((ob["lat"], ob["lon"]), arc["geometry"][0], arc["geometry"][1])
                dists.append((d, arc_id))
            dists.sort()
            cand = [arc_id for _, arc_id in dists[:4]]
            return cand, {
                arc_id: round(math.exp(-d / 25.0) * rng.uniform(0.7, 1.0), 4)
                for d, arc_id in dists[:4]
            }

        candidates: dict[int, list[str]] = {}
        scores: dict[int, list[dict]] = {}
        for ob, true_arc in zip(observations, obs_true_arc):
            cand, cand_scores = score_candidates_for(ob)
            if true_arc not in cand:  # keep the truth reachable ~always in mock
                cand[-1] = true_arc
                cand_scores[true_arc] = round(math.exp(-8.0) * rng.uniform(0.7, 1.0), 4)
            candidates[ob["index"]] = cand
            scores[ob["index"]] = [
                {"arc_id": a, "p_match": cand_scores[a]} for a in cand
            ]

        # Simulate a GPS gap in every third trip: four consecutive observations
        # lose all nearby candidates (their scores collapse below the match
        # threshold), so the decoder leaves them unmatched and the stretch
        # builder opens a gap instead of drawing across it.
        if seed % 3 == 0 and len(observations) > 12:
            start = rng.randrange(4, len(observations) - 8)
            far_arcs = rng.sample(sorted(self._arcs), 4)
            for ob in observations[start : start + 4]:
                candidates[ob["index"]] = far_arcs
                scores[ob["index"]] = [
                    {"arc_id": a, "p_match": round(rng.uniform(0.001, 0.02), 4)}
                    for a in far_arcs
                ]

        reference_geometry: list[list[float]] = []
        for n in path:
            la, lo = _node(*n)
            reference_geometry.append([la, lo])

        obs_true_arcs = {ob["index"]: t for ob, t in zip(observations, obs_true_arc)}

        return TripData(
            trip_id=trip_id,
            observations=observations,
            arcs={k: {kk: v[kk] for kk in ("arc_id", "geometry", "length_m")} for k, v in self._arcs.items()},
            candidates=candidates,
            scores=scores,
            reference_geometry=reference_geometry,
            reference_arc_ids=true_arcs,
            obs_true_arcs=obs_true_arcs,
        )

    # -- MatchingPipeline API ---------------------------------------------

    def list_trips(self) -> list[dict]:
        return [
            {
                "trip_id": t.trip_id,
                "num_observations": len(t.observations),
                "description": f"Synthetic grid trip {t.trip_id} (mock)",
            }
            for t in self._trips.values()
        ]

    def load_trip(self, trip_id: str) -> TripData:
        if trip_id not in self._trips:
            raise KeyError(trip_id)
        return self._trips[trip_id]

    # -- mock decoder: a small Viterbi over the candidate arcs -----------

    def decode(self, trip: TripData) -> DecodeResult:
        started = time.perf_counter()
        obs = trip.observations
        predictions: dict[int, str | None] = {}

        # Viterbi. Emission = p_match from the mock "model"; transition
        # penalty grows with graph distance between consecutive arcs.
        prev_scores: dict[str, float] = {}
        all_scores: dict[int, dict[str, float]] = {}
        backpointers: dict[int, dict[str, str | None]] = {}
        last_matched: int | None = None
        for ob in obs:
            i = ob["index"]
            cand_scores = {s["arc_id"]: s["p_match"] for s in trip.scores[i]}
            if not cand_scores or max(cand_scores.values()) < MATCH_THRESHOLD:
                predictions[i] = None
                prev_scores = {}
                continue
            cur: dict[str, float] = {}
            back: dict[str, str | None] = {}
            for arc_id, p in cand_scores.items():
                emit = math.log(max(p, 1e-6))
                if not prev_scores:
                    cur[arc_id] = emit
                    back[arc_id] = None
                else:
                    best_prev, best_val = None, -1e18
                    for pa, pv in prev_scores.items():
                        pen = 0.0 if pa == arc_id else -1.5 * self._arc_distance(pa, arc_id)
                        if pv + pen > best_val:
                            best_val, best_prev = pv + pen, pa
                    cur[arc_id] = best_val + emit
                    back[arc_id] = best_prev
            prev_scores = cur
            all_scores[i] = cur
            backpointers[i] = back
            last_matched = i

        # Backtrace each contiguous matched segment separately (Viterbi
        # restarts after unmatched observations, so chains cannot cross them).
        matched_idx = sorted(all_scores)
        segments: list[list[int]] = []
        for i in matched_idx:
            if segments and i == segments[-1][-1] + 1:
                segments[-1].append(i)
            else:
                segments.append([i])
        for seg in segments:
            arc: str | None = max(all_scores[seg[-1]], key=all_scores[seg[-1]].get)
            for i in reversed(seg):
                if arc is None or arc not in all_scores[i]:
                    arc = max(all_scores[i], key=all_scores[i].get)
                predictions[i] = arc
                arc = backpointers[i].get(arc)

        elapsed = (time.perf_counter() - started) * 1000
        return DecodeResult(predictions=predictions, processing_time_ms=round(elapsed, 2))

    def _arc_distance(self, a: str, b: str) -> int:
        na = set(self._arcs[a]["nodes"])
        nb = set(self._arcs[b]["nodes"])
        if na & nb:
            return 1
        best = 99
        for x in na:
            for y in nb:
                d = abs(x[0] - y[0]) + abs(x[1] - y[1])
                best = min(best, d)
        return best

    # -- stretch assembly (shared with the service layer) -----------------

    def build_stretches(self, trip: TripData, predictions: dict[int, str | None]) -> tuple[list[dict], list[int], list[dict]]:
        """Group consecutive matched observations into drawable stretches.

        Reconstructed intermediate arcs (BFS shortest path between two
        consecutive predicted arcs that are not adjacent) are included and
        flagged. Gaps (runs of unmatched observations) break stretches; a
        stretch polyline never spans a gap.
        """
        stretches: list[dict] = []
        unmatched: list[int] = []
        gaps: list[dict] = []
        matched_obs = [ob for ob in trip.observations if predictions.get(ob["index"])]

        for ob in trip.observations:
            if not predictions.get(ob["index"]):
                unmatched.append(ob["index"])

        # Record gaps between consecutive matched observations.
        for prev_ob, next_ob in zip(matched_obs, matched_obs[1:]):
            if next_ob["index"] - prev_ob["index"] > 1:
                gaps.append(
                    {
                        "after_obs": prev_ob["index"],
                        "before_obs": next_ob["index"],
                        "description": "Unmatched observations - no route drawn across this gap",
                    }
                )

        sid = 0
        cur: dict | None = None
        for ob in matched_obs:
            arc_id = predictions[ob["index"]]
            assert arc_id is not None
            if cur is None:
                cur = self._new_stretch(sid, arc_id, ob)
                continue
            last_arc = cur["arc_ids"][-1]
            gap_between = any(g["after_obs"] == cur["to_obs"] and g["before_obs"] == ob["index"] for g in gaps)
            if gap_between:
                stretches.append(cur)
                sid += 1
                cur = self._new_stretch(sid, arc_id, ob)
                continue
            if arc_id == last_arc:
                cur["to_obs"] = ob["index"]
                continue
            # Arc change: reconstruct intermediate arcs if not adjacent.
            intermediates = self._intermediate_arcs(last_arc, arc_id)
            cur["arc_ids"].extend(intermediates + [arc_id])
            cur["reconstructed_arc_ids"].extend(intermediates)
            cur["to_obs"] = ob["index"]

        if cur is not None:
            stretches.append(cur)

        for st in stretches:
            st["geometry"] = self._stitch_geometry(st["arc_ids"], trip.arcs)
        return stretches, unmatched, gaps

    def _new_stretch(self, sid: int, arc_id: str, ob: dict) -> dict:
        return {
            "stretch_id": sid,
            "arc_ids": [arc_id],
            "reconstructed_arc_ids": [],
            "from_obs": ob["index"],
            "to_obs": ob["index"],
        }

    def _intermediate_arcs(self, a: str, b: str) -> list[str]:
        na = self._arcs[a]["nodes"]
        nb = self._arcs[b]["nodes"]
        # Graph hooks: default to the mock grid; the real pipeline installs
        # adjacency/arc lookups built from the trip's actual arcs.
        neighbors = getattr(self, "_graph_neighbors", None) or _neighbors
        arc_between = getattr(self, "_graph_arc_between", None) or _arc_between
        best_path: list | None = None
        for x in na:
            for y in nb:
                p = _bfs_path(x, y, neighbors)
                if p is not None and (best_path is None or len(p) < len(best_path)):
                    best_path = p
        if not best_path or len(best_path) < 3:
            return []  # adjacent or identical - nothing to reconstruct
        mids = []
        for u, v in zip(best_path[1:-2], best_path[2:-1]):
            arc = arc_between(u, v)
            if arc is None:
                return []  # no real arc on this edge - leave unreconstructed
            mids.append(arc)
        return mids

    @staticmethod
    def _stitch_geometry(arc_ids: list[str], arcs: dict[str, dict]) -> list[list[float]]:
        coords: list[list[float]] = []
        for aid in arc_ids:
            seg = arcs[aid]["geometry"]
            if coords and coords[-1] == seg[0]:
                coords.extend(seg[1:])
            elif coords and coords[-1] == seg[-1]:
                coords.extend(reversed(seg[:-1]))
            else:
                coords.extend(seg)
        return coords
