"""Probabilistic forecasting of period start dates, bleeding days and fertile window.

Everything in here is pure Python (standard library only). The statistical core
works on plain lists of ``(start_date, end_date | None)`` tuples so it can be
backtested without a database; :class:`ForecastService` adds thin DB wrappers.

Model overview
--------------
* Each user has an unknown mean cycle length ``mu`` and within-person SD ``sigma``.
  Both live on a grid with broad population priors (``mu``: mostly N(29.3, 3) with a
  small heavy component for long-cycle users; ``sigma``: log-normal, median ~2.8,
  roughly 1 to 10 days). Cycle lengths are Student-t (df=5) around ``mu`` with SD
  ``sigma``: heavy-tailed, and the tail does NOT thin out as data accumulates.
  The posterior over the grid is exact (up to weights), so a regular user
  gets a narrow forecast and an irregular user a wide one.
* A small "something else is going on" component (prior 4%) models long, disrupted
  cycles with a slow exponential hazard. It is what keeps forecasts honest when a
  period is already late.
* Robustness: starts closer than 15 days are merged (data error); gaps >= 1.7x the
  user's typical cycle are treated as forgotten logs and excluded; extreme cycles
  are Huber-downweighted and older cycles get a mild recency discount.
* Conditioning on today: if the next period has not started, the start distribution
  is truncated to days >= today and renormalised.
* Recalibration: the (label x days-since-last-start) tempering exponents in
  ``CALIBRATION`` were fitted by ``scripts/calibrate_forecast.py`` on synthetic users
  generated from seeds that are never used for evaluation.
* Lapsed users (period long overdue) get an explicit "overdue" state, no forecast.
* Period length uses a Normal-inverse-gamma model with prior mean 5 days, SD 1.5.
"""

from __future__ import annotations

import datetime
import functools
import math
from dataclasses import dataclass
from statistics import median

from app.models import Period

PeriodTuple = tuple[datetime.date, datetime.date | None]

# --- Priors and constants -------------------------------------------------------
MIN_CYCLE = 15  # shorter "cycles" are data errors
MAX_CYCLE = 130  # support of the cycle-length distribution
T_DF = 5.0  # tail weight of within-person noise

MU_PRIOR = ((0.92, 29.3, 3.0), (0.08, 38.0, 10.0))  # (weight, mean, sd) mixture
SIGMA_PRIOR_MEDIAN = 2.8
SIGMA_PRIOR_LOG_SD = 0.55
SIGMA_GRID = [1.0 * 1.253**i for i in range(12)]  # ~1 .. ~12 days
MU_GRID = [17.0 + 0.5 * i for i in range(67)] + [51.0 + i for i in range(30)]
MAX_MU_GROUPS = 16

DISRUPTED_PRIOR = 0.04  # P(cycle is disrupted/very long)
DISRUPTED_MIN = 30
DISRUPTED_SCALE = 20.0  # days, exponential hazard beyond DISRUPTED_MIN

PRIOR_DURATION_MEAN = 5.0
PRIOR_DURATION_KAPPA = 1.5
PRIOR_DURATION_SD = 1.5
PRIOR_DURATION_NU = 4.0
MIN_DURATION = 1
MAX_DURATION = 14

MISSED_LOG_RATIO = 1.7  # gap >= ratio * typical cycle => a forgotten log
RECENCY_DECAY = 0.95  # per-cycle weight discount for older cycles
HUBER_C = 2.0
OVERDUE_MIN_DAYS = 90
LUTEAL_MEAN = 14.0
LUTEAL_SD = 2.0
SD_THRESHOLDS = (2.5, 4.5)  # regular / variable / irregular
LEARNING_CYCLES = 3

# Tempering exponents T keyed by (confidence label, age bin): p -> p**(1/T).
# Fitted by scripts/calibrate_forecast.py (seeds disjoint from evaluation seeds).
CALIBRATION: dict[tuple[str, int], float] = {
    ("irregular", 0): 1.0,
    ("irregular", 1): 0.95,
    ("irregular", 2): 0.9,
    ("learning", 0): 1.0,
    ("learning", 1): 1.0,
    ("learning", 2): 0.95,
    ("regular", 0): 0.85,
    ("regular", 1): 0.8,
    ("regular", 2): 0.85,
    ("variable", 0): 0.95,
    ("variable", 1): 0.95,
    ("variable", 2): 0.9,
}


def age_bin(age: int) -> int:
    """Bin of days since last period start used for recalibration."""
    if age < 16:
        return 0
    if age < 29:
        return 1
    if age < 45:
        return 2
    return 3


