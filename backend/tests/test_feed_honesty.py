"""The ICS feed must never promise more than Date Check does."""

import datetime

import pytest

from app.models import Period, User
from app.services.calendar_service import CalendarService
from app.services.date_check_service import (
    DateCheckService,
    cycle_start_pmfs,
    narrowest_window,
)
from app.services.forecast_service import ForecastService

D = datetime.date
TD = datetime.timedelta
IRREG = [24, 35, 29, 41, 26, 33, 38, 27]


def today():
    return D.today()


def user_with(db, name, age, gaps, open_last=False):
    u = User(username=name, email=f"{name}@x.example")
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    starts = [today() - TD(days=age)]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    for i, s in enumerate(reversed(starts)):
        end = None if (open_last and i == len(starts) - 1) else s + TD(days=4)
        Period(user_id=u.id, start_date=s, end_date=end).save()
    return u


USERS = {
    "regular": (10, [28] * 8),
    "late": (36, [28] * 8),
    "very_late": (75, [28] * 8),
    "very_late_irr": (85, IRREG),
    "c60": (25, [60, 58, 62, 61, 59, 60]),
    "c60_late": (70, [60, 58, 62, 61, 59, 60]),
    "irregular": (12, IRREG),
    "skipper": (20, [28, 56, 28, 28, 55, 28]),
    "single": (8, []),
    "learning": (5, [30]),
    "ongoing": (2, [28] * 6),
}


@pytest.mark.parametrize("name", list(USERS))
def test_every_published_prediction_is_backed_by_date_check(db, name):
    age, gaps = USERS[name]
    u = user_with(db, name, age, gaps, open_last=(name == "ongoing"))
    model = DateCheckService.load_model(u.id, today())
    events = CalendarService.predicted_events(u, today())
    for ev in events:
        if not ev["estimate"] or ev["kind"] != "period":
            continue
        first = max(ev["first"], today())
        last = min(ev["last"], first + TD(days=59))
        r = DateCheckService.check_with_model(model, first, last)
        assert r["probability_any"] >= 0.5, (name, ev, r["probability_any"])
        assert r["horizon_note"] is None, (name, ev)
    assert len([e for e in events if e["estimate"] and e["kind"] == "period"]) <= 3


def test_flat_forecasts_publish_no_prediction(db):
    # an irregular user 200 days after the last period is "overdue"; one with a very
    # variable history right now has a flat far future
    age, gaps = USERS["very_late_irr"]
    u = user_with(db, "x", age, gaps)
    events = CalendarService.predicted_events(u, today())
    pred = [e for e in events if e["estimate"]]
    model = DateCheckService.load_model(u.id, today())
    for e in pred:
        r = DateCheckService.check_with_model(
            model, max(e["first"], today()), e["last"]
        )
        assert r["horizon_note"] is None


@pytest.mark.parametrize("name", ["regular", "late", "skipper", "irregular", "single"])
def test_per_cycle_start_pmfs_add_up_to_the_engine_intensity(name):
    age, gaps = USERS[name]
    starts = [today() - TD(days=age)]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    periods = [(s, s + TD(days=4)) for s in reversed(starts)]
    model = ForecastService.fit(periods, today())
    horizon = (today() - model.last_start).days + 200
    pmfs = cycle_start_pmfs(model, 12, horizon)
    total = model.intensity(horizon)
    for d in range(horizon + 1):
        assert sum(p[d] for p in pmfs) == pytest.approx(total[d], abs=2e-3), (name, d)
    # first cycle is exactly the engine's next-start distribution
    first = model.next_start_pmf()
    for i, p in enumerate(first):
        off = 15 + i
        if off <= horizon:
            assert pmfs[0][off] == pytest.approx(p, abs=1e-6)


def test_narrowest_window():
    pmf = [0.0, 0.1, 0.4, 0.3, 0.1, 0.05, 0.05]
    assert narrowest_window(pmf, 0.5)[:2] == (2, 3)
    lo, hi, mass = narrowest_window(pmf, 0.8)
    assert hi - lo == 2 and mass >= 0.8
    assert narrowest_window([0.2, 0.2], 0.5) is None


