# Wind Intelligence — Wind Forecast Performance

A data analytics dashboard for understanding national wind generation forecast accuracy in Great Britain. The application compares Elexon wind generation forecasts with actual generation for January 2026, helping energy procurement teams assess forecast errors before delivery.

## Features

- Actual vs forecast wind generation chart
- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- Forecast bias
- Hourly interval explorer with filtering and sorting
- Forecast publication time and decision-cutoff checks
- Python backend with a React dashboard
- Docker-based local deployment

## Data Sources

The application uses national-level wind generation data from Elexon's BMRS API.

### Actual generation — FUELHH

Source: https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream

- Filters for wind generation (`fuelType = WIND`)
- Uses January 2026 settlement data
- Retrieves 30-minute actual generation intervals
- Aggregates two half-hourly records into an hourly average for comparison with hourly forecasts

### Forecast generation — WINDFOR

Source: https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream

- Uses forecast generation and publication timestamps
- Selects the latest eligible forecast for each delivery hour
- Excludes forecasts published after the assumed decision cutoff

## Forecast Selection Assumption

The assignment does not specify an exact procurement decision cutoff. This implementation uses **11:00 UTC on the day before delivery** as a working assumption.

For each delivery hour, the latest available forecast published at or before this cutoff is selected. This assumption should be confirmed with the intended procurement workflow before using the results for operational decisions.

All timestamps are handled in UTC.

## Performance Metrics

The current analysis covers January 2026.

| Metric | Result | Interpretation |
|---|---:|---|
| MAE | 2,122.81 | Average absolute forecast error |
| RMSE | 2,616.69 | Gives greater weight to larger errors |
| Bias | 1,840.30 | Positive values indicate average overforecasting |

Error is calculated as:

`Forecast generation − Actual generation`

Actual generation is represented by the hourly average of the two underlying half-hourly records.

These metrics are based on the stated cutoff and aggregation assumptions. They should be interpreted in the context of those assumptions.

## Validation

The following local validation checks have passed:

- Analysis validation: 10/10 checks
- Actual data validation: 5/5 checks
- Forecast selection validation: 7/7 checks

Validation includes hourly coverage, duplicate intervals, missing values, forecast publication cutoffs, error calculations, metric recalculation, chronological continuity, and comparison against raw actual and forecast records.

## Technology Stack

**Frontend**
- React
- TypeScript
- Vite
- Recharts
- Lucide React
- Nginx for production serving and API proxying

**Backend**
- Python
- FastAPI
- Uvicorn
- Pandas
- HTTPX

**Deployment and tooling**
- Docker
- Docker Compose
- Git and GitHub

## Project Structure

```text
gridbricks-wind-intelligence/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── validate_analysis.py
│   ├── validate_actuals.py
│   ├── validate_forecasts.py
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## Run Locally

### Prerequisites

- Python 3.11+
- Node.js and npm
- Docker Desktop (for containerised execution)

### Option 1: Run without Docker

**Start the backend**

From the project root, create and activate a Python virtual environment if you have not already done so. Install the backend dependencies:

```bash
python -m pip install -r backend/requirements.txt
```

Start the API:

```bash
python -m uvicorn main:app --reload --app-dir backend
```

The API will run at `http://127.0.0.1:8000`.

**Start the frontend**

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL displayed by Vite in the terminal.

### Option 2: Run with Docker

Ensure Docker Desktop is running. From the project root, execute:

```bash
docker compose up --build
```

Open the dashboard at:

`http://localhost:8080`

Check backend health through the frontend proxy:

`http://localhost:8080/api/health`

Stop the containers with:

```bash
docker compose down
```

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `/` | API status |
| `/health` | Health check |
| `/actuals` | Actual wind generation data |
| `/forecasts/sample` | Forecast sample |
| `/analysis` | January 2026 forecast accuracy analysis |

When running locally without Docker, the API base URL is `http://127.0.0.1:8000`.

## Limitations

- The 11:00 UTC forecast cutoff is an assumption, not a confirmed requirement.
- Half-hourly actual generation is averaged to hourly resolution to match the forecast series.
- Results depend on the source data returned by Elexon's API.
- This is an analytical prototype, not an automated procurement or trading system.
- The metrics should be reassessed if the decision cutoff or aggregation method changes.


## AI Tool Disclosure

AI tools, including ChatGPT, were used to assist with development, debugging, and documentation. The project implementation and results were reviewed by the author.

## Deployment

- **Demo video:** https://www.youtube.com/watch?v=RVnp8P1cjKw
- **Live Dashboard:** https://wind-analytics-frontend.vercel.app/
- **Backend API:** https://wind-analytics-7k2m.vercel.app/
- **Health Check:** https://wind-analytics-7k2m.vercel.app/health
- **Analysis Endpoint:** https://wind-analytics-7k2m.vercel.app/analysis
- **Source Code:** https://github.com/subhaliAR21/Wind-Analytics-7k2m

The live dashboard displays forecast performance metrics, wind generation data, and visualizations for January 2026.

The backend provides API endpoints for health checks and forecast analysis.
