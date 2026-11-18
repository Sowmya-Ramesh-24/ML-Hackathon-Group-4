# PathSnap - Intelligent GPS Map Matching

PathSnap matches noisy GPS traces to a road network. A trained machine
learning model scores candidate road arcs for each GPS point, a Hidden Markov
Model (Viterbi) decoder turns those scores into a globally plausible route,
and a FastAPI backend plus interactive web UI run and evaluate the whole
pipeline live.

Built by Group 4 for the ML Hackathon.

## What each part does

| Component | Where | What it is |
|---|---|---|
| Candidate generation | `src/pathsnap_candidates.py`, `data/candidates/` | For every GPS observation, finds nearby road arcs and builds an 18-feature candidate set with reference labels |
| ML model | `models/` (notebooks 01-06, `Metrics/`) | Five classifiers trained and compared; the tuned HistGradientBoosting pipeline won and is exported as `selected_pipeline.joblib` |
| HMM / Viterbi decoder | `src/decoder.py` | Picks the most plausible arc sequence per trip instead of per-point argmax |
| Backend + UI + integration | `backend/`, `frontend/` | FastAPI service that loads the team's data, model and decoder, serves a Leaflet UI, and computes accuracy metrics server-side |

## Results (student test set, 10 trips)

| Stage | Top-1 accuracy | Route continuity |
|---|---|---|
| Classifier only (per-point argmax) | 87.40% | 93.39% |
| Full pipeline (classifier + Viterbi) | 88.07% | 97.85% |

Numbers over 19,133 GPS points. Re-running the full pipeline through the
backend API reproduces them: 88.08% Top-1 over 19,160 scored points, with
per-trip accuracy from 64.6% (hardest trip) to 99.2% (easiest trip).

## Repository layout

```
backend/    FastAPI app: API, pipeline adapter, server-side evaluation, tests
frontend/   Plain HTML/JS + Leaflet UI (no build step)
src/        Candidate generation + Viterbi decoder (team pipeline code)
models/     Training notebooks 01-06, metrics CSVs, trained model
data/       Candidate CSVs (in repo) and student_test raw trips (see below)
docs/       SETUP.md (full setup guide), INTEGRATION_CONTRACT.md
```

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/Sowmya-Ramesh-24/ML-Hackathon-Group-4.git
cd ML-Hackathon-Group-4/backend
pip install -r requirements.txt
```

`scikit-learn` is pinned to 1.6.1, the version the trained model was built
with, so the model file loads cleanly.

### Two files are not in the repo

The raw test-trip geometry and the trained model binary are shared
separately (size). Place them like this:

1. Extract the `student_test` zip into `data/` so the path is
   `data/student_test/00000000/00000000.track` (etc. for all 10 trips).
2. Copy the trained model to `models/selected_pipeline.joblib`.

## Running

### Real mode (the team's actual pipeline)

Linux/macOS:

```bash
cd backend
PATHSNAP_MODE=real PATHSNAP_TEAMMATES_MODULE=app.pipeline.teammates_bridge python run.py
```

Windows PowerShell:

```powershell
cd backend
$env:PATHSNAP_MODE='real'; $env:PATHSNAP_TEAMMATES_MODULE='app.pipeline.teammates_bridge'; python run.py
```

Then open http://localhost:8000 - pick a trip, press **Run map matching**,
then **Evaluate** to reveal the reference route and metrics.

Optional: `$env:PATHSNAP_PORT='8002'` (or `PATHSNAP_PORT=8002`) changes the
port if 8000 is busy.

### Mock mode (labelled synthetic demo)

```bash
cd backend
python run.py
```

No setup needed. The UI shows a loud MOCK badge: synthetic grid data, not
model output. Useful for trying the UI without the dataset.

## API

Swagger UI (self-documenting): http://localhost:8000/docs

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Server status and which pipeline is active (`real` or `mock`) |
| `GET /api/trips` | Lists the available trips |
| `POST /api/match` | Runs matching for a trip, returns predicted route stretches |
| `GET /api/match/{trip_id}` | Re-reads an existing prediction |
| `POST /api/evaluate` | Server-side metrics vs the reference route (only after a prediction) |

Ground truth stays on the server: reference geometry is only returned by
`/api/evaluate`, and only after a prediction exists for that trip.

## The UI

The backend serves the frontend at `/` (same origin). From a second laptop
on the same network, open:

```
http://<server-ip>:8000/?api=http://<server-ip>:8000
```

The map shows GPS observations (red), the predicted route (blue), the
reference route after evaluation (green), and gaps where no route is drawn
(orange). The Results panel shows Top-1 accuracy, matched fraction,
candidate recall, route stretches, continuity and processing time.

## Testing

```bash
cd backend
pytest
```

12 tests cover the API contract, pipeline behaviour, mock labelling and
evaluation rules.

## Team

Group 4: candidate generation and data, model training and tuning,
HMM/Viterbi decoding, and backend/frontend integration.
