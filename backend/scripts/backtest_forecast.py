"""Walk-forward backtest of the cycle forecast on synthetic users.

Run with:  uv run python -m scripts.backtest_forecast [n_users] [seed ...]

The generator uses published population statistics (Bull et al. 2019, npj Digital
Medicine, ~600k cycles: mean cycle ~29.3 days, SD of user means ~3 days, within-user
SD varying widely and continuously) but deliberately includes features the
forecasting model does NOT assume: per-user tail weight (Student-t df 4, 5 or 8),
drifting means, occasional one-off long cycles and skipped logs (two cycles merged
into one gap). Synthetic data is still easier than real data.

Results are reported by SHOWN confidence label x evaluation day and by hidden
generator type x evaluation day. Seeds 11 and 99 are the evaluation seeds; the
recalibration (scripts/calibrate_forecast.py) never uses them.
"""

from __future__ import annotations

import datetime
import math
import random
import sys
from dataclasses import dataclass, field
from statistics import mean

from app.services.forecast_service import ForecastService, point_index

EPOCH = datetime.date(2022, 1, 1)
EVAL_DAYS = (1, 25, 32)  # days after the last logged start at which we forecast
EVAL_SEEDS = (11, 99)
EVAL_USERS = 600
GATE_MIN_N = 150
GATE_MAE_TOLERANCE = 0.1


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
        sd = min(max(math.exp(rng.gauss(math.log(3.2), 0.5)), 0.8), 12.0)
        kind = "regular" if sd < 2.2 else "typical" if sd < 4.5 else "irregular"
        drift = rng.gauss(0, 0.15) if rng.random() < 0.25 else 0.0
        df = rng.choice((4.0, 5.0, 8.0))
        t_scale = sd * math.sqrt((df - 2) / df)
        skipper = rng.random() < 0.05
        long_rate = 0.03
        n_cycles = rng.randint(6, 24)

        true_starts = [EPOCH + datetime.timedelta(days=rng.randint(0, 20))]
        for i in range(n_cycles):
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
class Record:
    """One walk-forward forecast, with the raw (uncalibrated) pmf for fitting."""

    label: str
    kind: str
    day: int
    age: int
    truth_index: int  # (truth - last_start) - MIN_CYCLE
    raw_pmf: list[float]
    truncated: bool
    point_naive: int  # naive prediction as days after last start (clipped to today)
    point_naive_buggy: int
    last_start_offset: int  # days from last start to truth
    point_model: int = 0
    in50: bool = False
    in80: bool = False
    median_pt: int = 0


def iter_cases(users: list[SyntheticUser]):
    for user in users:
        starts = user.starts
        for i in range(3, len(starts)):  # target is start i; >= 2 earlier cycles
            hist = starts[:i]
            truth = starts[i]
            gaps = [(b - a).days for a, b in zip(hist, hist[1:], strict=False)]
            naive_len = round(mean(gaps))
            periods = [
                (s, s + datetime.timedelta(days=d - 1))
                for s, d in zip(hist, user.durations, strict=False)
            ]
            for day in EVAL_DAYS:
                today = hist[-1] + datetime.timedelta(days=day)
                if truth < today:
                    continue  # already started; no forecast needed
                yield user, periods, hist[-1], truth, today, day, naive_len


def collect_records(users: list[SyntheticUser], calibration=None) -> list[Record]:
    """Forecast every case. ``calibration={}`` gives raw model output (for fitting)."""
    out = []
    for user, periods, last, truth, today, day, naive_len in iter_cases(users):
        model = ForecastService.fit(periods, today, calibration)
        label = model.label()
        if label == "overdue":
            continue
        _, i50, i80 = model.point_and_intervals()
        pt = point_index(model.next_start_pmf(), model._truncated)
        t_idx = (truth - last).days - 15
        out.append(
            Record(
                label=label,
                kind=user.kind,
                day=day,
                age=model.age,
                truth_index=t_idx,
                raw_pmf=model.raw_next_start_pmf(),
                truncated=model._truncated,
                point_naive=max(naive_len, day),
                point_naive_buggy=max(naive_len - 1, day),
                last_start_offset=(truth - last).days,
                point_model=pt + 15,
                in50=i50[0] <= t_idx <= i50[1],
                in80=i80[0] <= t_idx <= i80[1],
            )
        )
    return out


@dataclass
class Bucket:
    n: int = 0
    in50: int = 0
    in80: int = 0
    err_model: list[float] = field(default_factory=list)
    err_naive: list[float] = field(default_factory=list)
    err_naive_buggy: list[float] = field(default_factory=list)

    def add(self, r: Record) -> None:
        self.n += 1
        self.in50 += r.in50
        self.in80 += r.in80
        self.err_model.append(abs(r.point_model - r.last_start_offset))
        self.err_naive.append(abs(r.point_naive - r.last_start_offset))
        self.err_naive_buggy.append(abs(r.point_naive_buggy - r.last_start_offset))

    def summary(self) -> dict[str, float]:
        return {
            "n": self.n,
            "cov50": self.in50 / self.n,
            "cov80": self.in80 / self.n,
            "mae_model": mean(self.err_model),
            "mae_naive_fixed": mean(self.err_naive),
            "mae_naive_buggy": mean(self.err_naive_buggy),
        }


