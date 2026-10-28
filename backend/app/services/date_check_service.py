"""Date Check: the chance of bleeding at some point during a date range.

Why not sum or max the daily probabilities?
-------------------------------------------
``p_bleeding(d)`` are marginals of strongly dependent events (a period covers several
consecutive days). Summing them counts one period many times; taking the max
under-counts when the range straddles a start. ``probability_any`` is instead computed
from the renewal structure of the forecast engine.

Method (exact under the engine's model, verified against Monte Carlo)
---------------------------------------
For a future range ``[a, b]``, "no bleeding day in the range" happens iff the last
period start ``s`` before ``a`` (a start *on* ``a`` is bleeding) belongs to a period
that has already ended before ``a`` **and** the next start after ``s`` falls after
``b``. These cases are mutually exclusive over ``s``, so::

    P(none) = P(logged period over before a) * P(next start > b | last start)
            + sum_g sum_{s = today .. a-1} u_g[s] * P(D <= a - s) * P_g(L > b - s)

* ``g`` indexes the engine's cycle-length groups (ordinary mean-cycle groups, the
  "disrupted" group and the skipped-log group). Each group keeps its own cycles
  together, so a user whose next cycle turns out long keeps long cycles afterwards.
  ``u_g[s]`` is the expected number of period starts on day ``s`` coming from group
  ``g`` (starts are >= 15 days apart, so it is a probability per group), and
  ``P_g(L > m)`` is the tail of that group's normalised cycle-length distribution.
* ``D`` is the period length (survival from the engine).
* the first term uses the engine's conditioned next-start distribution, so a late
  period shifts mass correctly.

``probability_any = 1 - P(none)``. The expression is monotone by construction:
growing the range on either side can only shrink P(none). It is also floored at the
largest daily ``p_bleeding`` (a true lower bound) so a one-day range returns exactly
that day's engine probability. Remaining approximation: period length is independent
of cycle length. ``tests/test_date_check.py`` compares the result with a Monte Carlo
simulation of the engine's own generative model (late, skipping, single-period and
ongoing users), tolerance 0.02.

Past days: logged bleeding days count as certain (1.0). A range that mixes past and
future combines the past part and the future part as independent, which is exact
under the model: past days are either logged (0/1, so the past part is certain), or
belong to an unclosed period older than the longest plausible period, which the
engine treats as already over, so the future part no longer depends on it.
"""

from __future__ import annotations

import datetime
import weakref

from app.models import Period
from app.services.forecast_service import LEARNING_CYCLES, MIN_CYCLE, ForecastService
from app.utils.exceptions import ValidationError

MAX_RANGE_DAYS = 60
MIN_DATE = datetime.date(1900, 1, 1)
MAX_DAYS_AHEAD = 366
MOST_LIKELY_MIN_P = 0.05
FLAT_AMPLITUDE = 0.08  # max-min of p_bleeding over one cycle below this = no signal

STATUS_OK = "ok"
STATUS_LEARNING = "learning"
STATUS_OVERDUE = "overdue"
STATUS_NO_DATA = "no_data"

TD = datetime.timedelta


