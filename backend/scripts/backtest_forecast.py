"""Walk-forward backtest of the cycle forecast on synthetic users.

Run with:  uv run python -m scripts.backtest_forecast [n_users] [seed]

The generator uses published population statistics (Bull et al. 2019, npj Digital
Medicine, ~600k cycles: mean cycle ~29.3 days, SD of user means ~3 days, within-user
SD varying widely) but deliberately includes features the forecasting model does NOT
assume: Student-t noise, drifting means, occasional one-off long cycles and skipped
logs (two cycles merged into one gap). Synthetic data is still easier than real data.
"""

from __future__ import annotations

import datetime
import math
import random
import sys
from dataclasses import dataclass, field
from statistics import mean

from app.services.forecast_service import ForecastService

EPOCH = datetime.date(2022, 1, 1)
EVAL_DAYS = (1, 25, 32)  # days after the last logged start at which we forecast


@dataclass
class SyntheticUser:
    kind: str
    starts: list[datetime.date]  # as logged (skipped logs already removed)
    durations: list[int]  # duration of each logged period


def generate_users(n_users: int = 300, seed: int = 20240607) -> list[SyntheticUser]:
    rng = random.Random(seed)
    users = []
    for _ in range(n_users):
        mu = min(max(rng.gauss(29.3, 3.0), 21.0), 40.0)
        r = rng.random()
        if r < 0.25:
            kind, sd = "regular", rng.uniform(1.0, 2.0)
        elif r < 0.80:
            kind, sd = "typical", rng.uniform(2.3, 4.0)
        else:
            kind, sd = "irregular", rng.uniform(5.5, 9.0)
        drift = rng.gauss(0, 0.15) if rng.random() < 0.25 else 0.0
        df = 5.0
        t_scale = sd * math.sqrt((df - 2) / df)
        skipper = rng.random() < 0.05
        long_rate = 0.03
        n_cycles = rng.randint(6, 24)

        true_starts = [EPOCH + datetime.timedelta(days=rng.randint(0, 20))]
        for i in range(n_cycles):
            # Student-t noise: normal / sqrt(chi2/df)
            chi2 = rng.gammavariate(df / 2, 2.0)
            noise = rng.gauss(0, 1) / math.sqrt(chi2 / df) * t_scale
            length = mu + drift * i + noise
            if rng.random() < long_rate:
                length += rng.uniform(7, 20)
            length = int(round(min(max(length, 17), 70)))
            true_starts.append(true_starts[-1] + datetime.timedelta(days=length))

        logged = [true_starts[0]]
        for s in true_starts[1:]:
            if skipper and rng.random() < 0.10:
                continue  # forgot to log this period
            logged.append(s)
        durations = [int(min(max(round(rng.gauss(5.0, 1.2)), 2), 9)) for _ in logged]
        users.append(SyntheticUser(kind, logged, durations))
    return users


@dataclass
class Bucket:
    n: int = 0
    in50: int = 0
    in80: int = 0
    abs_err_mode: list[float] = field(default_factory=list)
    abs_err_median: list[float] = field(default_factory=list)
    abs_err_naive: list[float] = field(default_factory=list)
    abs_err_naive_buggy: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, float]:
        return {
            "n": self.n,
            "cov50": self.in50 / self.n,
            "cov80": self.in80 / self.n,
            "mae_model": mean(self.abs_err_mode),
            "mae_model_median": mean(self.abs_err_median),
            "mae_naive_fixed": mean(self.abs_err_naive),
            "mae_naive_buggy": mean(self.abs_err_naive_buggy),
        }


def _median_date(dist: dict[datetime.date, float]) -> datetime.date:
    acc = 0.0
    for d in sorted(dist):
        acc += dist[d]
        if acc >= 0.5:
            return d
    return max(dist)


def run_backtest(users: list[SyntheticUser]) -> dict[str, Bucket]:
    buckets: dict[str, Bucket] = {}

    def bucket(name: str) -> Bucket:
        return buckets.setdefault(name, Bucket())

    for user in users:
        starts = user.starts
        for i in range(3, len(starts)):  # target is start i; >= 2 earlier cycles
            hist = starts[:i]
            truth = starts[i]
            gaps = [(b - a).days for a, b in zip(hist, hist[1:], strict=False)]
            naive_len = round(mean(gaps))
            naive = hist[-1] + datetime.timedelta(days=naive_len)
            naive_buggy = hist[-1] + datetime.timedelta(days=naive_len - 1)
            periods = [
                (s, s + datetime.timedelta(days=d - 1))
                for s, d in zip(hist, user.durations, strict=False)
            ]
            for day in EVAL_DAYS:
                today = hist[-1] + datetime.timedelta(days=day)
                if truth < today:
                    continue  # already started; no forecast needed
                model = ForecastService.fit(periods, today)
                fc = model.forecast(horizon_days=1)
                dist = model.next_start_distribution()
                names = [f"day{day}", "all"]
                if day == 1:
                    names.append(f"day1/{user.kind}")
                for name in names:
                    b = bucket(name)
                    b.n += 1
                    b.in50 += (
                        fc["interval_50"]["start"] <= truth <= fc["interval_50"]["end"]
                    )
                    b.in80 += (
                        fc["interval_80"]["start"] <= truth <= fc["interval_80"]["end"]
                    )
                    b.abs_err_mode.append(abs((fc["most_likely_start"] - truth).days))
                    b.abs_err_median.append(abs((_median_date(dist) - truth).days))
                    # Naive predictors cannot condition on today; give them the benefit
                    # of the doubt and clip to today when they predict the past.
                    b.abs_err_naive.append(abs((max(naive, today) - truth).days))
                    b.abs_err_naive_buggy.append(
                        abs((max(naive_buggy, today) - truth).days)
                    )
    return buckets


def format_table(buckets: dict[str, Bucket]) -> str:
    header = (
        f"{'subset':<16}{'n':>6}{'cov50':>8}{'cov80':>8}"
        f"{'MAE mode':>10}{'MAE med':>9}{'naive fix':>10}{'naive bug':>10}"
    )
    lines = [header, "-" * len(header)]
    for name in sorted(buckets):
        s = buckets[name].summary()
        lines.append(
            f"{name:<16}{s['n']:>6}{s['cov50']:>8.3f}{s['cov80']:>8.3f}"
            f"{s['mae_model']:>10.3f}{s['mae_model_median']:>9.3f}"
            f"{s['mae_naive_fixed']:>10.3f}{s['mae_naive_buggy']:>10.3f}"
        )
    return "\n".join(lines)


def main() -> None:
    n_users = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20240607
    buckets = run_backtest(generate_users(n_users, seed))
    print(f"Backtest: {n_users} synthetic users, seed {seed}")
    print("cov50/cov80 targets: 0.50 / 0.80. MAE in days vs next logged start.")
    print(format_table(buckets))


if __name__ == "__main__":
    main()
