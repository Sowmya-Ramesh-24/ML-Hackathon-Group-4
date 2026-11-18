# PathSnap - Testing

## Automated backend tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Covers: health, trip listing (10 trips, no ground-truth leak), valid match,
unknown trip (404), malformed body (422), evaluate-before-predict (409),
evaluate-after-predict (metric ranges, reference revealed only after
prediction), all 10 trips end-to-end, Folium map, CORS preflight, and
real-mode-without-module failing loudly instead of fabricating.

## Manual smoke test

```bash
python run.py &
curl -s localhost:8000/api/health
curl -s localhost:8000/api/trips | head
curl -s -X POST localhost:8000/api/match -H 'Content-Type: application/json' \
     -d '{"trip_id": "trip_01"}' | head
curl -s -X POST localhost:8000/api/evaluate -H 'Content-Type: application/json' \
     -d '{"trip_id": "trip_01"}' | head
```

## Frontend checklist

- [ ] Dashboard loads, backend status shows "connected"
- [ ] MOCK badge visible in mock mode
- [ ] All 10 trips listed; selecting one enables the run button
- [ ] Running a trip draws GPS points + predicted stretches; legend appears
- [ ] Trips with a GPS gap show the orange gap marker and no line across it
- [ ] Evaluate populates the metrics table and adds the dashed reference route
- [ ] Errors surface as toasts (e.g. backend stopped)

## Ground-truth protection check

1. `GET /api/trips` and `POST /api/match` responses contain no reference data.
2. `POST /api/evaluate` before any prediction returns 409.
3. Only after prediction does evaluate return reference geometry (and only
   when the server config permits it).

## Two-laptop check

From Laptop 2: `curl http://<laptop1-ip>:8000/api/health` must return JSON.
See docs/DEMO_TWO_LAPTOPS.md.
