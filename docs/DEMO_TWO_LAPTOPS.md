# PathSnap - Two-Laptop Demonstration

## Roles

- **Laptop 1 (server):** runs the FastAPI backend, loads the trained model,
  performs route matching, serves the API over the local network.
- **Laptop 2 (evaluator):** opens the frontend in a browser, connects to
  Laptop 1's backend via its LAN IP, selects trips, views predicted routes.

Both laptops must be on the same network (same Wi-Fi / hotspot).

## Step 1 - Laptop 1: find its LAN IP

- Linux/macOS: `ip addr show` or `ifconfig` - look for `192.168.x.x` /
  `10.x.x.x` on the Wi-Fi interface.
- Windows: `ipconfig` - "IPv4 Address" under the Wi-Fi adapter.

Example result used below: `192.168.1.10`.

## Step 2 - Laptop 1: start the backend

```bash
cd backend
source .venv/bin/activate
python run.py          # binds 0.0.0.0:8000 - reachable from the LAN
```

`0.0.0.0` is required; binding `127.0.0.1` would only accept local
connections.

## Step 3 - Laptop 1: allow the port through the firewall

- Linux (ufw): `sudo ufw allow 8000/tcp`
- macOS: System Settings -> Network -> Firewall -> allow Python.
- Windows: allow "Python" / port 8000 when Windows Defender Firewall prompts,
  or add an inbound rule for TCP 8000.

## Step 4 - Laptop 2: open the frontend

```
http://192.168.1.10:8000/?api=http://192.168.1.10:8000
```

The header should read **Backend: connected**. Pick any of the 10 evaluator
trips, press **Run map matching**, then **Evaluate (server-side)**.

`localhost` on Laptop 2 means Laptop 2 - it will NOT reach Laptop 1. Always
use Laptop 1's LAN IP.

## Step 5 - verify connectivity from Laptop 2 (optional)

```bash
curl http://192.168.1.10:8000/api/health
```

A JSON response with `"status": "ok"` proves the API path works.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Backend: unreachable" on Laptop 2 | Wrong IP; backend not running; firewall blocking 8000; laptops on different networks (phone hotspots sometimes isolate clients - try the other laptop's hotspot) |
| Browser loads page but API calls fail (CORS) | `PATHSNAP_CORS_ORIGINS` on Laptop 1 does not include the origin. Default `*` avoids this on a closed LAN |
| Trip runs but shows MOCK badge | Expected until `PATHSNAP_MODE=real` + the teammates' module are set |
| 503 from `/api/trips` in real mode | The teammates' module failed validation; the error message names the missing function(s) |
| 409 from `/api/evaluate` | Working as designed - run matching first; evaluation never precedes prediction |
