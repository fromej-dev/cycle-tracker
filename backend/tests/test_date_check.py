import datetime

import pytest
from flask import url_for
from flask_jwt_extended import create_access_token

from app.models import Period, PlannedEvent, User
from app.services import ForecastService
from app.services.date_check_service import DateCheckService

D = datetime.date
TD = datetime.timedelta


def today():
    return D.today()


def add_periods(user, last_start, gaps, duration=5, open_last=False):
    """Periods ending at last_start, walking back through ``gaps`` (newest first)."""
    starts = [last_start]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    for i, s in enumerate(reversed(starts)):
        end = s + TD(days=duration - 1)
        if open_last and i == len(starts) - 1:
            end = None
        Period(user_id=user.id, start_date=s, end_date=end).save()


@pytest.fixture
def regular(db, test_user):
    """Very regular 28-day user, last period started 10 days ago."""
    add_periods(test_user, today() - TD(days=10), [28] * 8)
    return test_user


def other_headers(db):
    user = User(username="other", email="other@example.com")
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return user, {"Authorization": f"Bearer {token}"}


def check(client, start, end):
    return client.get(
        url_for("reports.get_date_check"),
        query_string={"start": start.isoformat(), "end": end.isoformat()},
    )


def pany(client, start, end):
    r = check(client, start, end)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["probability_any"]


# --- probability sanity ---------------------------------------------------------


def test_range_around_most_likely_start_is_near_certain(auth_client, regular):
    fc = ForecastService.forecast(regular.id)
    start = fc["most_likely_start"]
    data = check(auth_client, start - TD(days=1), start + TD(days=3)).get_json()
    assert data["status"] == "ok"
    assert data["confidence"] == "regular"
    assert data["probability_any"] > 0.8
    assert data["most_likely_days"]
    assert len(data["most_likely_days"]) <= 3
    assert len(data["days"]) == 5


def test_follicular_range_is_unlikely(auth_client, regular):
    # cycle days ~11-16 for a 28-day cycle: no bleeding expected
    r = check(auth_client, today(), today() + TD(days=5)).get_json()
    assert r["probability_any"] < 0.15
    assert r["most_likely_days"] is None  # nothing above 5%


def test_single_day_equals_that_days_p_bleeding(auth_client, regular):
    for off in (0, 8, 18, 20, 22, 40, 120):
        d = today() + TD(days=off)
        data = check(auth_client, d, d).get_json()
        engine = ForecastService.bleeding_probability(regular.id, [d])[d]
        assert data["probability_any"] == data["days"][0]["p_bleeding"]
        assert data["probability_any"] == pytest.approx(engine, abs=1e-4)


def test_not_the_sum_or_the_max_of_daily_probabilities(auth_client, regular):
    start = ForecastService.forecast(regular.id)["most_likely_start"]
    r = check(auth_client, start - TD(days=6), start + TD(days=6)).get_json()
    daily = [x["p_bleeding"] for x in r["days"]]
    assert sum(daily) > 1.5  # naive sum is nonsense (>100%)
    assert max(daily) <= r["probability_any"] <= 1.0
    assert r["probability_any"] > 0.95


def test_superset_range_is_never_less_likely(db, auth_client, regular):
    model = DateCheckService.load_model(regular.id, today())
    check_ = DateCheckService.check_with_model
    for a in range(-5, 400, 9):
        for length in (1, 3, 7, 14, 30):
            s = today() + TD(days=a)
            e = s + TD(days=length - 1)
            inner = check_(model, s, e)["probability_any"]
            for ds, de in ((1, 0), (0, 1), (2, 3)):
                outer = check_(model, s - TD(days=ds), e + TD(days=de))
                assert outer["probability_any"] >= inner - 1e-9, (s, e, ds, de)


def test_far_future_matches_long_run_renewal_rate(auth_client, regular):
    # Far ahead, P(any bleeding in an L-day window) -> (mean_period + L - 1) / cycle
    # (the window is hit iff a period starts within [a - D + 1, b]).
    model = DateCheckService.load_model(regular.id, today())
    rates = []
    for length in (1, 7, 14):
        probs = []
        for off in range(330, 330 + 28):
            s = today() + TD(days=off)
            r = DateCheckService.check_with_model(model, s, s + TD(days=length - 1))
            probs.append(r["probability_any"])
        expected = (5.0 + length - 1) / 28.0
        avg = sum(probs) / len(probs)
        rates.append((length, avg, expected))
        assert avg == pytest.approx(expected, abs=0.05), rates
    # a very regular user keeps a visible rhythm a year out: no "flat" note
    r = DateCheckService.check_with_model(
        model, today() + TD(days=330), today() + TD(days=336)
    )
    assert r["horizon_note"] is None