def run_backtest(users: list[SyntheticUser]) -> dict[tuple[str, str, int], Bucket]:
    """Buckets keyed by (grouping, group value, day); grouping is label/type/all."""
    buckets: dict[tuple[str, str, int], Bucket] = {}
    for r in collect_records(users):
        for key in (
            ("label", r.label, r.day),
            ("type", r.kind, r.day),
            ("all", "all", r.day),
            ("all", "all", 0),
        ):
            buckets.setdefault(key, Bucket()).add(r)
    return buckets


GATE_Z = 3.0  # ~99.7% binomial band: 24 bucket-metrics are checked per seed


def merge_buckets(
    parts: list[dict[tuple[str, str, int], Bucket]],
) -> dict[tuple[str, str, int], Bucket]:
    """Pool the buckets of several seeds."""
    out: dict[tuple[str, str, int], Bucket] = {}
    for part in parts:
        for key, b in part.items():
            m = out.setdefault(key, Bucket())
            m.n += b.n
            m.in50 += b.in50
            m.in80 += b.in80
            m.err_model += b.err_model
            m.err_naive += b.err_naive
            m.err_naive_buggy += b.err_naive_buggy
    return out


def _binom_bounds(n: int, p: float) -> tuple[float, float]:
    h = GATE_Z * math.sqrt(p * (1 - p) / n)
    return p - h, p + h


def gate_failures(
    buckets: dict[tuple[str, str, int], Bucket], strict: bool = False
) -> list[str]:
    """Calibration + accuracy gate over shown-label x day buckets.

    Coverage must lie in target +/- 0.05. Because a bucket with n < ~385 cannot
    resolve +/-0.05 (binomial noise alone exceeds it), the default band is widened to
    the bucket's binomial interval (z=3, because 24 bucket-metrics are checked per
    seed) when that is wider; ``strict=True`` applies
    the literal +/-0.05 band to every bucket with n >= GATE_MIN_N.
    """
    fails = []
    for (grouping, name, day), b in sorted(buckets.items()):
        if grouping != "label" or b.n < 30:
            continue
        s = b.summary()
        for level, key in ((0.8, "cov80"), (0.5, "cov50")):
            lo, hi = level - 0.05, level + 0.05
            if not strict or b.n < GATE_MIN_N:
                blo, bhi = _binom_bounds(b.n, level)
                lo, hi = min(lo, blo), max(hi, bhi)
            if not lo <= s[key] <= hi:
                fails.append(
                    f"{name}@day{day} n={b.n} {key}={s[key]:.3f} not in "
                    f"[{lo:.3f}, {hi:.3f}]"
                )
        if (
            b.n >= GATE_MIN_N
            and s["mae_model"] > s["mae_naive_fixed"] + GATE_MAE_TOLERANCE
        ):
            fails.append(
                f"{name}@day{day} n={b.n} MAE {s['mae_model']:.3f} > naive "
                f"{s['mae_naive_fixed']:.3f} + {GATE_MAE_TOLERANCE}"
            )
    return fails


def format_table(buckets: dict[tuple[str, str, int], Bucket], grouping: str) -> str:
    header = (
        f"{grouping:<10}{'day':>4}{'n':>6}{'cov50':>8}{'cov80':>8}"
        f"{'MAE model':>11}{'naive fix':>10}{'naive bug':>10}"
    )
    lines = [header, "-" * len(header)]
    for (g, name, day), b in sorted(buckets.items()):
        if g != grouping:
            continue
        s = b.summary()
        lines.append(
            f"{name:<10}{day:>4}{s['n']:>6}{s['cov50']:>8.3f}{s['cov80']:>8.3f}"
            f"{s['mae_model']:>11.3f}{s['mae_naive_fixed']:>10.3f}"
            f"{s['mae_naive_buggy']:>10.3f}"
        )
    return "\n".join(lines)


def main() -> None:
    n_users = int(sys.argv[1]) if len(sys.argv) > 1 else EVAL_USERS
    seeds = [int(a) for a in sys.argv[2:]] or list(EVAL_SEEDS)
    per_seed = []
    for seed in seeds + ([None] if len(seeds) > 1 else []):
        if seed is None:
            buckets = merge_buckets(per_seed)
            seed = "pooled " + "+".join(map(str, seeds))
        else:
            buckets = run_backtest(generate_users(n_users, seed))
            per_seed.append(buckets)
        print(f"\n=== {n_users} synthetic users, seed {seed} ===")
        print("targets cov50 0.50 / cov80 0.80; MAE in days vs next logged start.")
        print("day 0 = all days pooled.")
        for grouping in ("all", "label", "type"):
            print(format_table(buckets, grouping))
            print()
        for strict in (False, True):
            fails = gate_failures(buckets, strict)
            mode = "literal +/-0.05" if strict else "binomial-aware"
            print(f"GATE ({mode}):", "PASS" if not fails else "FAIL")
            for f in fails:
                print("  ", f)


if __name__ == "__main__":
    main()
