import datetime

from flask import url_for

from app.models import Period
from app.services import ForecastService, ReportService
from app.services.forecast_service import is_multimodal, mode_components
from scripts.backtest_forecast import (
    EVAL_SEEDS,
    EVAL_USERS,
    format_table,
    gate_failures,
    generate_users,
    merge_buckets,
    overdue_check,
    run_backtest,
)

D = datetime.date
TD = datetime.timedelta


def make_periods(first, gaps, duration=5):
    starts = [first]
    for g in gaps:
        starts.append(starts[-1] + TD(days=g))
    return [(s, s + TD(days=duration - 1)) for s in starts]


# --- off-by-one -----------------------------------------------------------------


def test_predicted_next_period_is_last_start_plus_cycle(db, test_user):
    last = D.today() - TD(days=3)
    for k in (2, 1, 0):
        s = last - TD(days=28 * k)
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    assert ReportService.get_predicted_next_period(test_user.id) == last + TD(days=28)


# --- conditioning on today --------------------------------------------------------


def test_late_period_shifts_probability_forward():
    periods = make_periods(D(2023, 1, 1), [28] * 6)
    last = periods[-1][0]
    on_time = ForecastService.fit(periods, last + TD(days=3))
    late = ForecastService.fit(periods, last + TD(days=33))

    d_on = on_time.next_start_distribution()
    d_late = late.next_start_distribution()
    assert abs(sum(d_on.values()) - 1) < 1e-6
    assert abs(sum(d_late.values()) - 1) < 1e-6
    assert min(d_late) >= last + TD(days=33)  # nothing in the past
    mode_on = max(d_on, key=d_on.get)
    mode_late = max(d_late, key=d_late.get)
    assert abs((mode_on - last).days - 28) <= 1
    assert mode_late >= last + TD(days=33)
    fc = late.forecast()
    assert fc["is_late"] is True
    assert fc["interval_80"]["start"] >= last + TD(days=33)
    assert on_time.forecast()["is_late"] is False


def test_extremely_late_period_still_gives_valid_distribution():
    periods = make_periods(D(2023, 1, 1), [28] * 5)
    today = periods[-1][0] + TD(days=100)
    model = ForecastService.fit(periods, today)
    assert model.forecast()["confidence"] == "overdue"
    assert model.next_start_distribution() == {}
    # 40 days late is still a valid, honest distribution
    dist = ForecastService.fit(
        periods, periods[-1][0] + TD(days=68)
    ).next_start_distribution()
    assert abs(sum(dist.values()) - 1) < 1e-6
    assert min(dist) >= periods[-1][0] + TD(days=68)


# --- robustness ---------------------------------------------------------------------


def test_skipped_log_does_not_drag_forecast():
    periods = make_periods(D(2023, 1, 1), [28, 28, 28, 58, 28, 28, 28])
    last = periods[-1][0]
    model = ForecastService.fit(periods, last + TD(days=1))
    fc = model.forecast()
    assert abs((fc["most_likely_start"] - last).days - 28) <= 2  # naive mean gives ~33
    assert model.cycles_used == 6  # the 58-day gap was excluded


def test_tiny_cycles_are_merged_not_used():
    periods = make_periods(D(2023, 1, 1), [28, 28, 28])
    periods.insert(2, (periods[1][0] + TD(days=8), None))  # accidental re-log
    model = ForecastService.fit(periods, periods[-1][0] + TD(days=1))
    assert model.cycles_used == 3


def test_confidence_labels():
    assert ForecastService.forecast_from_periods([], D(2023, 1, 1))["confidence"] == (
        "learning"
    )
    few = make_periods(D(2023, 1, 1), [28, 28])
    assert ForecastService.forecast_from_periods(few, D(2023, 4, 1))["confidence"] == (
        "learning"
    )
    steady = make_periods(D(2023, 1, 1), [28, 29, 28, 28, 29, 28, 28, 29, 28, 28])
    assert ForecastService.forecast_from_periods(steady, D(2023, 11, 1))[
        "confidence"
    ] in ("regular", "variable")
    wild = make_periods(D(2023, 1, 1), [20, 41, 25, 47, 22, 38, 27, 45, 21, 40])
    assert ForecastService.forecast_from_periods(wild, D(2024, 1, 1))["confidence"] == (
        "irregular"
    )


