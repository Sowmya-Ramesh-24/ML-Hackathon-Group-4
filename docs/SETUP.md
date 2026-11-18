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

## Switching to the real pipeline

```bash
export PATHSNAP_MODE=real
export PATHSNAP_TEAMMATES_MODULE=teammates_pipeline
python run.py
```

If the module or any required function is missing, the backend starts but the
matching endpoints return HTTP 503 naming exactly what is missing - it never
falls back to invented output silently.
