import datetime
import hashlib
import json
import random

import pytest
from flask import url_for

from app.models import Period, User
from app.services.date_check_service import DateCheckService
from app.utils import ics

D = datetime.date
TD = datetime.timedelta


def today():
    return D.today()


def add_periods(user, last_start, gaps, duration=5):
    starts = [last_start]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    for s in reversed(starts):
        Period(user_id=user.id, start_date=s, end_date=s + TD(days=duration - 1)).save()


@pytest.fixture
def regular(db, test_user):
    add_periods(test_user, today() - TD(days=10), [28] * 8)
    return test_user


def enable(auth_client):
    r = auth_client.post(url_for("users.create_calendar_feed"))
    assert r.status_code == 201
    body = r.get_json()
    assert body["url"] is None  # no PUBLIC_BASE_URL -> path only
    path = body["path"]
    token = path.rsplit("/", 1)[1].removesuffix(".ics")
    return path, token


def get_ics(client, token):
    return client.get(url_for("calendar.get_calendar_feed", token=token))


# --- a tiny RFC 5545 reader (independent of the writer) -----------------------------


def unfold(raw: str) -> list[str]:
    assert raw.endswith("\r\n")
    physical = raw[:-2].split("\r\n")
    logical: list[str] = []
    for line in physical:
        if line.startswith(" "):
            logical[-1] += line[1:]
        else:
            logical.append(line)
    return logical