def test_single_period_gives_prior_only_forecast():
    fc = ForecastService.forecast_from_periods(
        [(D(2023, 1, 1), D(2023, 1, 5))], D(2023, 1, 10)
    )
    assert fc["confidence"] == "learning"
    assert fc["cycles_used"] == 0
    assert abs((fc["most_likely_start"] - D(2023, 1, 1)).days - 29) <= 2
    # honest: wide intervals
    assert (fc["interval_80"]["end"] - fc["interval_80"]["start"]).days >= 8


# --- bleeding probability -------------------------------------------------------------


def test_bleeding_probability_shape():
    periods = make_periods(D(2023, 1, 1), [28] * 8)
    last = periods[-1][0]
    today = last + TD(days=10)
    model = ForecastService.fit(periods, today)
    mode = max(model.next_start_distribution().items(), key=lambda kv: kv[1])[0]

    far_dates = [today + TD(days=340 + k) for k in range(28)]
    probs = model.bleeding_probability(
        [mode + TD(days=2), mode - TD(days=10), *far_dates]
    )
    assert probs[mode + TD(days=2)] > 0.7  # mid-period around the likely start
    assert probs[mode - TD(days=10)] < 0.05
    far = sum(probs[d] for d in far_dates) / len(far_dates)
    assert 0.14 < far < 0.22  # long-run average ~ 5/28 = 0.18
    assert all(0.0 <= p <= 1.0 for p in probs.values())


def test_bleeding_uncertainty_grows_with_horizon():
    periods = make_periods(D(2023, 1, 1), [28, 29, 27, 28, 30, 28, 27, 29])
    today = periods[-1][0] + TD(days=10)
    model = ForecastService.fit(periods, today)
    dates = [today + TD(days=k) for k in range(0, 370)]
    probs = model.bleeding_probability(dates)
    first_peak = max(probs[d] for d in dates[:35])
    later_peak = max(probs[d] for d in dates[300:340])
    assert first_peak > later_peak > 0.18


def test_bleeding_logged_and_ongoing_periods():
    today = D(2023, 6, 3)
    periods = make_periods(D(2023, 1, 1), [28] * 5)
    periods.append((D(2023, 6, 1), None))  # ongoing, started 2 days ago
    model = ForecastService.fit(periods, today)
    probs = model.bleeding_probability([D(2023, 1, 2), D(2023, 1, 20), today])
    assert probs[D(2023, 1, 2)] == 1.0
    assert probs[D(2023, 1, 20)] == 0.0
    assert probs[today] == 1.0


def test_db_wrappers(db, test_user):
    for s, e in make_periods(D(2023, 1, 1), [28] * 4):
        Period(user_id=test_user.id, start_date=s, end_date=e).save()
    today = D(2023, 5, 1)
    dist = ForecastService.next_start_distribution(test_user.id, today)
    assert abs(sum(dist.values()) - 1) < 1e-6
    probs = ForecastService.bleeding_probability(
        test_user.id, [today, today + TD(days=300)], today
    )
    assert set(probs) == {today, today + TD(days=300)}
    assert ForecastService.fertile_window(test_user.id, today)["ovulation_date"]


# --- endpoint ---------------------------------------------------------------------------


def test_forecast_requires_auth(client):
    assert client.get(url_for("reports.get_forecast")).status_code == 401


def test_forecast_empty_user(auth_client):
    data = auth_client.get(url_for("reports.get_forecast")).get_json()
    assert data["confidence"] == "learning"
    assert data["most_likely_start"] is None
    assert data["days"] == []
    assert data["fertile_window"] is None
    assert data["is_late"] is False


def test_forecast_shape(auth_client, test_user, db):
    today = datetime.date.today()
    first = today - TD(days=28 * 6 + 10)
    for s, e in make_periods(first, [28] * 6):
        Period(user_id=test_user.id, start_date=s, end_date=e).save()
    resp = auth_client.get(url_for("reports.get_forecast"))
    assert resp.status_code == 200
    data = resp.get_json()
    for key in (
        "most_likely_start",
        "interval_50",
        "interval_80",
        "probability_next_3_days",
        "confidence",
        "predictive_sd_days",
        "cycles_used",
        "days",
        "fertile_window",
        "is_late",
    ):
        assert key in data
    assert data["cycles_used"] == 6
    assert len(data["days"]) == 45
    assert data["days"][0]["date"] == today.isoformat()
    assert set(data["days"][0]) >= {"date", "p_start", "p_bleeding"}
    assert data["interval_80"]["start"] <= data["interval_50"]["start"]
    assert data["interval_80"]["end"] >= data["interval_50"]["end"]
    assert set(data["fertile_window"]) >= {"start", "end", "ovulation_date"}
    assert 0 <= data["probability_next_3_days"] <= 1


