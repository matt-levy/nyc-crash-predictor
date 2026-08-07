# NYC Historical Collision Risk API

A small FastAPI backend that summarizes conditions associated with elevated collision risk from nearby historical NYC crash reports. It does **not** predict whether a crash will occur.

## Local setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open Swagger UI at http://localhost:8080/docs. An optional `NYC_OPEN_DATA_APP_TOKEN` environment variable raises Socrata rate limits. Set the required Roboflow secret only in the environment:

```powershell
$env:ROBOFLOW_API_KEY = "your-key"
$env:GEMINI_API_KEY = "your-key"
```

### Frontend development

Run FastAPI on port 8080 as above. In a second terminal, run Vite; its development proxy forwards API requests to FastAPI:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. A production frontend build can be checked with `npm run build`. FastAPI serves `frontend/dist` at `/` when that build exists.

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod 'http://localhost:8080/crashes/nearby?latitude=40.794668&longitude=-73.971788&radius_meters=250&days=365'
Invoke-RestMethod 'http://localhost:8080/risk?latitude=40.794668&longitude=-73.971788&radius_meters=250&days=365'
Invoke-RestMethod http://localhost:8080/cameras
Invoke-RestMethod http://localhost:8080/cameras/769a2e94-5bbc-4a03-86a7-39d3a70213f7
Invoke-WebRequest http://localhost:8080/cameras/769a2e94-5bbc-4a03-86a7-39d3a70213f7/snapshot -OutFile snapshot.jpg
Invoke-RestMethod http://localhost:8080/cameras/769a2e94-5bbc-4a03-86a7-39d3a70213f7/analyze
Invoke-RestMethod http://localhost:8080/cameras/769a2e94-5bbc-4a03-86a7-39d3a70213f7/risk
Invoke-RestMethod http://localhost:8080/cameras/769a2e94-5bbc-4a03-86a7-39d3a70213f7/risk/explain
Invoke-RestMethod -Method Post 'http://localhost:8080/map/refresh?area=Manhattan&limit=10'
Invoke-RestMethod http://localhost:8080/map/risk
pytest
```

The camera analysis passes the current NYC DOT image URL directly to the Roboflow Workflow and returns normalized counts, detections, and single-image spatial proximity indicators. Camera risk is a deterministic street-risk indicator: 70% historical score plus 30% current-condition score. Spatial indicators can add capped points to current conditions. They are not near-miss detection, crash probability, or prediction. Camera snapshots are not stored. Historical scoring is documented in `app/services/risk_analysis.py`; current and combined scoring is documented in `app/services/combined_risk.py`; proximity rules are documented in `app/services/spatial_analysis.py`.

The optional `/cameras/{camera_id}/risk/explain` endpoint sends only normalized evidence to Gemini for a concise structured explanation. Gemini does not receive camera images or raw detections and cannot modify the deterministic score. The regular risk endpoint has no Gemini dependency.

`POST /map/refresh` analyzes selected online cameras with bounded concurrency and stores lightweight heat-map points in memory; `GET /map/risk` only reads that cache and never invokes downstream analysis. Set `MAP_ANALYSIS_CONCURRENCY` to control parallel work (default 5, constrained to 1–20). Gemini is not used during map refresh.

Historical risk results are cached for 6 hours by default, and full per-camera results are cached for 5 minutes so map selections and Gemini explanations can reuse the latest analysis. Configure these process-local TTLs with `HISTORICAL_RISK_CACHE_TTL_SECONDS` and `CAMERA_RISK_CACHE_TTL_SECONDS`. Map refresh always forces a new camera observation while reusing historical data. `CAMERA_CATALOG_TIMEOUT_SECONDS` defaults to 60 seconds; catalog requests retry and fall back to the last in-process catalog.

The map cache is intentionally ephemeral for the hackathon MVP. A Cloud Run instance restart loses its cached result, and multiple Cloud Run instances do not share cache state. Persistent shared storage can be introduced later if required.

## Docker and Cloud Run

```powershell
docker build -t nyc-collision-risk .
docker run --rm -p 8080:8080 -e PORT=8080 nyc-collision-risk
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/nyc-collision-risk
gcloud run deploy nyc-collision-risk --image REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/nyc-collision-risk --region REGION --allow-unauthenticated
```

Cloud Run supplies `PORT`; the container binds Uvicorn to `0.0.0.0` and defaults to 8080.
The multi-stage image uses Node only to compile the React frontend. The final image contains one FastAPI server, which serves both the API and compiled UI. Configure `ROBOFLOW_API_KEY`, `GEMINI_API_KEY`, and optional `MAP_ANALYSIS_CONCURRENCY` as Cloud Run environment variables or secrets.
