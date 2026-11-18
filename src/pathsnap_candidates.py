"""PathSnap - candidate generation, feature engineering and (training-only) labelling.

generate_candidates()  : track + network -> one row per (GPS point, candidate arc) with features.
                         Uses NO route / label -> identical code is reused at inference (API).
label_points()         : track + network + reference route -> estimated true route position/arc per GPS point
                         (monotone Viterbi alignment of the track onto the ordered reference route).
build_trip_table()     : generate_candidates + labels (0/1) for one trip.
"""
import numpy as np, pandas as pd
from scipy.spatial import cKDTree

R_EARTH = 6_371_008.8
FEATURES = ["dist_m", "dist_min_m", "dist_rel_m", "rank_dist", "n_cands", "proj_frac", "arc_len_m",
            "dist_end_m", "head_diff_deg", "head_cos", "speed_mps", "moving", "dt_prev_s",
            "dist_prev_pt_m", "dist_next_pt_m", "has_reverse", "deg_from", "deg_to"]


def make_proj(lon0, lat0):
    kx = np.radians(1.0) * R_EARTH * np.cos(np.radians(lat0)); ky = np.radians(1.0) * R_EARTH
    return lambda lon, lat: np.column_stack(((np.asarray(lon) - lon0) * kx, (np.asarray(lat) - lat0) * ky))


def seg_dist(P, A, B):
    """Point->segment distance and projection fraction (all arrays (n,2), metres)."""
    AB = B - A; L2 = (AB ** 2).sum(1); L2s = np.where(L2 > 0, L2, 1.0)
    t = np.clip(((P - A) * AB).sum(1) / L2s, 0, 1); t = np.where(L2 > 0, t, 0.0)
    return np.linalg.norm(P - (A + t[:, None] * AB), axis=1), t


def _arc_index(nxy, arcs, step=5.0):
    """KD-tree over points sampled every `step` m along the given arcs. Returns (tree, arc_of_sample)."""
    A, B = nxy[arcs[:, 0]], nxy[arcs[:, 1]]
    L = np.linalg.norm(B - A, axis=1); ns = np.maximum(1, np.ceil(L / step).astype(int)) + 1
    aid = np.repeat(np.arange(len(arcs)), ns)
    off = np.cumsum(ns) - ns
    f = (np.arange(len(aid)) - np.repeat(off, ns)) / np.repeat(ns - 1, ns)
    pts = A[aid] + (B - A)[aid] * f[:, None]
    return cKDTree(pts), aid


def _bearing(d):  # radians, atan2(dx, dy) -> compass-like
    return np.arctan2(d[:, 0], d[:, 1])


def motion_features(xy, t, k=2):
    """Smoothed heading (rad), speed (m/s), dt_prev (s) per GPS point from points i-k..i+k."""
    n = len(xy); i0 = np.maximum(np.arange(n) - k, 0); i1 = np.minimum(np.arange(n) + k, n - 1)
    d = xy[i1] - xy[i0]; dt = np.maximum(t[i1] - t[i0], 1e-6)
    speed = np.linalg.norm(d, axis=1) / dt
    dtp = np.r_[0.0, np.diff(t)]
    return _bearing(d), speed, dtp


def generate_candidates_from_files(track_path, nodes_path, arcs_path, **kw):
    """Inference entry point (FastAPI): needs ONLY .track, .nodes, .arcs (no route, no labels)."""
    rd = lambda p, dt: pd.read_csv(p, sep=r"\s+", header=None, dtype=dt).to_numpy()
    return generate_candidates(rd(track_path, np.float64), rd(nodes_path, np.float64), rd(arcs_path, np.int64), **kw)


