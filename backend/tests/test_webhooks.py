import datetime
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from flask import url_for

from app.models import Period, Webhook
from app.services import webhook_service
from app.services.webhook_service import WebhookService

D = datetime.date
TD = datetime.timedelta
TODAY = D.today()


class Receiver:
    def __init__(self, statuses=(200,)):
        self.requests = []
        self.statuses = list(statuses)
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                outer.requests.append((dict(self.headers), self.rfile.read(n)))
                i = len(outer.requests) - 1
                code = outer.statuses[min(i, len(outer.statuses) - 1)]
                self.send_response(code)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def recv(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    r = Receiver()
    yield r
    r.close()


def register(auth_client, url, events=None):
    body = {"url": url}
    if events:
        body["events"] = events
    r = auth_client.post(url_for("integrations.create_webhook"), json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def add_periods(user, last_offset, gaps=(28,) * 8, duration=5):
    starts = [TODAY - TD(days=last_offset)]
    for g in gaps:
        starts.append(starts[-1] - TD(days=g))
    for s in reversed(starts):
        Period(user_id=user.id, start_date=s, end_date=s + TD(days=duration - 1)).save()


def fresh():
    # delivery commits from its own session (like a worker thread would)
    from app.extensions import db

    db.session.expire_all()
    return Webhook.query.one()


def verify(headers, body, secret):
    ts = headers["X-Timestamp"]
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return hmac.compare_digest(headers["X-Signature"], "sha256=" + mac.hexdigest())


# --- SSRF guard ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8123/api/webhook/x",
        "http://localhost/x",
        "http://10.0.0.5/x",
        "http://192.168.1.10/x",
        "http://172.16.0.1/x",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x",
        "http://[::ffff:127.0.0.1]/x",
        "http://0.0.0.0/x",
        "http://100.64.0.1/x",
        "ftp://example.com/x",
        "http://user:pw@8.8.8.8/x",
        "file:///etc/passwd",
        "not a url",
    ],
)
def test_ssrf_blocked_by_default(auth_client, monkeypatch, url):
    monkeypatch.delenv("ALLOW_PRIVATE_WEBHOOKS", raising=False)
    r = auth_client.post(url_for("integrations.create_webhook"), json={"url": url})
    assert r.status_code == 422
    assert "url" in r.get_json()["detail"]["json"]


def test_public_ip_accepted_private_with_flag(auth_client, monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_WEBHOOKS", raising=False)
    register(auth_client, "https://8.8.8.8/hook")
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    register(auth_client, "http://192.168.1.10:8123/api/webhook/abc")


def test_ssrf_rechecked_at_delivery(auth_client, test_user, recv, monkeypatch):
    register(auth_client, recv.url, ["period_started"])
    monkeypatch.delenv("ALLOW_PRIVATE_WEBHOOKS")
    r = auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    assert r.status_code == 201  # the request itself is unaffected
    assert recv.requests == []
    assert fresh().last_status == 0


def test_dns_resolution_pinned(monkeypatch):
    monkeypatch.delenv("ALLOW_PRIVATE_WEBHOOKS", raising=False)
    monkeypatch.setattr(
        webhook_service.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 80))],
    )
    with pytest.raises(webhook_service.WebhookUrlError):
        webhook_service.resolve_target("http://innocent.example/x")


# --- management ---------------------------------------------------------------------