def unescape(v: str) -> str:
    out, i = [], 0
    while i < len(v):
        if v[i] == "\\":
            nxt = v[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
        else:
            out.append(v[i])
            i += 1
    return "".join(out)


def parse(raw: str):
    """Returns (calendar properties dict, [event property dicts])."""
    lines = unfold(raw)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    cal, events, cur = {}, [], None
    for line in lines[1:-1]:
        if line == "BEGIN:VEVENT":
            assert cur is None
            cur = {}
        elif line == "END:VEVENT":
            events.append(cur)
            cur = None
        else:
            name, _, value = line.partition(":")
            (cur if cur is not None else cal)[name] = value
    assert cur is None
    return cal, events


def kind(ev) -> str:
    """'l' logged, 'f' fertile, 'x' predicted period (UIDs are opaque on purpose)."""
    if day(ev["DTSTART;VALUE=DATE"]) in {p.start_date for p in Period.query.all()}:
        return "l"
    if "·" in ev["SUMMARY"] or "🌱" in ev["SUMMARY"]:
        return "f"
    return "x"


def predicted(events):
    return [e for e in events if kind(e) == "x"]


def day(v: str) -> datetime.date:
    return datetime.datetime.strptime(v, "%Y%m%d").date()


# --- settings endpoints ----------------------------------------------------------------


def test_feed_endpoints_require_jwt(client):
    assert client.get(url_for("users.get_calendar_feed_settings")).status_code == 401
    assert client.post(url_for("users.create_calendar_feed")).status_code == 401
    assert (
        client.patch(url_for("users.update_calendar_feed"), json={}).status_code == 401
    )
    assert client.delete(url_for("users.revoke_calendar_feed")).status_code == 401


def test_default_settings(auth_client):
    data = auth_client.get(url_for("users.get_calendar_feed_settings")).get_json()
    assert data == {
        "enabled": False,
        "label": "🌙",
        "include_fertile": False,
        "fertile_label": None,
        "mark_estimates": False,
        "timezone": None,
    }


def test_create_returns_url_once_and_never_in_settings(auth_client, db, test_user):
    url, token = enable(auth_client)
    assert url == f"/calendar/{token}.ics"
    assert len(token) >= 43
    settings = auth_client.get(url_for("users.get_calendar_feed_settings")).get_json()
    assert settings["enabled"] is True
    assert token not in str(settings)
    assert set(settings) == {
        "enabled",
        "label",
        "include_fertile",
        "fertile_label",
        "mark_estimates",
        "timezone",
    }


def test_token_is_stored_only_as_sha256_hash(auth_client, db, test_user):
    _, token = enable(auth_client)
    db.session.refresh(test_user)
    stored = test_user.calendar_token_hash
    assert stored != token
    assert token not in stored
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    # not leaked through any user-facing representation either
    me = auth_client.get(url_for("users.get_own_user")).get_data(as_text=True)
    assert token not in me and stored not in me


def test_rotation_invalidates_old_url(auth_client, regular):
    _, old = enable(auth_client)
    assert get_ics(auth_client.application.test_client(), old).status_code == 200
    _, new = enable(auth_client)
    assert new != old
    c = auth_client.application.test_client()
    assert get_ics(c, old).status_code == 404
    assert get_ics(c, new).status_code == 200


def test_revoke_makes_feed_404(auth_client, regular):
    _, token = enable(auth_client)
    assert auth_client.delete(url_for("users.revoke_calendar_feed")).status_code == 204
    assert get_ics(auth_client.application.test_client(), token).status_code == 404
    settings = auth_client.get(url_for("users.get_calendar_feed_settings")).get_json()
    assert settings["enabled"] is False


@pytest.mark.parametrize(
    "token", ["nope", "a" * 43, "x" * 500, "..%2f", "A-_" * 15, "e" * 64]
)
def test_unknown_tokens_are_404(client, regular, token):
    r = get_ics(client, token)
    assert r.status_code == 404
    assert b"BEGIN:VCALENDAR" not in r.data


def test_patch_label_and_fertile(auth_client):
    url = url_for("users.update_calendar_feed")
    r = auth_client.patch(url, json={"label": "Cycle", "include_fertile": True})
    assert r.get_json()["label"] == "Cycle"
    assert r.get_json()["include_fertile"] is True
    r = auth_client.patch(url, json={"include_fertile": False})
    assert r.get_json()["label"] == "Cycle"  # untouched
    assert r.get_json()["include_fertile"] is False
    assert auth_client.patch(url, json={"label": None}).get_json()["label"] == "🌙"
    assert auth_client.patch(url, json={"label": "  "}).get_json()["label"] == "🌙"
    assert auth_client.patch(url, json={"label": "x" * 41}).status_code == 422
    assert auth_client.patch(url, json={"label": "a\nb"}).status_code == 422
    assert auth_client.patch(url, json={"include_fertile": "maybe"}).status_code == 422


# --- the feed itself --------------------------------------------------------------------


def test_feed_headers_and_envelope(auth_client, regular):
    _, token = enable(auth_client)
    r = get_ics(auth_client.application.test_client(), token)  # no JWT
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "text/calendar; charset=utf-8"
    assert r.headers["Content-Disposition"].startswith("inline")
    assert r.headers["Cache-Control"] == "no-store"
    raw = r.get_data(as_text=True)
    cal, events = parse(raw)
    assert cal["VERSION"] == "2.0"
    assert cal["PRODID"].startswith("-//")
    assert cal["CALSCALE"] == "GREGORIAN"
    assert cal["X-WR-CALNAME"] == "🌙"
    assert cal["REFRESH-INTERVAL;VALUE=DURATION"] == "PT12H"
    assert cal["X-PUBLISHED-TTL"] == "PT12H"
    assert len(events) == 5  # 2 logged + 3 predicted


def test_feed_is_valid_rfc5545_structure(auth_client, regular):
    label = "🌙é;," * 10  # 40 chars, 80 octets before escaping
    r = auth_client.patch(
        url_for("users.update_calendar_feed"),
        json={"label": label, "include_fertile": True},
    )
    assert r.status_code == 200
    _, token = enable(auth_client)
    raw = get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    # CRLF everywhere: no bare LF or CR
    assert raw.replace("\r\n", "").count("\n") == 0
    assert raw.replace("\r\n", "").count("\r") == 0
    assert raw.endswith("\r\n")
    # every physical line <= 75 octets, folded lines start with a space
    physical = raw[:-2].split("\r\n")
    assert all(len(line.encode("utf-8")) <= 75 for line in physical)
    assert any(line.startswith(" ") for line in physical)  # label forced folding
    # unfolding restores a parseable calendar with the original (escaped) label
    cal, events = parse(raw)
    assert unescape(cal["X-WR-CALNAME"]) == label
    assert len(events) == 8  # 2 logged + 3 predicted + 3 fertile windows
    for ev in events:
        for key in (
            "UID",
            "DTSTAMP",
            "DTSTART;VALUE=DATE",
            "DTEND;VALUE=DATE",
            "SUMMARY",
        ):
            assert key in ev
        assert ev["TRANSP"] == "TRANSPARENT"
        assert len(ev["DTSTAMP"]) == 16 and ev["DTSTAMP"].endswith("Z")
    assert len({ev["UID"] for ev in events}) == 8
    assert all(ev["UID"].endswith("@feed") for ev in events)
    assert cal["PRODID"] == "-//private-feed//EN"
    assert "cycle-tracker" not in raw.lower()


def test_all_day_events_use_exclusive_dtend_and_sane_dates(auth_client, regular):
    _, token = enable(auth_client)
    _, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    for ev in events:
        start, end = day(ev["DTSTART;VALUE=DATE"]), day(ev["DTEND;VALUE=DATE"])
        assert 2 <= (end - start).days <= 20  # DTEND exclusive
    events = predicted(events)
    assert all(day(e["DTSTART;VALUE=DATE"]) >= today() for e in events)
    starts = [day(ev["DTSTART;VALUE=DATE"]) for ev in events]
    assert starts == sorted(starts)
    # regular 28-day user, last start 10 days ago -> next start ~18 days out
    assert abs((starts[0] - today()).days - 18) <= 3
    gaps = [(b - a).days for a, b in zip(starts, starts[1:], strict=False)]
    assert all(25 <= g <= 31 for g in gaps)


def test_default_is_discreet(auth_client, regular):
    _, token = enable(auth_client)
    raw = get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    _, events = parse(raw)
    assert {ev["SUMMARY"] for ev in events} == {"🌙"}
    assert "DESCRIPTION" not in raw
    assert "CLASS:PRIVATE" in raw
    lowered = raw.lower()
    for word in ("period", "menstru", "fertile", "ovulat", "cycle", "tracker"):
        assert word not in lowered
    assert regular.username not in raw and regular.email not in raw


def test_custom_label_is_used_as_summary(auth_client, regular):
    auth_client.patch(url_for("users.update_calendar_feed"), json={"label": "Period"})
    _, token = enable(auth_client)
    cal, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    assert cal["X-WR-CALNAME"] == "Period"
    assert {ev["SUMMARY"] for ev in events} == {"Period"}


def test_include_fertile_toggle(auth_client, regular):
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    _, plain = parse(get_ics(c, token).get_data(as_text=True))
    assert len(plain) == 5 and not [e for e in plain if kind(e) == "f"]
    auth_client.patch(
        url_for("users.update_calendar_feed"), json={"include_fertile": True}
    )
    _, both = parse(get_ics(c, token).get_data(as_text=True))
    assert len(both) == 8
    # distinct but discreet by default: same title plus a middle dot ...
    assert {e["SUMMARY"] for e in both if kind(e) == "f"} == {"🌙 ·"}
    assert {e["SUMMARY"] for e in both if kind(e) != "f"} == {"🌙"}
    # ... or whatever the user picks
    r = auth_client.patch(
        url_for("users.update_calendar_feed"), json={"fertile_label": "🌱"}
    )
    assert r.get_json()["fertile_label"] == "🌱"
    _, both = parse(get_ics(c, token).get_data(as_text=True))
    fertile = [e for e in both if kind(e) == "f"]
    assert len(fertile) == 3 and {e["SUMMARY"] for e in fertile} == {"🌱"}
    # fertile windows precede the next period start (ovulation ~14d before)
    first_period = min(day(e["DTSTART;VALUE=DATE"]) for e in predicted(both))
    first_fertile = min(day(e["DTSTART;VALUE=DATE"]) for e in fertile)
    assert first_fertile < first_period
    auth_client.patch(
        url_for("users.update_calendar_feed"), json={"include_fertile": False}
    )
    _, off = parse(get_ics(c, token).get_data(as_text=True))
    assert len(off) == 5


def test_uids_are_opaque_and_stable_across_refreshes(auth_client, regular):
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    first = [e["UID"] for e in parse(get_ics(c, token).get_data(as_text=True))[1]]
    second = [e["UID"] for e in parse(get_ics(c, token).get_data(as_text=True))[1]]
    assert first == second
    for uid in first:
        head, _, tail = uid.partition("@")
        assert tail == "feed" and len(head) == 32 and int(head, 16) >= 0


def test_ongoing_period_is_included_from_its_start(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=20), [28] * 5)
    Period(user_id=test_user.id, start_date=today() - TD(days=1)).save()  # open
    _, token = enable(auth_client)
    _, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    logged = [e for e in events if kind(e) == "l"]
    assert len(logged) == 2  # previous period + the open one
    first = logged[-1]
    assert day(first["DTSTART;VALUE=DATE"]) == today() - TD(days=1)
    assert day(first["DTEND;VALUE=DATE"]) > today()
    assert len(predicted(events)) == 3