def generate_candidates(track, nodes, arcs, radius=60.0, max_k=25, min_k=3, move_thr=1.0):
    """observation_index = 0-based row number in the original .track file.
    Candidate set per GPS point = arcs within `radius` m; if fewer than `min_k`, the `min_k` nearest arcs
    are used instead; at most `max_k` nearest are kept. Returns DataFrame (observation_index, arc_id, FEATURES...)."""
    track = np.asarray(track, float); arcs = np.asarray(arcs, np.int64)
    proj = make_proj(track[:, 0].mean(), track[:, 1].mean())
    xy = proj(track[:, 0], track[:, 1]); nxy = proj(nodes[:, 0], nodes[:, 1]); t = track[:, 2]
    n = len(xy); buf = radius + 100.0
    lo, hi = xy.min(0) - buf, xy.max(0) + buf
    A_all, B_all = nxy[arcs[:, 0]], nxy[arcs[:, 1]]
    keep = np.where(~((np.maximum(A_all, B_all) < lo).any(1) | (np.minimum(A_all, B_all) > hi).any(1)))[0]  # arcs near the trip
    if len(keep) == 0: return pd.DataFrame(columns=["observation_index", "arc_id"] + FEATURES)
    tree, saml = _arc_index(nxy, arcs[keep])
    reach = radius + 3.0
    lists = tree.query_ball_point(xy, reach)
    pi, ai = [], []
    for i, l in enumerate(lists):
        if l:
            u = np.unique(saml[l]); pi.append(np.full(len(u), i)); ai.append(u)
    if not pi: return pd.DataFrame(columns=["observation_index", "arc_id"] + FEATURES)
    pi, ai = np.concatenate(pi), keep[np.concatenate(ai)]
    P = xy[pi]; A, B = nxy[arcs[ai, 0]], nxy[arcs[ai, 1]]
    d, tf = seg_dist(P, A, B)
    df = pd.DataFrame({"observation_index": pi, "arc_id": ai, "dist_m": d, "proj_frac": tf})
    df = df[df.dist_m <= radius]
    # points with fewer than min_k in-radius arcs -> add nearest arcs (k-NN fallback, bounded by 4*radius)
    cnt = np.bincount(df.observation_index.values, minlength=n); need = np.where(cnt < min_k)[0]
    if len(need):
        kk = min(40, len(saml)); dd, ii = tree.query(xy[need], k=kk)
        ex_p, ex_a = [], []
        for r, i in enumerate(need):
            u = pd.unique(saml[ii[r]])[: min_k * 3]; ex_p.append(np.full(len(u), i)); ex_a.append(keep[u])
        ex_p, ex_a = np.concatenate(ex_p), np.concatenate(ex_a)
        d2, t2 = seg_dist(xy[ex_p], nxy[arcs[ex_a, 0]], nxy[arcs[ex_a, 1]])
        ex = pd.DataFrame({"observation_index": ex_p, "arc_id": ex_a, "dist_m": d2, "proj_frac": t2})
        df = pd.concat([df, ex]).drop_duplicates(["observation_index", "arc_id"])
        df = df.sort_values(["observation_index", "dist_m"]); df["_r"] = df.groupby("observation_index").cumcount()
        df = df[(df._r < min_k) | (df.dist_m <= radius)].drop(columns="_r")
    df = df.sort_values(["observation_index", "dist_m", "arc_id"]).reset_index(drop=True)
    g = df.groupby("observation_index").dist_m
    df["rank_dist"] = g.cumcount(); df = df[df.rank_dist < max_k].reset_index(drop=True)
    df["n_cands"] = df.groupby("observation_index").dist_m.transform("size")
    df["dist_min_m"] = df.groupby("observation_index").dist_m.transform("min"); df["dist_rel_m"] = df.dist_m - df.dist_min_m
    pi, ai = df.observation_index.values, df.arc_id.values
    A, B = nxy[arcs[ai, 0]], nxy[arcs[ai, 1]]; AB = B - A
    df["arc_len_m"] = np.linalg.norm(AB, axis=1)
    df["dist_end_m"] = np.minimum(np.linalg.norm(xy[pi] - A, axis=1), np.linalg.norm(xy[pi] - B, axis=1))
    hd, sp, dtp = motion_features(xy, t)
    ab = _bearing(AB); diff = np.abs((hd[pi] - ab + np.pi) % (2 * np.pi) - np.pi)
    df["head_diff_deg"] = np.degrees(diff); df["head_cos"] = np.cos(diff)
    df["speed_mps"] = sp[pi]; df["moving"] = (sp[pi] > move_thr).astype(np.int8); df["dt_prev_s"] = dtp[pi]
    df.loc[df.moving == 0, ["head_diff_deg", "head_cos"]] = [90.0, 0.0]      # heading undefined when parked
    # neighbour-point consistency: distance of previous / next GPS point to the same arc
    for nm, sh in (("dist_prev_pt_m", -1), ("dist_next_pt_m", 1)):
        j = np.clip(pi + sh, 0, n - 1); df[nm] = seg_dist(xy[j], A, B)[0]
    # topology
    fr, to = arcs[:, 0].astype(np.int64), arcs[:, 1].astype(np.int64); N = len(nodes)
    rev = set((fr * N + to).tolist()); df["has_reverse"] = np.fromiter(((int(b) * N + int(a)) in rev for a, b in arcs[ai]), np.int8, len(ai))
    deg = np.bincount(np.r_[fr, to], minlength=N)
    df["deg_from"] = deg[arcs[ai, 0]]; df["deg_to"] = deg[arcs[ai, 1]]
    return df[["observation_index", "arc_id"] + FEATURES]