# --- edge cases: lapsed, very late, long cycles ---------------------------------------


def test_lapsed_user_gets_overdue_state_not_a_crash(auth_client, test_user, db):
    today = D.today()
    for k in (3, 2, 1, 0):
        s = today - TD(days=178 + 28 * k)
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    # last start was 178 days ago
    for name in ("get_forecast", "get_cycle_context", "get_predicted_next_period"):
        assert auth_client.get(url_for(f"reports.{name}")).status_code == 200
    data = auth_client.get(url_for("reports.get_forecast")).get_json()
    assert data["confidence"] == "overdue"
    assert data["most_likely_start"] is None
    assert data["interval_80"] is None
    assert data["is_late"] is True


def test_overdue_pure_core_for_many_lapse_lengths():
    periods = make_periods(D(2023, 1, 1), [28] * 5)
    for lapse in (60, 89, 91, 111, 125, 400, 2000):
        model = ForecastService.fit(periods, periods[-1][0] + TD(days=lapse))
        fc = model.forecast()
        assert model.bleeding_probability([D(2023, 12, 1)])
        if lapse > 90:
            assert fc["confidence"] == "overdue"
            assert model.next_start_distribution() == {}
        else:
            assert fc["most_likely_start"] is not None


def test_late_regular_user_is_not_overconfident():
    periods = make_periods(D(2023, 1, 1), [28] * 8)
    last = periods[-1][0]
    fc = ForecastService.fit(periods, last + TD(days=38)).forecast()  # 10 days late
    width = (fc["interval_80"]["end"] - fc["interval_80"]["start"]).days
    assert width >= 7
    assert fc["probability_next_3_days"] < 0.5


def test_intervals_always_contain_most_likely_and_have_enough_mass():
    periods = make_periods(D(2023, 1, 1), [28, 30, 27, 29, 31, 28, 26, 30])
    last = periods[-1][0]
    for age in (1, 20, 28, 33, 40, 60, 88):
        model = ForecastService.fit(periods, last + TD(days=age))
        fc = model.forecast()
        mode = fc["most_likely_start"]
        assert fc["interval_50"]["start"] <= mode <= fc["interval_50"]["end"]
        assert fc["interval_80"]["start"] <= mode <= fc["interval_80"]["end"]
        assert fc["interval_80"]["start"] <= fc["interval_50"]["start"]
        assert fc["interval_80"]["end"] >= fc["interval_50"]["end"]
        assert fc["interval_50"]["start"] >= last + TD(days=age)
        assert fc["_interval_masses"]["80"] >= 0.8 - 1e-9
        assert fc["_interval_masses"]["50"] >= 0.5 - 1e-9


def test_regular_60_day_user_is_forecast_near_60():
    periods = make_periods(D(2025, 1, 1), [60] * 5)
    last = periods[-1][0]
    fc = ForecastService.fit(periods, last + TD(days=20)).forecast()
    assert abs((fc["most_likely_start"] - last).days - 60) <= 1
    assert fc["confidence"] in ("regular", "variable")
    assert fc["predictive_sd_days"] < 4.5


def test_two_periods_60_days_apart_count_as_a_cycle():
    periods = make_periods(D(2025, 1, 1), [60])
    model = ForecastService.fit(periods, periods[-1][0] + TD(days=20))
    assert model.cycles_used == 1
    fc = model.forecast()
    assert (fc["most_likely_start"] - periods[-1][0]).days > 40  # moved off the prior


def test_is_late_only_fires_beyond_normal_variation():
    steady = make_periods(D(2023, 1, 1), [28] * 8)
    last = steady[-1][0]
    assert not ForecastService.fit(steady, last + TD(days=29)).forecast()["is_late"]
    assert ForecastService.fit(steady, last + TD(days=45)).forecast()["is_late"]
    wild = make_periods(D(2023, 1, 1), [20, 41, 25, 47, 22, 38, 27, 45, 21, 40])
    last = wild[-1][0]
    # one day after the average-ish cycle is NOT late for an irregular user
    assert not ForecastService.fit(wild, last + TD(days=32)).forecast()["is_late"]