def test_secret_shown_once_and_crud(auth_client, recv):
    created = register(auth_client, recv.url)
    assert created["secret"].startswith("whsec_")
    assert created["events"] == [
        "period_ended",
        "period_expected_soon",
        "period_started",
    ]  # fertile is opt-in
    hid = created["id"]
    got = auth_client.get(url_for("integrations.get_webhook", hook_id=hid)).get_json()
    assert "secret" not in got
    lst = auth_client.get(url_for("integrations.list_webhooks")).get_json()
    assert len(lst) == 1 and "secret" not in lst[0]
    r = auth_client.patch(
        url_for("integrations.update_webhook", hook_id=hid),
        json={"events": ["fertile_window_starting"], "active": False},
    )
    assert r.get_json()["events"] == ["fertile_window_starting"]
    assert r.get_json()["active"] is False
    new = auth_client.post(
        url_for("integrations.rotate_webhook_secret", hook_id=hid)
    ).get_json()["secret"]
    assert new != created["secret"]
    assert fresh().secret == new
    assert (
        auth_client.delete(
            url_for("integrations.delete_webhook", hook_id=hid)
        ).status_code
        == 204
    )
    assert Webhook.query.count() == 0


def test_unknown_event_and_limit(auth_client, recv):
    r = auth_client.post(
        url_for("integrations.create_webhook"),
        json={"url": recv.url, "events": ["nope"]},
    )
    assert r.status_code == 422
    for _ in range(webhook_service.MAX_WEBHOOKS):
        register(auth_client, recv.url)
    r = auth_client.post(url_for("integrations.create_webhook"), json={"url": recv.url})
    assert r.status_code == 422


def test_other_users_hook_is_404(auth_client, db, recv):
    from app.models import User

    other = User(username="o2", email="o2@example.com")
    other.set_password("x")
    db.session.add(other)
    db.session.commit()
    h = Webhook(user_id=other.id, url=recv.url, events="[]", secret="s").save()
    assert (
        auth_client.get(url_for("integrations.get_webhook", hook_id=h.id)).status_code
        == 404
    )


# --- delivery -----------------------------------------------------------------------


def test_period_started_and_ended_signed(auth_client, test_user, recv):
    created = register(auth_client, recv.url)
    r = auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    pid = r.get_json()["id"]
    assert len(recv.requests) == 1
    headers, body = recv.requests[0]
    assert verify(headers, body, created["secret"])
    payload = json.loads(body)
    assert payload["event"] == "period_started" and payload["date"] == TODAY.isoformat()
    assert set(payload) == {"id", "event", "timestamp", "date"}  # minimal
    assert abs(payload["timestamp"] - int(headers["X-Timestamp"])) == 0
    assert headers["X-Signature"].startswith("sha256=")
    end = TODAY + TD(days=4)
    auth_client.put(f"/periods/{pid}", json={"end_date": end.isoformat()})
    p2 = json.loads(recv.requests[1][1])
    assert p2["event"] == "period_ended" and p2["date"] == end.isoformat()
    assert fresh().last_status == 200


def test_wrong_secret_fails_verification(auth_client, recv):
    register(auth_client, recv.url)
    auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    headers, body = recv.requests[0]
    assert not verify(headers, body, "whsec_wrong")


def test_only_subscribed_events(auth_client, recv):
    register(auth_client, recv.url, ["period_ended"])
    auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    assert recv.requests == []


def test_inactive_hook_not_called(auth_client, recv):
    h = register(auth_client, recv.url)
    auth_client.patch(
        url_for("integrations.update_webhook", hook_id=h["id"]), json={"active": False}
    )
    auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    assert recv.requests == []


