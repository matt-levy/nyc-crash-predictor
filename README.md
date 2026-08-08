# NYC Street Risk

NYC Street Risk is a map-based web application that combines historical NYC collision records with current NYC DOT traffic-camera observations. It produces a simple, explainable **street-risk indicator** for selected camera locations.

The application is designed as a decision-support and awareness tool. A score describes relative street interaction conditions; it is **not** the probability of a crash and does not predict individual collisions.

## What the application does

- Displays analyzed NYC traffic-camera locations on an interactive map.
- Retrieves live camera metadata and current snapshots from NYC DOT.
- Uses a Roboflow Workflow to count visible cars, trucks, buses, motorcycles, bicycles, and pedestrians.
- Finds simple spatial proximity indicators between motor vehicles and vulnerable road users in a single image.
- Calculates historical risk from nearby NYC Open Data collision records.
- Combines historical and current conditions into a deterministic score from 0 to 100.
- Shows the factors that contributed to each score.
- Optionally asks Gemini to explain the already-calculated evidence in plain language. Gemini cannot change the score.

## How it works

```text
NYC collision records ──> Historical risk ───────────────┐
                                                         ├──> Street-risk score ──> Map
NYC DOT snapshot ──> Roboflow ──> Current conditions ───┘
                                      │
                                      └──> Spatial proximity indicators

Normalized evidence ──> Gemini explanation (optional)
```

The deterministic combined score is:

```text
70% historical risk + 30% current-condition score
```

Scores are categorized as:

| Score | Level |
| --- | --- |
| 0-33 | Low |
| 34-66 | Moderate |
| 67-100 | High |

Current conditions receive capped points for visible vehicles, pedestrians, bicycles, large vehicles, motorcycles, and spatial proximity indicators. The complete rules are kept in replaceable service modules:

- `app/services/risk_analysis.py` - historical scoring
- `app/services/combined_risk.py` - current and combined scoring
- `app/services/spatial_analysis.py` - single-image proximity analysis

## Important limitations

- The application analyzes one still image at a time, not video or movement.
- Proximity in an image is not proof of a near miss, collision, unsafe behavior, or future collision.
- Camera angle, visibility, weather, occlusion, and model errors can affect detections.
- The score is a relative collision-risk indicator, not crash probability.
- Camera snapshots are proxied or analyzed temporarily and are not permanently stored.
- Gemini explains normalized evidence only. It does not receive camera images or raw detections and does not calculate the score.

## Technology

- FastAPI and Pydantic backend
- React, TypeScript, Vite, and MapLibre frontend
- NYC Open Data collision records
- NYC DOT traffic-camera catalog and snapshots
- Roboflow `inference-sdk`
- Google Gemini API for optional explanations
- Docker and Google Cloud Run

## Local development

### Requirements

- Python 3.11 or newer
- Node.js and npm
- A Roboflow API key for camera analysis
- A Gemini API key only if AI explanations are needed

### Start the backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

$env:ROBOFLOW_API_KEY = "your-roboflow-key"
$env:GEMINI_API_KEY = "your-gemini-key"

uvicorn app.main:app --host 0.0.0.0 --port 8080
```

The application reads secrets from environment variables. It does not currently load `.env` automatically. Never commit `.env`; it is excluded by both `.gitignore` and `.dockerignore`.

Open the API documentation at [http://localhost:8080/docs](http://localhost:8080/docs).

### Start the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite forwards API requests to the backend on port 8080.

For a production frontend build:

```powershell
cd frontend
npm run build
```

FastAPI serves the compiled `frontend/dist` application at `/` when the directory exists.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ROBOFLOW_API_KEY` | For camera analysis | None | Authenticates the Roboflow Workflow |
| `GEMINI_API_KEY` | For explanations only | None | Authenticates optional Gemini explanations |
| `NYC_OPEN_DATA_APP_TOKEN` | No | None | Raises NYC Open Data rate limits |
| `MAP_ANALYSIS_CONCURRENCY` | No | `5` | Concurrent camera analyses; constrained to 1-20 |
| `HISTORICAL_RISK_CACHE_TTL_SECONDS` | No | `21600` | Historical-risk cache lifetime |
| `CAMERA_RISK_CACHE_TTL_SECONDS` | No | `300` | Full camera-risk cache lifetime |
| `CAMERA_CATALOG_TIMEOUT_SECONDS` | No | `60` | NYC DOT catalog request timeout |
| `PORT` | No | `8080` | HTTP port; supplied automatically by Cloud Run |