def test_horizon_note_follows_flatness_not_a_fixed_cutoff(db, test_user):
    add_periods(test_user, today() - TD(days=12), [24, 35, 29, 41, 26, 33, 38, 27])
    model = DateCheckService.load_model(test_user.id, today())
    near = DateCheckService.check_with_model(
        model, today() + TD(days=8), today() + TD(days=12)
    )
    far = DateCheckService.check_with_model(
        model, today() + TD(days=200), today() + TD(days=204)
    )
    assert near["horizon_note"] is None
    assert far["horizon_note"] and "far ahead" in far["horizon_note"]


def test_near_range_has_no_horizon_note(auth_client, regular):
    r = check(auth_client, today() + TD(days=5), today() + TD(days=9)).get_json()
    assert r["horizon_note"] is None


def test_probabilities_are_valid(auth_client, regular):
    r = check(auth_client, today(), today() + TD(days=59)).get_json()
    assert 0.0 <= r["probability_any"] <= 1.0
    assert all(0.0 <= d["p_bleeding"] <= 1.0 for d in r["days"])
    assert len(r["days"]) == 60


def test_range_during_ongoing_period_is_certain(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=1), [28] * 5, open_last=True)
    r = check(auth_client, today(), today() + TD(days=1)).get_json()
    assert r["probability_any"] == 1.0


def test_late_period_shifts_odds_to_the_future(db, auth_client, test_user):
    # 28-day user who is 6 days late: the engine spreads (heavy-tailed) mass over the
    # next weeks instead of treating the missed date as impossible.
    add_periods(test_user, today() - TD(days=34), [28] * 8)
    r = check(auth_client, today(), today() + TD(days=14)).get_json()
    assert r["probability_any"] > 0.25


# --- past dates / validation ---------------------------------------------------------


def test_past_range_is_flagged_and_uses_logged_days(auth_client, regular):
    last = today() - TD(days=10)
    r = check(auth_client, last, last + TD(days=2)).get_json()
    assert r["includes_past_dates"] is True
    assert r["probability_any"] == 1.0
    r = check(auth_client, last + TD(days=8), last + TD(days=9)).get_json()
    assert r["includes_past_dates"] is True
    assert r["probability_any"] == 0.0
    assert (
        check(auth_client, today(), today()).get_json()["includes_past_dates"] is False
    )


def test_range_straddling_today(auth_client, regular):
    r = check(auth_client, today() - TD(days=15), today() + TD(days=25)).get_json()
    assert r["includes_past_dates"] is True
    assert r["probability_any"] == 1.0


@pytest.mark.parametrize(
    "start,end,field",
    [
        (5, 4, "end"),  # end before start
        (0, 60, "end"),  # 61 days
        (367, 368, "start"),  # too far ahead
    ],
)
def test_validation_errors(auth_client, regular, start, end, field):
    r = check(auth_client, today() + TD(days=start), today() + TD(days=end))
    assert r.status_code == 422
    assert field in r.get_json()["detail"]["query"]


def test_boundaries_are_accepted(auth_client, regular):
    assert check(auth_client, today(), today() + TD(days=59)).status_code == 200
    s = today() + TD(days=366)
    assert check(auth_client, s, s + TD(days=59)).status_code == 200


def test_missing_or_malformed_params(auth_client, regular):
    assert auth_client.get(url_for("reports.get_date_check")).status_code == 422
    r = auth_client.get(
        url_for("reports.get_date_check"),
        query_string={"start": "tomorrow", "end": "2030-01-01"},
    )
    assert r.status_code == 422


def test_date_check_requires_auth(client):
    r = client.get(
        url_for("reports.get_date_check"),
        query_string={"start": "2030-01-01", "end": "2030-01-02"},
    )
    assert r.status_code == 401


# --- states ----------------------------------------------------------------------------


def test_no_data_state(auth_client, test_user):
    r = check(auth_client, today(), today() + TD(days=3)).get_json()
    assert r["status"] == "no_data"
    assert r["probability_any"] is None
    assert r["most_likely_days"] is None
    assert r["days"] == []
    assert r["reason"]


def test_overdue_state(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=200), [28] * 6)
    r = check(auth_client, today(), today() + TD(days=3)).get_json()
    assert r["status"] == "overdue"
    assert r["confidence"] == "overdue"
    assert r["probability_any"] is None
    assert r["reason"]