def align_reference(track, nodes, arcs, route, label_radius=150.0, back_pen=20.0, skip_pen=1.0, certain_m=50.0):
    """Estimate, for every GPS point, which element of the ordered reference route it belongs to.
    Monotone Viterbi: state = route position j; emission = point->arc distance (m);
    transition j->j' costs skip_pen*(j'-j-1) if forward, 0 if same, back_pen*(j-j') if backwards.
    Returns DataFrame(observation_index, route_pos, reference_arc_id, ref_dist_m, ref_certain);
    ref_certain = aligned arc is within `certain_m` m of the GPS point (else reference is treated as uncertain)."""
    track = np.asarray(track, float); route = np.asarray(route, np.int64); arcs = np.asarray(arcs, np.int64)
    proj = make_proj(track[:, 0].mean(), track[:, 1].mean())
    xy = proj(track[:, 0], track[:, 1]); nxy = proj(nodes[:, 0], nodes[:, 1]); n = len(xy)
    tree, saml = _arc_index(nxy, arcs[route], step=5.0)           # saml = route position
    lists = tree.query_ball_point(xy, label_radius + 3.0)
    S_pos, S_cost = [], []
    for i, l in enumerate(lists):
        if not l:
            _, ii = tree.query(xy[i], k=min(30, len(saml))); l = np.atleast_1d(ii)
        pos = np.unique(saml[l]); a = nxy[arcs[route[pos], 0]]; b = nxy[arcs[route[pos], 1]]
        S_pos.append(pos); S_cost.append(seg_dist(np.repeat(xy[i][None], len(pos), 0), a, b)[0])
    bp = [None] * n; cost_prev = S_cost[0].copy()
    for i in range(1, n):
        pp, pc = S_pos[i - 1], cost_prev; cp = S_pos[i]
        dj = cp[None, :] - pp[:, None]                       # (prev, cur)
        trans = np.where(dj >= 0, skip_pen * np.maximum(dj - 1, 0), back_pen * (-dj))
        tot = pc[:, None] + trans; arg = tot.argmin(0)
        cost_prev = tot[arg, np.arange(len(cp))] + S_cost[i]; bp[i] = arg
    k = int(cost_prev.argmin()); idx = np.empty(n, int); idx[-1] = k
    for i in range(n - 1, 0, -1): k = int(bp[i][k]); idx[i - 1] = k
    rp = np.array([S_pos[i][idx[i]] for i in range(n)]); td = np.array([S_cost[i][idx[i]] for i in range(n)])
    return pd.DataFrame({"observation_index": np.arange(n), "route_pos": rp, "reference_arc_id": route[rp],
                         "ref_dist_m": td, "ref_certain": td <= certain_m})


def build_trip_table(track, nodes, arcs, route, radius=60.0, max_k=25, min_k=3, certain_m=50.0):
    """Training/scoring helper: candidates (route-free) + separate reference alignment -> 0/1 `label`.
    Returns (candidate table incl. label, reference table incl. blank reference_arc_id where uncertain)."""
    cand = generate_candidates(track, nodes, arcs, radius, max_k, min_k)
    ref = align_reference(track, nodes, arcs, route, certain_m=certain_m)
    cand = cand.merge(ref[["observation_index", "reference_arc_id"]], on="observation_index", how="left")
    cand["label"] = (cand.arc_id == cand.reference_arc_id).astype(np.int8)
    ref["reference_arc_id"] = ref.reference_arc_id.astype("Int64").where(ref.ref_certain)   # blank when uncertain
    return cand.drop(columns="reference_arc_id"), ref
