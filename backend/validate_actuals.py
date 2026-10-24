
from collections import defaultdict
from datetime import datetime, timezone

import httpx

BASE_URL = "http://127.0.0.1:8000"


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    print("\nRAW ACTUALS CROSS-CHECK")
    print("=" * 50)

    with httpx.Client(timeout=120) as client:
        actual_response = client.get(f"{BASE_URL}/actuals")
        actual_response.raise_for_status()
        actual_data = actual_response.json()

        analysis_response = client.get(f"{BASE_URL}/analysis")
        analysis_response.raise_for_status()
        analysis_data = analysis_response.json()

    raw_records = actual_data["records"]
    matched_rows = analysis_data["matched_intervals"]

    print(f"Raw API count: {actual_data['count']}")
    print(f"Raw records received: {len(raw_records)}")
    print(f"Matched hourly records: {len(matched_rows)}")

    # Group raw half-hour actuals by UTC delivery hour.
    grouped = defaultdict(list)

    for record in raw_records:
        if record.get("fuelType") != "WIND":
            continue

        start_time = parse_time(record["startTime"]).astimezone(timezone.utc)

        # Exclude any records outside January 2026.
        if start_time.year != 2026 or start_time.month != 1:
            continue

        hour_start = start_time.replace(
            minute=0, second=0, microsecond=0
        )

        grouped[hour_start].append(float(record["generation"]))

    # Independently average the half-hour actuals.
    hourly_actuals = {}

    wrong_interval_counts = []

    for hour, values in grouped.items():
        if len(values) != 2:
            wrong_interval_counts.append((hour.isoformat(), len(values)))
            continue

        hourly_actuals[hour] = sum(values) / len(values)

    dashboard_actuals = {}

    for row in matched_rows:
        delivery_hour = parse_time(row["delivery_hour"]).astimezone(
            timezone.utc
        )
        dashboard_actuals[delivery_hour] = float(row["actual_generation"])

    missing_dashboard_hours = sorted(
        set(hourly_actuals) - set(dashboard_actuals)
    )
    missing_raw_hours = sorted(
        set(dashboard_actuals) - set(hourly_actuals)
    )

    mismatches = []

    for hour in sorted(set(hourly_actuals) & set(dashboard_actuals)):
        independently_calculated = hourly_actuals[hour]
        dashboard_value = dashboard_actuals[hour]

        if abs(independently_calculated - dashboard_value) > 0.01:
            mismatches.append(
                (
                    hour.isoformat(),
                    independently_calculated,
                    dashboard_value,
                )
            )

    checks = [
        (
            "Raw half-hour records",
            len(raw_records) == actual_data["count"] == 1488,
            f"{len(raw_records)} records",
        ),
        (
            "January hourly coverage",
            len(hourly_actuals) == 744,
            f"{len(hourly_actuals)} complete hourly averages",
        ),
        (
            "Exactly two half-hour records per hour",
            len(wrong_interval_counts) == 0,
            f"{len(wrong_interval_counts)} hours with unexpected counts",
        ),
        (
            "Same hours in raw and dashboard data",
            not missing_dashboard_hours and not missing_raw_hours,
            f"{len(missing_dashboard_hours)} absent from dashboard; "
            f"{len(missing_raw_hours)} absent from raw averages",
        ),
        (
            "Hourly averages match dashboard",
            len(mismatches) == 0,
            f"{len(mismatches)} value mismatches",
        ),
    ]

    print("\nVALIDATION RESULTS")
    print("-" * 50)

    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")

    if mismatches:
        print("\nFirst mismatches:")
        for item in mismatches[:5]:
            print(item)

    if wrong_interval_counts:
        print("\nFirst unexpected interval counts:")
        for item in wrong_interval_counts[:5]:
            print(item)

    print("-" * 50)
    print(f"Checks passed: {sum(c[1] for c in checks)}/{len(checks)}")

    if all(c[1] for c in checks):
        print("RESULT: Raw actuals match the dashboard hourly averages.")
    else:
        print("RESULT: Investigate the failed checks before submission.")


if __name__ == "__main__":
    main()