def test_learning_state_still_gives_odds(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=10), [28])  # 1 cycle only
    r = check(auth_client, today(), today() + TD(days=30)).get_json()
    assert r["status"] == "learning"
    assert r["confidence"] == "learning"
    assert 0.0 < r["probability_any"] <= 1.0
    assert r["reason"]
    assert r["cycles_used"] == 1
    assert r["cycles_needed"] == 3


def test_openapi_documents_new_endpoints(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.get_json()["paths"]
    for p in (
        "/reports/date-check",
        "/events",
        "/events/{event_id}",
        "/users/me/calendar-feed",
        "/calendar/{token}.ics",
    ):
        assert p in paths, p


def test_docs_page_loads(client):
    assert client.get("/docs").status_code == 200


# --- events ----------------------------------------------------------------------------


def make_event(client, name="Lisbon", start=None, end=None):
    start = start or today() + TD(days=19)
    end = end or start + TD(days=7)
    return client.post(
        url_for("events.create_event"),
        json={
            "name": name,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )


def test_events_require_auth(client):
    assert client.get(url_for("events.list_events")).status_code == 401
    assert client.post(url_for("events.create_event"), json={}).status_code == 401
    assert client.put(url_for("events.update_event", event_id=1)).status_code == 401
    assert client.delete(url_for("events.delete_event", event_id=1)).status_code == 401


def test_create_event_returns_live_odds(auth_client, regular):
    r = make_event(auth_client)
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Lisbon"
    assert data["probability_any"] > 0.8
    assert data["most_likely_days"]
    assert data["status"] == "ok"
    assert data["is_past"] is False
    assert data["id"]


def test_list_events_sorted_with_odds(db, auth_client, regular):
    make_event(auth_client, "later", today() + TD(days=100), today() + TD(days=103))
    make_event(auth_client, "soon", today() + TD(days=2), today() + TD(days=4))
    make_event(auth_client, "old", today() - TD(days=60), today() - TD(days=55))
    make_event(auth_client, "older", today() - TD(days=90), today() - TD(days=85))
    data = auth_client.get(url_for("events.list_events")).get_json()
    assert [e["name"] for e in data] == ["soon", "later", "old", "older"]
    assert [e["is_past"] for e in data] == [False, False, True, True]
    for e in data:
        assert "probability_any" in e and "most_likely_days" in e
    assert data[0]["probability_any"] < 0.15  # days 12-14 of cycle
    # a past event with no logged bleeding in it is certain-not
    assert data[2]["probability_any"] is None and data[2]["status"] == "past"


def test_update_and_delete_event(auth_client, regular):
    event_id = make_event(auth_client).get_json()["id"]
    new_start = today() + TD(days=2)
    r = auth_client.put(
        url_for("events.update_event", event_id=event_id),
        json={
            "name": "Renamed",
            "start_date": new_start.isoformat(),
            "end_date": (new_start + TD(days=1)).isoformat(),
        },
    )
    assert r.status_code == 200
    assert r.get_json()["name"] == "Renamed"
    assert r.get_json()["probability_any"] < 0.15
    assert (
        auth_client.delete(
            url_for("events.delete_event", event_id=event_id)
        ).status_code
        == 204
    )
    assert auth_client.get(url_for("events.list_events")).get_json() == []
    assert (
        auth_client.delete(
            url_for("events.delete_event", event_id=event_id)
        ).status_code
        == 404
    )


def test_event_odds_for_user_without_data(auth_client, test_user):
    data = make_event(auth_client).get_json()
    assert data["status"] == "no_data"
    assert data["probability_any"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "start_date": "2030-01-01", "end_date": "2030-01-02"},
        {"name": "   ", "start_date": "2030-01-01", "end_date": "2030-01-02"},
        {"name": "x" * 121, "start_date": "2030-01-01", "end_date": "2030-01-02"},
        {"start_date": "2030-01-01", "end_date": "2030-01-02"},
        {"name": "x", "start_date": "2030-01-05", "end_date": "2030-01-02"},
        {"name": "x", "start_date": "nope", "end_date": "2030-01-02"},
    ],
)
def test_event_validation(auth_client, payload):
    assert (
        auth_client.post(url_for("events.create_event"), json=payload).status_code
        == 422
    )


def test_event_range_limits(auth_client):
    t = today()
    long_end = t + TD(days=60)
    assert make_event(auth_client, "long", t, long_end).status_code == 422
    assert make_event(auth_client, "ok60", t, t + TD(days=59)).status_code == 201
    far = t + TD(days=367)
    assert make_event(auth_client, "far", far, far + TD(days=2)).status_code == 422
    assert make_event(auth_client, "x" * 120, t, t).status_code == 201


