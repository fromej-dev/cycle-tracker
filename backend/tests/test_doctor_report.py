import datetime
import re

import pytest
from flask import url_for

from app.models import Period, User
from app.services.doctor_report_service import DoctorReportService

D = datetime.date
TD = datetime.timedelta
TODAY = D.today()


def mk(gaps, last_offset=10, duration=5):
    """Periods whose consecutive start gaps are ``gaps`` (oldest first); the newest
    starts ``last_offset`` days before today."""
    starts = [TODAY - TD(days=last_offset)]
    for g in reversed(gaps):
        starts.append(starts[-1] - TD(days=g))
    return [(s, s + TD(days=duration - 1)) for s in reversed(starts)]


class U:
    username = "alice"


def build(periods, months=24, name=False):
    return DoctorReportService.build(U, periods, months, TODAY, include_name=name)


def codes(r):
    return {f["code"] for f in r["flags"]}


def test_regular_has_no_flags_and_stats():
    r = build(mk([28] * 8))
    assert codes(r) == set()
    assert r["stats"]["median_cycle_days"] == 28
    assert r["stats"]["variability_days"] == 0
    assert r["stats"]["median_period_days"] == 5
    assert r["stats"]["cycles_counted"] == 8


@pytest.mark.parametrize(
    "gaps,flagged",
    [
        ([28] * 4 + [36, 28], False),  # one long
        ([28] * 3 + [35, 35, 28], False),  # 35 is inside the band
        ([28] * 3 + [21, 21, 28], False),  # 21 is inside the band
        ([28] * 3 + [36, 28, 36], True),  # two long
        ([28] * 3 + [20, 28, 20], True),  # two short
        ([28] * 3 + [36, 28, 20], True),  # one long + one short
        ([36, 36] + [28] * 6, False),  # old ones are outside the last 6
    ],
)
def test_out_of_range_threshold(gaps, flagged):
    r = build(mk(gaps))
    assert ("cycle_length_out_of_range" in codes(r)) is flagged


@pytest.mark.parametrize("last,flagged", [(34, False), (35, True), (36, True)])
def test_variability_exactly_seven(last, flagged):
    # spread = last - 28 (28 is the shortest); all within the band of non-flag lengths
    r = build(mk([28, 28, 28, 28, 28, last]))
    assert r["stats"]["variability_days"] == last - 28
    assert ("cycle_variability" in codes(r)) is flagged


def test_variability_wording_cites_thresholds():
    r = build(mk([28, 28, 28, 28, 28, 38]))
    f = next(f for f in r["flags"] if f["code"] == "cycle_variability")
    assert "7 days or more" in f["threshold"] and "7-9" in f["threshold"]
    assert "above the 9-day" in f["observed"]


def test_variability_uses_last_six_only():
    r = build(mk([28, 40] + [28] * 6))
    assert r["stats"]["variability_days"] == 0


@pytest.mark.parametrize("dur,flagged", [(8, False), (9, True)])
def test_long_period_threshold(dur, flagged):
    r = build(mk([28] * 4, duration=dur))
    assert ("long_period" in codes(r)) is flagged


@pytest.mark.parametrize("offset,flagged", [(90, False), (91, True)])
def test_no_period_90_days(offset, flagged):
    r = build(mk([28] * 4, last_offset=offset))
    assert ("no_period_90_days" in codes(r)) is flagged


def test_ongoing_period_is_not_a_gap():
    ps = mk([28] * 4, last_offset=3)
    ps[-1] = (ps[-1][0], None)
    assert "no_period_90_days" not in codes(build(ps))


def test_missed_log_excluded_and_listed():
    ps = mk([28, 28, 28, 28, 60, 28, 28], last_offset=10)
    r = build(ps)
    assert 60 not in [c["cycle_days"] for c in r["cycles"] if not c["excluded"]]
    assert [g["gap_days"] for g in r["excluded_gaps"]] == [60]
    assert r["stats"]["max_cycle_days"] == 28  # gap not in the stats
    assert r["stats"]["variability_days"] == 0
    assert "possible_missed_logs" in codes(r)
    assert "60 days" in DoctorReportService.render_html(r)


def test_gap_over_90_flags_and_is_excluded():
    r = build(mk([28, 28, 28, 120, 28, 28]))
    assert {"no_period_90_days", "possible_missed_logs"} <= codes(r)
    assert r["stats"]["max_cycle_days"] == 28


def test_empty_and_single_period():
    r = build([])
    assert r["cycles"] == [] and r["flags"] == []
    assert r["stats"]["median_cycle_days"] is None
    html = DoctorReportService.render_html(r)
    assert "No periods logged" in html and "Not a diagnosis" in html
    r1 = build(mk([]))
    assert len(r1["cycles"]) == 1 and r1["stats"]["cycles_counted"] == 0
    assert r1["stats"]["variability_days"] is None
    assert codes(r1) == set()
    DoctorReportService.render_html(r1)


def test_months_window_limits_rows():
    ps = mk([28] * 20)
    assert len(build(ps, months=6)["cycles"]) < len(build(ps, months=24)["cycles"])


def test_html_self_contained_and_printable():
    html = DoctorReportService.render_html(
        build(mk([28, 30, 27, 29, 28, 31]), name=True)
    )
    assert "<svg" in html and "polyline" in html
    assert "@media print" in html and "@page" in html
    assert not re.search(r"https?://|//cdn|<link|<script src|@import|url\(", html)
    assert "alice" in html
    assert "FIGO" in html and "Not a diagnosis" in html


def test_name_hidden_by_default_and_escaped():
    class Evil:
        username = "<b>x</b>"

    html = DoctorReportService.render_html(
        DoctorReportService.build(Evil, mk([28] * 3), 12, TODAY, include_name=True)
    )
    assert "<b>x</b>" not in html and "&lt;b&gt;" in html
    assert "alice" not in DoctorReportService.render_html(build(mk([28] * 3)))


def test_endpoints(auth_client, test_user):
    for s, e in mk([28] * 5, duration=5):
        Period(user_id=test_user.id, start_date=s, end_date=e).save()
    r = auth_client.get(url_for("doctor_report.doctor_report_html", months=6))
    assert r.status_code == 200 and r.mimetype == "text/html"
    assert "no-store" in r.headers["Cache-Control"]
    assert "testuser" not in r.get_data(as_text=True)
    r = auth_client.get(
        url_for("doctor_report.doctor_report_html", include_name="true")
    )
    assert "testuser" in r.get_data(as_text=True)
    j = auth_client.get(url_for("doctor_report.doctor_report_json", months=12))
    body = j.get_json()
    assert j.status_code == 200
    assert body["stats"]["median_cycle_days"] == 28
    assert body["generated"] == TODAY.isoformat()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", body["cycles"][0]["start"])
    bad = auth_client.get(url_for("doctor_report.doctor_report_json", months=7))
    assert bad.status_code == 422


def test_requires_auth(client):
    assert client.get("/reports/doctor").status_code == 401
    assert client.get("/reports/doctor.json").status_code == 401


def test_only_own_data(auth_client, test_user, db):
    other = User(username="other", email="o@example.com")
    other.set_password("x")
    db.session.add(other)
    db.session.commit()
    for s, e in mk([28] * 5):
        Period(user_id=other.id, start_date=s, end_date=e).save()
    body = auth_client.get(url_for("doctor_report.doctor_report_json")).get_json()
    assert body["cycles"] == []
