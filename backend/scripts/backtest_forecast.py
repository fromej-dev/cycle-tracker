"""Walk-forward backtest of the cycle forecast on synthetic users.

Run with:  uv run python -m scripts.backtest_forecast [n_users] [scenario] [seed ...]

Scenarios (see ``SCENARIOS``): ``native`` (Student-t noise, mild drift, 5% skippers),
``skips`` (30% of users skip 25% of logs, log-normal noise), ``regime`` (30% of users
change mean by -4/+5 days and double their SD part-way), and the stress test
``lognormal_drift_skips``. The calibration fit uses ``random_world`` generators whose
rare-event rates and noise family are drawn per seed, so no evaluation scenario is
the fitting distribution.

The generator uses published population statistics (Bull et al. 2019, npj Digital
Medicine, ~600k cycles: mean cycle ~29.3 days, SD of user means ~3 days, within-user
SD varying widely and continuously). Synthetic data is still easier than real data.

Results are reported by SHOWN confidence label x evaluation day, by whether the user
has excluded (skipped-log) gaps x day, and by hidden generator type and trait.
Never fit on seeds 5, 11, 42, 99 or 123: those are evaluation seeds.
"""

from __future__ import annotations

import datetime
import math
import random
import sys
from dataclasses import dataclass, field
from statistics import mean, pstdev

from app.services.forecast_service import (
    ForecastService,
    error_point_index,
    mode_index,
)

EPOCH = datetime.date(2022, 1, 1)
EVAL_DAYS = (1, 25, 32)  # days after the last logged start at which we forecast
EVAL_SEEDS = (11, 99)
EVAL_USERS = 600
GATE_MIN_N = 30
GATE_MAE_MIN_N = 150
GATE_MAE_TOLERANCE = 0.1
GATE_SLACK = 0.05
GATE_SE_MULT = 2.0


@dataclass(frozen=True)
class World:
    """Generator settings. Rates here are NOT the forecasting model's priors."""

    noise: str = "t"  # "t" | "gauss" | "lognormal" | "mixed"
    df_choices: tuple[float, ...] = (4.0, 5.0, 8.0)
    sd_median: float = 3.2
    sd_log_sd: float = 0.5
    drift_frac: float = 0.25
    drift_sd: float = 0.15
    skipper_frac: float = 0.05
    skip_rate: float = 0.10
    long_rate: float = 0.03
    regime_frac: float = 0.0
    max_cycle: int = 70


SCENARIOS: dict[str, World] = {
    "native": World(),
    "skips": World(
        noise="lognormal",
        drift_frac=0.0,
        skipper_frac=0.30,
        skip_rate=0.25,
        max_cycle=90,
    ),
    "regime": World(noise="gauss", drift_frac=0.0, regime_frac=0.30, max_cycle=90),
    "lognormal_drift_skips": World(
        noise="lognormal",
        drift_frac=0.5,
        drift_sd=0.4,
        skipper_frac=0.20,
        skip_rate=0.20,
        long_rate=0.06,
        max_cycle=90,
    ),
}


def random_world(rng: random.Random) -> World:
    """A world with randomised rare-event rates and noise family (for calibration)."""
    return World(
        noise=rng.choice(("t", "gauss", "lognormal", "mixed")),
        sd_median=rng.uniform(2.6, 3.8),
        sd_log_sd=rng.uniform(0.4, 0.6),
        drift_frac=rng.uniform(0.0, 0.5),
        drift_sd=rng.uniform(0.1, 0.4),
        skipper_frac=rng.uniform(0.02, 0.30),
        skip_rate=rng.uniform(0.05, 0.30),
        long_rate=rng.uniform(0.01, 0.07),
        regime_frac=rng.uniform(0.0, 0.3),
        max_cycle=rng.choice((70, 90)),
    )


@dataclass
class SyntheticUser:
    kind: str
    starts: list[datetime.date]  # as logged (skipped logs already removed)
    durations: list[int]  # duration of each logged period
    trait: str = "stable"  # stable | drift | regime