class DateCheckService:
    """Probability of a period during a date range."""

    @staticmethod
    def validate_range(
        start: datetime.date,
        end: datetime.date,
        today: datetime.date | None = None,
        fields: tuple[str, str] = ("start", "end"),
    ) -> None:
        """Raise ValidationError if the range is not acceptable.

        ``fields`` names the request fields the errors are keyed by (``start``/``end``
        for the query string, ``start_date``/``end_date`` for event payloads).
        """
        f_start, f_end = fields
        today = today or datetime.date.today()
        errors: dict[str, list[str]] = {}
        if end < start:
            errors[f_end] = ["End date cannot be before start date."]
        elif (end - start).days + 1 > MAX_RANGE_DAYS:
            errors[f_end] = [f"Range cannot be longer than {MAX_RANGE_DAYS} days."]
        if start < MIN_DATE:
            errors[f_start] = [f"Dates before {MIN_DATE.year} are not supported."]
        elif (start - today).days > MAX_DAYS_AHEAD:
            errors[f_start] = [
                f"Start date cannot be more than {MAX_DAYS_AHEAD} days ahead."
            ]
        if errors:
            raise ValidationError(payload=errors)

    @staticmethod
    def load_model(user_id: int, today: datetime.date | None = None):
        """Fit the forecast model for a user (fit once, check many ranges)."""
        today = today or datetime.date.today()
        rows = Period.query.filter_by(user_id=user_id).order_by(Period.start_date).all()
        return ForecastService.fit([(p.start_date, p.end_date) for p in rows], today)

    @staticmethod
    def prime(model, last_day: datetime.date) -> None:
        """Warm the engine caches once for the farthest day that will be queried."""
        if model.last_start is None or model.overdue:
            return
        last_day = max(last_day, model.today)
        horizon = (last_day - model.last_start).days
        model.bleeding_probability([last_day])
        engine_view(model).groups(horizon)

    @staticmethod
    def check(
        user_id: int,
        start: datetime.date,
        end: datetime.date,
        today: datetime.date | None = None,
    ) -> dict:
        today = today or datetime.date.today()
        DateCheckService.validate_range(start, end, today)
        model = DateCheckService.load_model(user_id, today)
        return DateCheckService.check_with_model(model, start, end)

    @staticmethod
    def check_with_model(model, start: datetime.date, end: datetime.date) -> dict:
        """Date check against an already fitted model (no validation)."""
        today = model.today
        n = (end - start).days + 1
        base = {
            "start": start,
            "end": end,
            "probability_any": None,
            "days": [],
            "most_likely_days": None,
            "confidence": model.label() if model.last_start else "learning",
            "horizon_note": None,
            "includes_past_dates": start < today,
            "status": STATUS_OK,
            "reason": None,
            "cycles_used": model.cycles_used,
            "cycles_needed": LEARNING_CYCLES,
        }
        if model.last_start is None:
            return {
                **base,
                "status": STATUS_NO_DATA,
                "reason": "Log at least one period to get odds for a date range.",
            }
        if model.overdue:
            return {
                **base,
                "status": STATUS_OVERDUE,
                "confidence": "overdue",
                "reason": (
                    "Your last logged period was a long time ago, so there is no "
                    "reliable forecast. Log your latest period to get odds again."
                ),
            }

        dates = [start + TD(days=k) for k in range(n)]
        probs = model.bleeding_probability(dates)
        daily = [probs[d] for d in dates]
        p_any = _probability_any(model, start, end, daily)

        status = STATUS_OK
        reason = None
        if model.label() == "learning":
            status = STATUS_LEARNING
            to_go = LEARNING_CYCLES - model.cycles_used
            reason = (
                f"Only {model.cycles_used} full cycle(s) logged so far, so these odds "
                "lean on population averages. Log "
                f"{to_go} more period(s) for odds based on your own cycle."
            )
        note = None
        if profile_is_flat(model, start):
            note = "far ahead — odds are close to the long-run average"
        return {
            **base,
            "probability_any": round(p_any, 4),
            "days": [
                {"date": d, "p_bleeding": round(p, 4)}
                for d, p in zip(dates, daily, strict=True)
            ],
            "most_likely_days": _most_likely_days(dates, daily),
            "horizon_note": note,
            "status": status,
            "reason": reason,
        }


def profile_is_flat(model, start: datetime.date) -> bool:
    """True when the forecast has lost its shape around ``start``.

    Looks at one mean cycle of daily bleeding probabilities from ``start``: if the
    peak-to-trough amplitude is tiny the forecast carries no timing information (the
    odds are the long-run average) however many cycles ahead that is. Past/logged
    stretches are never flat.
    """
    if start < model.today:
        return False
    n = max(int(round(model.mean_cycle)), 21)
    dates = [start + TD(days=k) for k in range(n)]
    vals = list(model.bleeding_probability(dates).values())
    return max(vals) - min(vals) < FLAT_AMPLITUDE


def _most_likely_days(
    dates: list[datetime.date], daily: list[float]
) -> list[datetime.date] | None:
    """Up to 3 standout days, chronologically; None when no day stands out.

    A day qualifies if p >= 0.05 and p >= half of the range maximum. A profile that is
    flat (max - min < 0.03, e.g. far in the future) has no meaningful peak -> None.
    """
    top = max(daily)
    if top < MOST_LIKELY_MIN_P or top - min(daily) < 0.03:
        return None
    ranked = sorted(range(len(dates)), key=lambda i: (-daily[i], i))
    picked = [i for i in ranked[:3] if daily[i] >= max(MOST_LIKELY_MIN_P, top / 2)]
    return [dates[i] for i in sorted(picked)]


def _probability_any(
    model, start: datetime.date, end: datetime.date, daily: list[float]
) -> float:
    today = model.today
    floor = max(daily)
    if end < today:  # entirely in the past: logged data
        return floor
    p_past = max((p for d, p in zip_dates(start, daily) if d < today), default=0.0)
    a = max(start, today)
    if start == end:
        return floor
    p_future = 1.0 - _p_none_future(model, a, end)
    p = 1.0 - (1.0 - p_past) * (1.0 - p_future)
    return min(max(p, floor), 1.0)


def zip_dates(start: datetime.date, daily: list[float]):
    return ((start + TD(days=k), p) for k, p in enumerate(daily))


def _p_none_future(model, a: datetime.date, b: datetime.date) -> float:
    """P(no bleeding day in [a, b]) for a >= today (see module docstring)."""
    engine = engine_view(model)
    s0 = model.last_start
    ended = engine.logged_period_over_before(a)
    nxt = model.next_start_pmf()
    first = s0 + TD(days=MIN_CYCLE)
    after_b = sum(p for i, p in enumerate(nxt) if first + TD(days=i) > b)
    none = ended * after_b
    horizon = (b - s0).days
    groups = engine.groups(horizon)
    lo = max((model.today - s0).days, MIN_CYCLE)
    hi = (a - s0).days  # exclusive
    for off in range(lo, hi):
        ended_by = engine.ended_by(hi - off)
        remaining = horizon - off
        for u, tail in groups:
            w = u[off]
            if w > 1e-12:
                none += w * ended_by * _tail_gt(tail, remaining)
    return min(max(none, 0.0), 1.0)