def test_no_data_and_overdue_users_get_valid_empty_calendars(
    db, auth_client, test_user
):
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    raw = get_ics(c, token).get_data(as_text=True)
    assert "BEGIN:VEVENT" not in raw
    cal, events = parse(raw)
    assert cal["VERSION"] == "2.0" and events == []
    add_periods(test_user, today() - TD(days=300), [28] * 5)
    cal, events = parse(get_ics(c, token).get_data(as_text=True))
    assert [kind(e) for e in events] == ["l", "l"]  # logged history only
    assert all(day(e["DTEND;VALUE=DATE"]) < today() for e in events)


def test_feed_is_per_user(db, auth_client, regular):
    other = User(username="other", email="o@example.com")
    other.set_password("password")
    db.session.add(other)
    db.session.commit()
    add_periods(other, today() - TD(days=3), [35] * 6)
    other.update(calendar_label="Other")
    c = auth_client.application.test_client()
    _, mine = enable(auth_client)
    mine_cal, _ = parse(get_ics(c, mine).get_data(as_text=True))
    from app.services.calendar_service import CalendarService

    other_token = CalendarService.rotate_token(other)
    other_cal, other_events = parse(get_ics(c, other_token).get_data(as_text=True))
    assert mine_cal["X-WR-CALNAME"] == "🌙"
    assert other_cal["X-WR-CALNAME"] == "Other"
    assert other_events


