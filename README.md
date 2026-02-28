# Smart Road Safety System

Python backend + React frontend application implementing:

1. Safety Score & Color-Coded Roads (1-5, green/yellow/red)
2. Safest Route vs Fastest Route with ETA, distance, and safety comparison
3. Smart Tracking with inactivity alert and emergency sharing flow
4. Emergency SOS one-tap action with live location link and timestamp
5. Guardian live tracking, destination reached notification, inactivity alerts

## Tech Stack

- Backend: FastAPI (Python)
- Frontend: React + Vite + Leaflet
- Containers: Docker + Docker Compose

## Project Structure

- `backend/` FastAPI API and safety services
- `frontend/` React UI
- `docker-compose.yml` full app orchestration

## Safety Score Logic

Road safety score uses:

- India-only accident/risk data from `backend/data/accidents_sample.csv` (sample safety points)
- Time-of-day adjustment: night adds risk
- Traffic density input: slider in UI or route API-derived fallback

Scores map to categories:

- `4-5` -> Safe (green)
- `3` -> Moderate (yellow)
- `1-2` -> Risk-prone (red)

## API Endpoints

- `POST /roads/safety`
- `POST /routes/compare`
- `POST /tracking/start`
- `POST /tracking/update`
- `POST /tracking/check-inactivity`
- `POST /sos/trigger`
- `POST /guardian/share`
- `GET /health`

## Run With Docker

1. Copy environment variables:

```bash
cp .env.example .env
```

2. Build and start:

```bash
docker compose up --build
```

3. Open:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Notes

- If `MAPBOX_TOKEN` is provided, route data can use Mapbox traffic-aware directions.
- Without token, backend returns deterministic fallback route values for development/testing.
- Guardian and emergency notifications are sent by email (SMTP) when tracking starts, destination is reached, inactivity is detected, or SOS is triggered.
- Configure these env vars for email delivery:
  - `SMTP_HOST` (example: `smtp.gmail.com`)
  - `SMTP_PORT` (usually `587` for TLS)
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD` (for Gmail use an App Password)
  - `SMTP_FROM_EMAIL`
  - `SMTP_USE_TLS` (`true` or `false`)
