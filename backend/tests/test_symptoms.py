import datetime

from app.models import Period, SymptomLog, User
from app.services.doctor_report_service import DoctorReportService

D = datetime.date
TD = datetime.timedelta
TODAY = D.today()


def put(client, day, symptoms=(), custom=()):
    return client.put(
        f"/symptoms/{day.isoformat()}",
        json={"symptoms": list(symptoms), "custom": list(custom)},
    )


def test_save_and_list_day(auth_client):
    r = put(auth_client, TODAY, ["headache", "cramps", "cramps"], ["  Kaakpijn  "])
    assert r.status_code == 200
    # canonical order, duplicates dropped, whitespace trimmed
    assert r.json == {
        "date": TODAY.isoformat(),
        "symptoms": ["cramps", "headache"],
        "custom": ["Kaakpijn"],
    }
    r = auth_client.get(
        "/symptoms",
        query_string={
            "start": (TODAY - TD(days=3)).isoformat(),
            "end": TODAY.isoformat(),
        },
    )
    assert r.status_code == 200
    assert [d["date"] for d in r.json] == [TODAY.isoformat()]


def test_saving_again_replaces_and_empty_clears(auth_client, db):
    put(auth_client, TODAY, ["cramps"])
    put(auth_client, TODAY, ["fatigue"])
    assert SymptomLog.query.count() == 1
    assert put(auth_client, TODAY).json["symptoms"] == []
    assert SymptomLog.query.count() == 0


def test_rejects_unknown_future_and_long(auth_client):
    assert put(auth_client, TODAY, ["not_a_symptom"]).status_code == 422
    assert put(auth_client, TODAY + TD(days=3), ["cramps"]).status_code == 422
    assert put(auth_client, TODAY, custom=["x" * 41]).status_code == 422
    assert put(auth_client, TODAY, custom=["a\x07b"]).status_code == 422
    assert (
        put(auth_client, TODAY, custom=[f"s{i}" for i in range(11)]).status_code == 422
    )
    assert auth_client.put("/symptoms/2024-13-40", json={}).status_code == 404


def test_custom_dedupes_case_insensitively(auth_client):
    r = put(auth_client, TODAY, custom=["Kaakpijn", "kaakpijn", " "])
    assert r.json["custom"] == ["Kaakpijn"]


def test_range_limits(auth_client):
    q = {"start": TODAY.isoformat(), "end": (TODAY - TD(days=1)).isoformat()}
    assert auth_client.get("/symptoms", query_string=q).status_code == 422
    q = {"start": (TODAY - TD(days=500)).isoformat(), "end": TODAY.isoformat()}
    assert auth_client.get("/symptoms", query_string=q).status_code == 422


def test_suggestions(auth_client):
    put(auth_client, TODAY - TD(days=2), ["cramps", "fatigue"], ["Kaakpijn"])
    put(auth_client, TODAY - TD(days=1), ["cramps"], ["Oorsuizen"])
    r = auth_client.get("/symptoms/suggestions")
    assert r.status_code == 200
    assert r.json["frequent"][0] == "cramps"
    assert set(r.json["frequent"]) == {"cramps", "fatigue"}
    assert r.json["recent_custom"] == ["Oorsuizen", "Kaakpijn"]  # newest first


def test_other_users_days_are_private(auth_client, db):
    other = User(username="other", email="other@example.com")
    other.set_password("password")
    db.session.add(other)
    db.session.commit()
    db.session.add(SymptomLog(user_id=other.id, date=TODAY, symptoms='["acne"]'))
    db.session.commit()
    q = {"start": TODAY.isoformat(), "end": TODAY.isoformat()}
    assert auth_client.get("/symptoms", query_string=q).json == []


def test_requires_login(client):
    assert client.get("/symptoms/suggestions").status_code == 401


def test_deleting_user_removes_symptoms(app, db, test_user):
    db.session.add(SymptomLog(user_id=test_user.id, date=TODAY, symptoms='["acne"]'))
    db.session.commit()
    db.session.delete(test_user)
    db.session.commit()
    assert SymptomLog.query.count() == 0


class U:
    username = "alice"


def test_report_counts_symptoms_by_phase():
    start = TODAY - TD(days=10)
    periods = [(start - TD(days=28), start - TD(days=24)), (start, start + TD(days=4))]
    symptoms = [
        (start, ["Cramps"]),  # during
        (start - TD(days=2), ["Cramps", "Irritability"]),  # before
        (start - TD(days=15), ["cramps"]),  # neither, same label other case
    ]
    r = DoctorReportService.build(U, periods, 12, TODAY, symptoms=symptoms)
    s = r["symptoms"]
    assert s["days_logged"] == 3
    assert s["items"][0] == {
        "label": "Cramps",
        "days": 3,
        "during_period": 1,
        "before_period": 1,
    }
    html = DoctorReportService.render_html(r)
    assert "<h2>Symptoms</h2>" in html and "Irritability" in html


def test_report_without_symptoms_has_no_section():
    r = DoctorReportService.build(U, [(TODAY - TD(days=5), None)], 12, TODAY)
    assert "<h2>Symptoms</h2>" not in DoctorReportService.render_html(r)


def test_report_escapes_own_symptoms(auth_client, db, test_user):
    db.session.add(Period(user_id=test_user.id, start_date=TODAY - TD(days=3)))
    db.session.commit()
    put(auth_client, TODAY, custom=["<b>x</b>"])
    html = auth_client.get("/reports/doctor").get_data(as_text=True)
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
