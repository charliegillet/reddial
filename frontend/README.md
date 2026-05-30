# RedDial Dashboard

A voice-agent **threat console** for the RedDial offline harness — launch loopback
scans, read the vulnerability scorecard (grade, breach/leak rates, per-vector
breakdown, breach evidence), and browse the attack library.

Security-operations-console aesthetic: near-black field, phosphor-green / alert-red
accents, JetBrains Mono + IBM Plex Sans, scanline texture. All data shown is **FAKE**
(offline loopback against a mock); the console never places live calls.

## Run

```bash
# 1) start the control-plane API (from ../server)
cd ../server && uv run uvicorn api:app --port 8080

# 2) start the dashboard
cd ../frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api -> :8080)
```

Configure the API base with `VITE_API_BASE` (default `/api`, proxied to
`VITE_API_TARGET`, default `http://localhost:8080`).

## Build

```bash
npm run build        # -> dist/  (static; serve behind any web server / CDN)
```

## What it talks to

The FastAPI control plane (`server/api.py`): `GET /healthz`, `GET /attacks`,
`POST /scans`, `GET /scorecard/latest`. Offline-only — no live/PSTN path is exposed.