def generate_users(
    n_users: int = 300,
    seed: int = 20240607,
    scenario: str | World = "native",
) -> list[SyntheticUser]:
    rng = random.Random(seed)
    if isinstance(scenario, World):
        world = scenario
    elif scenario == "random":
        world = random_world(rng)
    else:
        world = SCENARIOS[scenario]
    users = []
    for _ in range(n_users):
        mu = min(max(rng.gauss(29.3, 3.0), 21.0), 40.0)
        sd = min(
            max(math.exp(rng.gauss(math.log(world.sd_median), world.sd_log_sd)), 0.8),
            12.0,
        )
        kind = "regular" if sd < 2.2 else "typical" if sd < 4.5 else "irregular"
        drift = rng.gauss(0, world.drift_sd) if rng.random() < world.drift_frac else 0.0
        noise = (
            rng.choice(("t", "gauss", "lognormal"))
            if world.noise == "mixed"
            else world.noise
        )
        df = rng.choice(world.df_choices)
        skipper = rng.random() < world.skipper_frac
        n_cycles = rng.randint(6, 24)
        change = rng.randint(2, n_cycles) if rng.random() < world.regime_frac else None
        shift = rng.choice((-4.0, 5.0))
        trait = (
            "regime"
            if change is not None
            else "drift"
            if abs(drift) > 0.1
            else "stable"
        )

        true_starts = [EPOCH + datetime.timedelta(days=rng.randint(0, 20))]
        for i in range(n_cycles):
            m, s = max(mu + drift * i, 12.0), sd
            if change is not None and i >= change:
                m, s = mu + shift, sd * 2
            if noise == "gauss":
                length = rng.gauss(m, s)
            elif noise == "lognormal":
                v = math.log(1 + (s / m) ** 2)
                length = math.exp(rng.gauss(math.log(m) - v / 2, math.sqrt(v)))
            else:
                chi2 = rng.gammavariate(df / 2, 2.0)
                length = m + rng.gauss(0, 1) / math.sqrt(chi2 / df) * s * math.sqrt(
                    (df - 2) / df
                )
            if rng.random() < world.long_rate:
                length += rng.uniform(7, 25)
            length = int(round(min(max(length, 17), world.max_cycle)))
            true_starts.append(true_starts[-1] + datetime.timedelta(days=length))

        logged = [true_starts[0]]
        for st in true_starts[1:]:
            if skipper and rng.random() < world.skip_rate:
                continue  # forgot to log this period
            logged.append(st)
        durations = [int(min(max(round(rng.gauss(5.0, 1.2)), 2), 9)) for _ in logged]
        users.append(SyntheticUser(kind, logged, durations, trait))
    return users


@dataclass
class Record:
    """One walk-forward forecast, with the raw (uncalibrated) pmf for fitting."""

    label: str
    kind: str
    trait: str
    excluded: bool
    day: int
    age: int
    truth_index: int  # (truth - last_start) - MIN_CYCLE
    raw_pmf: list[float]
    truncated: bool
    point_naive: int  # naive prediction as days after last start (clipped to today)
    point_naive_buggy: int
    last_start_offset: int  # days from last start to truth
    point_model: int = 0
    mode_model: int = 0
    in50: bool = False
    in80: bool = False


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
        pmf = model.next_start_pmf()
        _, i50, i80 = model.point_and_intervals()
        t_idx = (truth - last).days - 15
        out.append(
            Record(
                label=label,
                kind=user.kind,
                trait=user.trait,
                excluded=model.has_excluded,
                day=day,
                age=model.age,
                truth_index=t_idx,
                raw_pmf=model.raw_next_start_pmf(),
                truncated=model._truncated,
                point_naive=max(naive_len, day),
                point_naive_buggy=max(naive_len - 1, day),
                last_start_offset=(truth - last).days,
                point_model=error_point_index(pmf, model._truncated) + 15,
                mode_model=mode_index(pmf) + 15,
                in50=i50[0] <= t_idx <= i50[1],
                in80=i80[0] <= t_idx <= i80[1],
            )
        )
    return out


Key = tuple[str, str, int]