def test_account_deletion_removes_feed(auth_client, db, regular):
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    assert auth_client.delete(url_for("users.delete_own_user")).status_code == 204
    assert get_ics(c, token).status_code == 404
    assert User.query.count() == 0


def test_feed_response_does_not_depend_on_token_case_shape(client, db):
    # Looks like a valid token but unknown -> same 404 body as garbage
    a = get_ics(client, "A" * 43)
    b = get_ics(client, "bad")
    assert a.status_code == b.status_code == 404
    assert a.get_data() == b.get_data()


# --- writer unit tests ------------------------------------------------------------------


def test_escape_text():
    assert ics.escape_text("a,b;c\\d\ne\r\nf") == "a\\,b\\;c\\\\d\\ne\\nf"
    assert ics.escape_text("plain 🌙") == "plain 🌙"
    assert unescape(ics.escape_text("x;y,z\\\n!")) == "x;y,z\\\n!"


def test_fold_short_line_untouched():
    assert ics.fold_line("SUMMARY:hi") == ["SUMMARY:hi"]
    assert ics.fold_line("a" * 75) == ["a" * 75]
    assert len(ics.fold_line("a" * 76)) == 2


@pytest.mark.parametrize("alphabet", ["a", "é", "🌙", "aé🌙日"])
def test_fold_is_utf8_safe_and_lossless(alphabet):
    rng = random.Random(7)
    for n in list(range(1, 200)) + [500]:
        line = "".join(rng.choice(alphabet) for _ in range(n))
        parts = ics.fold_line(line)
        assert all(len(p.encode("utf-8")) <= 75 for p in parts)
        assert all(p.startswith(" ") for p in parts[1:])
        assert parts[0] + "".join(p[1:] for p in parts[1:]) == line
        for p in parts:
            p.encode("utf-8")  # no broken surrogates / half characters


def test_serialize_uses_crlf():
    out = ics.serialize(["BEGIN:VCALENDAR", "X:" + "é" * 100, "END:VCALENDAR"])
    assert out.endswith("\r\n")
    assert "\n" not in out.replace("\r\n", "")
    assert unfold(out)[1] == "X:" + "é" * 100


# --- round 2: security / consistency ---------------------------------------------------


def test_feed_url_never_built_from_host_header(auth_client, db, test_user):
    r = auth_client.post(
        url_for("users.create_calendar_feed"),
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil2.example"},
    )
    body = r.get_json()
    assert body["url"] is None
    assert body["path"].startswith("/calendar/") and "evil" not in str(body)


def test_absolute_url_only_from_public_base_url(auth_client, app, db, test_user):
    app.config["PUBLIC_BASE_URL"] = "https://cycle.example.com/"
    try:
        body = auth_client.post(url_for("users.create_calendar_feed")).get_json()
    finally:
        app.config["PUBLIC_BASE_URL"] = None
    assert body["url"] == "https://cycle.example.com" + body["path"]


