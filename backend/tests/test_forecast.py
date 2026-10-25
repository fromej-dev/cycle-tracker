import datetime

from flask import url_for

from app.models import Period
from app.services import ForecastService, ReportService
from scripts.backtest_forecast import format_table, generate_users, run_backtest

D = datetime.date
TD = datetime.timedelta


def make_periods(first, gaps, duration=5):
    starts = [first]
    for g in gaps:
        starts.append(starts[-1] + TD(days=g))
    return [(s, s + TD(days=duration - 1)) for s in starts]


# --- off-by-one -----------------------------------------------------------------


def test_predicted_next_period_is_last_start_plus_cycle(db, test_user):
    for s in (D(2023, 1, 1), D(2023, 1, 29), D(2023, 2, 26)):
        Period(user_id=test_user.id, start_date=s, end_date=s + TD(days=4)).save()
    assert ReportService.get_predicted_next_period(test_user.id) == D(2023, 3, 26)


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
    dist = ForecastService.fit(periods, today).next_start_distribution()
    assert abs(sum(dist.values()) - 1) < 1e-6
    assert min(dist) >= today


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

    probs = model.bleeding_probability(
        [mode + TD(days=2), mode - TD(days=10), today + TD(days=360)]
    )
    assert probs[mode + TD(days=2)] > 0.7  # mid-period around the likely start
    assert probs[mode - TD(days=10)] < 0.05
    far = probs[today + TD(days=360)]
    assert 0.10 < far < 0.25  # long-run average ~ 5/28 = 0.18
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


# --- backtest (the measurable bar) ----------------------------------------------------------


def test_backtest_calibration_and_accuracy():
    buckets = run_backtest(generate_users(n_users=200, seed=20240607))
    print("\n" + format_table(buckets))
    day1 = buckets["day1"].summary()
    assert 0.75 <= day1["cov80"] <= 0.85
    assert 0.43 <= day1["cov50"] <= 0.57
    assert day1["mae_model"] < day1["mae_naive_fixed"]
    assert day1["mae_model"] < day1["mae_naive_buggy"]
    # Conditional-on-today forecasts should stay roughly calibrated too.
    allb = buckets["all"].summary()
    assert 0.72 <= allb["cov80"] <= 0.86
    assert allb["mae_model"] < allb["mae_naive_fixed"]
