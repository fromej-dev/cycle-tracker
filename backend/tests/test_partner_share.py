import datetime
import hashlib
import json
import re

import pytest
from flask import url_for

from app.models import Period, User
from app.services import headsup_service

D = datetime.date
TD = datetime.timedelta
TODAY = D.today()


def add(user, last_offset, gaps=(28,) * 8, duration=5, ongoing=False):
    starts = [TODAY - TD(days=last_offset)]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    for i, s in enumerate(reversed(starts)):
        last = i == len(starts) - 1
        end = None if (last and ongoing) else s + TD(days=duration - 1)
        Period(user_id=user.id, start_date=s, end_date=end).save()
    return list(starts)


def enable(auth_client, **body):
    r = auth_client.post(url_for("integrations.create_partner_share"), json=body)
    assert r.status_code == 201, r.get_json()
    j = r.get_json()
    return j, j["path"].rsplit("/", 1)[1]


def page(client, token, ext=""):
    return client.get(f"/share/{token}{ext}")


def test_create_returns_path_once_and_settings_hide_token(auth_client, test_user):
    j, token = enable(auth_client)
    assert j["url"] is None and j["path"] == f"/share/{token}"
    assert len(token) >= 40
    s = auth_client.get(url_for("integrations.get_partner_share")).get_json()
    assert s == {
        "enabled": True,
        "name": "Shared calendar",
        "scope": {"fertile": False, "window_days": 7},
    }
    assert token not in json.dumps(s)


def test_token_stored_hashed(auth_client, test_user, db):
    _, token = enable(auth_client)
    db.session.refresh(test_user)
    assert (
        test_user.partner_share_token_hash == hashlib.sha256(token.encode()).hexdigest()
    )
    row = {c.name: getattr(test_user, c.name) for c in User.__table__.columns}
    assert token not in json.dumps(row, default=str)


def test_states(auth_client, test_user, client):
    # about two days before the expected start
    add(test_user, 26)
    _, token = enable(auth_client)
    j = page(client, token, ".json").get_json()
    assert j["status"] == "soon" and j["days_bucket"] in ("0-2", "3-7")
    assert "Period likely starts" in j["message"]


def test_period_now(auth_client, test_user, client):
    add(test_user, 1, ongoing=True)
    _, token = enable(auth_client)
    j = page(client, token, ".json").get_json()
    assert j["status"] == "period" and j["message"] == "Period now"


def test_none_state(auth_client, test_user, client):
    add(test_user, 5)
    _, token = enable(auth_client)
    j = page(client, token, ".json").get_json()
    assert j["status"] == "none" and j["days_bucket"] is None


def test_no_data_user(auth_client, client):
    _, token = enable(auth_client)
    assert page(client, token, ".json").get_json()["status"] == "none"
    assert page(client, token).status_code == 200


@pytest.mark.parametrize("offset", [1, 5, 14, 26, 27])
def test_scope_enforcement_no_dates_lengths_or_fertile(
    auth_client, test_user, client, offset
):
    starts = add(test_user, offset, gaps=(27, 29, 30, 26, 31, 28))
    _, token = enable(auth_client)  # fertile defaults to false
    h = page(client, token)
    j = page(client, token, ".json")
    blob = h.get_data(as_text=True) + j.get_data(as_text=True)
    for s in starts:
        assert s.isoformat() not in blob
        assert s.strftime("%d %b") not in blob
    assert not re.search(r"\d{4}-\d{2}-\d{2}", blob)
    low = blob.lower()
    for word in ("fertile", "ovulat", "symptom", "cycle", "probab", "tracker"):
        assert word not in low
    assert set(j.get_json()) == {"name", "status", "message", "days_bucket"}
    assert not re.search(r"\b(2[0-9]|3[0-9])\s*days\b", blob)


def test_fertile_opt_in(auth_client, test_user, client):
    add(test_user, 9)
    _, token = enable(auth_client, scope={"fertile": True})
    j = page(client, token, ".json").get_json()
    assert j["fertile"] in ("now", "soon", "no")
    assert "fertile_message" in j
    assert not re.search(r"\d{4}-\d{2}-\d{2}", json.dumps(j))
    auth_client.patch(
        url_for("integrations.update_partner_share"), json={"scope": {"fertile": False}}
    )
    assert "fertile" not in page(client, token, ".json").get_json()


def test_discreet_page_and_headers(auth_client, test_user, client):
    add(test_user, 5)
    _, token = enable(auth_client, name="Our <b>plans</b>")
    r = page(client, token)
    html = r.get_data(as_text=True)
    assert "<title>Our &lt;b&gt;plans&lt;/b&gt;</title>" in html
    assert "<b>plans</b>" not in html
    assert "noindex" in html and "no-referrer" in html
    assert "no-store" in r.headers["Cache-Control"]
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "noindex" in r.headers["X-Robots-Tag"]
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert not re.search(r"https?://|<script|<link", html)
    default = enable(auth_client, name="")[1]
    assert "<title>Shared calendar</title>" in page(client, default).get_data(
        as_text=True
    )


def test_rejects_control_chars_in_name(auth_client):
    r = auth_client.post(
        url_for("integrations.create_partner_share"), json={"name": "a‮b"}
    )
    assert r.status_code == 422


def test_rotate_and_revoke_are_immediate(auth_client, test_user, client):
    _, t1 = enable(auth_client)
    assert page(client, t1, ".json").status_code == 200
    _, t2 = enable(auth_client)
    assert t1 != t2
    assert page(client, t1).status_code == 404
    assert page(client, t1, ".json").status_code == 404
    assert page(client, t2).status_code == 200
    assert (
        auth_client.delete(url_for("integrations.revoke_partner_share")).status_code
        == 204
    )
    assert page(client, t2).status_code == 404
    assert page(client, t2, ".json").status_code == 404
    s = auth_client.get(url_for("integrations.get_partner_share")).get_json()
    assert s["enabled"] is False


def test_garbage_tokens_404(client):
    for t in ("x", "a" * 43, "a" * 500, "a b", "%2e%2e"):
        r = page(client, t)
        assert r.status_code == 404
        assert "no-store" in r.headers["Cache-Control"]


def test_constant_time_compare_used(auth_client, client, monkeypatch):
    _, token = enable(auth_client)
    calls = []
    real = headsup_service.hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(headsup_service.hmac, "compare_digest", spy)
    page(client, token)
    page(client, "z" * 43)
    page(client, "short")
    assert len(calls) == 3


def test_no_host_header_urls(auth_client, app):
    r = auth_client.post(
        url_for("integrations.create_partner_share"),
        json={},
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
    )
    assert r.get_json()["url"] is None
    app.config["PUBLIC_BASE_URL"] = "https://cal.example.org/"
    try:
        r = auth_client.post(
            url_for("integrations.create_partner_share"),
            json={},
            headers={"Host": "evil.example"},
        )
        j = r.get_json()
        assert j["url"] == "https://cal.example.org" + j["path"]
        assert "evil" not in j["url"]
    finally:
        app.config["PUBLIC_BASE_URL"] = None


def test_window_days_validated(auth_client):
    r = auth_client.post(
        url_for("integrations.create_partner_share"),
        json={"scope": {"window_days": 40}},
    )
    assert r.status_code == 422


def test_needs_jwt_to_manage(client):
    assert client.post("/users/me/partner-share", json={}).status_code == 401
