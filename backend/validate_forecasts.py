
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# Allow importing the backend's existing data-fetching function.
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from main import fetch_forecast_records  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
UTC = timezone.utc
JAN_START = datetime(2026, 1, 1, tzinfo=UTC)
FEB_START = datetime(2026, 2, 1, tzinfo=UTC)
CUTOFF_HOUR_UTC = 11
TOLERANCE = 0.02


def parse_time(value):
    if not value:
        return None

    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC)


def delivery_hour(value):
    timestamp = parse_time(value)
    if timestamp is None:
        return None

    return timestamp.replace(minute=0, second=0, microsecond=0)


def cutoff_for(hour):
    previous_day = hour.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)

    return previous_day + timedelta(hours=CUTOFF_HOUR_UTC)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def main():
    print("\nFULL FORECAST SELECTION VALIDATION")
    print("=" * 60)
    print("Working assumption: forecast must be published by")
    print("11:00 UTC on the day before delivery.")
    print()

    # Fetch every forecast record using the existing backend function.
    print("1. Fetching all raw WINDFOR records...")
    raw_records = fetch_forecast_records()

    if isinstance(raw_records, dict):
        raw_records = raw_records.get(
            "records", raw_records.get("data", [])
        )

    print(f"   Raw forecast records fetched: {len(raw_records)}")

    # Independently apply the cutoff and latest-publication rule.
    print("2. Independently selecting the latest eligible forecast...")
    eligible_by_hour = defaultdict(list)
    missing_fields = 0
    january_forecast_records = 0

    for record in raw_records:
        start = delivery_hour(record.get("startTime"))
        published = parse_time(record.get("publishTime"))
        generation = number(record.get("generation"))

        if start is None or published is None or generation is None:
            missing_fields += 1
            continue

        if not (JAN_START <= start < FEB_START):
            continue

        january_forecast_records += 1
        cutoff = cutoff_for(start)

        if published <= cutoff:
            eligible_by_hour[start].append(
                (published, generation)
            )

    # Pick the latest publication timestamp for each delivery hour.
    selected = {}

    for hour, candidates in eligible_by_hour.items():
        latest_publish_time = max(item[0] for item in candidates)
        latest_candidates = [
            item for item in candidates
            if item[0] == latest_publish_time
        ]

        # If the same publication timestamp has conflicting values,
        # flag it rather than silently choosing one.
        distinct_values = {item[1] for item in latest_candidates}

        if len(distinct_values) == 1:
            selected[hour] = (
                latest_publish_time,
                latest_candidates[0][1],
            )

    print(f"   January forecast records with valid fields: "
          f"{january_forecast_records}")
    print(f"   Records missing required fields: {missing_fields}")
    print(f"   Delivery hours with eligible forecasts: "
          f"{len(eligible_by_hour)}")
    print(f"   Hours with unambiguous latest forecast: {len(selected)}")

    # Retrieve the backend's final analysis for comparison.
    print("3. Comparing selections with /analysis...")

    with httpx.Client(timeout=120) as client:
        response = client.get(f"{BASE_URL}/analysis")
        response.raise_for_status()
        analysis = response.json()

    dashboard_rows = analysis.get("matched_intervals", [])
    dashboard_by_hour = {}

    for row in dashboard_rows:
        hour = delivery_hour(
    row.get("delivery_hour")
    or row.get("start_time")
    or row.get("startTime")
)

        if hour is not None:
            dashboard_by_hour[hour] = row

    # Some versions may use a different field name for the delivery hour.
    if not dashboard_by_hour and dashboard_rows:
        print("   Could not identify delivery-time field in analysis rows.")
        print("   First analysis row fields:", list(dashboard_rows[0]))
        print("\nRESULT: Comparison needs the actual response field names.")
        return

    common_hours = set(selected) & set(dashboard_by_hour)
    missing_from_dashboard = set(selected) - set(dashboard_by_hour)
    missing_from_selection = set(dashboard_by_hour) - set(selected)

    generation_mismatches = []
    publish_time_mismatches = []
    ambiguous_hours = sum(
        1 for candidates in eligible_by_hour.values()
        if candidates
        and len({
            generation
            for published, generation in candidates
            if published == max(item[0] for item in candidates)
        }) > 1
    )

    for hour in sorted(common_hours):
        expected_publish, expected_generation = selected[hour]
        row = dashboard_by_hour[hour]

        actual_generation = number(
            row.get("forecast_generation")
        )
        if actual_generation is None:
            actual_generation = number(row.get("forecastGeneration"))

        actual_publish = parse_time(
            row.get("forecast_published_at")
            or row.get("forecast_publish_time")
            or row.get("publishTime")
        )

        if (
            actual_generation is None
            or abs(actual_generation - expected_generation) > TOLERANCE
        ):
            generation_mismatches.append(
                (hour, expected_generation, actual_generation)
            )

        if actual_publish != expected_publish:
            publish_time_mismatches.append(
                (hour, expected_publish, actual_publish)
            )

    checks = [
        (
            "Raw forecast records fetched",
            len(raw_records) > 0,
            f"{len(raw_records)} records",
        ),
        (
            "Eligible forecasts cover January",
            len(selected) == 744,
            f"{len(selected)} of 744 hours",
        ),
        (
            "No ambiguous latest-publication timestamps",
            ambiguous_hours == 0,
            f"{ambiguous_hours} ambiguous hours",
        ),
        (
            "All selected hours exist in dashboard",
            len(missing_from_dashboard) == 0,
            f"{len(missing_from_dashboard)} missing hours",
        ),
        (
            "No extra dashboard hours",
            len(missing_from_selection) == 0,
            f"{len(missing_from_selection)} extra hours",
        ),
        (
            "Forecast generation matches",
            len(generation_mismatches) == 0,
            f"{len(generation_mismatches)} mismatches",
        ),
        (
            "Forecast publication time matches",
            len(publish_time_mismatches) == 0,
            f"{len(publish_time_mismatches)} mismatches",
        ),
    ]

    print("\nVALIDATION RESULTS")
    print("-" * 60)

    passed = 0
    for label, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")
        passed += int(ok)

    if generation_mismatches:
        print("\nFirst generation mismatches:")
        for item in generation_mismatches[:5]:
            print(" ", item)

    if publish_time_mismatches:
        print("\nFirst publication-time mismatches:")
        for item in publish_time_mismatches[:5]:
            print(" ", item)

    print(f"\nChecks passed: {passed}/{len(checks)}")

    if passed == len(checks):
        print("RESULT: All forecast selection checks passed.")
    else:
        print("RESULT: Some checks need investigation.")
        print("The cutoff remains a working assumption, not an")
        print("explicit time confirmed by the assignment.")


if __name__ == "__main__":
    main()