# --- round 4: shape, hysteresis, fertile, time zone, writes --------------------------


def _periods_events(events):
    return [e for e in events if e["kind"] == "period" and e["estimate"]]


def test_random_users_never_get_overlapping_or_overlong_events(db):
    import random

    from app.services import calendar_service as cs

    checked = 0
    for seed in range(40):
        rng = random.Random(seed)
        lo = rng.choice([20, 24, 28, 32])
        hi = lo + rng.choice([3, 8, 15, 25])
        gaps = [rng.randint(lo, hi) for _ in range(rng.randint(1, 10))]
        u = user_with(db, f"r{seed}", rng.randint(0, 120), gaps)
        model = DateCheckService.load_model(u.id, today())
        events = CalendarService.predicted_events(u, today())
        ordered = sorted(events, key=lambda e: e["first"])
        for a, b in zip(ordered, ordered[1:], strict=False):
            if a["kind"] == b["kind"] == "period":
                assert b["first"] > a["last"] + TD(days=cs.MIN_GAP), (seed, a, b)
        prev = None
        for e in _periods_events(ordered):
            length = (e["last"] - e["first"]).days + 1
            assert length <= min(cs.MAX_EVENT_DAYS, max(round(model.mean_cycle), 1))
            # the gate is applied to the exact dates, never clipped
            r = DateCheckService.check_with_model(
                model, max(e["first"], today()), e["last"]
            )
            assert r["probability_any"] >= 0.5 and r["horizon_note"] is None
            prev = e
            checked += 1
        del prev
    assert checked > 40


@pytest.mark.parametrize("name", list(USERS))
def test_fertile_events_are_tight_future_and_clear_of_periods(db, name):
    age, gaps = USERS[name]
    u = user_with(db, name, age, gaps, open_last=(name == "ongoing"))
    u.update(calendar_include_fertile=True)
    model = DateCheckService.load_model(u.id, today())
    events = CalendarService.predicted_events(u, today())
    periods = [e for e in events if e["kind"] == "period"]
    for f in (e for e in events if e["kind"] == "fertile"):
        assert (f["last"] - f["first"]).days + 1 <= 10
        assert f["first"] >= today() and f["last"] >= today()
        assert not any(
            f["first"] <= p["last"] and p["first"] <= f["last"] for p in periods
        )
        days = [
            f["first"] + TD(days=i) for i in range((f["last"] - f["first"]).days + 1)
        ]
        assert max(model.bleeding_probability(days).values()) < 0.2


def test_fertile_window_matches_engine_for_a_regular_user(db):
    u = user_with(db, "reg", 10, [28] * 8)
    u.update(calendar_include_fertile=True)
    model = DateCheckService.load_model(u.id, today())
    fw = model.forecast(horizon_days=1)["fertile_window"]
    fert = [
        e
        for e in CalendarService.predicted_events(u, today())
        if e["kind"] == "fertile"
    ]
    assert fert
    # same ovulation logic: the feed's first window overlaps the engine's cycle-1 window
    assert fert[0]["first"] <= fw["end"] and fw["start"] <= fert[0]["last"]


def test_hysteresis_keeps_a_published_event_at_forty_percent(db, monkeypatch):
    from app.services import calendar_service as cs

    u = user_with(db, "h", 10, [28] * 8)

    def fake(prob):
        return lambda model, a, b: {"probability_any": prob, "horizon_note": None}

    def preds():
        return [
            e for e in CalendarService.predicted_events(u, today()) if e["estimate"]
        ]

    monkeypatch.setattr(cs.DateCheckService, "check_with_model", fake(0.45))
    assert preds() == []  # not published yet: needs 0.5
    monkeypatch.setattr(cs.DateCheckService, "check_with_model", fake(0.9))
    CalendarService.build_ics(u, today(), datetime.datetime(2026, 10, 25, 6))
    assert len(preds()) >= 1
    monkeypatch.setattr(cs.DateCheckService, "check_with_model", fake(0.45))
    assert len(preds()) >= 1  # kept: 0.45 >= 0.40
    monkeypatch.setattr(cs.DateCheckService, "check_with_model", fake(0.35))
    assert preds() == []  # dropped below the keep threshold


