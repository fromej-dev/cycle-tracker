import datetime
import json

from flask_jwt_extended import create_access_token

from app.models import Period, SymptomLog, User
from app.services.admin_stats_service import MIN_GROUP

D = datetime.date


def _user(db, name, admin=False):
    u = User(username=name, email=f"{name}@example.com", is_admin=admin)
    u.set_password("password")
    db.session.add(u)
    db.session.commit()
    return u


def _auth(client, user):
    token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _cohort(db, n):
    """n users with three 28-day cycles, 5-day periods and cramps logged."""
    users = []
    for i in range(n):
        u = _user(db, f"person{i}")
        for k in range(3):
            start = D(2026, 1, 1) + datetime.timedelta(days=28 * k)
            db.session.add(
                Period(
                    user_id=u.id,
                    start_date=start,
                    end_date=start + datetime.timedelta(days=4),
                )
            )
        db.session.add(
            SymptomLog(
                user_id=u.id,
                date=D(2026, 1, 2),
                symptoms=json.dumps(["cramps"]),
                custom=json.dumps(["my secret note"]),
            )
        )
        users.append(u)
    db.session.commit()
    return users


def test_requires_login(client):
    assert client.get("/admin/stats").status_code == 401


def test_non_admin_is_forbidden(client, db):
    u = _user(db, "regular")
    assert client.get("/admin/stats", headers=_auth(client, u)).status_code == 403


def test_user_cannot_make_themselves_admin(client, db):
    u = _user(db, "sneaky")
    r = client.patch("/users/me", json={"is_admin": True}, headers=_auth(client, u))
    assert r.status_code in (400, 422)
    db.session.refresh(u)
    assert u.is_admin is False


def test_me_reports_admin_flag(client, db):
    u = _user(db, "boss", admin=True)
    assert client.get("/users/me", headers=_auth(client, u)).json["is_admin"] is True


def test_stats_are_aggregates_without_personal_data(client, db):
    admin = _user(db, "boss", admin=True)
    _cohort(db, MIN_GROUP)
    r = client.get("/admin/stats", headers=_auth(client, admin))
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"
    body = r.json
    assert body["users"]["total"] == MIN_GROUP + 1
    assert body["users"]["new_7d"] == MIN_GROUP + 1
    assert body["features"]["periods"] == MIN_GROUP
    assert body["data"]["periods"] == 3 * MIN_GROUP
    assert body["cycles"]["median_cycle_length"] == 28
    assert body["cycles"]["median_period_length"] == 5
    assert body["symptoms"]["top"] == [
        {"key": "cramps", "users": MIN_GROUP, "share": 1.0}
    ]
    assert len(body["signups_by_month"]) == 12
    assert sum(m["count"] for m in body["signups_by_month"]) == MIN_GROUP + 1

    raw = r.get_data(as_text=True)
    for leak in ("person0", "boss", "@example.com", "my secret note", "2026-01-01"):
        assert leak not in raw


def test_health_aggregates_hidden_for_small_groups(client, db):
    admin = _user(db, "boss", admin=True)
    _cohort(db, MIN_GROUP - 1)
    body = client.get("/admin/stats", headers=_auth(client, admin)).json
    assert body["cycles"]["users_with_cycles"] == MIN_GROUP - 1
    assert body["cycles"]["median_cycle_length"] is None
    assert body["cycles"]["median_period_length"] is None
    assert body["symptoms"]["users_logging"] == MIN_GROUP - 1
    assert body["symptoms"]["top"] == []


def test_cli_grant_and_revoke(runner, db):
    u = _user(db, "Owner")
    out = runner.invoke(args=["admin", "grant", "owner"])
    assert out.exit_code == 0, out.output
    db.session.refresh(u)
    assert u.is_admin is True
    runner.invoke(args=["admin", "revoke", "owner"])
    db.session.refresh(u)
    assert u.is_admin is False
    assert runner.invoke(args=["admin", "grant", "nobody"]).exit_code != 0
