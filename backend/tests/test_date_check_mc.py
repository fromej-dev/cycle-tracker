"""Date Check against a Monte Carlo simulation of the forecast engine's own model.

The simulator draws a first cycle from the engine's conditioned next-start
distribution, picks the cycle-length group (ordinary / disrupted / skipped logs) in
proportion to its posterior weight given that cycle, then keeps drawing later cycles
from that group, with period lengths from the engine's duration distribution. It is
independent of the closed-form formula in ``DateCheckService``.
"""

import bisect
import datetime
import random

import pytest

from app.services import ForecastService
from app.services.date_check_service import DateCheckService
from app.services.forecast_service import MAX_DURATION, MIN_CYCLE

D = datetime.date
TD = datetime.timedelta
TODAY = D(2026, 10, 25)
N = 5000
TOL = 0.02


def mk(last_start, gaps, dur=5, open_last=False):
    starts = [last_start]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    out = []
    for i, s in enumerate(reversed(starts)):
        end = None if (open_last and i == len(starts) - 1) else s + TD(days=dur - 1)
        out.append((s, end))
    return out


def _cum(pmf):
    acc, out = 0.0, []
    for v in pmf:
        acc += v
        out.append(acc)
    return out


def _draw(cum, rng):
    return min(bisect.bisect_left(cum, rng.random() * cum[-1]), len(cum) - 1)


def simulate(model, max_off, n, seed):
    """Sets of bleeding day offsets (days after the last logged start).

    Uses only the engine's public API: ``start_intensities`` (group weights and cycle
    pmfs), ``next_start_pmf`` and ``duration_cdf``.
    """
    rng = random.Random(seed)
    groups = model.start_intensities(MIN_CYCLE)
    steps = []
    unc: dict[int, float] = {}
    for g in groups:
        pmf = dict(g.step)
        steps.append(pmf)
        for length, q in pmf.items():
            unc[length] = unc.get(length, 0.0) + g.weight * q
    step_cum = [(sorted(pmf), _cum([pmf[k] for k in sorted(pmf)])) for pmf in steps]
    p1 = model.next_start_pmf()
    first_cum = _cum(p1)
    durations = list(range(1, MAX_DURATION + 1))
    dur_pmf = [model.duration_cdf(d) - model.duration_cdf(d - 1) for d in durations]
    dur_cum = _cum(dur_pmf)
    out = []
    for _ in range(n):
        bleed: set[int] = set()
        if model.last_end is not None:
            bleed.update(range((model.last_end - model.last_start).days + 1))
        elif model.age < MAX_DURATION:  # open period: length > age, given so far
            while True:
                d0 = _draw(dur_cum, rng) + 1
                if d0 > model.age:
                    break
            bleed.update(range(d0))
        i1 = _draw(first_cum, rng)
        length1 = MIN_CYCLE + i1
        weights = [g.weight * steps[j].get(length1, 0.0) for j, g in enumerate(groups)]
        g = _draw(_cum(weights), rng)
        s = length1
        while s <= max_off:
            d = _draw(dur_cum, rng) + 1
            bleed.update(range(s, min(s + d, max_off + 1)))
            lengths, cum = step_cum[g]
            s += lengths[_draw(cum, rng)]
        out.append(bleed)
    return out


USERS = {
    "late": lambda: mk(TODAY - TD(days=38), [28] * 8),
    "skipper": lambda: mk(TODAY - TD(days=20), [28, 56, 28, 28, 55, 28]),
    "single": lambda: mk(TODAY - TD(days=8), []),
    "ongoing_open": lambda: mk(TODAY - TD(days=2), [28] * 6, open_last=True),
    "regular": lambda: mk(TODAY - TD(days=10), [28] * 8),
}
RANGES = [(0, 14), (3, 7), (20, 30), (45, 14), (90, 30), (150, 14), (250, 30)]


@pytest.mark.parametrize("name", list(USERS))
def test_probability_any_matches_monte_carlo(name):
    model = ForecastService.fit(USERS[name](), TODAY)
    assert not model.overdue
    max_off = (TODAY - model.last_start).days + 320
    sims = simulate(model, max_off, N, seed=20261025)
    worst = 0.0
    for off, length in RANGES:
        a = TODAY + TD(days=off)
        b = a + TD(days=length - 1)
        oa, ob = (a - model.last_start).days, (b - model.last_start).days
        mc = sum(1 for s in sims if any(oa <= x <= ob for x in s)) / N
        got = DateCheckService.check_with_model(model, a, b)["probability_any"]
        worst = max(worst, abs(got - mc))
        assert got == pytest.approx(mc, abs=TOL), (name, off, length, got, mc)
    assert worst <= TOL