@dataclass
class Bucket:
    n: int = 0
    in50: int = 0
    in80: int = 0
    err_model: list[float] = field(default_factory=list)  # median-when-late point
    err_mode: list[float] = field(default_factory=list)
    err_naive: list[float] = field(default_factory=list)
    err_naive_buggy: list[float] = field(default_factory=list)

    def add(self, r: Record) -> None:
        self.n += 1
        self.in50 += r.in50
        self.in80 += r.in80
        self.err_model.append(abs(r.point_model - r.last_start_offset))
        self.err_mode.append(abs(r.mode_model - r.last_start_offset))
        self.err_naive.append(abs(r.point_naive - r.last_start_offset))
        self.err_naive_buggy.append(abs(r.point_naive_buggy - r.last_start_offset))

    def summary(self) -> dict[str, float]:
        return {
            "n": self.n,
            "cov50": self.in50 / self.n,
            "cov80": self.in80 / self.n,
            "mae_model": mean(self.err_model),
            "mae_mode": mean(self.err_mode),
            "mae_naive_fixed": mean(self.err_naive),
            "mae_naive_buggy": mean(self.err_naive_buggy),
        }


def bucketize(records: list[Record]) -> dict[Key, Bucket]:
    buckets: dict[Key, Bucket] = {}
    for r in records:
        for key in (
            ("label", r.label, r.day),
            ("excl", "excluded" if r.excluded else "clean", r.day),
            ("type", r.kind, r.day),
            ("trait", r.trait, r.day),
            ("all", "all", r.day),
            ("all", "all", 0),
        ):
            buckets.setdefault(key, Bucket()).add(r)
    return buckets


def run_backtest(users: list[SyntheticUser]) -> dict[Key, Bucket]:
    return bucketize(collect_records(users))


def merge_buckets(parts: list[dict[Key, Bucket]]) -> dict[Key, Bucket]:
    """Pool the buckets of several seeds."""
    out: dict[Key, Bucket] = {}
    for part in parts:
        for key, b in part.items():
            m = out.setdefault(key, Bucket())
            m.n += b.n
            m.in50 += b.in50
            m.in80 += b.in80
            m.err_model += b.err_model
            m.err_mode += b.err_mode
            m.err_naive += b.err_naive
            m.err_naive_buggy += b.err_naive_buggy
    return out


def tolerance(n: int, p: float, slack: float = GATE_SLACK) -> float:
    return slack + GATE_SE_MULT * math.sqrt(p * (1 - p) / n)


def gate_failures(
    buckets: dict[Key, Bucket], groupings=("label", "excl"), slack: float = GATE_SLACK
) -> list[str]:
    """Calibration + accuracy gate.

    Every label x day and has-excluded-gaps x day bucket must satisfy
    |coverage - p| <= 0.05 + 2*sqrt(p(1-p)/n), and the model's MAE must not exceed
    the naive mean predictor's by more than 0.1 day + 2 SE of the paired difference
    (buckets with n >= 150).
    """
    fails = []
    for (grouping, name, day), b in sorted(buckets.items()):
        if grouping not in groupings or b.n < GATE_MIN_N:
            continue
        s = b.summary()
        for level, key in ((0.8, "cov80"), (0.5, "cov50")):
            tol = tolerance(b.n, level, slack)
            if abs(s[key] - level) > tol:
                fails.append(
                    f"{grouping}:{name}@day{day} n={b.n} {key}={s[key]:.3f} "
                    f"outside {level} +/- {tol:.3f}"
                )
        if b.n >= GATE_MAE_MIN_N:
            diffs = [m - nv for m, nv in zip(b.err_model, b.err_naive, strict=True)]
            mean_diff = mean(diffs)
            se = pstdev(diffs) / math.sqrt(b.n)
            if mean_diff > GATE_MAE_TOLERANCE + GATE_SE_MULT * se:
                fails.append(
                    f"{grouping}:{name}@day{day} n={b.n} MAE {s['mae_model']:.3f} > "
                    f"naive {s['mae_naive_fixed']:.3f} + {GATE_MAE_TOLERANCE} "
                    f"+ {GATE_SE_MULT} SE ({se:.3f})"
                )
    return fails


