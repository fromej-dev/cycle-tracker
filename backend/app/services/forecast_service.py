"""Probabilistic forecasting of period start dates, bleeding days and fertile window.

Everything in here is pure Python (standard library only). The statistical core
works on plain lists of ``(start_date, end_date | None)`` tuples so it can be
backtested without a database; :class:`ForecastService` adds thin DB wrappers.

Model overview
--------------
* Cycle length (start to start of consecutive periods) follows a per-user
  Normal-inverse-gamma model with a population prior (mean 29 days, between-person
  SD 3, within-person SD ~2.75, weak prior on the variance). The posterior
  predictive is a Student-t, discretised to whole days and represented as a
  mixture over a grid of the user's mean (this keeps the mean-uncertainty shared
  between successive cycles, so uncertainty grows honestly with horizon).
* Robustness: cycles shorter than 15 days are treated as data errors (the later
  start is merged into the earlier period); gaps >= 1.7x the user's typical cycle
  are treated as forgotten logs and excluded; remaining extreme values are
  down-weighted (Huber-style) and older cycles get a mild recency discount.
* Conditioning on today: if the next period has not started yet, the start
  distribution is truncated to days >= today and renormalised (the mean-grid
  weights are updated too, so a late period also shifts the belief about the mean).
* Period length uses the same family with a prior of mean 5 days, SD 1.5.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from statistics import median

from app.models import Period

PeriodTuple = tuple[datetime.date, datetime.date | None]

# --- Priors and constants -------------------------------------------------------
PRIOR_CYCLE_MEAN = 29.0
PRIOR_CYCLE_KAPPA = 1.0  # within-SD^2 / between-SD^2 ~ 2.75^2 / 3^2
PRIOR_CYCLE_SD = 2.75
PRIOR_CYCLE_NU = 4.0

PRIOR_DURATION_MEAN = 5.0
PRIOR_DURATION_KAPPA = 1.5
PRIOR_DURATION_SD = 1.5
PRIOR_DURATION_NU = 4.0

MIN_CYCLE = 15  # shorter "cycles" are data errors
MAX_CYCLE = 110  # support of the cycle-length distribution
MIN_DURATION = 1
MAX_DURATION = 14
MISSED_LOG_RATIO = 1.7  # gap >= ratio * typical cycle => a forgotten log
RECENCY_DECAY = 0.95  # per-cycle weight discount for older cycles
HUBER_C = 2.0
MU_GRID_POINTS = 13
MU_GRID_RANGE = 4.0  # +/- this many posterior SDs of the mean
LUTEAL_MEAN = 14.0
LUTEAL_SD = 2.0
SD_THRESHOLDS = (2.5, 4.5)  # regular / variable / irregular
LEARNING_CYCLES = 3


@dataclass(frozen=True)
class _Posterior:
    mu: float
    kappa: float
    nu: float
    ss: float  # sum of squares term (nu * sigma^2 scale)


def _posterior(
    values: list[float],
    weights: list[float],
    mu0: float,
    kappa0: float,
    nu0: float,
    s0: float,
) -> _Posterior:
    n = sum(weights)
    if n <= 0:
        return _Posterior(mu0, kappa0, nu0, nu0 * s0**2)
    xbar = sum(w * x for w, x in zip(weights, values, strict=True)) / n
    s = sum(w * (x - xbar) ** 2 for w, x in zip(weights, values, strict=True))
    kn = kappa0 + n
    return _Posterior(
        mu=(kappa0 * mu0 + n * xbar) / kn,
        kappa=kn,
        nu=nu0 + n,
        ss=nu0 * s0**2 + s + kappa0 * n / kn * (xbar - mu0) ** 2,
    )


def _t_pmf(loc: float, scale2: float, df: float, lo: int, hi: int) -> list[float]:
    """Student-t discretised to integers lo..hi (inclusive), normalised."""
    expo = -(df + 1.0) / 2.0
    raw = [(1.0 + (k - loc) ** 2 / (df * scale2)) ** expo for k in range(lo, hi + 1)]
    total = sum(raw)
    return [r / total for r in raw]


def _mean_sd(pmf: list[float], lo: int) -> tuple[float, float]:
    m = sum((lo + i) * p for i, p in enumerate(pmf))
    v = sum((lo + i - m) ** 2 * p for i, p in enumerate(pmf))
    return m, math.sqrt(v)


def _best_interval(pmf: list[float], level: float) -> tuple[int, int, float]:
    """Index interval [s, e] whose mass is closest to ``level``.

    Searches around the central quantiles and prefers equal tails, so the result
    is approximately a central interval but not systematically over-covering
    because of day discretisation.
    """
    n = len(pmf)
    cdf = []
    acc = 0.0
    for p in pmf:
        acc += p
        cdf.append(acc)

    def before(i: int) -> float:
        return cdf[i - 1] if i > 0 else 0.0

    tail = (1.0 - level) / 2.0
    q_lo = next((i for i in range(n) if cdf[i] >= tail), 0)
    best: tuple[float, int, int, float] | None = None
    for s in range(max(0, q_lo - 3), min(n, q_lo + 4)):
        if pmf[s] <= 1e-12:
            continue  # never start an interval on a day with no probability
        e0 = next((i for i in range(s, n) if cdf[i] - before(s) >= level), n - 1)
        for e in (e0 - 1, e0, e0 + 1):
            if e < s or e >= n or pmf[e] <= 1e-12:
                continue
            mass = cdf[e] - before(s)
            score = abs(mass - level) + 0.25 * abs(before(s) - (1.0 - cdf[e]))
            if best is None or score < best[0]:
                best = (score, s, e, mass)
    assert best is not None
    return best[1], best[2], best[3]


def _clean_periods(periods: list[PeriodTuple]) -> list[PeriodTuple]:
    """Sort, dedupe, and merge starts closer than MIN_CYCLE days (data errors)."""
    cleaned: list[list] = []
    for start, end in sorted(periods, key=lambda p: p[0]):
        if cleaned and (start - cleaned[-1][0]).days < MIN_CYCLE:
            # Same bleed logged twice: keep the first start, take the later end.
            cleaned[-1][1] = end
            continue
        cleaned.append([start, end])
    return [(s, e) for s, e in cleaned]


def _cycle_lengths(starts: list[datetime.date]) -> tuple[list[int], int]:
    """Usable cycle lengths (chronological) and how many gaps were excluded."""
    gaps = [(b - a).days for a, b in zip(starts, starts[1:], strict=False)]
    if not gaps:
        return [], 0
    normal = [g for g in gaps if g <= 50]
    if normal:
        ref = median(normal)
    elif len(gaps) >= 3:
        ref = median(gaps)
    else:
        ref = PRIOR_CYCLE_MEAN
    kept = [g for g in gaps if g < MISSED_LOG_RATIO * ref and g <= MAX_CYCLE]
    return kept, len(gaps) - len(kept)


def _cycle_weights(cycles: list[int]) -> list[float]:
    n = len(cycles)
    w = [1.0] * n
    if n >= 4:
        med = median(cycles)
        mad = median([abs(c - med) for c in cycles])
        scale = max(1.4826 * mad, 2.0)
        for i, c in enumerate(cycles):
            z = abs(c - med) / scale
            if z > HUBER_C:
                w[i] = HUBER_C / z
    return [wi * RECENCY_DECAY ** (n - 1 - i) for i, wi in enumerate(w)]


@dataclass
class _Component:
    weight: float
    pmf: list[float]  # unconditioned, index = cycle length - MIN_CYCLE
    cond: list[float] | None = None  # conditioned on today, same indexing


class FittedModel:
    """A user's fitted model, anchored at their last period start."""

    def __init__(self, periods: list[PeriodTuple], today: datetime.date):
        self.today = today
        self.periods = _clean_periods(periods)
        self.starts = [p[0] for p in self.periods]
        self.last_start = self.starts[-1] if self.starts else None
        self.last_end = self.periods[-1][1] if self.periods else None
        self.age = (today - self.last_start).days if self.last_start else 0

        cycles, self.cycles_excluded = _cycle_lengths(self.starts)
        self.cycles_used = len(cycles)
        self.cycle_post = _posterior(
            [float(c) for c in cycles],
            _cycle_weights(cycles),
            PRIOR_CYCLE_MEAN,
            PRIOR_CYCLE_KAPPA,
            PRIOR_CYCLE_NU,
            PRIOR_CYCLE_SD,
        )
        durations = [
            (e - s).days + 1
            for s, e in self.periods
            if e is not None and MIN_DURATION <= (e - s).days + 1 <= MAX_DURATION
        ]
        self.durations_used = len(durations)
        self.duration_post = _posterior(
            [float(d) for d in durations],
            [1.0] * len(durations),
            PRIOR_DURATION_MEAN,
            PRIOR_DURATION_KAPPA,
            PRIOR_DURATION_NU,
            PRIOR_DURATION_SD,
        )
        self._components = self._build_components()
        self._duration_pmf = self._build_duration_pmf()
        self._intensity_cache: tuple[int, list[float]] | None = None

    # --- model construction -----------------------------------------------------

    def _build_components(self) -> list[_Component]:
        p = self.cycle_post
        sd_mu = math.sqrt(p.ss / (p.nu * p.kappa))
        k = MU_GRID_POINTS
        zs = [-MU_GRID_RANGE + 2 * MU_GRID_RANGE * i / (k - 1) for i in range(k)]
        ws = [(1.0 + z * z / p.nu) ** (-(p.nu + 1) / 2) for z in zs]
        total = sum(ws)
        comps = []
        for z, w in zip(zs, ws, strict=True):
            mu = p.mu + z * sd_mu
            scale2 = (p.ss + p.kappa * (mu - p.mu) ** 2) / (p.nu + 1)
            pmf = _t_pmf(mu, scale2, p.nu + 1, MIN_CYCLE, MAX_CYCLE)
            comps.append(_Component(w / total, pmf))
        # Condition on today: the next start is on or after today.
        if self.last_start is not None and self.age > MIN_CYCLE:
            first = self.age - MIN_CYCLE
            for c in comps:
                c.cond = [0.0] * first + c.pmf[first:]
            masses = [sum(c.cond) * c.weight for c in comps]
            if sum(masses) > 1e-6:
                tot = sum(masses)
                for c, m in zip(comps, masses, strict=True):
                    mass_c = sum(c.cond)
                    c.cond = [v / mass_c for v in c.cond] if mass_c > 0 else c.cond
                    c.weight = m / tot
            else:
                # Absurdly late relative to the model: fall back to a hazard-style
                # exponential tail starting today.
                tail = [
                    math.exp(-(i - first) / 5.0) if i >= first else 0.0
                    for i in range(len(comps[0].pmf))
                ]
                s = sum(tail)
                comps = [_Component(1.0, comps[0].pmf, [t / s for t in tail])]
        for c in comps:
            if c.cond is None:
                c.cond = c.pmf
        return comps

    def _build_duration_pmf(self) -> list[float]:
        p = self.duration_post
        scale2 = p.ss / p.nu * (1 + 1 / p.kappa)
        return _t_pmf(p.mu, scale2, p.nu, MIN_DURATION, MAX_DURATION)

    # --- cycle-length / next-start distributions -------------------------------

    def _unconditioned_cycle_pmf(self) -> list[float]:
        n = len(self._components[0].pmf)
        out = [0.0] * n
        for c in self._components:
            for i, v in enumerate(c.pmf):
                out[i] += c.weight * v
        return out

    def next_start_pmf(self) -> list[float]:
        """P(next start = last_start + MIN_CYCLE + i), conditioned on today."""
        n = len(self._components[0].pmf)
        out = [0.0] * n
        for c in self._components:
            assert c.cond is not None
            for i, v in enumerate(c.cond):
                out[i] += c.weight * v
        return out

    def next_start_distribution(self) -> dict[datetime.date, float]:
        if self.last_start is None:
            return {}
        pmf = self.next_start_pmf()
        return {
            self.last_start + datetime.timedelta(days=MIN_CYCLE + i): p
            for i, p in enumerate(pmf)
            if p > 1e-9
        }

    def predictive_sd(self) -> float:
        return _mean_sd(self._unconditioned_cycle_pmf(), MIN_CYCLE)[1]

    def confidence(self) -> str:
        if self.cycles_used < LEARNING_CYCLES:
            return "learning"
        sd = self.predictive_sd()
        if sd <= SD_THRESHOLDS[0]:
            return "regular"
        if sd <= SD_THRESHOLDS[1]:
            return "variable"
        return "irregular"

    # --- bleeding ----------------------------------------------------------------

    def _survival(self) -> list[float]:
        """surv[k] = P(period lasts >= k+1 days), k = 0..MAX_DURATION-1."""
        out = []
        remaining = 1.0
        for p in self._duration_pmf:
            out.append(remaining)
            remaining -= p
        return [max(s, 0.0) for s in out]

    def long_run_bleeding_rate(self) -> float:
        mean_dur = sum((MIN_DURATION + i) * p for i, p in enumerate(self._duration_pmf))
        mean_cycle, _ = _mean_sd(self._unconditioned_cycle_pmf(), MIN_CYCLE)
        return mean_dur / mean_cycle

    def _intensity(self, horizon: int) -> list[float]:
        """Expected number of future period starts on each day offset (cycles >= 1).

        Offsets are days after ``last_start``. Later cycles convolve the unconditioned
        cycle pmf per mean-grid component, so uncertainty grows with horizon.
        """
        if self._intensity_cache and self._intensity_cache[0] >= horizon:
            return self._intensity_cache[1]
        u = [0.0] * (horizon + 1)
        for c in self._components:
            assert c.cond is not None
            step = [(MIN_CYCLE + i, v) for i, v in enumerate(c.pmf) if v > 2e-5]
            norm = sum(v for _, v in step)
            step = [(length, v / norm) for length, v in step]
            cur = [0.0] * (horizon + 1)
            for i, v in enumerate(c.cond):
                if MIN_CYCLE + i <= horizon:
                    cur[MIN_CYCLE + i] = v
            for _ in range(60):
                lo = next((d for d, v in enumerate(cur) if v > 1e-12), None)
                if lo is None:
                    break
                for d in range(lo, horizon + 1):
                    u[d] += c.weight * cur[d]
                if lo + MIN_CYCLE > horizon:
                    break
                nxt = [0.0] * (horizon + 1)
                for d in range(lo, horizon + 1):
                    v = cur[d]
                    if v <= 1e-12:
                        continue
                    for length, p in step:
                        if d + length > horizon:
                            break
                        nxt[d + length] += v * p
                cur = nxt
        self._intensity_cache = (horizon, u)
        return u

    def _logged_bleeding_days(self) -> set[datetime.date]:
        days: set[datetime.date] = set()
        for i, (s, e) in enumerate(self.periods):
            if e is not None:
                end = e
            elif i == len(self.periods) - 1 and self._ongoing():
                end = self.today
            else:
                continue
            days.update(
                s + datetime.timedelta(days=k) for k in range((end - s).days + 1)
            )
        return days

    def _ongoing(self) -> bool:
        if self.last_start is None:
            return False
        if self.last_end is not None:
            return self.last_end >= self.today
        return 0 <= self.age < MAX_DURATION

    def bleeding_probability(
        self, dates: list[datetime.date]
    ) -> dict[datetime.date, float]:
        if not dates:
            return {}
        if self.last_start is None:
            rate = self.long_run_bleeding_rate()
            return dict.fromkeys(dates, rate)
        surv = self._survival()
        logged = self._logged_bleeding_days()
        horizon = max(max((d - self.last_start).days for d in dates), MIN_CYCLE)
        u = self._intensity(horizon)
        ongoing_no_end = self.last_end is None and self._ongoing()
        out: dict[datetime.date, float] = {}
        for d in dates:
            if d in logged:
                out[d] = 1.0
                continue
            off = (d - self.last_start).days
            if d < self.today:
                # Unlogged past day. The last period's end may be missing.
                if self.last_end is None and 0 <= off < MAX_DURATION:
                    out[d] = surv[off]
                else:
                    out[d] = 0.0
                continue
            p = sum(u[off - k] * surv[k] for k in range(MAX_DURATION) if 0 <= off - k)
            if ongoing_no_end and off < MAX_DURATION and self.age < MAX_DURATION:
                denom = surv[self.age]
                if denom > 0:
                    p += surv[off] / denom
            out[d] = min(p, 1.0)
        return out

    # --- forecast summaries --------------------------------------------------------

    def _date(self, i: int) -> datetime.date:
        assert self.last_start is not None
        return self.last_start + datetime.timedelta(days=MIN_CYCLE + i)

    def _ovulation_pmf(self, pmf: list[float]) -> dict[datetime.date, float]:
        luteal = {
            lut: math.exp(-0.5 * ((lut - LUTEAL_MEAN) / LUTEAL_SD) ** 2)
            for lut in range(9, 20)
        }
        z = sum(luteal.values())
        out: dict[datetime.date, float] = {}
        for i, p in enumerate(pmf):
            if p < 1e-9:
                continue
            for lut, w in luteal.items():
                d = self._date(i) - datetime.timedelta(days=lut)
                out[d] = out.get(d, 0.0) + p * w / z
        return out

    def forecast(self, horizon_days: int = 45) -> dict:
        """JSON-ready forecast dictionary (see ``/reports/forecast``)."""
        base = {
            "most_likely_start": None,
            "interval_50": None,
            "interval_80": None,
            "probability_next_3_days": None,
            "confidence": "learning",
            "predictive_sd_days": None,
            "cycles_used": self.cycles_used,
            "days": [],
            "fertile_window": None,
            "is_late": False,
        }
        if self.last_start is None:
            return base

        pmf = self.next_start_pmf()
        mode_i = max(range(len(pmf)), key=lambda i: (pmf[i], -i))
        s50, e50, m50 = _best_interval(pmf, 0.5)
        s80, e80, m80 = _best_interval(pmf, 0.8)
        if s80 > s50 or e80 < e50:  # keep the intervals nested
            s80, e80 = min(s80, s50), max(e80, e50)
            m80 = sum(pmf[s80 : e80 + 1])
        today = self.today
        p3 = sum(p for i, p in enumerate(pmf) if 0 <= (self._date(i) - today).days <= 2)
        ucond = self._unconditioned_cycle_pmf()
        umode = max(range(len(ucond)), key=lambda i: (ucond[i], -i))
        is_late = not self._ongoing() and self.age > MIN_CYCLE + umode

        dates = [today + datetime.timedelta(days=k) for k in range(horizon_days)]
        by_date = {self._date(i): p for i, p in enumerate(pmf)}
        bleed = self.bleeding_probability(dates)
        ov = self._ovulation_pmf(pmf)
        ov_dates = sorted(ov)
        ov_mode = max(ov_dates, key=lambda d: (ov[d], -d.toordinal()))
        ov_pmf = [ov.get(d, 0.0) for d in ov_dates]
        os_i, oe_i, _ = _best_interval(ov_pmf, 0.8)

        def p_fertile(day: datetime.date) -> float:
            return sum(
                ov.get(day + datetime.timedelta(days=k), 0.0) for k in range(-1, 6)
            )

        return {
            **base,
            "most_likely_start": self._date(mode_i),
            "interval_50": {"start": self._date(s50), "end": self._date(e50)},
            "interval_80": {"start": self._date(s80), "end": self._date(e80)},
            "probability_next_3_days": min(p3, 1.0),
            "confidence": self.confidence(),
            "predictive_sd_days": round(self.predictive_sd(), 2),
            "days": [
                {
                    "date": d,
                    "p_start": by_date.get(d, 0.0),
                    "p_bleeding": bleed[d],
                    "p_fertile": min(p_fertile(d), 1.0),
                }
                for d in dates
            ],
            "fertile_window": {
                "start": ov_mode - datetime.timedelta(days=5),
                "end": ov_mode + datetime.timedelta(days=1),
                "ovulation_date": ov_mode,
                "ovulation_interval_80": {
                    "start": ov_dates[os_i],
                    "end": ov_dates[oe_i],
                },
            },
            "is_late": bool(is_late),
            "_interval_masses": {"50": m50, "80": m80},
        }