def test_events_are_private_to_their_owner(db, auth_client, regular):
    event_id = make_event(auth_client).get_json()["id"]
    other, headers = other_headers(db)
    c = auth_client.application.test_client()
    assert c.get(url_for("events.list_events"), headers=headers).get_json() == []
    body = {"name": "hack", "start_date": "2030-01-01", "end_date": "2030-01-02"}
    r = c.put(
        url_for("events.update_event", event_id=event_id), json=body, headers=headers
    )
    assert r.status_code == 404
    r = c.delete(url_for("events.delete_event", event_id=event_id), headers=headers)
    assert r.status_code == 404
    still = auth_client.get(url_for("events.list_events")).get_json()
    assert [e["name"] for e in still] == ["Lisbon"]


def test_events_cascade_with_user(db, test_user):
    PlannedEvent(
        user_id=test_user.id, name="t", start_date=today(), end_date=today()
    ).save()
    assert PlannedEvent.query.count() == 1
    test_user.delete()
    assert PlannedEvent.query.count() == 0


def test_events_cascade_via_account_deletion_endpoint(auth_client, test_user):
    make_event(auth_client)
    assert PlannedEvent.query.count() == 1
    assert auth_client.delete(url_for("users.delete_own_user")).status_code == 204
    assert PlannedEvent.query.count() == 0


# --- round 2 ---------------------------------------------------------------------------


def test_events_honour_client_today(db, auth_client, regular):
    event_id = make_event(
        auth_client, "soon", today() + TD(days=1), today() + TD(days=2)
    ).get_json()["id"]
    plain = auth_client.get(url_for("events.list_events")).get_json()[0]
    assert plain["is_past"] is False
    shifted = auth_client.get(
        url_for("events.list_events"),
        query_string={"today": (today() + TD(days=1)).isoformat()},
    ).get_json()[0]
    assert shifted["id"] == event_id
    assert shifted["is_past"] is False
    # a client one day ahead sees an event that ended yesterday (their time) as past
    ended = make_event(auth_client, "gone", today() - TD(days=1), today())
    assert ended.status_code == 201
    rows = auth_client.get(
        url_for("events.list_events"),
        query_string={"today": (today() + TD(days=1)).isoformat()},
    ).get_json()
    assert {r["name"]: r["is_past"] for r in rows}["gone"] is True
    # and a wildly wrong client date is rejected like everywhere else
    r = auth_client.get(
        url_for("events.list_events"),
        query_string={"today": (today() + TD(days=9)).isoformat()},
    )
    assert r.status_code == 422


def test_validation_error_shape_is_the_same_everywhere(auth_client, regular):
    t = today()
    dc = check(auth_client, t + TD(days=5), t)  # service-level error
    dc_missing = auth_client.get(url_for("reports.get_date_check"))  # schema-level
    ev = make_event(auth_client, "x", t + TD(days=5), t)  # schema-level
    ev_long = make_event(auth_client, "x", t, t + TD(days=70))  # service-level
    for r in (dc, dc_missing, ev, ev_long):
        body = r.get_json()
        assert r.status_code == 422
        assert body["message"] == "Validation error"
        assert set(body["detail"]) <= {"json", "query"}
    # error keys use the request's own field names
    assert "end" in dc.get_json()["detail"]["query"]
    assert "end_date" in ev_long.get_json()["detail"]["json"]
    far = make_event(auth_client, "x", t + TD(days=400), t + TD(days=401))
    assert "start_date" in far.get_json()["detail"]["json"]


def test_events_list_builds_the_engine_once(db, auth_client, regular, monkeypatch):
    from app.services.forecast_service import FittedModel

    builds = []
    real = FittedModel._compute_groups

    def counting(self, horizon):
        builds.append(horizon)
        return real(self, horizon)

    monkeypatch.setattr(FittedModel, "_compute_groups", counting)
    for k in range(20):
        s = today() + TD(days=12 * k)
        make_event(auth_client, f"e{k}", s, s + TD(days=6))
    builds.clear()
    rows = auth_client.get(url_for("events.list_events")).get_json()
    assert len(rows) == 20
    assert len(builds) == 1


def test_straddling_range_with_open_period_is_certain(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=1), [28] * 6, open_last=True)
    r = check(auth_client, today() - TD(days=3), today() + TD(days=5)).get_json()
    assert r["probability_any"] == 1.0
    assert r["includes_past_dates"] is True