def test_feed_is_not_cacheable_so_revoke_takes_effect(auth_client, regular):
    _, token = enable(auth_client)
    r = get_ics(auth_client.application.test_client(), token)
    assert r.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "label",
    [
        "a‮b",  # right-to-left override
        "a b",  # line separator
        "a b",
        "a‏b",  # RLM
        "a⁦b",  # isolate
        "a\x1bb",
        "a\x85b",  # NEL
        "a﻿b",  # BOM / zero width no-break
    ],
)
def test_label_rejects_unicode_control_and_format_chars(auth_client, label):
    url = url_for("users.update_calendar_feed")
    assert auth_client.patch(url, json={"label": label}).status_code == 422
    assert auth_client.patch(url, json={"fertile_label": label}).status_code == 422


def test_label_allows_compound_emoji(auth_client):
    label = "👩‍👩‍👧 ❤️"
    r = auth_client.patch(url_for("users.update_calendar_feed"), json={"label": label})
    assert r.status_code == 200 and r.get_json()["label"] == label


def test_mark_estimates_is_opt_in_and_discreet(auth_client, regular):
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    _, plain = parse(get_ics(c, token).get_data(as_text=True))
    assert {ev["SUMMARY"] for ev in plain} == {"🌙"}
    auth_client.patch(
        url_for("users.update_calendar_feed"), json={"mark_estimates": True}
    )
    _, marked = parse(get_ics(c, token).get_data(as_text=True))
    # only predictions are marked, logged periods are facts
    assert {e["SUMMARY"] for e in predicted(marked)} == {"🌙 ~"}
    assert {e["SUMMARY"] for e in marked if kind(e) == "l"} == {"🌙"}


def test_ongoing_period_is_not_marked_as_estimate(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=20), [28] * 5)
    Period(user_id=test_user.id, start_date=today() - TD(days=1)).save()
    auth_client.patch(
        url_for("users.update_calendar_feed"), json={"mark_estimates": True}
    )
    _, token = enable(auth_client)
    _, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    logged = [e for e in events if kind(e) == "l"]
    assert {e["SUMMARY"] for e in logged} == {"🌙"}
    assert {e["SUMMARY"] for e in predicted(events)} == {"🌙 ~"}


def test_at_most_three_predicted_cycles_and_they_widen(auth_client, regular):
    _, token = enable(auth_client)
    _, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    pred = predicted(events)
    assert 1 <= len(pred) <= 3
    lengths = [
        (day(e["DTEND;VALUE=DATE"]) - day(e["DTSTART;VALUE=DATE"])).days for e in pred
    ]
    assert lengths[-1] >= lengths[0]


def test_logged_periods_stay_in_the_feed_with_stable_uids(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=40), [28] * 6)
    rows = (
        Period.query.filter_by(user_id=test_user.id).order_by(Period.start_date).all()
    )
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    _, events = parse(get_ics(c, token).get_data(as_text=True))
    logged = [e for e in events if kind(e) == "l"]
    # the last two logged periods, even though both are over
    assert [day(e["DTSTART;VALUE=DATE"]) for e in logged] == [
        r.start_date for r in rows[-2:]
    ]
    # deleting an OLD period does not change any identity
    rows[0].delete()
    _, events2 = parse(get_ics(c, token).get_data(as_text=True))
    assert {e["UID"] for e in events} == {e["UID"] for e in events2}


def test_predicted_period_keeps_its_uid_when_it_is_logged(db, auth_client, test_user):
    """Alarms and notes on the predicted event survive logging the real period."""
    add_periods(test_user, today() - TD(days=26), [28] * 6)
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    _, before = parse(get_ics(c, token).get_data(as_text=True))
    pred = predicted(before)
    first_uid, second_uid = pred[0]["UID"], pred[1]["UID"]
    Period(user_id=test_user.id, start_date=today()).save()  # the user logs it
    _, after = parse(get_ics(c, token).get_data(as_text=True))
    by_uid = {e["UID"]: e for e in after}
    assert kind(by_uid[first_uid]) == "l"  # same event, now a logged period
    assert day(by_uid[first_uid]["DTSTART;VALUE=DATE"]) == today()
    # the old second prediction is now the first
    assert second_uid in {e["UID"] for e in predicted(after)}
    # nothing that was published before vanished except the oldest logged period
    gone = {e["UID"] for e in before} - set(by_uid)
    assert len(gone) <= 1