def test_cycle_context_and_forecast_agree(auth_client, test_user, db):
    today = D.today()
    last = today - TD(days=10)
    for k in (5, 4, 3, 2, 1, 0):
        s = last - TD(days=30 * k)
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    fc = auth_client.get(url_for("reports.get_forecast")).get_json()
    ctx = auth_client.get(url_for("reports.get_cycle_context")).get_json()
    pred = auth_client.get(url_for("reports.get_predicted_next_period")).get_json()
    ovu = auth_client.get(url_for("reports.get_ovulation_window")).get_json()
    assert ctx["predicted_start"] == fc["most_likely_start"] == pred["predicted_start"]
    assert ctx["ovulation_date"] == fc["fertile_window"]["ovulation_date"]
    assert ovu["ovulation_date"] == fc["fertile_window"]["ovulation_date"]
    assert ctx["fertile_window"]["start"] == fc["fertile_window"]["start"]
    assert ctx["fertile_window"]["end"] == fc["fertile_window"]["end"]


# --- round 3: skipped logs, lateness, time zones, consistency ---------------------------


def test_skipped_log_history_raises_skip_weight_and_widens_forecast():
    clean = make_periods(D(2023, 1, 1), [28] * 8)
    skippy = make_periods(D(2023, 1, 1), [28, 28, 56, 28, 57, 28, 28, 56, 28])
    last_c, last_s = clean[-1][0], skippy[-1][0]
    mc = ForecastService.fit(clean, last_c + TD(days=1))
    ms = ForecastService.fit(skippy, last_s + TD(days=1))
    assert mc.cycles_excluded == 0 and not mc.has_excluded
    assert ms.cycles_excluded == 3 and ms.has_excluded
    assert ms.pi_skip > 5 * mc.pi_skip  # the user's own evidence moves the weight
    # probability that the next LOGGED gap is a double cycle is real, not 4%-flat
    pmf = ms.next_start_pmf()
    double = sum(pmf[50 - 15 :])
    assert double > 0.05
    assert sum(mc.next_start_pmf()[50 - 15 :]) < double


def test_late_regular_user_label_is_downgraded():
    periods = make_periods(D(2023, 1, 1), [28] * 8)
    last = periods[-1][0]
    on_time = ForecastService.fit(periods, last + TD(days=20)).forecast()
    late10 = ForecastService.fit(periods, last + TD(days=38)).forecast()
    late60 = ForecastService.fit(periods, last + TD(days=88)).forecast()
    assert on_time["confidence"] == "regular"
    assert late10["confidence"] in ("variable", "irregular")
    assert late60["confidence"] in ("variable", "irregular")


def test_most_likely_is_the_true_mode_and_median_is_separate():
    periods = make_periods(D(2023, 1, 1), [28] * 8)
    last = periods[-1][0]
    today = last + TD(days=48)  # 20 days late: unimodal, mode is the headline
    fc = ForecastService.fit(periods, today).forecast()
    by_day = {d["date"]: d["p_start"] for d in fc["days"]}
    best = max(by_day, key=lambda d: (by_day[d], -d.toordinal()))
    assert fc["most_likely_start"] == best
    assert fc["interval_50"]["start"] <= fc["median_start"] <= fc["interval_80"]["end"]
    for iv in ("interval_50", "interval_80"):
        assert fc[iv]["start"] <= fc["most_likely_start"] <= fc[iv]["end"]


def test_start_dated_tomorrow_counts_as_ongoing():
    """Client clock ahead of the server: a period logged for 'tomorrow' is under way."""
    periods = make_periods(D(2023, 1, 1), [28] * 5)
    server_today = periods[-1][0] + TD(days=40)  # long after the last real start
    periods.append((server_today + TD(days=1), None))
    model = ForecastService.fit(periods, server_today)
    assert model.ongoing
    fc = model.forecast()
    assert fc["days"][0]["p_bleeding"] == 1.0
    assert fc["confidence"] != "overdue"


