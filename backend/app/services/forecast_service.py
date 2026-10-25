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

DISRUPTED_PRIOR = 0.04  # prior mean P(cycle is disrupted/very long); updated per user
DISRUPTED_PRIOR_N = 12.5  # prior pseudo-gaps behind that mean
# Skipped logs (two cycles merged into one gap): a two-class model of the user's skip
# habit. Most users almost never skip; a minority skips often. Their own count of
# excluded long gaps decides which class is likely.
SKIP_CLASS_PRIOR = 0.10  # P(user is a habitual skipper)
SKIP_RATE_HABITUAL = 0.20
SKIP_RATE_RARE = 0.004
MAX_SKIP_WEIGHT = 0.4
MAX_DISRUPTED_WEIGHT = 0.25
DISRUPTED_MIN = 30
DISRUPTED_SCALES = ((0.7, 6.0), (0.3, 25.0))  # (share, days): short slip / long gap

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
MIN_INTENSITY_HORIZON = 400  # intensities are computed once for at least this

# Recalibration keyed by (confidence label, age bin, has-excluded-gaps), fitted by
# scripts/calibrate_forecast.py on randomised synthetic worlds (never evaluation seeds).
# CALIBRATION: tempering exponent T, p -> p**(1/T), set so the 80% interval covers 80%.
CALIBRATION: dict[tuple[str, int, bool], float] = {
    ("irregular", 0, False): 1.15,
    ("irregular", 0, True): 1.0,
    ("irregular", 1, False): 1.1,
    ("irregular", 1, True): 0.95,
    ("irregular", 2, False): 1.15,
    ("irregular", 2, True): 0.9,
    ("learning", 0, False): 1.15,
    ("learning", 0, True): 0.95,
    ("learning", 1, False): 1.15,
    ("learning", 1, True): 0.9,
    ("learning", 2, False): 1.1,
    ("learning", 2, True): 0.85,
    ("regular", 0, False): 1.0,
    ("regular", 0, True): 0.9,
    ("regular", 1, False): 1.0,
    ("regular", 1, True): 0.9,
    ("regular", 2, False): 1.05,
    ("regular", 2, True): 0.85,
    ("variable", 0, False): 1.1,
    ("variable", 0, True): 0.95,
    ("variable", 1, False): 1.15,
    ("variable", 1, True): 0.9,
    ("variable", 2, False): 1.1,
    ("variable", 2, True): 0.85,
}

