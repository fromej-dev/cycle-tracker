import datetime

from flask import url_for

from app.models import Period
from app.services import ForecastService, ReportService
from scripts.backtest_forecast import (
    EVAL_SEEDS,
    EVAL_USERS,
    format_table,
    gate_failures,
    generate_users,
    merge_buckets,
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


# --- backtest gate (the measurable bar) -----------------------------------------------------


def test_backtest_calibration_and_accuracy_gate():
    """Every shown-label x day bucket is calibrated and not worse than naive.

    Evaluated on seeds that are never used by scripts/calibrate_forecast.py. Single
    buckets hold only 200-1700 forecasts, so the calibration band is the binomial one
    (see gate_failures); the pooled two-seed run is the main calibration assertion,
    and each seed alone must pass the accuracy (MAE) and overall-calibration checks.
    """
    per_seed = []
    for seed in EVAL_SEEDS:
        buckets = run_backtest(generate_users(n_users=EVAL_USERS, seed=seed))
        per_seed.append(buckets)
        print(f"\nseed {seed}\n" + format_table(buckets, "label"))
        fails = [f for f in gate_failures(buckets) if "MAE" in f]
        assert not fails, f"seed {seed}: " + "; ".join(fails)
        for day in (0, 1, 25, 32):
            s = buckets[("all", "all", day)].summary()
            assert 0.45 <= s["cov50"] <= 0.55 and 0.75 <= s["cov80"] <= 0.85, (
                seed,
                day,
            )
            assert s["mae_model"] < s["mae_naive_fixed"] < s["mae_naive_buggy"] + 0.2
            assert s["mae_model"] < s["mae_naive_buggy"]
    pooled = merge_buckets(per_seed)
    print("\npooled\n" + format_table(pooled, "label"))
    fails = gate_failures(pooled)
    assert not fails, "pooled: " + "; ".join(fails)