## API overview

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Service health check |
| `GET` | `/crashes/nearby` | Nearby historical collision records |
| `GET` | `/risk` | Historical risk for coordinates |
| `GET` | `/cameras` | NYC DOT camera metadata |
| `GET` | `/cameras/{camera_id}` | One camera's metadata |
| `GET` | `/cameras/{camera_id}/snapshot` | Proxy the current camera image |
| `GET` | `/cameras/{camera_id}/analyze` | Roboflow observations and spatial indicators |
| `GET` | `/cameras/{camera_id}/risk` | Historical, current, spatial, and combined risk |
| `GET` | `/cameras/{camera_id}/risk/explain` | Risk response with an optional Gemini explanation |
| `POST` | `/map/refresh` | Analyze cameras and refresh the in-memory heat map |
| `GET` | `/map/risk` | Read the latest heat-map result without new analysis |

Example PowerShell requests:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod -Method Post 'http://localhost:8080/map/refresh?area=Manhattan&limit=5'
Invoke-RestMethod http://localhost:8080/map/risk
Invoke-RestMethod http://localhost:8080/cameras
```

Camera IDs come from `/cameras` and may change with the upstream catalog.

## Caching and performance

Historical results are cached for six hours by default. Full per-camera results are cached for five minutes, allowing map selections and Gemini explanations to reuse recent analysis. A map refresh requests a current camera observation while reusing cached historical data.

The map cache is intentionally process-local for this MVP. A Cloud Run instance restart loses the cached map, and multiple instances do not share cache state.

## Tests

Run the backend test suite from the repository root:

```powershell
python -m pytest -q
```

Build-check the frontend:

```powershell
cd frontend
npm run build
```

## Docker

```powershell
docker build -t nyc-street-risk .
docker run --rm -p 8080:8080 `
  -e ROBOFLOW_API_KEY=$env:ROBOFLOW_API_KEY `
  -e GEMINI_API_KEY=$env:GEMINI_API_KEY `
  nyc-street-risk
```

The multi-stage image uses Node.js only to build the frontend. The final image runs one FastAPI server that serves both the API and compiled React application.

## Google Cloud Run deployment

The current deployment uses project `cloudrun-hack26nyc-4303`, region `us-east1`, and service `nyc-accident-predictor`.

From Google Cloud Shell:

```bash
gcloud builds submit \
  --project=cloudrun-hack26nyc-4303 \
  --tag=us-east1-docker.pkg.dev/cloudrun-hack26nyc-4303/nyc-collision-risk/nyc-collision-risk:latest \
  .

gcloud run deploy nyc-accident-predictor \
  --project=cloudrun-hack26nyc-4303 \
  --region=us-east1 \
  --image=us-east1-docker.pkg.dev/cloudrun-hack26nyc-4303/nyc-collision-risk/nyc-collision-risk:latest \
  --allow-unauthenticated \
  --timeout=300 \
  --min-instances=1
```

Configure `ROBOFLOW_API_KEY` and `GEMINI_API_KEY` through Cloud Run using Secret Manager. Do not place secret values in deployment commands or commit them to Git.

Cloud Run services are regional. Deploying the same service name in another region creates another service rather than moving the existing one.

### View Cloud Run logs

Read recent logs:

```bash
gcloud run services logs read nyc-accident-predictor \
  --project=cloudrun-hack26nyc-4303 \
  --region=us-east1 \
  --limit=100
```

Stream logs when the installed gcloud version supports the beta command:

```bash
gcloud beta run services logs tail nyc-accident-predictor \
  --project=cloudrun-hack26nyc-4303 \
  --region=us-east1
```

Searchable application events include `camera_catalog_fetch_*`, `nyc_crash_query_*`, `roboflow_workflow_*`, `map_camera_analysis_*`, `gemini_explanation_*`, `analysis_cache_*`, and `http_request_completed`.

## Future improvements

- Store map and analysis caches in shared persistent storage.
- Add scheduled background refreshes instead of refreshing only on demand.
- Improve handling when a Roboflow result omits image dimensions.
- Add time-series analysis using multiple snapshots rather than interpreting motion from one image.
- Add monitoring and alerting for upstream NYC DOT, Roboflow, and Gemini failures.