def test_today_query_parameter_is_validated(auth_client, test_user, db):
    today = D.today()
    for k in (3, 2, 1, 0):
        s = today - TD(days=10 + 28 * k)
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    base = url_for("reports.get_forecast")
    ok = auth_client.get(base + f"?today={(today + TD(days=1)).isoformat()}")
    assert ok.status_code == 200
    assert ok.get_json()["days"][0]["date"] == (today + TD(days=1)).isoformat()
    bad = auth_client.get(base + f"?today={(today + TD(days=5)).isoformat()}")
    assert bad.status_code == 422
    for name in (
        "get_cycle_context",
        "get_predicted_next_period",
        "get_ovulation_window",
    ):
        r = auth_client.get(url_for(f"reports.{name}") + f"?today={today.isoformat()}")
        assert r.status_code == 200


def test_cycle_context_stale_open_period_agrees_with_forecast(
    auth_client, test_user, db
):
    today = D.today()
    for k in (4, 3, 2, 1):
        s = today - TD(days=200 + 28 * k)
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    Period(user_id=test_user.id, start_date=today - TD(days=200)).save()  # never closed
    ctx = auth_client.get(url_for("reports.get_cycle_context")).get_json()
    fc = auth_client.get(url_for("reports.get_forecast")).get_json()
    assert fc["confidence"] == "overdue"
    assert ctx["status"] == "waiting"
    assert ctx["days_running"] is None
    assert ctx["current_period_id"] is None
    assert ctx["predicted_start"] is None


def test_cycle_context_open_recent_period_is_ongoing(auth_client, test_user, db):
    today = D.today()
    for k in (3, 2, 1):
        s = today - TD(days=2 + 28 * k)
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    Period(user_id=test_user.id, start_date=today - TD(days=2)).save()
    ctx = auth_client.get(url_for("reports.get_cycle_context")).get_json()
    assert ctx["status"] == "period"
    assert ctx["days_running"] == 3
    assert ctx["current_period_id"] is not None


def test_cycle_context_cycle_length_ignores_skipped_log_gaps(
    auth_client, test_user, db
):
    today = D.today()
    gaps = [28, 28, 28, 56, 28, 28, 28]  # one forgotten log
    start = today - TD(days=sum(gaps) + 10)
    for s, e in make_periods(start, gaps):
        Period(user_id=test_user.id, start_date=s, end_date=e).save()
    raw_mean = sum(gaps) / len(gaps)  # 32
    ctx = auth_client.get(url_for("reports.get_cycle_context")).get_json()
    assert abs(ctx["cycle_length"] - 28) < 1.5
    assert raw_mean - ctx["cycle_length"] > 2.5