# --- lapsed users ------------------------------------------------------------------


def overdue_check(users: list[SyntheticUser]) -> dict[str, float]:
    """How the overdue state behaves.

    * ``false_overdue``: share of real forecasts (the day before the next period
      actually started) wrongly labelled overdue.
    * ``lapsed_detected``: share of lapsed users (stopped logging, e.g. pregnancy or
      stopping the app) labelled overdue 100, 150 and 200 days after their last start.
    """
    false_overdue = total = 0
    lapsed_hit = {100: 0, 150: 0, 200: 0}
    lapsed_total = 0
    for user in users:
        starts = user.starts
        for i in range(3, len(starts)):
            hist = starts[:i]
            periods = [
                (s, s + datetime.timedelta(days=d - 1))
                for s, d in zip(hist, user.durations, strict=False)
            ]
            gap = (starts[i] - hist[-1]).days
            model = ForecastService.fit(
                periods, hist[-1] + datetime.timedelta(days=gap - 1)
            )
            total += 1
            false_overdue += model.label() == "overdue"
        # lapse: the user's whole history, then silence
        periods = [
            (s, s + datetime.timedelta(days=d - 1))
            for s, d in zip(starts, user.durations, strict=False)
        ]
        if len(periods) >= 3:
            lapsed_total += 1
            for age in lapsed_hit:
                m = ForecastService.fit(
                    periods, starts[-1] + datetime.timedelta(days=age)
                )
                lapsed_hit[age] += m.label() == "overdue"
    return {
        "forecasts": total,
        "false_overdue": false_overdue / total,
        "lapsed_users": lapsed_total,
        **{f"lapsed_detected_{a}d": h / lapsed_total for a, h in lapsed_hit.items()},
    }


def format_table(buckets: dict[Key, Bucket], grouping: str) -> str:
    header = (
        f"{grouping:<10}{'day':>4}{'n':>7}{'cov50':>8}{'cov80':>8}"
        f"{'MAE pt':>8}{'MAE mode':>9}{'naive fix':>10}{'naive bug':>10}"
    )
    lines = [header, "-" * len(header)]
    for (g, name, day), b in sorted(buckets.items()):
        if g != grouping:
            continue
        s = b.summary()
        lines.append(
            f"{name:<10}{day:>4}{s['n']:>7}{s['cov50']:>8.3f}{s['cov80']:>8.3f}"
            f"{s['mae_model']:>8.3f}{s['mae_mode']:>9.3f}{s['mae_naive_fixed']:>10.3f}"
            f"{s['mae_naive_buggy']:>10.3f}"
        )
    return "\n".join(lines)


def main() -> None:
    n_users = int(sys.argv[1]) if len(sys.argv) > 1 else EVAL_USERS
    scenario = sys.argv[2] if len(sys.argv) > 2 else "native"
    seeds = [int(a) for a in sys.argv[3:]] or list(EVAL_SEEDS)
    names = list(SCENARIOS) if scenario == "all" else [scenario]
    for name in names:
        per_seed = []
        for seed in seeds:
            users = generate_users(n_users, seed, name)
            buckets = run_backtest(users)
            per_seed.append(buckets)
            print(f"\n=== {name}: {n_users} users, seed {seed} ===")
            print("targets cov50 0.50 / cov80 0.80; MAE in days; day 0 = pooled.")
            for grouping in ("all", "label", "excl", "type", "trait"):
                print(format_table(buckets, grouping))
                print()
            fails = gate_failures(buckets)
            print("GATE:", "PASS" if not fails else "FAIL")
            for f in fails:
                print("  ", f)
        if len(seeds) > 1:
            pooled = merge_buckets(per_seed)
            fails = gate_failures(pooled)
            print(
                f"\n=== {name}: pooled seeds {seeds} GATE:",
                "PASS" if not fails else "FAIL",
            )
            for f in fails:
                print("  ", f)
    if scenario in ("all", "native"):
        print("\noverdue behaviour:", overdue_check(generate_users(150, seeds[0])))


if __name__ == "__main__":
    main()