def test_retries_on_5xx_then_succeeds(auth_client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    r = Receiver([500, 503, 200])
    try:
        register(auth_client, r.url, ["period_started"])
        auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
        assert len(r.requests) == 3
        assert fresh().failures == 0
    finally:
        r.close()


def test_gives_up_after_three_and_counts_failure(auth_client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    r = Receiver([500])
    try:
        register(auth_client, r.url, ["period_started"])
        resp = auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
        assert resp.status_code == 201
        assert len(r.requests) == 3
        h = fresh()
        assert h.last_status == 500 and h.failures == 1
    finally:
        r.close()


def test_client_error_not_retried(auth_client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    r = Receiver([404])
    try:
        register(auth_client, r.url, ["period_started"])
        auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
        assert len(r.requests) == 1
    finally:
        r.close()


def test_unreachable_target_never_breaks_request(auth_client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    r = Receiver()
    url = r.url
    r.close()  # nothing listens any more
    register(auth_client, url, ["period_started"])
    resp = auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    assert resp.status_code == 201
    assert fresh().last_status == 0


def test_async_mode_does_not_block(app, auth_client, monkeypatch):
    """Outside sync mode delivery happens in a thread: the request returns first."""
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    gate = threading.Event()
    seen = threading.Event()

    def slow(url, secret, payload, attempts=3, sleep=None):
        seen.set()
        gate.wait(5)
        return 200, 1

    monkeypatch.setattr(webhook_service, "deliver", slow)
    app.config["WEBHOOK_SYNC"] = False
    try:
        register(auth_client, "http://127.0.0.1:9/x", ["period_started"])
        resp = auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
        assert resp.status_code == 201
        assert seen.wait(2)
    finally:
        gate.set()
        app.config["WEBHOOK_SYNC"] = True


def test_test_endpoint(auth_client, recv):
    h = register(auth_client, recv.url)
    r = auth_client.post(url_for("integrations.test_webhook", hook_id=h["id"]))
    assert r.get_json()["delivered"] is True
    assert json.loads(recv.requests[0][1])["event"] == "test"
    assert verify(*recv.requests[0], h["secret"])


# --- time-driven events ---------------------------------------------------------------


def test_expected_soon_fires_once_per_cycle(auth_client, test_user, recv):
    add_periods(test_user, 27)  # regular 28-day user, next start tomorrow
    register(auth_client, recv.url, ["period_expected_soon"])
    assert WebhookService.tick(TODAY) == {test_user.id: ["period_expected_soon"]}
    assert WebhookService.tick(TODAY) == {}
    assert len(recv.requests) == 1
    p = json.loads(recv.requests[0][1])
    assert p["event"] == "period_expected_soon"
    assert p["probability"] in ("50-75%", "75-100%")
    assert p["date"] == TODAY.isoformat()
    # a newly logged period re-arms the next cycle
    auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    later = TODAY + TD(days=27)
    assert WebhookService.tick(later) == {test_user.id: ["period_expected_soon"]}


def test_expected_soon_not_early(auth_client, test_user, recv):
    add_periods(test_user, 10)
    register(auth_client, recv.url, ["period_expected_soon"])
    assert WebhookService.tick(TODAY) == {}
    assert recv.requests == []


def test_no_time_events_without_subscription(auth_client, test_user, recv):
    add_periods(test_user, 27)
    register(auth_client, recv.url, ["period_started"])
    assert WebhookService.tick(TODAY) == {}


def test_fertile_opt_in_only(auth_client, test_user, recv):
    add_periods(test_user, 9)
    register(auth_client, recv.url)  # defaults: no fertile
    assert WebhookService.tick(TODAY) == {}
    register(auth_client, recv.url, ["fertile_window_starting"])
    out = WebhookService.tick(TODAY)
    assert out == {test_user.id: ["fertile_window_starting"]}
    assert WebhookService.tick(TODAY) == {}
    assert json.loads(recv.requests[-1][1])["event"] == "fertile_window_starting"


# --- Home Assistant state ---------------------------------------------------------------


def ha_enable(auth_client, **body):
    r = auth_client.post(url_for("integrations.create_home_assistant"), json=body)
    assert r.status_code == 201
    return r.get_json()["path"]


def test_ha_state_shapes(auth_client, test_user, client):
    path = ha_enable(auth_client)
    assert path.startswith("/ha/") and path.endswith("/state")
    r = client.get(path)  # no data
    assert r.get_json() == {
        "state": "none",
        "attributes": {"days_until_likely_start": None},
    }
    assert "no-store" in r.headers["Cache-Control"]
    add_periods(test_user, 26)
    j = client.get(path).get_json()
    assert j["state"] == "expected_soon"
    assert j["attributes"]["days_until_likely_start"] in ("0-2", "3-7")
    assert "fertile_window" not in j["attributes"]


def test_ha_period_and_none(auth_client, test_user, client):
    path = ha_enable(auth_client)
    Period(user_id=test_user.id, start_date=TODAY - TD(days=1)).save()
    assert client.get(path).get_json()["state"] == "period"


def test_ha_fertile_opt_in_and_revoke(auth_client, test_user, client):
    add_periods(test_user, 9)
    path = ha_enable(auth_client, include_fertile=True)
    assert client.get(path).get_json()["attributes"]["fertile_window"] in (
        "now",
        "soon",
        "no",
    )
    old = path
    path = ha_enable(auth_client)  # rotate
    assert client.get(old).status_code == 404
    assert client.get(path).status_code == 200
    auth_client.delete(url_for("integrations.revoke_home_assistant"))
    assert client.get(path).status_code == 404


# --- SSRF: embedded IPv4, multicast, reserved ---------------------------------------


def _teredo(server: str, client: str) -> str:
    import ipaddress

    c = int(ipaddress.IPv4Address(client)) ^ 0xFFFFFFFF
    s = int(ipaddress.IPv4Address(server))
    return str(ipaddress.IPv6Address((0x2001 << 112) | (s << 64) | (0x8000 << 48) | c))


@pytest.mark.parametrize(
    "ip",
    [
        "64:ff9b::7f00:1",  # NAT64 -> 127.0.0.1
        "64:ff9b::a00:5",  # NAT64 -> 10.0.0.5
        "64:ff9b::a9fe:a9fe",  # NAT64 -> 169.254.169.254
        "64:ff9b:1::7f00:1",  # local-use NAT64 prefix
        "::ffff:0:127.0.0.1",  # SIIT
        "::ffff:0:a00:5",
        "::ffff:127.0.0.1",  # mapped
        "::127.0.0.1",  # IPv4-compatible
        "224.0.0.1",
        "239.255.255.250",
        "ff02::1",
        "ff0e::1",
        "240.0.0.1",
        "255.255.255.255",
        "0.0.0.0",
        "::",
        "::1",
        "fe80::1",
        "fd00::1",
        "2002:7f00:1::",  # 6to4 -> 127.0.0.1
        "2002:a00:5::1",  # 6to4 -> 10.0.0.5
        _teredo("8.8.8.8", "10.0.0.1"),  # Teredo, private client
        _teredo("127.0.0.1", "8.8.8.8"),  # Teredo, loopback server
    ],
)
def test_addr_ok_rejects(ip):
    assert webhook_service._addr_ok(ip) is False


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_addr_ok_accepts_public(ip):
    assert webhook_service._addr_ok(ip) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://[64:ff9b::7f00:1]/",
        "http://[::ffff:0:127.0.0.1]/",
        "http://[64:ff9b:1::7f00:1]/",
        "http://[2002:7f00:1::]/",
        "http://224.0.0.1/",
        "http://[ff02::1]/",
    ],
)
def test_ssrf_embedded_and_multicast_blocked(auth_client, monkeypatch, url):
    monkeypatch.delenv("ALLOW_PRIVATE_WEBHOOKS", raising=False)
    r = auth_client.post(url_for("integrations.create_webhook"), json={"url": url})
    assert r.status_code == 422


# --- hard deadline, pool, auto-disable ------------------------------------------------


class Tarpit:
    """Accepts, then trickles a never-ending response one byte at a time."""

    def __init__(self, interval=0.4):
        import socket

        self.interval = interval
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}/hook"
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._trickle, args=(conn,), daemon=True).start()

    def _trickle(self, conn):
        try:
            conn.settimeout(1)
            try:
                conn.recv(65536)
            except OSError:
                pass
            for ch in b"HTTP/1.1 200 OK\r\n" + b"X-A: " + b"a" * 500:
                if self.stop.is_set():
                    break
                conn.sendall(bytes([ch]))
                time.sleep(self.interval)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.stop.set()
        self.sock.close()