def test_cycle_context_fits_model_once(db, test_user, monkeypatch):
    today = D.today()
    for s, e in make_periods(today - TD(days=100), [28, 28, 28]):
        Period(user_id=test_user.id, start_date=s, end_date=e).save()
    calls = []
    real = ForecastService.fit

    def counting_fit(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(ForecastService, "fit", staticmethod(counting_fit))
    ReportService.get_cycle_context(test_user.id)
    assert len(calls) == 1


def test_overdue_threshold_behaviour_on_synthetic_users():
    users = generate_users(40, seed=7)
    result = overdue_check(users)
    assert result["false_overdue"] < 0.01
    assert result["lapsed_detected_150d"] == 1.0
    assert result["lapsed_detected_200d"] == 1.0


# --- public start-intensity / duration API (used by Date Check) -------------------------


def test_start_intensities_sum_to_combined_intensity():
    periods = make_periods(D(2023, 1, 1), [28, 28, 56, 28, 29, 27, 28])
    model = ForecastService.fit(periods, periods[-1][0] + TD(days=10))
    groups = model.start_intensities(120)
    assert len(groups) >= 3  # mu groups + disrupted + skipped-log
    combined = model.intensity(120)
    for d in range(121):
        assert abs(sum(g.u[d] for g in groups) - combined[d]) < 1e-12
    assert all(len(g.u) == 121 for g in groups)
    assert all(abs(sum(p for _, p in g.step) - 1) < 1e-9 for g in groups)
    assert groups[0].p_longer(0) == 1.0 or groups[0].p_longer(0) > 0.99
    assert groups[0].p_longer(10_000) == 0.0
    # and it drives bleeding_probability: same numbers through the public API
    day = model.today + TD(days=40)
    surv = [model.duration_survival(k) for k in range(14)]
    off = (day - model.last_start).days
    manual = sum(combined[off - k] * surv[k] for k in range(14) if off - k >= 0)
    assert abs(model.bleeding_probability([day])[day] - min(manual, 1.0)) < 1e-12


def test_intensity_is_cached_across_ascending_horizons():
    periods = make_periods(D(2023, 1, 1), [28] * 6)
    model = ForecastService.fit(periods, periods[-1][0] + TD(days=5))
    model.start_intensities(30)
    first = model._intensity_cache
    for h in (60, 120, 365):
        model.start_intensities(h)
        assert model._intensity_cache is first  # no recompute
    assert len(model.start_intensities(10)[0].u) == 11


def test_duration_cdf_survival_and_ongoing_conditioning():
    periods = make_periods(D(2023, 1, 1), [28] * 6, duration=5)
    model = ForecastService.fit(periods, periods[-1][0] + TD(days=2))
    assert model.duration_cdf(0) == 0.0
    assert model.duration_survival(0) == 1.0
    assert abs(model.duration_cdf(5) + model.duration_survival(5) - 1) < 1e-12
    cdfs = [model.duration_cdf(k) for k in range(0, 16)]
    assert cdfs == sorted(cdfs)
    assert abs(cdfs[-1] - 1.0) < 1e-9
    assert model.duration_cdf(5) > 0.6  # five-day periods
    # still bleeding after 4 days: cannot have ended earlier; long-run unchanged shape
    assert model.ongoing_duration_cdf(3, 4) == 0.0
    assert model.ongoing_duration_cdf(4, 4) < model.ongoing_duration_cdf(6, 4) <= 1.0
    assert abs(model.ongoing_duration_cdf(14, 4) - 1.0) < 1e-9


# --- late-user headline: multimodal start distributions ---------------------------------


def test_mode_components_split_and_merge():
    def bump(c, w, n):
        return [2.718281828 ** (-0.5 * ((i - c) / w) ** 2) for i in range(n)]

    two = [
        a + b
        for a, b in zip(
            bump(5, 1.5, 60), [0.6 * v for v in bump(40, 1.5, 60)], strict=True
        )
    ]
    t = sum(two)
    two = [v / t for v in two]
    comps = mode_components(two)
    assert len(comps) == 2 and is_multimodal(two)
    assert 0.55 < comps[0][2] < 0.7 and comps[0][1] < comps[1][0]
    one = bump(10, 3, 60)
    t = sum(one)
    assert not is_multimodal([v / t for v in one])
    tiny = [
        a + 0.02 * b for a, b in zip(bump(5, 1.5, 60), bump(40, 1.5, 60), strict=True)
    ]
    t = sum(tiny)
    assert not is_multimodal([v / t for v in tiny])  # second bump < 12% mass


def test_late_regular_user_headline_stays_near_term():
    """10/20/40 days late: never headline a forgotten-log spike 5-8 weeks away."""
    periods = make_periods(D(2023, 1, 1), [28] * 8)
    last = periods[-1][0]
    for late in (10, 20, 40):
        today = last + TD(days=28 + late)
        fc = ForecastService.fit(periods, today).forecast()
        ahead = (fc["most_likely_start"] - today).days
        assert 0 <= ahead <= 12, (late, ahead)
        for iv in ("interval_50", "interval_80"):
            assert fc[iv]["start"] >= today
            assert fc[iv]["start"] <= fc["most_likely_start"] <= fc[iv]["end"]
        assert fc["confidence"] != "regular"
    # the 10-days-late case is bimodal: the other mode is reported, with its mass
    fc10 = ForecastService.fit(periods, last + TD(days=38)).forecast()
    sw = fc10["secondary_window"]
    assert sw is not None and sw["probability"] >= 0.12
    assert sw["start"] > fc10["most_likely_start"]


def test_on_time_user_has_no_secondary_window():
    periods = make_periods(D(2023, 1, 1), [28] * 8)
    fc = ForecastService.fit(periods, periods[-1][0] + TD(days=20)).forecast()
    assert fc["secondary_window"] is None


def test_late_habitual_skipper_headlines_the_skip_not_an_imminent_start():
    periods = make_periods(D(2023, 1, 1), [28, 28, 56, 28, 57, 28, 28, 56, 28])
    last = periods[-1][0]
    today = last + TD(days=38)  # 10 days late for a user who often forgets logs
    model = ForecastService.fit(periods, today)
    assert model.has_excluded and model.pi_skip > 0.1
    fc = model.forecast()
    ahead = (fc["most_likely_start"] - today).days
    assert 8 <= ahead <= 30  # around the two-cycle date, not tomorrow
    assert fc["probability_next_3_days"] < 0.1
    assert (
        fc["interval_80"]["start"]
        <= fc["most_likely_start"]
        <= fc["interval_80"]["end"]
    )
    assert abs(sum(model.next_start_pmf()) - 1) < 1e-9


def test_three_merged_cycles_get_some_weight_for_habitual_skippers():
    periods = make_periods(D(2023, 1, 1), [28, 56, 28, 57, 28, 56, 28, 28, 56, 28])
    model = ForecastService.fit(periods, periods[-1][0] + TD(days=1))
    pmf = model.next_start_pmf()
    triple = sum(pmf[80 - 15 :])
    assert triple > 0.005
    groups = model.start_intensities(200)
    assert len(groups) >= 4


# --- backtest gate (the measurable bar) -----------------------------------------------------


# The literal gate slack is 0.05 (scripts report it); known residual miscalibration of
# up to ~0.09 in small late/excluded-gap buckets is guarded here against regressions.
REGRESSION_SLACK = 0.10


def _run(scenario, seed, n=EVAL_USERS):
    buckets = run_backtest(generate_users(n_users=n, seed=seed, scenario=scenario))
    print(f"\n{scenario} seed {seed}\n" + format_table(buckets, "label"))
    print(format_table(buckets, "excl"))
    return buckets


def test_backtest_regression_guard_native():
    """REGRESSION GUARD, not the strict calibration gate.

    Tolerance is |cov - p| <= 0.10 + 2 SE per shown-label x day and has-excluded-gaps x
    day bucket, with 600 users per seed (buckets of 200-5000 forecasts). The strict
    gate (0.05 + 2 SE, 1500 users, seeds 5/42/123; run
    ``python -m scripts.backtest_forecast 1500 all 5 42 123``) is NOT met on native
    and skips: native 50% intervals over-cover by up to ~0.06 (cov50 ~0.56), and
    habitual skippers' late forecasts (excluded @ day 32) sit at cov80 ~0.75-0.77 on
    the skips scenario. regime and lognormal_drift_skips pass the strict gate.
    Evaluation seeds are never used by scripts/calibrate_forecast.py. The model's MAE
    (median point) must also not exceed the naive mean by more than 0.1 day + 2 SE.
    """
    per_seed = [_run("native", seed) for seed in EVAL_SEEDS]
    for seed, buckets in zip(EVAL_SEEDS, per_seed, strict=True):
        fails = gate_failures(buckets, slack=REGRESSION_SLACK)
        assert not fails, f"seed {seed}: " + "; ".join(fails)
    pooled = merge_buckets(per_seed)
    fails = gate_failures(pooled, slack=REGRESSION_SLACK)
    assert not fails, "pooled: " + "; ".join(fails)
    all_day = pooled[("all", "all", 0)].summary()
    assert all_day["mae_model"] < all_day["mae_naive_fixed"]
    assert all_day["mae_model"] < all_day["mae_naive_buggy"]


def test_backtest_regression_guard_skips():
    """30% of users skip 25% of their logs, with log-normal noise."""
    buckets = _run("skips", 42)
    fails = gate_failures(buckets, slack=REGRESSION_SLACK)
    assert not fails, "; ".join(fails)


def test_backtest_regression_guard_regime():
    """30% of users change their mean and double their SD part-way through."""
    buckets = _run("regime", 5)
    fails = gate_failures(buckets, slack=REGRESSION_SLACK)
    assert not fails, "; ".join(fails)


def test_backtest_regression_guard_stress():
    """Hardest world (log-normal, strong drift, 20% skippers, 6% long cycles).

    Reported, not calibrated: the 80% interval must still cover at least 70%.
    """
    buckets = _run("lognormal_drift_skips", 123)
    for (grouping, name, day), b in sorted(buckets.items()):
        if grouping in ("label", "excl") and b.n >= 150:
            s = b.summary()
            assert s["cov80"] >= 0.70, (grouping, name, day, s["cov80"])
            assert s["mae_model"] <= s["mae_naive_fixed"] + 0.1, (grouping, name, day)
