"""Fit the recalibration table (``CALIBRATION`` in forecast_service.py).

Run with:  uv run python -m scripts.calibrate_forecast [n_users] [seed ...]

For every (shown confidence label, days-since-last-start bin) the tempering exponent
T (p -> p**(1/T), renormalised) is chosen so the 50% and 80% interval coverages on
synthetic walk-forward forecasts are as close to nominal as possible. Fitting seeds
default to 7, 13 and 21 and must never include the evaluation seeds (11, 99).
"""

from __future__ import annotations

import sys
from collections import defaultdict

from app.services.forecast_service import _temper, age_bin, point_and_intervals
from scripts.backtest_forecast import EVAL_SEEDS, collect_records, generate_users

FIT_SEEDS = (7, 13, 21)
T_GRID = [0.5 + 0.05 * i for i in range(51)]  # 0.5 .. 3.0
MIN_RECORDS = 60


def coverage(records, temperature: float) -> tuple[float, float]:
    c50 = c80 = 0
    for r in records:
        _, i50, i80 = point_and_intervals(_temper(r.raw_pmf, temperature), r.truncated)
        c50 += i50[0] <= r.truth_index <= i50[1]
        c80 += i80[0] <= r.truth_index <= i80[1]
    return c50 / len(records), c80 / len(records)


def fit(records) -> dict[tuple[str, int], float]:
    groups = defaultdict(list)
    for r in records:
        groups[(r.label, age_bin(r.age))].append(r)
    table = {}
    for key, recs in sorted(groups.items()):
        if len(recs) < MIN_RECORDS:
            continue
        best = min(
            T_GRID,
            key=lambda t: sum(
                (c - target) ** 2
                for c, target in zip(coverage(recs, t), (0.5, 0.8), strict=True)
            ),
        )
        c50, c80 = coverage(recs, best)
        print(f"{key}: n={len(recs)} T={best:.2f} cov50={c50:.3f} cov80={c80:.3f}")
        table[key] = round(best, 2)
    return table


def main() -> None:
    n_users = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    seeds = [int(a) for a in sys.argv[2:]] or list(FIT_SEEDS)
    assert not set(seeds) & set(EVAL_SEEDS), "never fit on evaluation seeds"
    records = []
    for seed in seeds:
        records += collect_records(generate_users(n_users, seed), calibration={})
    print(f"{len(records)} records from seeds {seeds}")
    table = fit(records)
    print("\nCALIBRATION = {")
    for k, v in table.items():
        print(f"    {k!r}: {v},")
    print("}")


if __name__ == "__main__":
    main()
