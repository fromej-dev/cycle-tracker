"""Fit the recalibration table (``CALIBRATION`` in forecast_service.py).

Run with:  uv run python -m scripts.calibrate_forecast [n_users] [seed ...]

For every (shown confidence label, days-since-last-start bin, has-excluded-gaps) the tempering exponent
T (p -> p**(1/T), renormalised) is chosen so the 50% and 80% interval coverages on
synthetic walk-forward forecasts are as close to nominal as possible. Fitting seeds
default to 1001-1006, each a differently randomised world (noise family, skip, drift,
regime and long-cycle rates), and must never include evaluation seeds 5, 11, 42, 99, 123.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from app.services.forecast_service import _temper, age_bin, point_and_intervals
from scripts.backtest_forecast import EVAL_SEEDS, collect_records, generate_users

FIT_SEEDS = (1001, 1002, 1003, 1004, 1005, 1006)
T_GRID = [0.6 + 0.05 * i for i in range(29)]  # 0.6 .. 2.0
MIN_RECORDS = 60


def coverage(records, temperature: float, q50: float = 0.5) -> tuple[float, float]:
    c50 = c80 = 0
    for r in records:
        _, i50, i80 = point_and_intervals(
            _temper(r.raw_pmf, temperature), r.truncated, q50
        )
        c50 += i50[0] <= r.truth_index <= i50[1]
        c80 += i80[0] <= r.truth_index <= i80[1]
    return c50 / len(records), c80 / len(records)


Q_GRID = [0.30 + 0.02 * i for i in range(16)]  # model mass of the 50% interval


def fit(records):
    """Return (T table, q50 table). T matches 80% coverage, then q50 matches 50%."""
    groups = defaultdict(list)
    for r in records:
        groups[(r.label, age_bin(r.age), r.excluded)].append(r)
    table, q_table = {}, {}
    for key, recs in sorted(groups.items()):
        if len(recs) < MIN_RECORDS:
            continue
        best = min(T_GRID, key=lambda t: abs(coverage(recs, t)[1] - 0.8))
        q = min(Q_GRID, key=lambda q: abs(coverage(recs, best, q)[0] - 0.5))
        c50, c80 = coverage(recs, best, q)
        print(
            f"{key}: n={len(recs)} T={best:.2f} q50={q:.2f} "
            f"cov50={c50:.3f} cov80={c80:.3f}"
        )
        table[key] = round(best, 2)
        q_table[key] = round(q, 2)
    return table, q_table


def main() -> None:
    n_users = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    seeds = [int(a) for a in sys.argv[2:]] or list(FIT_SEEDS)
    assert not set(seeds) & {5, 11, 42, 99, 123, *EVAL_SEEDS}, "never fit on eval seeds"
    records = []
    for seed in seeds:
        records += collect_records(
            generate_users(n_users, seed, "random"), calibration={}
        )
    print(f"{len(records)} records from seeds {seeds}")
    import pickle

    with open("/tmp/calib_records.pkl", "wb") as fh:
        pickle.dump(records, fh)
    table, q_table = fit(records)
    for name, tab in (("CALIBRATION", table), ("CALIBRATION_Q50", q_table)):
        print(f"\n{name} = {{")
        for k, v in tab.items():
            print(f"    {k!r}: {v},")
        print("}")


if __name__ == "__main__":
    main()