class ForecastService:
    """Probabilistic period forecasts. Pure core plus database wrappers."""

    # --- pure core (no DB) -----------------------------------------------------------

    @staticmethod
    def fit(
        periods: list[PeriodTuple], today: datetime.date | None = None
    ) -> FittedModel:
        """Fit the model on plain ``(start, end_or_None)`` tuples."""
        return FittedModel(periods, today or datetime.date.today())

    @staticmethod
    def forecast_from_periods(
        periods: list[PeriodTuple],
        today: datetime.date | None = None,
        horizon_days: int = 45,
    ) -> dict:
        return ForecastService.fit(periods, today).forecast(horizon_days)

    # --- DB wrappers ----------------------------------------------------------------

    @staticmethod
    def _load(user_id: int) -> list[PeriodTuple]:
        rows = Period.query.filter_by(user_id=user_id).order_by(Period.start_date).all()
        return [(p.start_date, p.end_date) for p in rows]

    @staticmethod
    def forecast(
        user_id: int, today: datetime.date | None = None, horizon_days: int = 45
    ) -> dict:
        return ForecastService.forecast_from_periods(
            ForecastService._load(user_id), today, horizon_days
        )

    @staticmethod
    def next_start_distribution(
        user_id: int, today: datetime.date | None = None
    ) -> dict[datetime.date, float]:
        """P(next period starts on date d), conditioned on today."""
        return ForecastService.fit(
            ForecastService._load(user_id), today
        ).next_start_distribution()

    @staticmethod
    def bleeding_probability(
        user_id: int,
        dates: list[datetime.date],
        today: datetime.date | None = None,
    ) -> dict[datetime.date, float]:
        """P(user is bleeding on each date); valid up to ~12 months ahead."""
        return ForecastService.fit(
            ForecastService._load(user_id), today
        ).bleeding_probability(list(dates))

    @staticmethod
    def fertile_window(user_id: int, today: datetime.date | None = None) -> dict | None:
        return ForecastService.forecast(user_id, today, horizon_days=1)[
            "fertile_window"
        ]
