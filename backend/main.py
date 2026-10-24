from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Wind Intelligence API",
    description="UK national wind generation forecast accuracy analysis",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets"

ACTUALS_URL = f"{BASE_URL}/FUELHH/stream"
FORECASTS_URL = f"{BASE_URL}/WINDFOR/stream"

START_DATE = "2026-01-01"
END_DATE = "2026-01-31"

# Working assumption only: the assignment does not specify a decision cutoff.
DECISION_CUTOFF_HOUR_UTC = 11


def fetch_records(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch records from an Elexon API endpoint."""
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            # Accommodate common API response wrappers.
            for key in ("data", "results", "items"):
                if isinstance(data.get(key), list):
                    return data[key]

        raise ValueError("The API response was not in the expected list format.")

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to retrieve data from Elexon: {exc}",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected response from Elexon: {exc}",
        ) from exc


def fetch_actual_records() -> list[dict[str, Any]]:
    """Retrieve national wind actual generation for January 2026."""
    return fetch_records(
        ACTUALS_URL,
        {
            "settlementDateFrom": START_DATE,
            "settlementDateTo": END_DATE,
            "fuelType": "WIND",
        },
    )


def fetch_forecast_records() -> list[dict[str, Any]]:
    """Retrieve forecasts published around the January delivery period."""
    return fetch_records(
        FORECASTS_URL,
        {
            "publishDateTimeFrom": "2025-12-31T00:00:00Z",
            "publishDateTimeTo": "2026-02-01T00:00:00Z",
        },
    )


def records_to_dataframe(
    records: list[dict[str, Any]],
    required_columns: list[str],
) -> pd.DataFrame:
    """Convert API records into a dataframe and validate required fields."""
    if not records:
        return pd.DataFrame(columns=required_columns)

    df = pd.DataFrame(records)

    missing_columns = [
        column for column in required_columns if column not in df.columns
    ]
    if missing_columns:
        raise HTTPException(
            status_code=502,
            detail=f"Elexon response is missing required fields: {missing_columns}",
        )

    return df


def parse_utc(series: pd.Series) -> pd.Series:
    """Parse timestamp values consistently as UTC."""
    return pd.to_datetime(series, utc=True, errors="coerce")


def prepare_actuals(records: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Filter January 2026 actuals and aggregate two half-hour intervals
    into an hourly average for comparison with hourly forecasts.
    """
    df = records_to_dataframe(records, ["startTime", "generation"])

    if df.empty:
        return pd.DataFrame(columns=["delivery_hour", "actual_generation"])

    df["startTime"] = parse_utc(df["startTime"])
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["startTime", "generation"])

    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-02-01T00:00:00Z")

    df = df[(df["startTime"] >= start) & (df["startTime"] < end)].copy()

    # Actuals are reported every 30 minutes; compare using the hourly mean.
    df["delivery_hour"] = df["startTime"].dt.floor("h")

    hourly = (
        df.groupby("delivery_hour", as_index=False)
        .agg(actual_generation=("generation", "mean"))
        .sort_values("delivery_hour")
        .reset_index(drop=True)
    )

    return hourly


def prepare_eligible_forecasts(
    records: list[dict[str, Any]],
) -> pd.DataFrame:
    """
    For each delivery hour, select the latest forecast published on or
    before 11:00 UTC on the previous calendar day.

    This cutoff is a documented working assumption, not a requirement
    specified in the assignment.
    """
    df = records_to_dataframe(
        records,
        ["startTime", "publishTime", "generation"],
    )

    if df.empty:
        return pd.DataFrame(
            columns=[
                "delivery_hour",
                "forecast_generation",
                "forecast_published_at",
                "decision_cutoff",
            ]
        )

    df["startTime"] = parse_utc(df["startTime"])
    df["publishTime"] = parse_utc(df["publishTime"])
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["startTime", "publishTime", "generation"])

    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-02-01T00:00:00Z")

    df["delivery_hour"] = df["startTime"].dt.floor("h")
    df = df[
        (df["delivery_hour"] >= start) & (df["delivery_hour"] < end)
    ].copy()

    # For a delivery hour, cutoff is 11:00 UTC on the previous calendar day.
    previous_day = df["delivery_hour"].dt.normalize() - pd.Timedelta(days=1)
    df["decision_cutoff"] = previous_day + pd.Timedelta(
        hours=DECISION_CUTOFF_HOUR_UTC
    )

    eligible = df[df["publishTime"] <= df["decision_cutoff"]].copy()

    # Keep the latest forecast publication available by the cutoff.
    eligible = eligible.sort_values(
        ["delivery_hour", "publishTime"]
    ).drop_duplicates(subset=["delivery_hour"], keep="last")

    eligible = eligible.rename(
        columns={
            "generation": "forecast_generation",
            "publishTime": "forecast_published_at",
        }
    )

    return eligible[
        [
            "delivery_hour",
            "forecast_generation",
            "forecast_published_at",
            "decision_cutoff",
        ]
    ].sort_values("delivery_hour").reset_index(drop=True)


