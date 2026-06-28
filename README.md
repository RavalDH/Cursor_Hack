# Mine Gas Safety

An offline early-warning system for underground mine gas. A FastAPI backend
classifies multi-gas sensor readings (CH4, CO, CO2, NO2, O2) per mine level,
flags a level that's *climbing* toward danger before it crosses the limit, and
serves a Reg 854 procedure + citation for any alert. A TanStack/Vite dashboard
polls it live and speaks the alert aloud.

Everything runs locally — no internet, no cloud, no LLM. Safety answers are
fixed templates grounded in local regulation text, so they never hallucinate.

## Layout

- `backend/` — FastAPI app, gas/trend logic, MQTT + simulator, offline historian
- `frontend/` — TanStack Start + Vite dashboard

## Backend

```bash
cd backend
pip install -r requirements.txt
USE_MQTT=false uvicorn main:app --reload   # Windows: set USE_MQTT=false first
```

`USE_MQTT=false` drives levels from an internal timer, so no MQTT broker is
needed. Serves on `http://localhost:8000`:

- `GET /zones` (alias `/levels`) — per-level status, gas values, fan, actions
- `GET /alert` — highest-severity level needing action, with procedure + citation
- `POST /ask` — free-text safety question, answered from local Reg 854 docs
- `GET /health` — liveness snapshot

With a real broker, leave `USE_MQTT=true` and run `python simulator.py` in a
second terminal to publish readings.

## Frontend

```bash
cd frontend
bun install
bun dev
```

Polls the backend at `http://localhost:8000` every 2s and renders each level's
status, fan, and actions. Watch `1200L` cycle red -> clearing -> all-clear.

## Offline

No network calls anywhere. Readings and events are appended to dated JSONL files
under `backend/logs/`, which survive restarts. The only external dependency is
an optional local MQTT broker, and `USE_MQTT=false` removes even that.