def _tail_gt(tail: list[float], m: int) -> float:
    """P(L > m) from a tail array (tail[i] = P(L >= MIN_CYCLE + i))."""
    i = m + 1 - MIN_CYCLE
    if i <= 0:
        return 1.0
    if i >= len(tail):
        return 0.0
    return tail[i]


_VIEWS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def engine_view(model) -> _EngineView:
    """One cached adapter per fitted model (so many ranges share the same work)."""
    view = _VIEWS.get(model)
    if view is None:
        view = _VIEWS[model] = _EngineView(model)
    return view


class _EngineView:
    """Per-model cache of the engine's public start-intensity API.

    ``groups(horizon)`` -> [(u_g, tail_g)] where ``tail_g[i] = P_g(L >= MIN_CYCLE + i)``.
    """

    def __init__(self, model):
        self.m = model
        self._horizon = -1
        self._groups: list[tuple[list[float], list[float]]] = []

    def groups(self, horizon: int):
        if horizon > self._horizon:
            horizon = max(horizon, MIN_CYCLE)
            self._groups = [
                (g.u, _tail(g.step)) for g in self.m.start_intensities(horizon)
            ]
            self._horizon = horizon
        return self._groups

    def ended_by(self, k: int) -> float:
        """P(a period that started k days earlier is over): P(D <= k)."""
        return self.m.duration_cdf(k)

    def logged_period_over_before(self, a: datetime.date) -> float:
        """P(the most recent logged period has ended before day ``a``)."""
        m = self.m
        if m.last_end is not None:
            return 1.0 if m.last_end < a else 0.0
        if not m.ongoing:  # opened long ago and never closed: treated as over
            return 1.0
        return m.ongoing_duration_cdf((a - m.last_start).days, m.age + 1)


def _tail(step: list[tuple[int, float]]) -> list[float]:
    """tail[i] = P(L >= MIN_CYCLE + i) from a normalised (length, prob) pmf."""
    top = max(length for length, _ in step)
    tail = [0.0] * (top - MIN_CYCLE + 2)
    for length, p in step:
        tail[length - MIN_CYCLE] += p
    for i in range(len(tail) - 2, -1, -1):
        tail[i] += tail[i + 1]
    return tail


def cycle_start_pmfs(model, kmax: int, horizon: int) -> list[list[float]]:
    """P(the k-th future period starts on day offset s), k = 1..kmax.

    Offsets are days after the last logged start. Built from the engine's public
    per-group data: a group's share of the first cycle is its weight times its pmf at
    the first-cycle length, relative to the unconditioned mixture (so a late period
    reweights the groups); later cycles convolve that group's own cycle pmf. Summed
    over all k this reproduces ``model.intensity(horizon)`` (tested). Mass beyond
    ``horizon`` is dropped, not renormalised.
    """
    groups = model.start_intensities(horizon)
    p1 = model.next_start_pmf()
    steps = [dict(g.step) for g in groups]
    out = [[0.0] * (horizon + 1) for _ in range(kmax)]
    unc: dict[int, float] = {}
    for g, step in zip(groups, steps, strict=True):
        for length, q in step.items():
            unc[length] = unc.get(length, 0.0) + g.weight * q
    for g, step in zip(groups, steps, strict=True):
        cur = [0.0] * (horizon + 1)
        for i, p in enumerate(p1):
            length = MIN_CYCLE + i
            if length > horizon or p <= 0:
                continue
            if unc.get(length, 0.0) > 0:
                cur[length] = g.weight * step.get(length, 0.0) * p / unc[length]
        for k in range(kmax):
            for d, v in enumerate(cur):
                out[k][d] += v
            if k + 1 == kmax:
                break
            nxt = [0.0] * (horizon + 1)
            for d, v in enumerate(cur):
                if v <= 1e-12:
                    continue
                for length, q in step.items():
                    if d + length > horizon:
                        continue
                    nxt[d + length] += v * q
            cur = nxt
    return out


def narrowest_window(pmf: list[float], mass: float) -> tuple[int, int, float] | None:
    """Narrowest contiguous index window holding at least ``mass`` (None if the
    total is below it). Ties go to the window with more mass."""
    if sum(pmf) < mass:
        return None
    best = None
    lo, acc = 0, 0.0
    for hi, v in enumerate(pmf):
        acc += v
        while acc - pmf[lo] >= mass:
            acc -= pmf[lo]
            lo += 1
        if acc >= mass:
            key = (hi - lo, -acc)
            if best is None or key < best[0]:
                best = (key, lo, hi, acc)
    return None if best is None else (best[1], best[2], best[3])