def test_straddling_range_with_forgotten_open_period(db, auth_client, test_user):
    # period opened 20 days ago and never closed: treated as over, future part decides
    add_periods(test_user, today() - TD(days=20), [28] * 6, open_last=True)
    model = DateCheckService.load_model(test_user.id, today())
    past_only = DateCheckService.check_with_model(
        model, today() - TD(days=12), today() - TD(days=11)
    )
    assert past_only["probability_any"] < 0.01  # unknown end, but long over
    mixed = DateCheckService.check_with_model(
        model, today() - TD(days=12), today() + TD(days=3)
    )
    future = DateCheckService.check_with_model(model, today(), today() + TD(days=3))
    p_past = max(d["p_bleeding"] for d in mixed["days"][:12])
    expected = max(
        1 - (1 - p_past) * (1 - future["probability_any"]),
        max(d["p_bleeding"] for d in mixed["days"]),  # never below the daily floor
    )
    assert mixed["probability_any"] == pytest.approx(expected, abs=2e-3)


# --- round 3 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["a\x00b", "a‮b", "line\nbreak", "a b", "tab\tb", "a‏b"],
)
def test_event_names_reject_control_and_bidi_characters(auth_client, name):
    r = make_event(auth_client, name, today(), today())
    assert r.status_code == 422
    assert "name" in r.get_json()["detail"]["json"]


def test_event_name_is_trimmed_and_allows_emoji(auth_client):
    r = make_event(auth_client, "  Lisbon 🇵🇹 trip  ", today(), today())
    assert r.status_code == 201 and r.get_json()["name"] == "Lisbon 🇵🇹 trip"


def test_event_dates_are_bounded(auth_client):
    r = make_event(auth_client, "x", D(1, 1, 1), D(1, 1, 5))
    assert r.status_code == 422 and "start_date" in r.get_json()["detail"]["json"]
    r = make_event(auth_client, "x", D(1899, 12, 31), D(1899, 12, 31))
    assert r.status_code == 422
    r = make_event(auth_client, "x", D(1900, 1, 1), D(1900, 1, 1))
    assert r.status_code == 201
    r = check(auth_client, D(1, 1, 1), D(1, 1, 3))
    assert r.status_code == 422 and "start" in r.get_json()["detail"]["query"]


def test_event_cap_per_user(db, auth_client, test_user, monkeypatch):
    from app.services import planned_event_service as pes

    monkeypatch.setattr(pes, "MAX_EVENTS_PER_USER", 3)
    for k in range(3):
        assert make_event(auth_client, f"e{k}", today(), today()).status_code == 201
    r = make_event(auth_client, "one too many", today(), today())
    assert r.status_code == 422 and "name" in r.get_json()["detail"]["json"]
    # other users are unaffected
    other, headers = other_headers(db)
    c = auth_client.application.test_client()
    body = {
        "name": "mine",
        "start_date": today().isoformat(),
        "end_date": today().isoformat(),
    }
    assert c.post("/events", json=body, headers=headers).status_code == 201


def test_past_events_carry_no_odds(auth_client, regular):
    r = make_event(auth_client, "gone", today() - TD(days=30), today() - TD(days=25))
    body = r.get_json()
    assert body["is_past"] is True
    assert body["probability_any"] is None and body["most_likely_days"] is None
    assert body["status"] == "past"


def test_get_single_event(db, auth_client, regular):
    event_id = make_event(auth_client).get_json()["id"]
    r = auth_client.get(url_for("events.get_event", event_id=event_id))
    assert r.status_code == 200 and r.get_json()["name"] == "Lisbon"
    other, headers = other_headers(db)
    c = auth_client.application.test_client()
    assert c.get(f"/events/{event_id}", headers=headers).status_code == 404  # not yours
    assert auth_client.get("/events/99999").status_code == 404
    assert c.get(f"/events/{event_id}").status_code == 401


def test_bad_client_today_uses_the_standard_query_error_shape(auth_client, regular):
    far = (today() + TD(days=9)).isoformat()
    bad = auth_client.get(
        url_for("reports.get_date_check"),
        query_string={
            "start": today().isoformat(),
            "end": today().isoformat(),
            "today": far,
        },
    )
    malformed = auth_client.get(
        url_for("reports.get_date_check"),
        query_string={
            "start": today().isoformat(),
            "end": today().isoformat(),
            "today": "x",
        },
    )
    for r in (bad, malformed):
        assert r.status_code == 422
        assert "today" in r.get_json()["detail"]["query"]