def test_tarpit_attempt_ends_within_deadline(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    monkeypatch.setattr(webhook_service, "DEADLINE", 1.0)
    # each byte arrives well inside the 2 s per-operation timeout
    tp = Tarpit(interval=0.4)
    try:
        t0 = time.monotonic()
        with pytest.raises(OSError):
            webhook_service.post_once(tp.url, "s", {"timestamp": 1, "event": "x"})
        assert time.monotonic() - t0 < 2.5
    finally:
        tp.close()


def test_default_deadline_is_bounded():
    assert webhook_service.DEADLINE <= 5.0
    assert webhook_service.DEADLINE >= webhook_service.TIMEOUT


def test_send_test_uses_deadline(auth_client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    monkeypatch.setattr(webhook_service, "DEADLINE", 1.0)
    tp = Tarpit(interval=0.4)
    try:
        h = register(auth_client, tp.url)
        t0 = time.monotonic()
        r = auth_client.post(url_for("integrations.test_webhook", hook_id=h["id"]))
        assert time.monotonic() - t0 < 3
        assert r.get_json()["delivered"] is False
    finally:
        tp.close()


def test_pool_is_bounded_and_drops_when_full(monkeypatch):
    monkeypatch.setattr(webhook_service, "MAX_WORKERS", 2)
    monkeypatch.setattr(webhook_service, "MAX_PENDING", 5)
    pool = webhook_service.POOL
    pool.reset()
    gate = threading.Event()
    lock = threading.Lock()
    state = {"now": 0, "max": 0, "done": 0}

    def job():
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        gate.wait(5)
        with lock:
            state["now"] -= 1
            state["done"] += 1

    try:
        accepted = [pool.submit(job) for _ in range(12)]
        assert accepted.count(True) == 5 and accepted.count(False) == 7
        assert pool.dropped == 7
        gate.set()
        deadline = time.monotonic() + 5
        while state["done"] < 5 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert state["done"] == 5 and state["max"] <= 2
        time.sleep(0.1)
        assert pool.submit(lambda: None) is True  # slots were released
    finally:
        gate.set()
        pool.reset()


def test_dispatch_uses_pool_not_threads(app, auth_client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    submitted = []
    monkeypatch.setattr(
        webhook_service.POOL, "submit", lambda fn, *a: submitted.append(a) or True
    )
    app.config["WEBHOOK_SYNC"] = False
    try:
        register(auth_client, "http://127.0.0.1:9/x", ["period_started"])
        auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    finally:
        app.config["WEBHOOK_SYNC"] = True
    assert len(submitted) == 1


def test_auto_disable_after_consecutive_failures(auth_client, db, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_WEBHOOKS", "1")
    r = Receiver([500])
    try:
        h = register(auth_client, r.url, ["period_started"])
        hook = Webhook.query.one()
        hook.update(failures=webhook_service.AUTO_DISABLE_AFTER - 1)
        auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
        hook = fresh()
        assert hook.active is False
        assert "automatically" in hook.disabled_reason
        got = auth_client.get(url_for("integrations.get_webhook", hook_id=h["id"]))
        assert got.get_json()["active"] is False
        assert "automatically" in got.get_json()["disabled_reason"]
        # re-enabling clears the counter and the reason
        up = auth_client.patch(
            url_for("integrations.update_webhook", hook_id=h["id"]),
            json={"active": True},
        )
        assert up.get_json()["disabled_reason"] is None
        assert up.get_json()["failures"] == 0
    finally:
        r.close()


def test_failure_counter_resets_on_success(auth_client, recv):
    register(auth_client, recv.url, ["period_started"])
    Webhook.query.one().update(failures=webhook_service.AUTO_DISABLE_AFTER - 2)
    auth_client.post("/periods", json={"start_date": TODAY.isoformat()})
    hook = fresh()
    assert hook.failures == 0 and hook.active is True
