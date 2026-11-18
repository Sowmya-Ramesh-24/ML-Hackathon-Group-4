"""Decode candidate road scores against a directed graph. Coordinates are lon, lat."""

from collections import defaultdict
from functools import lru_cache
from heapq import heappop, heappush

import numpy as np
import pandas as pd


def decode_trip(track, nodes, arcs, candidates, *, transition_scale_m=30.0,
                max_speed_mps=55.0, gap_seconds=60.0):
    """Return per-observation matches and connected route sections for one trip.

    track columns: longitude, latitude, time in seconds.
    arcs row index is arc_id and columns are start/end node indices.
    candidates columns: observation_index, arc_id, p_match.
    """
    track, nodes, arcs = np.asarray(track), np.asarray(nodes), np.asarray(arcs, dtype=int)
    if not len(track):
        return {"matches": [], "route_sections": []}

    center = track[:, :2].mean(axis=0)
    scale = 111195.0 * np.array([np.cos(np.deg2rad(center[1])), 1.0])
    gps = (track[:, :2] - center) * scale
    xy = (nodes[:, :2] - center) * scale
    starts, ends = arcs.T
    segments = xy[ends] - xy[starts]
    lengths = np.linalg.norm(segments, axis=1)
    adjacency = defaultdict(list)
    for arc, (start, end) in enumerate(arcs):
        adjacency[int(start)].append((int(end), arc, lengths[arc]))

    @lru_cache(maxsize=8192)
    def paths_from(source, limit):
        distances = {source: 0.0}
        predecessors = {}
        queue = [(0.0, source)]
        while queue:
            distance, node = heappop(queue)
            if distance != distances[node]:
                continue
            for nxt, arc, length in adjacency[node]:
                new = distance + length
                if new <= limit and new < distances.get(nxt, np.inf):
                    distances[nxt] = new
                    predecessors[nxt] = (node, arc)
                    heappush(queue, (new, nxt))
        return distances, predecessors

    def position(observation, arc):
        length = lengths[arc]
        if not length:
            return 0.0
        offset = np.dot(gps[observation] - xy[starts[arc]], segments[arc]) / length
        return float(np.clip(offset, 0, length))

    def travel(previous, current, pos_previous, pos_current, limit):
        if previous == current and pos_current >= pos_previous - 10:
            return max(0.0, pos_current - pos_previous), False
        distances, _ = paths_from(int(ends[previous]), limit)
        distance = lengths[previous] - pos_previous
        distance += distances.get(int(starts[current]), np.inf) + pos_current
        return distance, True

    prediction = [None] * len(track)
    sections = []
    block = []
    values = None

    def finish_block():
        if not block:
            return
        choice = int(np.argmax(values))
        chosen = []
        for observation, ids, back, offset in reversed(block):
            arc = int(ids[choice])
            prediction[observation] = arc
            chosen.append((observation, arc, offset[choice]))
            choice = int(back[choice])
        chosen.reverse()
        section = [chosen[0][1]]
        for (i, previous, ppos), (j, current, cpos) in zip(chosen, chosen[1:]):
            seconds = track[j, 2] - track[i, 2]
            limit = int(np.ceil(max(50, seconds * max_speed_mps) / 50) * 50)
            _, via_graph = travel(previous, current, ppos, cpos, limit)
            if via_graph:
                source, target = int(ends[previous]), int(starts[current])
                _, predecessors = paths_from(source, limit)
                bridges = []
                while target != source:
                    target, arc = predecessors[target]
                    bridges.append(arc)
                section.extend(reversed(bridges))
                section.append(current)
        sections.append(section)
        block.clear()

    groups = candidates.groupby("observation_index", sort=False)
    for i in range(len(track)):
        if i not in groups.indices:
            finish_block()
            continue
        frame = groups.get_group(i)
        ids = frame["arc_id"].to_numpy(dtype=int)
        if np.any((ids < 0) | (ids >= len(arcs))):
            raise ValueError(f"Invalid arc ID at observation {i}")
        scores = np.log(np.clip(frame["p_match"].to_numpy(dtype=float), 1e-8, 1))
        offsets = np.array([position(i, arc) for arc in ids])
        back = np.full(len(ids), -1)
        if block:
            j, previous_ids, _, previous_offsets = block[-1]
            seconds = track[i, 2] - track[j, 2]
            if not 0 < seconds <= gap_seconds:
                finish_block()
            else:
                displacement = np.linalg.norm(gps[i] - gps[j])
                budget = max(50, seconds * max_speed_mps)
                limit = int(np.ceil(budget / 50) * 50)
                next_values = np.full(len(ids), -np.inf)
                for k, current in enumerate(ids):
                    for m, previous in enumerate(previous_ids):
                        if not np.isfinite(values[m]):
                            continue
                        distance, _ = travel(previous, current, previous_offsets[m], offsets[k], limit)
                        if distance <= budget:
                            score = values[m] - abs(distance - displacement) / transition_scale_m + scores[k]
                            if score > next_values[k]:
                                next_values[k], back[k] = score, m
                if np.isfinite(next_values).any():
                    scores = next_values
                else:
                    finish_block()
        block.append((i, ids, back, offsets))
        values = scores
    finish_block()
    return {
        "matches": [{"observation_index": i, "arc_id": arc} for i, arc in enumerate(prediction)],
        "route_sections": sections,
    }