# CALIBRATION_Q50: model mass of the displayed "50%" interval, set so it covers 50%.
CALIBRATION_Q50: dict[tuple[str, int, bool], float] = {
    ("irregular", 0, False): 0.5,
    ("irregular", 0, True): 0.56,
    ("irregular", 1, False): 0.5,
    ("irregular", 1, True): 0.52,
    ("irregular", 2, False): 0.48,
    ("irregular", 2, True): 0.52,
    ("learning", 0, False): 0.48,
    ("learning", 0, True): 0.56,
    ("learning", 1, False): 0.48,
    ("learning", 1, True): 0.56,
    ("learning", 2, False): 0.46,
    ("learning", 2, True): 0.46,
    ("regular", 0, False): 0.46,
    ("regular", 0, True): 0.48,
    ("regular", 1, False): 0.46,
    ("regular", 1, True): 0.5,
    ("regular", 2, False): 0.4,
    ("regular", 2, True): 0.42,
    ("variable", 0, False): 0.5,
    ("variable", 0, True): 0.52,
    ("variable", 1, False): 0.48,
    ("variable", 1, True): 0.52,
    ("variable", 2, False): 0.48,
    ("variable", 2, True): 0.52,
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
    """Late/disrupted cycle: starts at least DISRUPTED_MIN days, slow exponential tail.

    70% of the mass is a short slip (scale 6 days: a few days late), 30% a long
    disruption (scale 25 days).
    """
    raw = [
        sum(w * math.exp(-(k - DISRUPTED_MIN) / sc) / sc for w, sc in DISRUPTED_SCALES)
        if k >= DISRUPTED_MIN
        else 0.0
        for k in range(MIN_CYCLE, MAX_CYCLE + 1)
    ]
    t = sum(raw)
    return tuple(r / t for r in raw)


@dataclass(frozen=True)
class StartGroup:
    """One latent group of the start-time mixture (see ``start_intensities``)."""

    weight: float  # mixture weight of the group for the next gap
    u: list[float]  # P(a period starts on day offset s) through this group
    step: list[tuple[int, float]]  # normalised cycle-length pmf: (length, prob)

    def p_longer(self, n: int) -> float:
        """P(cycle length > n) for this group."""
        return sum(p for length, p in self.step if length > n)


@dataclass(frozen=True)
class _CycleFit:
    groups: tuple[tuple[float, tuple[float, ...]], ...]  # (weight, pmf) per mu group
    main: tuple[float, ...]  # posterior predictive of an ordinary cycle
    skip2: tuple[float, ...]  # a skipped log: two ordinary cycles merged into one gap
    skip3: tuple[float, ...]  # two skipped logs in a row: three cycles in one gap
    pi_skip: float  # P(next logged gap swallows a skipped log)
    pi_disrupted: float  # P(next cycle is disrupted/very long)


def _skip_probability(n_skipped: int, n_gaps: int) -> float:
    """Posterior mean rate of skipped logs under the two-class skip-habit model."""
    s, r = SKIP_RATE_HABITUAL, SKIP_RATE_RARE
    log_hab = n_skipped * math.log(s) + (n_gaps - n_skipped) * math.log(1 - s)
    log_rare = n_skipped * math.log(r) + (n_gaps - n_skipped) * math.log(1 - r)
    odds = SKIP_CLASS_PRIOR / (1 - SKIP_CLASS_PRIOR) * math.exp(log_hab - log_rare)
    p_hab = odds / (1 + odds)
    return p_hab * s + (1 - p_hab) * r


def _upward_outliers(cycles: tuple[int, ...]) -> int:
    if len(cycles) < 4:
        return 0
    med = median(cycles)
    mad = median([abs(c - med) for c in cycles])
    scale = max(1.4826 * mad, 2.0)
    return sum(1 for c in cycles if (c - med) / scale > HUBER_C)


@functools.lru_cache(maxsize=2048)
def _fit_cycles(cycles: tuple[int, ...], n_excluded: int = 0) -> _CycleFit:
    """Posterior over the (mu, sigma) grid for chronological cycle lengths.

    ``n_excluded`` is how many gaps were thrown out as forgotten logs; together with
    the number of upward outliers it sets this user's own skip/disruption weights.
    """
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

    # A skipped log merges two cycles: sum of two draws from the ordinary predictive.
    skip2 = [0.0] * n_pmf
    for i, a in enumerate(main):
        if a < 1e-7:
            continue
        for j in range(n_pmf - MIN_CYCLE - i):
            skip2[i + j + MIN_CYCLE] += a * main[j]
    t = sum(skip2)
    skip2 = [v / t for v in skip2]
    skip3 = [0.0] * n_pmf
    for i, a in enumerate(skip2):
        if a < 1e-7:
            continue
        for j in range(n_pmf - MIN_CYCLE - i):
            skip3[i + j + MIN_CYCLE] += a * main[j]
    t = sum(skip3)
    skip3 = [v / t for v in skip3] if t > 0 else skip2

    n_gaps = len(cycles) + n_excluded
    pi_skip = min(_skip_probability(n_excluded, n_gaps), MAX_SKIP_WEIGHT)
    pi_dis = min(
        (DISRUPTED_PRIOR * DISRUPTED_PRIOR_N + _upward_outliers(cycles))
        / (DISRUPTED_PRIOR_N + n_gaps),
        MAX_DISRUPTED_WEIGHT,
    )
    return _CycleFit(
        tuple(groups), tuple(main), tuple(skip2), tuple(skip3), pi_skip, pi_dis
    )


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


def mode_index(pmf: list[float]) -> int:
    return max(range(len(pmf)), key=lambda i: (pmf[i], -i))


MODE_VALLEY_RATIO = 0.5  # a dip below this fraction of the lower peak separates modes
MODE_MIN_MASS = 0.12  # a separate mode must hold at least this much probability


def mode_components(pmf: list[float]) -> list[tuple[int, int, float]]:
    """Split a pmf into its significant modes: [(start, end, mass)] left to right.

    Modes are separated at valleys deeper than MODE_VALLEY_RATIO of the lower
    neighbouring peak (on a 3-day smoothed pmf); components lighter than
    MODE_MIN_MASS are folded into their neighbour.
    """
    n = len(pmf)
    sm = [
        (pmf[max(i - 1, 0)] + pmf[i] + pmf[min(i + 1, n - 1)]) / 3.0 for i in range(n)
    ]
    peaks = [
        i
        for i in range(n)
        if sm[i] > 0
        and (i == 0 or sm[i] >= sm[i - 1])
        and (i == n - 1 or sm[i] > sm[i + 1])
    ]
    if not peaks:
        return [(0, n - 1, 1.0)]
    kept = [peaks[0]]
    valleys: list[int] = []
    for pk in peaks[1:]:
        last = kept[-1]
        v = min(range(last, pk + 1), key=lambda i: sm[i])
        if sm[v] < MODE_VALLEY_RATIO * min(sm[last], sm[pk]):
            kept.append(pk)
            valleys.append(v)
        elif sm[pk] > sm[last]:
            kept[-1] = pk
    bounds = [0, *[v + 1 for v in valleys], n]
    comps = [
        (bounds[i], bounds[i + 1] - 1, sum(pmf[bounds[i] : bounds[i + 1]]))
        for i in range(len(kept))
    ]
    # Fold light components into the heavier neighbour.
    while len(comps) > 1:
        i = min(range(len(comps)), key=lambda k: comps[k][2])
        if comps[i][2] >= MODE_MIN_MASS:
            break
        j = (
            i - 1
            if i > 0 and (i == len(comps) - 1 or comps[i - 1][2] >= comps[i + 1][2])
            else i + 1
        )
        lo, hi = min(i, j), max(i, j)
        merged = (comps[lo][0], comps[hi][1], comps[lo][2] + comps[hi][2])
        comps[lo : hi + 1] = [merged]
    return comps


def is_multimodal(pmf: list[float]) -> bool:
    return len(mode_components(pmf)) > 1


def headline_index(pmf: list[float]) -> int:
    """User-facing point estimate: the mode, or if multimodal the near-term mode.

    With two distinct possibilities (say "a few days late" and "a forgotten log, so
    two cycles") the argmax can sit on a far, narrow spike. The headline then is the
    median of the EARLIEST significant mode (what the user should plan around);
    ``secondary_window`` reports the other mode and the probability it holds.
    """
    comps = mode_components(pmf)
    if len(comps) == 1:
        return mode_index(pmf)
    s, e, mass = comps[0]
    acc = 0.0
    for i in range(s, e + 1):
        acc += pmf[i]
        if acc >= mass / 2:
            return i
    return e


def secondary_component(pmf: list[float], point: int) -> tuple[int, int, float] | None:
    """The heaviest significant mode not containing ``point``, trimmed to its bulk."""
    others = [c for c in mode_components(pmf) if not c[0] <= point <= c[1]]
    if not others:
        return None
    s, e, mass = max(others, key=lambda c: c[2])
    peak = max(pmf[s : e + 1])
    while s < e and pmf[s] < 0.02 * peak:
        s += 1
    while e > s and pmf[e] < 0.02 * peak:
        e -= 1
    return s, e, mass


def point_and_intervals(
    pmf: list[float], truncated: bool = False, q50: float = 0.5
) -> tuple[int, tuple[int, int, float], tuple[int, int, float]]:
    """Headline point plus nested 50% and 80% index intervals that contain it.

    ``q50`` is the model mass of the "50%" interval; recalibration lowers it where
    day-discretisation and a pinned mode make a 0.5-mass interval over-cover.
    """
    pt = headline_index(pmf)
    i50 = _hdi(pmf, q50, pt)
    i80 = _hdi(pmf, 0.8, pt)
    if i80[0] > i50[0] or i80[1] < i50[1]:  # keep nested
        s, e = min(i80[0], i50[0]), max(i80[1], i50[1])
        i80 = (s, e, sum(pmf[s : e + 1]))
    return pt, i50, i80


def error_point_index(pmf: list[float], truncated: bool = False) -> int:
    """Best single-date guess for absolute error: the median of the distribution.

    ``most_likely_start`` is the mode (what is most probable); the median
    (``median_start``) minimises expected absolute error, and is what backtests
    use for MAE.
    """
    return _median_index(pmf)


# Backwards-compatible name.
point_index = error_point_index


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
        calibration: dict[tuple[str, int, bool], float] | None = None,
    ):
        # A period dated tomorrow means the client's clock is ahead of the server's
        # (time zones): treat it as started rather than ignoring it.
        if periods and max(p[0] for p in periods) == today + datetime.timedelta(days=1):
            today = today + datetime.timedelta(days=1)
        self.today = today
        self.calibration = CALIBRATION if calibration is None else calibration
        self.periods = _clean_periods(periods)
        self.starts = [p[0] for p in self.periods]
        self.last_start = self.starts[-1] if self.starts else None
        self.last_end = self.periods[-1][1] if self.periods else None
        self.age = (today - self.last_start).days if self.last_start else 0

        cycles, self.cycles_excluded = _cycle_lengths(self.starts)
        self.cycles_used = len(cycles)
        self._fit = _fit_cycles(tuple(cycles), self.cycles_excluded)
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
        # Full unconditioned next-gap distribution: ordinary cycle, a skipped log
        # (two cycles merged), or a disrupted/very long cycle, with per-user weights.
        f = self._fit
        self.pi_skip, self.pi_disrupted = f.pi_skip, f.pi_disrupted
        w_main = 1 - f.pi_skip - f.pi_skip**2 - f.pi_disrupted
        dis = _disrupted_pmf()
        self._unc = [
            w_main * m + f.pi_disrupted * d + f.pi_skip * k + f.pi_skip**2 * k3
            for m, d, k, k3 in zip(f.main, dis, f.skip2, f.skip3, strict=True)
        ]
        self._build_start_pmf()
        self._intensity_cache: tuple[int, list[StartGroup]] | None = None

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
        return self._label

    confidence = label

    def _compute_label(self) -> str:
        if self.overdue:
            return "overdue"
        if self.cycles_used < LEARNING_CYCLES:
            return "learning"
        sd = self._main_sd
        if self._is_late():
            # Late: the spread that matters is the conditioned one, not the ordinary one.
            sd = max(sd, _mean_sd(self._raw, MIN_CYCLE)[1])
        if sd <= SD_THRESHOLDS[0]:
            return "regular"
        if sd <= SD_THRESHOLDS[1]:
            return "variable"
        return "irregular"

    @property
    def has_excluded(self) -> bool:
        """True if some of this user's gaps looked like forgotten logs."""
        return self.cycles_excluded > 0

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
                self._truncated = False
            else:
                self._raw = [0.0] * first + [v / mass for v in tail]
        self._label = self._compute_label()
        bin_ = age_bin(self.age)
        cal = self.calibration
        excl = self.has_excluded
        self._temperature = cal.get(
            (self._label, bin_, excl), cal.get((self._label, bin_, False), 1.0)
        )
        self._p1 = _temper(self._raw, self._temperature)
        self._q50 = (
            CALIBRATION_Q50.get((self._label, bin_, excl), 0.5)
            if self.calibration is CALIBRATION
            else 0.5
        )

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

    def start_intensities(self, horizon: int) -> list[StartGroup]:
        """Per latent group: when periods start, and that group's cycle-length pmf.

        One :class:`StartGroup` per mean-group of the posterior, plus the disrupted
        and skipped-log groups. ``u[s]`` is the probability that a future period
        (first or later cycle, offsets are days after the last logged start) starts
        on day ``s`` through this group, so ``sum(g.u[s] for g in groups)`` is the
        combined start intensity (see :meth:`intensity`). ``step`` is the group's
        normalised cycle-length pmf, for questions like "no period starts in
        (s, b]" -> ``P(L > b - s)`` via :meth:`StartGroup.p_longer`.

        Computed once for ``max(horizon, MIN_INTENSITY_HORIZON)`` days and cached, so
        repeated calls in any order are cheap. Offsets beyond ``horizon`` are cut.
        """
        if self._intensity_cache is None or self._intensity_cache[0] < horizon:
            self._intensity_cache = self._compute_groups(
                max(horizon, MIN_INTENSITY_HORIZON)
            )
        return [
            StartGroup(g.weight, g.u[: horizon + 1], g.step)
            for g in self._intensity_cache[1]
        ]

    def intensity(self, horizon: int) -> list[float]:
        """Expected number of future period starts on each day offset (cycles >= 1)."""
        groups = self.start_intensities(horizon)
        return [sum(g.u[d] for g in groups) for d in range(horizon + 1)]

    def _intensity(self, horizon: int) -> list[float]:
        return self.intensity(horizon)

    def _compute_groups(self, horizon: int) -> tuple[int, list[StartGroup]]:
        """The first cycle uses the conditioned, recalibrated distribution; later
        cycles convolve each group's cycle pmf, so the shared uncertainty about the
        user's mean grows with horizon."""
        f = self._fit
        w_main = 1 - f.pi_skip - f.pi_skip**2 - f.pi_disrupted
        groups = (
            [(w_main * w, pmf) for w, pmf in f.groups]
            + [(f.pi_disrupted, _disrupted_pmf())]
            + [(f.pi_skip, f.skip2)]
            + [(f.pi_skip**2, f.skip3)]
        )
        out = []
        for w, pmf in groups:
            u = [0.0] * (horizon + 1)
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
            out.append(StartGroup(w, u, step))
        return horizon, out

    # --- period length (public) ------------------------------------------------

    def duration_cdf(self, k: int) -> float:
        """P(period lasts at most ``k`` days), ``k`` >= 0."""
        return 1.0 - self.duration_survival(k)

    def duration_survival(self, k: int) -> float:
        """P(period lasts more than ``k`` days), ``k`` >= 0."""
        if k < MIN_DURATION:
            return 1.0
        return sum(self._duration_pmf[k - MIN_DURATION + 1 :])

    def ongoing_duration_cdf(self, k: int, days_so_far: int) -> float:
        """P(duration <= k | the period is still going after ``days_so_far`` days).

        For an open period that is under way (``days_so_far`` = days bled so far,
        including today). Returns 1.0 for k beyond the longest plausible period.
        """
        alive = self.duration_survival(days_so_far - 1)  # P(D >= days_so_far)
        if alive <= 1e-12:
            return 1.0 if k >= days_so_far else 0.0
        if k < days_so_far:
            return 0.0
        return 1.0 - self.duration_survival(k) / alive

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

    @property
    def ongoing(self) -> bool:
        return self._ongoing()

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
        u = [0.0] * (horizon + 1) if self.overdue else self.intensity(horizon)
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
        return point_and_intervals(self._p1, self._truncated, self._q50)

    def _secondary_window(self, point: int) -> dict | None:
        """The other mode of a multimodal start distribution, if any."""
        comp = secondary_component(self._p1, point)
        if comp is None:
            return None
        s, e, mass = comp
        return {
            "start": self._date(s),
            "end": self._date(e),
            "probability": round(mass, 4),
        }

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
            "median_start": None,
            "secondary_window": None,
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
            "median_start": self._date(_median_index(pmf)),
            "secondary_window": self._secondary_window(pt),
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
        calibration: dict[tuple[str, int, bool], float] | None = None,
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
