# PathSnap - Architecture

```
                          Laptop 2 (evaluator)
                        +----------------------+
                        |  Browser             |
                        |  frontend/ (Leaflet) |
                        +----------+-----------+
                                   | HTTP (LAN IP of Laptop 1)
                                   v
                          Laptop 1 (server)
+----------------------------------------------------------------------------+
| FastAPI backend (backend/)                                                 |
|                                                                            |
|  /api/health   /api/trips   /api/match   /api/evaluate   /api/trips/*/map  |
|        |              |           |             |                          |
|        v              v           v             v                          |
|  +--------------------------------------------------------------+          |
|  | pipeline/service.py  - run state, ground-truth custody        |         |
|  +----------------------+---------------------------------------+          |
|                         | MatchingPipeline interface (base.py)             |
|          +--------------+---------------+                                  |
|          v                              v                                  |
|  pipeline/real_pipeline.py      pipeline/mock_pipeline.py                  |
|  (PATHSNAP_MODE=real)           (PATHSNAP_MODE=mock, labelled)             |
|          |                                                               |
|          v                                                               |
|  Teammates' module (docs/INTEGRATION_CONTRACT.md):                         |
|    Person 1  data/road graph  ->  list_trips, load_trip                    |
|    Person 2  ML model         ->  score_candidates (p_match)               |
|    Person 3  HMM/Viterbi      ->  decode                                   |
+----------------------------------------------------------------------------+
```

## Information flow

Person 1 (GPS observations, candidates, road graph)
  + Person 2 (`p_match` for every candidate arc at every observation)
  -> Person 3 (HMM/Viterbi decode to predicted `arc_id` per observation)
  -> FastAPI assembles continuous stretches (with reconstructed intermediate
     arcs, gaps preserved)
  -> frontend draws each stretch as its own polyline.

## Ground-truth custody

Evaluator reference routes live only on the server (`TripData`). They are
never included in `/api/trips` or `/api/match` responses. `/api/evaluate`
returns 409 until a prediction exists for the trip, computes metrics
server-side, and only then (optionally) returns the reference geometry for
visual comparison.
