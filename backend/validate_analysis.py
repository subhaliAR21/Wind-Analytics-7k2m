
import math
from datetime import datetime, timedelta, timezone

import httpx

API_URL = "http://127.0.0.1:8000/analysis"


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    print("\nWIND INTELLIGENCE - DATA VALIDATION")
    print("=" * 45)

    response = httpx.get(API_URL, timeout=120)
    response.raise_for_status()
    data = response.json()

    rows = data.get("matched_intervals", [])
    metrics = data.get("metrics", {})

    checks = []

    def check(name, passed, detail):
        checks.append(passed)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {detail}")

    # 1. Dataset completeness
    check(
        "Hourly matched records",
        len(rows) == data.get("matched_hourly_intervals"),
        f"{len(rows)} rows; API reports "
        f"{data.get('matched_hourly_intervals')} matched intervals",
    )

    check(
        "January expected hours",
        len(rows) == 744,
        f"Expected 744 hourly intervals; found {len(rows)}",
    )

    # 2. Unique delivery hours
    delivery_times = [row.get("delivery_hour") for row in rows]
    check(
        "No duplicate delivery hours",
        len(delivery_times) == len(set(delivery_times)),
        f"{len(delivery_times) - len(set(delivery_times))} duplicates",
    )

    # 3. Missing or invalid numeric data
    numeric_fields = [
        "actual_generation",
        "forecast_generation",
        "error",
        "absolute_error",
    ]

    invalid_rows = []
    for index, row in enumerate(rows):
        for field in numeric_fields:
            value = row.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                invalid_rows.append((index, field))
                break

    check(
        "No missing/non-finite numeric values",
        len(invalid_rows) == 0,
        f"{len(invalid_rows)} invalid rows",
    )

    # 4. Forecast publication cutoff
    cutoff_violations = []
    missing_timestamps = []

    for row in rows:
        published = parse_time(row.get("forecast_published_at"))
        cutoff = parse_time(row.get("decision_cutoff"))

        if published is None or cutoff is None:
            missing_timestamps.append(row.get("delivery_hour"))
        elif published > cutoff:
            cutoff_violations.append(
                (
                    row.get("delivery_hour"),
                    row.get("forecast_published_at"),
                    row.get("decision_cutoff"),
                )
            )

    check(
        "Forecasts published by cutoff",
        len(cutoff_violations) == 0 and len(missing_timestamps) == 0,
        f"{len(cutoff_violations)} cutoff violations; "
        f"{len(missing_timestamps)} missing timestamp pairs",
    )

    # 5. Error arithmetic
    error_mismatches = []

    for row in rows:
        expected_error = (
            row["forecast_generation"] - row["actual_generation"]
        )
        expected_absolute_error = abs(expected_error)

        if (
            abs(expected_error - row["error"]) > 0.02
            or abs(expected_absolute_error - row["absolute_error"]) > 0.02
        ):
            error_mismatches.append(row.get("delivery_hour"))

    check(
        "Error arithmetic",
        len(error_mismatches) == 0,
        f"{len(error_mismatches)} mismatches",
    )

    # 6. Independently recalculate MAE, RMSE and bias
    if rows:
        errors = [row["error"] for row in rows]
        absolute_errors = [abs(value) for value in errors]

        calculated_mae = sum(absolute_errors) / len(errors)
        calculated_rmse = math.sqrt(
            sum(value * value for value in errors) / len(errors)
        )
        calculated_bias = sum(errors) / len(errors)

        def metric_matches(name, calculated):
            api_value = metrics.get(name)
            passed = (
                isinstance(api_value, (int, float))
                and abs(calculated - api_value) <= 0.02
            )
            check(
                f"{name} recalculation",
                passed,
                f"API={api_value}; recalculated={calculated:.2f}",
            )

        metric_matches("MAE", calculated_mae)
        metric_matches("RMSE", calculated_rmse)
        metric_matches("bias", calculated_bias)
    else:
        check("Metric recalculation", False, "No matched rows available")

    # 7. Timestamp sequence should be hourly and chronological
    parsed_times = [parse_time(value) for value in delivery_times]
    sorted_times = sorted(parsed_times)

    chronological = parsed_times == sorted_times
    consecutive = all(
        current - previous == timedelta(hours=1)
        for previous, current in zip(sorted_times, sorted_times[1:])
    )

    check(
        "Chronological hourly sequence",
        chronological and consecutive,
        "Sorted with no gaps" if chronological and consecutive
        else "Order issue or missing delivery hours detected",
    )

    print("=" * 45)
    print(f"Checks passed: {sum(checks)}/{len(checks)}")

    if all(checks):
        print("RESULT: All automated checks passed.")
    else:
        print("RESULT: Investigate the failed checks before submission.")

    print(
        "\nNote: This script checks the returned matched dataset. "
        "It does not independently prove that the source API returned "
        "every raw half-hour actual or every eligible forecast."
    )


if __name__ == "__main__":
    main()
