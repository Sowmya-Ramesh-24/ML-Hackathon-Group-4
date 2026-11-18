# PathSnap - Setup

## Backend (Laptop 1)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # optional; defaults work out of the box
python run.py             # serves API + frontend on 0.0.0.0:8000
```

Swagger UI: `http://localhost:8000/docs`

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PATHSNAP_MODE` | `mock` | `mock` = labelled synthetic pipeline; `real` = teammates' module |
| `PATHSNAP_TEAMMATES_MODULE` | (empty) | Import name or `.py` path of the teammates' integration module (real mode) |
| `PATHSNAP_DATA_DIR` | `./data` | Server-side datasets/reference routes (never served) |
| `PATHSNAP_CORS_ORIGINS` | `*` | Allowed origins (fine for a closed demo LAN; restrict otherwise) |
| `PATHSNAP_RETURN_REFERENCE_GEOMETRY` | `true` | Return reference geometry in evaluate responses (post-prediction only) |
| `PATHSNAP_HOST` / `PATHSNAP_PORT` | `0.0.0.0` / `8000` | Bind address |

## Frontend (Laptop 2 or same machine)

The backend already serves the frontend at `/`. From another laptop, open:

```
http://<laptop1-ip>:8000/?api=http://<laptop1-ip>:8000
```

(When served by the backend itself, same-origin is used automatically; the
`?api=` parameter makes the target explicit and is remembered in the browser.)

To serve the frontend separately instead (any static server):

```bash
cd frontend
python -m http.server 8080
# open http://localhost:8080/?api=http://<laptop1-ip>:8000
```

No build step, no npm: plain HTML/JS + Leaflet from CDN.

## Running the real pipeline (team mode)

The integration bridge `backend/app/pipeline/teammates_bridge.py` wires the
team's actual artifacts into the backend without re-implementing anyone's
work:

- Person 1 data: `data/student_test/<trip>/<trip>.{track,nodes,arcs,route}`
  plus `data/candidates/student_test_candidates.csv` and
  `student_test_references.csv`
- Person 2 model: `models/selected_pipeline.joblib` (tuned
  HistGradientBoosting pipeline, loaded once)
- Person 3 decoder: `src/decoder.py` (imported and called verbatim)

Before starting, make sure these are present in the repo root:

1. `data/student_test/` - extract the student_test zip into `data/` so the
   path is `data/student_test/<trip_id>/<trip_id>.track` etc.
2. `models/selected_pipeline.joblib` - the trained model file shared by
   Person 2.

Then:

```bash
cd backend
pip install -r requirements.txt   # adds numpy/pandas/scikit-learn/joblib

# Linux/macOS:
PATHSNAP_MODE=real PATHSNAP_TEAMMATES_MODULE=app.pipeline.teammates_bridge python run.py

# Windows PowerShell:
$env:PATHSNAP_MODE='real'; $env:PATHSNAP_TEAMMATES_MODULE='app.pipeline.teammates_bridge'; python run.py
```

The scikit-learn version is pinned to the one the model was trained with, so
the pickle loads cleanly.

Verified against the team's own outputs: bridge scores match the shared
candidate-scores CSV exactly (max abs diff ~1e-16), decoder output matches
the shared decoder JSON on every observation, and combined Top-1 across all
ten student-test trips is 88.1% (19,160 points) vs the team's reported
88.07%.

### Generic adapter (if the team swaps in a different module)

```bash
export PATHSNAP_MODE=real
export PATHSNAP_TEAMMATES_MODULE=teammates_pipeline   # import name or .py path
python run.py
```

If the module or any required function is missing, the backend starts but the
matching endpoints return HTTP 503 naming exactly what is missing - it never
falls back to invented output silently.
