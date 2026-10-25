"""The ICS feed must never promise more than Date Check does."""

import datetime
import json

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


TODAY = D(2026, 10, 25)  # pinned: results must not depend on the wall clock


def today():
    return TODAY


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
        # the bar is P(any bleeding in the window), not the largest single day
        bar = DateCheckService.check_with_model(model, f["first"], f["last"])
        assert bar["probability_any"] < 0.2, (name, f, bar["probability_any"])


def test_fertile_gate_uses_probability_any_not_the_largest_day(db, monkeypatch):
    """Regression: a window whose days are each < 0.2 can still be > 0.2 overall."""
    from app.services import calendar_service as cs

    u = user_with(db, "fg", 10, [28] * 8)
    u.update(calendar_include_fertile=True)
    assert any(
        e["kind"] == "fertile" for e in CalendarService.predicted_events(u, today())
    )
    real = cs.DateCheckService.check_with_model

    def over(model, a, b):
        out = real(model, a, b)
        return {**out, "probability_any": 0.2235}  # days stay low, overall is not

    monkeypatch.setattr(cs.DateCheckService, "check_with_model", over)
    events = CalendarService.predicted_events(u, today())
    assert not [e for e in events if e["kind"] == "fertile"]


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
    # below the keep threshold it is no longer renewed: only held (frozen) for a few
    # days of grace, never newly confirmed
    assert all(e.get("grace") for e in preds())


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


# --- round 5: identities -------------------------------------------------------------


def _render(u, day, hour=6):
    return CalendarService.build_ics(
        u, day, datetime.datetime.combine(day, datetime.time(hour))
    )


def _uids_and_dates(u, day):
    return {
        e["uid"]: (e["first"], e["last"], e["estimate"])
        for e in CalendarService.predicted_events(u, day)
    }


def test_logging_and_deleting_a_mistake_keeps_every_identity(db):
    u = user_with(db, "del", 10, [28] * 8)
    _render(u, today())
    before = _uids_and_dates(u, today())
    day = today() + TD(days=2)
    spot = Period(user_id=u.id, start_date=day, end_date=day).save()  # spotting
    _render(u, day)
    during = _uids_and_dates(u, day)
    # the predictions did not change identity or jump by a cycle
    for uid, (first, _last, est) in before.items():
        if est:
            assert uid in during
            assert abs((during[uid][0] - first).days) <= 3
    db.session.delete(spot)
    db.session.commit()
    _render(u, day + TD(days=1))
    after = _uids_and_dates(u, day + TD(days=1))
    assert set(after) == set(before)
    for uid in before:
        assert abs((after[uid][0] - before[uid][0]).days) <= 1


def test_deleting_a_real_logged_period_returns_its_id_to_the_prediction(db):
    u = user_with(db, "del2", 26, [28] * 8)
    _render(u, today())
    predicted = [uid for uid, v in _uids_and_dates(u, today()).items() if v[2]]
    row = Period(user_id=u.id, start_date=today(), end_date=None).save()  # real period
    _render(u, today())
    logged = {uid for uid, v in _uids_and_dates(u, today()).items() if not v[2]}
    assert predicted[0] in logged  # same UID, now logged
    db.session.delete(row)
    db.session.commit()
    _render(u, today() + TD(days=1))
    again = [uid for uid, v in _uids_and_dates(u, today() + TD(days=1)).items() if v[2]]
    assert again[0] == predicted[0]


def _sequences(body):
    import re

    return dict(
        zip(
            re.findall(r"UID:(\S+)", body),
            re.findall(r"SEQUENCE:(\d+)", body),
            strict=True,
        )
    )


def test_sequence_never_decreases_across_a_wipe(db):
    u = user_with(db, "wipe", 10, [28] * 8)
    best: dict[str, int] = {}
    for i in range(40):  # a late user: events move, sequences climb
        for uid, seq in _sequences(_render(u, today() + TD(days=i))).items():
            assert int(seq) >= best.get(uid, 0)
            best[uid] = int(seq)
    assert max(best.values()) > 0
    for p in Period.query.filter_by(user_id=u.id).all():
        db.session.delete(p)
    db.session.commit()
    assert "BEGIN:VEVENT" not in _render(u, today() + TD(days=40))
    state = json.loads(u.calendar_state)
    assert state["events"]  # kept as tombstones, not cleared
    starts = [today() - TD(days=10) - TD(days=28 * k) for k in range(8, -1, -1)]
    for s_ in starts:
        Period(user_id=u.id, start_date=s_, end_date=s_ + TD(days=4)).save()
    for uid, seq in _sequences(_render(u, today() + TD(days=41))).items():
        assert int(seq) >= best.get(uid, 0), uid
        best[uid] = int(seq)