# --- Student-t grid -------------------------------------------------------------


@dataclass(frozen=True)
class _GridComp:
    mu: float
    log_prior: float
    pmf: tuple[float, ...]
    logpmf: tuple[float, ...]


def _t_pmf(loc: float, scale2: float, df: float, lo: int, hi: int) -> list[float]:
    """Student-t discretised to integers lo..hi (inclusive), normalised."""
    expo = -(df + 1.0) / 2.0
    raw = [(1.0 + (k - loc) ** 2 / (df * scale2)) ** expo for k in range(lo, hi + 1)]
    total = sum(raw)
    return [r / total for r in raw]


def _normal_pdf(x: float, m: float, sd: float) -> float:
    return math.exp(-0.5 * ((x - m) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))


@functools.lru_cache(maxsize=1)
def _grid() -> tuple[_GridComp, ...]:
    mu_w = []
    for i, mu in enumerate(MU_GRID):
        step = (MU_GRID[i + 1] - mu) if i + 1 < len(MU_GRID) else 1.0
        mu_w.append(sum(w * _normal_pdf(mu, m, sd) for w, m, sd in MU_PRIOR) * step)
    sg_w = [
        math.exp(-0.5 * (math.log(s / SIGMA_PRIOR_MEDIAN) / SIGMA_PRIOR_LOG_SD) ** 2)
        for s in SIGMA_GRID
    ]
    z = sum(mu_w) * sum(sg_w)
    comps = []
    shrink = (T_DF - 2.0) / T_DF  # t scale^2 = sigma^2 * (df-2)/df gives SD sigma
    for mu, mw in zip(MU_GRID, mu_w, strict=True):
        for sigma, sw in zip(SIGMA_GRID, sg_w, strict=True):
            pmf = _t_pmf(mu, sigma**2 * shrink, T_DF, MIN_CYCLE, MAX_CYCLE)
            comps.append(
                _GridComp(
                    mu,
                    math.log(mw * sw / z),
                    tuple(pmf),
                    tuple(math.log(max(p, 1e-300)) for p in pmf),
                )
            )
    return tuple(comps)


@functools.lru_cache(maxsize=1)
def _disrupted_pmf() -> tuple[float, ...]:
    raw = [
        math.exp(-(k - DISRUPTED_MIN) / DISRUPTED_SCALE) if k >= DISRUPTED_MIN else 0.0
        for k in range(MIN_CYCLE, MAX_CYCLE + 1)
    ]
    t = sum(raw)
    return tuple(r / t for r in raw)


@dataclass(frozen=True)
class _CycleFit:
    groups: tuple[tuple[float, tuple[float, ...]], ...]  # (weight, pmf) per mu group
    main: tuple[float, ...]  # posterior predictive without the disrupted component


@functools.lru_cache(maxsize=2048)
def _fit_cycles(cycles: tuple[int, ...]) -> _CycleFit:
    """Posterior over the (mu, sigma) grid for chronological cycle lengths."""
    weights = _cycle_weights(list(cycles))
    comps = _grid()
    logw = []
    for c in comps:
        ll = c.log_prior
        for x, w in zip(cycles, weights, strict=True):
            ll += w * c.logpmf[x - MIN_CYCLE]
        logw.append(ll)
    top = max(logw)
    post = [math.exp(v - top) for v in logw]
    total = sum(post)
    n_pmf = MAX_CYCLE - MIN_CYCLE + 1

    by_mu: dict[float, tuple[float, list[float]]] = {}
    for c, w in zip(comps, post, strict=True):
        w /= total
        if w < 1e-5:
            continue
        acc = by_mu.setdefault(c.mu, (0.0, [0.0] * n_pmf))
        arr = acc[1]
        for i, p in enumerate(c.pmf):
            arr[i] += w * p
        by_mu[c.mu] = (acc[0] + w, arr)
    items = sorted(by_mu.items())
    norm = sum(w for _, (w, _) in items)
    # Merge adjacent mu groups so later-cycle convolutions stay cheap.
    size = max(1, math.ceil(len(items) / MAX_MU_GROUPS))
    groups = []
    main = [0.0] * n_pmf
    for i in range(0, len(items), size):
        chunk = items[i : i + size]
        gw = sum(w for _, (w, _) in chunk) / norm
        arr = [sum(a[j] for _, (_, a) in chunk) / norm for j in range(n_pmf)]
        for j, v in enumerate(arr):
            main[j] += v
        groups.append((gw, tuple(v / gw for v in arr)))
    return _CycleFit(tuple(groups), tuple(main))