def test_events_that_come_back_continue_their_sequence(db, auth_client, test_user):
    from app.services.calendar_service import CalendarService

    add_periods(test_user, today() - TD(days=10), [28] * 6)
    t = datetime.datetime(2026, 10, 25, 6, 0, 0)
    CalendarService.build_ics(test_user, today(), t)
    # pretend the forecast flattened (nothing but logged), then returned
    state = json.loads(test_user.calendar_state)
    uid = next(u for u, r in state["events"].items() if r["s"] == 0)
    state["events"][uid] = {**state["events"][uid], "x": 1, "s": 4}
    test_user.update(calendar_state=json.dumps(state))
    out = CalendarService.build_ics(test_user, today(), t + TD(days=1))
    assert f"UID:{uid}" in out
    seq = out.split(f"UID:{uid}")[1].split("SEQUENCE:")[1].split("\r\n")[0]
    assert int(seq) == 5


def test_late_user_feed_window_covers_where_date_check_puts_the_mass(
    db, auth_client, test_user
):
    add_periods(test_user, today() - TD(days=36), [28] * 8)
    model = DateCheckService.load_model(test_user.id, today())
    _, token = enable(auth_client)
    _, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    pred = predicted(events)
    assert pred
    first = day(pred[0]["DTSTART;VALUE=DATE"])
    last = day(pred[0]["DTEND;VALUE=DATE"]) - TD(days=1)
    assert last >= today()
    r = DateCheckService.check_with_model(model, max(first, today()), last)
    assert r["probability_any"] >= 0.5
    # the feed does not claim an early block the user is already past
    assert last >= today() + TD(days=1)


def test_skipper_feed_window_holds_half_the_start_mass(db, auth_client, test_user):
    add_periods(test_user, today() - TD(days=20), [28, 56, 28, 28, 55, 28])
    model = DateCheckService.load_model(test_user.id, today())
    dist = model.next_start_distribution()
    _, token = enable(auth_client)
    _, events = parse(
        get_ics(auth_client.application.test_client(), token).get_data(as_text=True)
    )
    first_ev = predicted(events)[0]
    lo = day(first_ev["DTSTART;VALUE=DATE"])
    hi = day(first_ev["DTEND;VALUE=DATE"])  # exclusive
    mass = sum(p for d, p in dist.items() if lo <= d < hi)
    assert mass >= 0.5


def test_uid_of_a_prediction_is_stable_across_refreshes(auth_client, regular):
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    a = [e["UID"] for e in parse(get_ics(c, token).get_data(as_text=True))[1]]
    b = [e["UID"] for e in parse(get_ics(c, token).get_data(as_text=True))[1]]
    assert a == b


def test_sequence_is_per_event_and_only_moves_with_that_event(
    db, auth_client, test_user
):
    add_periods(test_user, today() - TD(days=10), [28] * 6)
    _, token = enable(auth_client)
    c = auth_client.application.test_client()
    r1 = get_ics(c, token).get_data(as_text=True)
    r2 = get_ics(c, token).get_data(as_text=True)
    assert r1 == r2  # byte-identical: clients see no change
    _, ev1 = parse(r1)
    for ev in ev1:
        assert ev["LAST-MODIFIED"] == ev["DTSTAMP"]
        assert ev["SEQUENCE"] == "0"
    # label change revises every event (title changed) ...
    auth_client.patch(url_for("users.update_calendar_feed"), json={"label": "X"})
    _, ev2 = parse(get_ics(c, token).get_data(as_text=True))
    assert all(e["SEQUENCE"] == "1" for e in ev2)
    # ... but turning on a feature that adds events leaves existing ones alone
    auth_client.patch(
        url_for("users.update_calendar_feed"), json={"include_fertile": True}
    )
    _, ev3 = parse(get_ics(c, token).get_data(as_text=True))
    old = {e["UID"]: e for e in ev2}
    for e in ev3:
        if e["UID"] in old:
            assert e["SEQUENCE"] == old[e["UID"]]["SEQUENCE"]
            assert e["DTSTAMP"] == old[e["UID"]]["DTSTAMP"]
        else:
            assert e["SEQUENCE"] == "0"


def test_stamp_uses_the_time_of_the_change(db, test_user):
    from app.services.calendar_service import CalendarService

    add_periods(test_user, today() - TD(days=10), [28] * 6)
    t1 = datetime.datetime(2026, 10, 25, 10, 0, 0)
    first = CalendarService.build_ics(test_user, today(), t1)
    later = CalendarService.build_ics(test_user, today(), t1 + TD(hours=5))
    assert first == later
    assert "DTSTAMP:20261025T100000Z" in first