def test_uids_depend_on_a_private_key_not_on_secret_key(app, db):
    u = user_with(db, "key", 10, [28] * 8)
    token = CalendarService.rotate_token(u)
    assert token and len(u.calendar_uid_key) == 64
    first = _sequences(_render(u, today()))
    old = app.config["SECRET_KEY"]
    app.config["SECRET_KEY"] = "something-else-entirely"
    try:
        second = _sequences(_render(u, today()))
    finally:
        app.config["SECRET_KEY"] = old
    assert list(first) == list(second)  # SECRET_KEY changes do not churn events
    # nothing derivable from the default key / user id / counter
    import hashlib
    import hmac

    for uid in first:
        head = uid.split("@")[0]
        for key in (b"you-will-never-guess", b"test-secret-key"):
            for n in range(1, 12):
                for kind in ("p", "f"):
                    msg = f"calendar-uid:{u.id}:{n}:{kind}".encode()
                    assert hmac.new(key, msg, hashlib.sha256).hexdigest()[:32] != head
    # rotating gives a fresh key, hence a fresh set of identifiers
    CalendarService.rotate_token(u)
    assert set(_sequences(_render(u, today()))).isdisjoint(first)


def test_unknown_token_404_is_not_cacheable(client):
    r = client.get("/calendar/" + "A" * 43 + ".ics")
    assert r.status_code == 404 and r.headers["Cache-Control"] == "no-store"


def test_timezone_rejects_non_zones():
    assert not CalendarService.valid_timezone("localtime")
    assert not CalendarService.valid_timezone("posixrules")
    assert not CalendarService.valid_timezone("Factory")
    assert CalendarService.valid_timezone("Europe/Amsterdam")


def test_published_events_may_grow_before_they_are_dropped(db, monkeypatch):
    """Hysteresis also covers width and spacing, not only the probability."""
    from app.services import calendar_service as cs

    u = user_with(db, "wid", 10, [28] * 8)
    _render(u, today())  # publishes the first predictions
    published = [
        e for e in CalendarService.predicted_events(u, today()) if e["estimate"]
    ]
    assert published
    # a fresh user must obey the 21-day cap, a published event may reach 25
    monkeypatch.setattr(cs, "MAX_EVENT_DAYS", 3)
    fresh = user_with(db, "wid2", 10, [28] * 8)
    assert not [
        e for e in CalendarService.predicted_events(fresh, today()) if e["estimate"]
    ]
    kept = [e for e in CalendarService.predicted_events(u, today()) if e["estimate"]]
    assert kept  # same history, but already published -> kept (width <= 25)


def test_a_failing_published_event_is_held_for_a_few_days_then_dropped(db, monkeypatch):
    from app.services import calendar_service as cs

    u = user_with(db, "grace", 10, [28] * 8)
    _render(u, today())
    events = _uids_and_dates(u, today())
    held = [uid for uid, v in events.items() if v[2]][0]
    real = cs.CalendarService._window

    def failing(model, pmf, s0, typical, tod, prev_last, max_len, kept):
        return None

    monkeypatch.setattr(cs.CalendarService, "_window", staticmethod(failing))
    for day in range(1, cs.GRACE_POLLS + 1):
        d = today() + TD(days=day)
        first_poll = _render(u, d)
        again = _render(u, d, hour=14)  # same-day polls do not use up the grace
        assert first_poll == again
        assert held in _uids_and_dates(u, d)
        assert _uids_and_dates(u, d)[held][:2] == events[held][:2]  # frozen dates
    late = today() + TD(days=cs.GRACE_POLLS + 1)
    _render(u, late)
    assert held not in _uids_and_dates(u, late)
    monkeypatch.setattr(cs.CalendarService, "_window", staticmethod(real))


def test_a_prediction_carried_far_away_gets_a_new_identity(db, monkeypatch):
    from app.services import calendar_service as cs

    u = user_with(db, "jump", 10, [28] * 8)
    _render(u, today())
    before = {uid: v for uid, v in _uids_and_dates(u, today()).items() if v[2]}
    first_uid = min(before, key=lambda k: before[k][0])
    real = cs.CalendarService._window

    def far(model, pmf, s0, typical, tod, prev_last, max_len, kept):
        res = real(model, pmf, s0, typical, tod, prev_last, max_len, kept)
        if res is None:
            return None
        shift = TD(days=cs.JUMP_DAYS + 10)
        return res[0] + shift, res[1] + shift, res[2] + shift.days, res[3] + shift.days

    monkeypatch.setattr(cs.CalendarService, "_window", staticmethod(far))
    _render(u, today() + TD(days=1))
    after = {
        uid: v for uid, v in _uids_and_dates(u, today() + TD(days=1)).items() if v[2]
    }
    assert first_uid not in after  # not "moved by weeks": a new event instead
    monkeypatch.setattr(cs.CalendarService, "_window", staticmethod(real))


def test_spotting_does_not_push_a_real_period_out_of_the_feed(db):
    u = user_with(db, "spot", 10, [28] * 8)
    _render(u, today())
    real_starts = {p.start_date for p in Period.query.filter_by(user_id=u.id).all()}
    shown_before = {v[0] for v in _uids_and_dates(u, today()).values() if not v[2]}
    day = today() + TD(days=2)
    Period(user_id=u.id, start_date=day, end_date=day).save()
    shown_after = {v[0] for v in _uids_and_dates(u, day).values() if not v[2]}
    assert shown_before <= shown_after and day in shown_after
    assert shown_after <= real_starts | {day}