# --- Duration model ------------------------------------------------------------------


@dataclass(frozen=True)
class _Posterior:
    mu: float
    kappa: float
    nu: float
    ss: float


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


def _mean_sd(pmf: list[float] | tuple[float, ...], lo: int) -> tuple[float, float]:
    t = sum(pmf)
    m = sum((lo + i) * p for i, p in enumerate(pmf)) / t
    v = sum((lo + i - m) ** 2 * p for i, p in enumerate(pmf)) / t
    return m, math.sqrt(v)


# --- Intervals ------------------------------------------------------------------------


def _median_index(pmf: list[float]) -> int:
    acc = 0.0
    for i, p in enumerate(pmf):
        acc += p
        if acc >= 0.5:
            return i
    return len(pmf) - 1


def _hdi(pmf: list[float], level: float, point: int) -> tuple[int, int, float]:
    """Narrowest contiguous index interval containing ``point`` with mass >= level."""
    n = len(pmf)
    cdf = []
    acc = 0.0
    for p in pmf:
        acc += p
        cdf.append(acc)

    def mass(s: int, e: int) -> float:
        return cdf[e] - (cdf[s - 1] if s > 0 else 0.0)

    best: tuple[int, float, int, int] | None = None
    e = n - 1
    for s in range(point, -1, -1):
        if pmf[s] <= 1e-12 and s != point:
            continue
        while e - 1 >= point and mass(s, e - 1) >= level - 1e-12:
            e -= 1
        if mass(s, e) < level - 1e-12:
            continue
        key = (e - s, abs((cdf[s - 1] if s > 0 else 0.0) - (1.0 - cdf[e])))
        if best is None or key < (best[0], best[1]):
            best = (key[0], key[1], s, e)
    if best is None:  # level unreachable (should not happen): whole support
        return 0, n - 1, 1.0
    return best[2], best[3], mass(best[2], best[3])


def _temper(pmf: list[float], temperature: float) -> list[float]:
    if abs(temperature - 1.0) < 1e-9:
        return pmf
    out = [p ** (1.0 / temperature) if p > 0 else 0.0 for p in pmf]
    t = sum(out)
    return [v / t for v in out]


def point_and_intervals(
    pmf: list[float], truncated: bool
) -> tuple[int, tuple[int, int, float], tuple[int, int, float]]:
    """Point estimate plus nested 50% and 80% index intervals containing it."""
    pt = point_index(pmf, truncated)
    i50 = _hdi(pmf, 0.5, pt)
    i80 = _hdi(pmf, 0.8, pt)
    if i80[0] > i50[0] or i80[1] < i50[1]:  # keep nested
        s, e = min(i80[0], i50[0]), max(i80[1], i50[1])
        i80 = (s, e, sum(pmf[s : e + 1]))
    return pt, i50, i80


def point_index(pmf: list[float], truncated: bool) -> int:
    """Mode, or the median when the mode is pinned to today's truncation edge."""
    mode = max(range(len(pmf)), key=lambda i: (pmf[i], -i))
    first = next(i for i, p in enumerate(pmf) if p > 0)
    if truncated and mode == first:
        return _median_index(pmf)
    return mode


# --- Data cleaning ----------------------------------------------------------------------


def _clean_periods(periods: list[PeriodTuple]) -> list[PeriodTuple]:
    """Sort, dedupe, and merge starts closer than MIN_CYCLE days (data errors)."""
    cleaned: list[list] = []
    for start, end in sorted(periods, key=lambda p: p[0]):
        if cleaned and (start - cleaned[-1][0]).days < MIN_CYCLE:
            cleaned[-1][1] = end  # same bleed logged twice
            continue
        cleaned.append([start, end])
    return [(s, e) for s, e in cleaned]


def _cycle_lengths(starts: list[datetime.date]) -> tuple[list[int], int]:
    """Usable cycle lengths (chronological) and how many gaps were excluded."""
    gaps = [(b - a).days for a, b in zip(starts, starts[1:], strict=False)]
    if not gaps:
        return [], 0
    normal = [g for g in gaps if g <= 50]
    ref = median(normal) if normal else median(gaps)
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