def test_timezone_validation_and_local_today():
    ok = ["Europe/Amsterdam", "UTC", "Pacific/Kiritimati", "America/Argentina/Salta"]
    bad = [
        "",
        "Nope/Zone",
        "../etc/passwd",
        "/etc/passwd",
        "a" * 80,
        "Europe/Amster dam",
    ]
    assert all(CalendarService.valid_timezone(z) for z in ok)
    assert not any(CalendarService.valid_timezone(z) for z in bad)


def test_feed_today_follows_the_user_time_zone(db, test_user):
    from zoneinfo import ZoneInfo

    for name in ("Pacific/Kiritimati", "Pacific/Pago_Pago", None):
        test_user.update(calendar_timezone=name)
        tz = ZoneInfo(name) if name else datetime.UTC
        assert (
            CalendarService.local_today(test_user) == datetime.datetime.now(tz).date()
        )


def test_timezone_api(auth_client, db, test_user):
    from flask import url_for

    r = auth_client.post(
        url_for("users.create_calendar_feed"), json={"timezone": "Europe/Amsterdam"}
    )
    assert r.status_code == 201
    got = auth_client.get(url_for("users.get_calendar_feed_settings")).get_json()
    assert got["timezone"] == "Europe/Amsterdam"
    bad = auth_client.post(
        url_for("users.create_calendar_feed"), json={"timezone": "Mars/Base"}
    )
    assert bad.status_code == 422 and "timezone" in bad.get_json()["detail"]["json"]
    bad = auth_client.patch(
        url_for("users.update_calendar_feed"), json={"timezone": "../x"}
    )
    assert bad.status_code == 422
    ok = auth_client.patch(url_for("users.update_calendar_feed"), json={"timezone": ""})
    assert ok.get_json()["timezone"] is None


def test_head_never_writes_and_get_writes_once(db, client, test_user):
    from app.services.calendar_service import CalendarService as CS

    user_with_periods = user_with(db, "w", 10, [28] * 6)
    token = CS.rotate_token(user_with_periods)
    path = f"/calendar/{token}.ics"
    assert user_with_periods.calendar_state is None
    assert client.head(path).status_code == 200
    db.session.refresh(user_with_periods)
    assert user_with_periods.calendar_state is None  # HEAD did not write
    assert client.get(path).status_code == 200
    db.session.refresh(user_with_periods)
    state1 = user_with_periods.calendar_state
    assert state1
    client.get(path)
    db.session.refresh(user_with_periods)
    assert user_with_periods.calendar_state == state1  # unchanged feed: no write


def test_state_update_is_compare_and_swap(db):
    u = user_with(db, "cas", 10, [28] * 6)
    assert CalendarService._compare_and_swap(u, None, '{"a":1}') is True
    # a stale writer (still believes the state is None) loses and changes nothing
    assert CalendarService._compare_and_swap(u, None, '{"a":2}') is False
    db.session.refresh(u)
    assert u.calendar_state == '{"a":1}'


def test_render_retries_after_losing_a_race(db, monkeypatch):
    u = user_with(db, "race", 10, [28] * 6)
    real = CalendarService._compare_and_swap
    calls = []

    def flaky(user, old, new):
        calls.append(1)
        if len(calls) == 1:
            return False  # someone else wrote first
        return real(user, old, new)

    monkeypatch.setattr(CalendarService, "_compare_and_swap", staticmethod(flaky))
    out = CalendarService.build_ics(u, today(), datetime.datetime(2026, 10, 25, 6))
    assert "BEGIN:VEVENT" in out and len(calls) == 2
    assert u.calendar_state


def test_empty_calendar_is_deliberate(db):
    u = User(username="e", email="e@x.example")
    u.set_password("pw")
    db.session.add(u)
    db.session.commit()
    out = CalendarService.build_ics(u, today(), datetime.datetime(2026, 10, 25, 6))
    assert out.startswith("BEGIN:VCALENDAR\r\n") and out.endswith("END:VCALENDAR\r\n")
    assert "BEGIN:VEVENT" not in out