def timestamp_string(value: Any) -> str | None:
    """Convert a pandas/Python timestamp to an ISO UTC string."""
    if pd.isna(value):
        return None

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    return timestamp.isoformat().replace("+00:00", "Z")


def build_analysis() -> dict[str, Any]:
    """Build the full January dataset and calculate forecast error metrics."""
    actual_records = fetch_actual_records()
    forecast_records = fetch_forecast_records()

    actuals = prepare_actuals(actual_records)
    forecasts = prepare_eligible_forecasts(forecast_records)

    matched = actuals.merge(
        forecasts,
        on="delivery_hour",
        how="inner",
    )

    if not matched.empty:
        matched["error"] = (
            matched["forecast_generation"] - matched["actual_generation"]
        )
        matched["absolute_error"] = matched["error"].abs()
        matched["squared_error"] = matched["error"] ** 2

        mae = float(matched["absolute_error"].mean())
        rmse = float((matched["squared_error"].mean()) ** 0.5)
        bias = float(matched["error"].mean())
    else:
        mae = None
        rmse = None
        bias = None

    matched = matched.sort_values("delivery_hour").reset_index(drop=True)

    # Return every matched hourly interval, not just the first ten.
    matched_intervals = []
    for _, row in matched.iterrows():
        matched_intervals.append(
            {
                "delivery_hour": timestamp_string(row["delivery_hour"]),
                "actual_generation": round(float(row["actual_generation"]), 2),
                "forecast_generation": round(float(row["forecast_generation"]), 2),
                "forecast_published_at": timestamp_string(
                    row["forecast_published_at"]
                ),
                "decision_cutoff": timestamp_string(row["decision_cutoff"]),
                "error": round(float(row["error"]), 2),
                "absolute_error": round(float(row["absolute_error"]), 2),
            }
        )

    return {
        "period": "January 2026",
        "timezone": "UTC",
        "decision_cutoff_assumption": (
            "11:00 UTC on the day before delivery. "
            "This is a working assumption because the assignment does not "
            "specify an exact cutoff time."
        ),
        "actual_records_returned": len(actual_records),
        "forecast_records_returned": len(forecast_records),
        "january_actual_half_hour_intervals": len(actuals) * 2,
        "hourly_actual_points": len(actuals),
        "eligible_hourly_forecasts": len(forecasts),
        "matched_hourly_intervals": len(matched),
        "unmatched_hourly_actual_points": len(actuals) - len(matched),
        "metrics": {
            "MAE": round(mae, 2) if mae is not None else None,
            "RMSE": round(rmse, 2) if rmse is not None else None,
            "bias": round(bias, 2) if bias is not None else None,
        },
        "error_definition": (
            "forecast generation - hourly average actual generation"
        ),
        "metric_interpretation": {
            "MAE": "Average absolute forecast error.",
            "RMSE": "Root mean squared error; larger errors receive more weight.",
            "bias": (
                "Mean signed error; positive means overforecasting, "
                "negative means underforecasting."
            ),
        },
        "matched_intervals": matched_intervals,
        # Keep the existing field so the current frontend still works.
        "sample_matches": matched_intervals[:10],
    }


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Wind Intelligence API is running",
        "status": "healthy",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/actuals")
def get_actuals() -> dict[str, Any]:
    records = fetch_actual_records()
    return {
        "period": "January 2026",
        "count": len(records),
        "records": records,
    }


@app.get("/forecasts/sample")
def get_forecast_sample() -> dict[str, Any]:
    records = fetch_forecast_records()
    return {
        "count": len(records),
        "records": records[:10],
    }


@app.get("/analysis")
def get_analysis() -> dict[str, Any]:
    return build_analysis()