class FittedModel:
    """A user's fitted model, anchored at their last period start."""

    def __init__(
        self,
        periods: list[PeriodTuple],
        today: datetime.date,
        calibration: dict[tuple[str, int], float] | None = None,
    ):
        self.today = today
        self.calibration = CALIBRATION if calibration is None else calibration
        self.periods = _clean_periods(periods)
        self.starts = [p[0] for p in self.periods]
        self.last_start = self.starts[-1] if self.starts else None
        self.last_end = self.periods[-1][1] if self.periods else None
        self.age = (today - self.last_start).days if self.last_start else 0

        cycles, self.cycles_excluded = _cycle_lengths(self.starts)
        self.cycles_used = len(cycles)
        self._fit = _fit_cycles(tuple(cycles))
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
        p = self.duration_post
        scale2 = p.ss / p.nu * (1 + 1 / p.kappa)
        expo = -(p.nu + 1) / 2
        raw = [
            (1 + (k - p.mu) ** 2 / (p.nu * scale2)) ** expo
            for k in range(MIN_DURATION, MAX_DURATION + 1)
        ]
        self._duration_pmf = [r / sum(raw) for r in raw]

        mean_cycle, self._main_sd = _mean_sd(self._fit.main, MIN_CYCLE)
        self.mean_cycle = mean_cycle
        # Full unconditioned cycle distribution = main + disrupted component.
        dis = _disrupted_pmf()
        self._unc = [
            (1 - DISRUPTED_PRIOR) * m + DISRUPTED_PRIOR * d
            for m, d in zip(self._fit.main, dis, strict=True)
        ]
        self._build_start_pmf()
        self._intensity_cache: tuple[int, list[float]] | None = None

    # --- cycle-length / next-start distributions -------------------------------

    @property
    def overdue(self) -> bool:
        """True for lapsed users: no period for far longer than any cycle."""
        return (
            self.last_start is not None
            and not self._ongoing()
            and self.age > max(OVERDUE_MIN_DAYS, 2 * self.mean_cycle)
        )

    def label(self) -> str:
        if self.overdue:
            return "overdue"
        if self.cycles_used < LEARNING_CYCLES:
            return "learning"
        if self._main_sd <= SD_THRESHOLDS[0]:
            return "regular"
        if self._main_sd <= SD_THRESHOLDS[1]:
            return "variable"
        return "irregular"

    confidence = label

    def predictive_sd(self) -> float:
        """SD (days) of the ordinary cycle-length predictive (excludes disruptions)."""
        return self._main_sd

    def _build_start_pmf(self) -> None:
        unc = self._unc
        self._truncated = self.age > MIN_CYCLE
        if not self._truncated:
            self._raw = list(unc)
        else:
            first = self.age - MIN_CYCLE
            tail = unc[first:] if first < len(unc) else []
            mass = sum(tail)
            if mass < 1e-9:
                self._raw = list(unc)
                self._no_mass = True
                self._truncated = False
            else:
                self._raw = [0.0] * first + [v / mass for v in tail]
        self._no_mass = getattr(self, "_no_mass", False)
        key = (self.label(), age_bin(self.age))
        self._temperature = self.calibration.get(key, 1.0)
        self._p1 = _temper(self._raw, self._temperature)

    def raw_next_start_pmf(self) -> list[float]:
        """Conditioned (on today) but not recalibrated; index = length - MIN_CYCLE."""
        return list(self._raw)

    def next_start_pmf(self) -> list[float]:
        """P(next start = last_start + MIN_CYCLE + i), conditioned and recalibrated."""
        return list(self._p1)

    def next_start_distribution(self) -> dict[datetime.date, float]:
        if self.last_start is None or self.overdue:
            return {}
        return {self._date(i): p for i, p in enumerate(self._p1) if p > 1e-9}

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
        return mean_dur / self.mean_cycle

    def _intensity(self, horizon: int) -> list[float]:
        """Expected number of future period starts on each day offset (cycles >= 1).

        Offsets are days after ``last_start``. The first cycle uses the conditioned,
        recalibrated distribution; later cycles convolve each mu group's cycle pmf, so
        the shared uncertainty about the user's mean grows with horizon.
        """
        if self._intensity_cache and self._intensity_cache[0] >= horizon:
            return self._intensity_cache[1]
        u = [0.0] * (horizon + 1)
        groups = [((1 - DISRUPTED_PRIOR) * w, pmf) for w, pmf in self._fit.groups] + [
            (DISRUPTED_PRIOR, _disrupted_pmf())
        ]
        for w, pmf in groups:
            step = [(MIN_CYCLE + i, v) for i, v in enumerate(pmf) if v > 2e-5]
            norm = sum(v for _, v in step)
            step = [(length, v / norm) for length, v in step]
            cur = [0.0] * (horizon + 1)
            for i, v in enumerate(pmf):
                length = MIN_CYCLE + i
                if length <= horizon and self._unc[i] > 0:
                    cur[length] = w * v * self._p1[i] / self._unc[i]
            for _ in range(60):
                lo = next((d for d, v in enumerate(cur) if v > 1e-12), None)
                if lo is None:
                    break
                for d in range(lo, horizon + 1):
                    u[d] += cur[d]
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
        """P(bleeding) per date. Logged days are 1/0; the future uses the model.

        With no history, or for an overdue (lapsed) user, future dates get the
        long-run average rate: no reliable timing information exists.
        """
        if not dates:
            return {}
        rate = self.long_run_bleeding_rate()
        if self.last_start is None:
            return dict.fromkeys(dates, rate)
        surv = self._survival()
        logged = self._logged_bleeding_days()
        horizon = max(max((d - self.last_start).days for d in dates), MIN_CYCLE)
        u = [0.0] * (horizon + 1) if self.overdue else self._intensity(horizon)
        ongoing_no_end = self.last_end is None and self._ongoing()
        out: dict[datetime.date, float] = {}
        for d in dates:
            if d in logged:
                out[d] = 1.0
                continue
            off = (d - self.last_start).days
            if d < self.today:
                if self.last_end is None and 0 <= off < MAX_DURATION:
                    out[d] = surv[off]
                else:
                    out[d] = 0.0
                continue
            if self.overdue:
                out[d] = rate
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

    def point_and_intervals(
        self,
    ) -> tuple[int, tuple[int, int, float], tuple[int, int, float]]:
        return point_and_intervals(self._p1, self._truncated)

    def _is_late(self) -> bool:
        """Today is beyond the 90th percentile of the unconditioned cycle length."""
        if self.last_start is None or self._ongoing():
            return False
        if self.overdue:
            return True
        cdf_before_today = sum(self._unc[: max(self.age - MIN_CYCLE, 0)])
        return cdf_before_today >= 0.9

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
        if self.overdue:
            return {**base, "confidence": "overdue", "is_late": True}

        pmf = self._p1
        pt, i50, i80 = self.point_and_intervals()
        today = self.today
        p3 = sum(p for i, p in enumerate(pmf) if 0 <= (self._date(i) - today).days <= 2)
        dates = [today + datetime.timedelta(days=k) for k in range(horizon_days)]
        by_date = {self._date(i): p for i, p in enumerate(pmf)}
        bleed = self.bleeding_probability(dates)
        ov = self._ovulation_pmf(pmf)
        first_ov, last_ov = min(ov), max(ov)
        ov_dates = [
            first_ov + datetime.timedelta(days=k)
            for k in range((last_ov - first_ov).days + 1)
        ]
        ov_pmf = [ov.get(d, 0.0) for d in ov_dates]
        ov_pt = max(range(len(ov_pmf)), key=lambda i: (ov_pmf[i], -i))
        os_i, oe_i, _ = _hdi(ov_pmf, 0.8, ov_pt)
        ov_point = self._date(pt) - datetime.timedelta(days=round(LUTEAL_MEAN))

        def p_fertile(day: datetime.date) -> float:
            return sum(
                ov.get(day + datetime.timedelta(days=k), 0.0) for k in range(-1, 6)
            )

        return {
            **base,
            "most_likely_start": self._date(pt),
            "interval_50": {"start": self._date(i50[0]), "end": self._date(i50[1])},
            "interval_80": {"start": self._date(i80[0]), "end": self._date(i80[1])},
            "probability_next_3_days": min(p3, 1.0),
            "confidence": self.label(),
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
                "start": ov_point - datetime.timedelta(days=5),
                "end": ov_point + datetime.timedelta(days=1),
                "ovulation_date": ov_point,
                "ovulation_interval_80": {
                    "start": ov_dates[os_i],
                    "end": ov_dates[oe_i],
                },
            },
            "is_late": self._is_late(),
            "_interval_masses": {"50": i50[2], "80": i80[2]},
        }


class ForecastService:
    """Probabilistic period forecasts. Pure core plus database wrappers."""

    # --- pure core (no DB) -----------------------------------------------------------

    @staticmethod
    def fit(
        periods: list[PeriodTuple],
        today: datetime.date | None = None,
        calibration: dict[tuple[str, int], float] | None = None,
    ) -> FittedModel:
        """Fit the model on plain ``(start, end_or_None)`` tuples."""
        return FittedModel(periods, today or datetime.date.today(), calibration)

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
        """P(next period starts on date d), conditioned on today ({} if overdue)."""
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
