"""Outgoing signed webhooks (for Home Assistant and friends).

* The owner registers a URL; an HMAC-SHA256 signing secret is generated and shown
  once. Each delivery is a small JSON body (event name, date, optional coarse
  probability bucket, an id and a timestamp) signed as
  ``X-Signature: sha256=HMAC(secret, "<timestamp>.<body>")`` with ``X-Timestamp``.
* SSRF guard: only http(s) URLs whose host resolves to public addresses are accepted
  unless the ALLOW_PRIVATE_WEBHOOKS=1 environment flag is set (homelab / Home
  Assistant on the LAN). The check is repeated at delivery time and the connection is
  pinned to the validated IP (no DNS rebinding); redirects are never followed.
* Deliveries run on a small bounded worker pool (the request never waits; when the
  pool's queue is full the event is dropped and counted), 3 attempts with backoff.
  Every attempt has a hard 5 s wall-clock deadline (a watchdog closes the socket), so a
  tarpit that trickles bytes cannot hold a worker. A hook that fails 10 times in a row
  is switched off with a visible ``disabled_reason``. Tests set WEBHOOK_SYNC to
  deliver inline.
* period_started / period_ended are emitted by PeriodService. The time-driven events
  (period_expected_soon, fertile_window_starting) are produced by ``tick``: run
  ``flask webhooks tick`` from cron, or set WEBHOOK_SCHEDULER_SECONDS for a built-in
  loop. Each fires at most once per cycle (compare-and-swap on ``webhook_state``).
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from flask import current_app
from sqlalchemy import update

from app.extensions import db
from app.models import User, Webhook
from app.services.calendar_service import CalendarService
from app.services.date_check_service import DateCheckService
from app.services.headsup_service import (
    FERTILE_NOW,
    FERTILE_SOON,
    HeadsUpService,
)

EVENTS = (
    "period_started",
    "period_ended",
    "period_expected_soon",
    "fertile_window_starting",
)
DEFAULT_EVENTS = ("period_started", "period_ended", "period_expected_soon")
MAX_WEBHOOKS = 5
ATTEMPTS = 3
TIMEOUT = 2.0  # per socket operation; the hard limit is DEADLINE
DEADLINE = 5.0  # wall-clock seconds for one whole attempt (connect + TLS + I/O)
MAX_WORKERS = 8
MAX_PENDING = 64  # running + queued jobs; beyond this events are dropped
AUTO_DISABLE_AFTER = 10  # consecutive failed deliveries
DEFAULT_BACKOFF = (0.0, 1.0, 3.0)
SOON_THRESHOLD = 0.5
SOON_DAYS = 2


class WebhookUrlError(ValueError):
    pass


def private_allowed() -> bool:
    return os.environ.get("ALLOW_PRIVATE_WEBHOOKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


_V4_COMPAT = ipaddress.ip_network("::/96")
_SIIT = ipaddress.ip_network("::ffff:0:0:0/96")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")


def _embedded_v4(addr: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """IPv4 addresses a transition mechanism would deliver this IPv6 address to."""
    out = []
    if addr.ipv4_mapped:  # ::ffff:0:0/96
        out.append(addr.ipv4_mapped)
    low = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    if addr in _NAT64 or addr in _SIIT or (addr in _V4_COMPAT and int(addr) > 1):
        out.append(low)
    if addr in _NAT64_LOCAL:  # RFC 6052 section 2.2, /48 prefix: bits 48-63 and 72-87
        v = int(addr)
        out.append(
            ipaddress.IPv4Address((((v >> 64) & 0xFFFF) << 16) | ((v >> 40) & 0xFFFF))
        )
    if addr.sixtofour:  # 2002::/16
        out.append(addr.sixtofour)
    if addr.teredo:  # 2001::/32: the relay/server and the (obfuscated) client
        out.extend(addr.teredo)
    return out


def _addr_ok(ip: str) -> bool:
    """True only for a globally routable unicast address (embedded IPv4 included)."""
    addr = ipaddress.ip_address(ip.split("%")[0])
    if (
        addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_private
        or not addr.is_global
    ):
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        return all(_addr_ok(str(v4)) for v4 in _embedded_v4(addr))
    return True


def resolve_target(url: str) -> tuple[str, str, int, str, list[str]]:
    """Validate ``url``; returns (scheme, host, port, path, ips). Raises WebhookUrlError."""
    if not isinstance(url, str) or len(url) > 500:
        raise WebhookUrlError("URL is missing or too long.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise WebhookUrlError("Invalid URL.") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebhookUrlError("URL must be http(s) with a host name.")
    if parts.username or parts.password:
        raise WebhookUrlError("Credentials in the URL are not allowed.")
    host = parts.hostname
    port = port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(i[4][0] for i in infos))
    except OSError:
        ips = []
    if not ips:
        if private_allowed():
            ips = []
        else:
            raise WebhookUrlError("Host name does not resolve.")
    if not private_allowed() and not all(_addr_ok(ip) for ip in ips):
        raise WebhookUrlError(
            "URL points to a private, loopback or link-local address "
            "(set ALLOW_PRIVATE_WEBHOOKS=1 on the server to allow this)."
        )
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return parts.scheme, host, port, path, ips


class _Guard:
    """Hard wall-clock limit for one attempt.

    ``socket`` timeouts apply per operation, so a peer that trickles one byte every
    few seconds would never time out. A watchdog timer shuts every tracked socket down
    when the deadline passes, which wakes any blocked connect/handshake/read.
    """

    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds
        self.expired = False
        self._socks: list[socket.socket] = []
        self._lock = threading.Lock()
        self._timer = threading.Timer(seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def remaining(self) -> float:
        left = self.end - time.monotonic()
        if left <= 0:
            raise TimeoutError("webhook attempt exceeded its deadline")
        return left

    def track(self, sock: socket.socket) -> None:
        with self._lock:
            self._socks.append(sock)
            expired = self.expired
        if expired:
            self._kill(sock)

    @staticmethod
    def _kill(sock: socket.socket) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _fire(self) -> None:
        with self._lock:
            self.expired = True
            socks = list(self._socks)
        for sock in socks:
            self._kill(sock)

    def cancel(self) -> None:
        self._timer.cancel()


def _connect(ip: str, port: int, guard: _Guard) -> socket.socket:
    sock = socket.create_connection((ip, port), min(TIMEOUT, guard.remaining()))
    guard.track(sock)
    sock.settimeout(min(TIMEOUT, guard.remaining()))
    return sock


class _Pinned(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout, guard):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip
        self._guard = guard

    def connect(self):
        self.sock = _connect(self._ip, self.port, self._guard)


class _PinnedTLS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout, guard):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip
        self._guard = guard

    def connect(self):
        sock = _connect(self._ip, self.port, self._guard)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def post_once(url: str, secret: str, payload: dict) -> int:
    """One signed POST, at most DEADLINE seconds in total (connect, TLS, send, read).

    Returns the HTTP status; raises on network/URL errors (TimeoutError on deadline).
    """
    scheme, host, port, path, ips = resolve_target(url)
    if not ips:
        raise OSError("Host name does not resolve.")
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ts = int(payload["timestamp"])
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "webhook/1",
        "X-Timestamp": str(ts),
        "X-Signature": sign(secret, ts, body),
    }
    guard = _Guard(DEADLINE)
    last: Exception | None = None
    try:
        for ip in ips:
            cls = _PinnedTLS if scheme == "https" else _Pinned
            conn = cls(host, port, ip, TIMEOUT, guard)
            try:
                conn.request("POST", path, body=body, headers=headers)
                resp = conn.getresponse()
                resp.read(1024)
                if guard.expired:
                    raise TimeoutError("webhook attempt exceeded its deadline")
                return resp.status
            except (OSError, http.client.HTTPException) as exc:
                last = exc
                if guard.expired:
                    raise TimeoutError("webhook attempt exceeded its deadline") from exc
            finally:
                conn.close()
        raise last or OSError("connection failed")
    finally:
        guard.cancel()


def _backoff() -> tuple[float, ...]:
    return tuple(current_app.config.get("WEBHOOK_BACKOFF", DEFAULT_BACKOFF))


def deliver(url: str, secret: str, payload: dict, attempts: int = ATTEMPTS, sleep=None):
    """Deliver with retries; returns (status, attempts_used). status 0 = no response."""
    sleep = sleep or time.sleep
    delays = _backoff()
    status = 0
    used = 0
    for i in range(attempts):
        if i:
            sleep(delays[min(i, len(delays) - 1)])
        used += 1
        try:
            status = post_once(url, secret, payload)
        except (OSError, WebhookUrlError, http.client.HTTPException):
            status = 0
        if 200 <= status < 300:
            break
        if 300 <= status < 500 and status not in (408, 429):
            break  # the receiver rejected it: retrying will not help
    return status, used


def record_result(hook: Webhook, status: int) -> None:
    """Update delivery bookkeeping on ``hook`` (caller commits); auto-disable on streaks."""
    ok = 200 <= status < 300
    hook.last_status = status
    hook.last_attempt_at = datetime.datetime.utcnow()
    hook.failures = 0 if ok else (hook.failures or 0) + 1
    if ok:
        hook.disabled_reason = None
    elif hook.failures >= AUTO_DISABLE_AFTER and hook.active:
        hook.active = False
        hook.disabled_reason = (
            f"Switched off automatically after {hook.failures} failed deliveries in a "
            "row. Fix the receiver, then set active=true to re-enable."
        )


def _job(app, webhook_id: int, url: str, secret: str, payload: dict, own=True) -> None:
    with app.app_context():
        try:
            status, _ = deliver(url, secret, payload)
        except Exception:
            app.logger.exception("webhook delivery crashed")
            status = 0
        try:
            hook = db.session.get(Webhook, webhook_id)
            if hook is not None:
                record_result(hook, status)
                db.session.commit()
        except Exception:  # bookkeeping must never raise out of a worker thread
            db.session.rollback()
        finally:
            if own:
                db.session.remove()


class _Pool:
    """Process-wide bounded worker pool; full -> drop and count (never block a request)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pid = None
        self._executor = None
        self._slots = None
        self.dropped = 0

    def _ensure(self):
        if self._executor is None or self._pid != os.getpid():  # also after fork
            self._pid = os.getpid()
            self._executor = ThreadPoolExecutor(
                max_workers=MAX_WORKERS, thread_name_prefix="webhook"
            )
            self._slots = threading.BoundedSemaphore(MAX_PENDING)

    def submit(self, fn, *args) -> bool:
        with self._lock:
            self._ensure()
            if not self._slots.acquire(blocking=False):
                self.dropped += 1
                return False
            slots = self._slots
        try:
            fut = self._executor.submit(fn, *args)
        except RuntimeError:  # executor shut down (interpreter exit)
            slots.release()
            return False
        fut.add_done_callback(lambda _f: slots.release())
        return True

    def reset(self):
        """Forget the pool (tests); running jobs finish on their own."""
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False)
            self._executor = None
            self.dropped = 0


POOL = _Pool()


def _pack(event: str, date: datetime.date | None, **extra) -> dict:
    payload = {
        "id": uuid.uuid4().hex,
        "event": event,
        "timestamp": int(time.time()),
    }
    if date is not None:
        payload["date"] = date.isoformat()
    payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


class WebhookService:
    # --- management -----------------------------------------------------------------

    @staticmethod
    def events_of(hook: Webhook) -> list[str]:
        try:
            return list(json.loads(hook.events))
        except ValueError:
            return []

    @staticmethod
    def to_dict(hook: Webhook) -> dict:
        return {
            "id": hook.id,
            "url": hook.url,
            "events": WebhookService.events_of(hook),
            "active": bool(hook.active),
            "last_status": hook.last_status,
            "last_attempt_at": hook.last_attempt_at,
            "failures": hook.failures or 0,
            "disabled_reason": None if hook.active else hook.disabled_reason,
        }

    @staticmethod
    def new_secret() -> str:
        return "whsec_" + secrets.token_hex(24)

    @staticmethod
    def create(user: User, url: str, events: list[str] | None) -> tuple[Webhook, str]:
        if Webhook.query.filter_by(user_id=user.id).count() >= MAX_WEBHOOKS:
            raise WebhookUrlError(f"At most {MAX_WEBHOOKS} webhooks are allowed.")
        resolve_target(url)
        secret = WebhookService.new_secret()
        hook = Webhook(
            user_id=user.id,
            url=url,
            events=json.dumps(sorted(set(events or DEFAULT_EVENTS))),
            secret=secret,
        ).save()
        return hook, secret

    @staticmethod
    def update(hook: Webhook, data: dict) -> Webhook:
        changes = {}
        if "url" in data:
            resolve_target(data["url"])
            changes["url"] = data["url"]
        if "events" in data:
            changes["events"] = json.dumps(sorted(set(data["events"])))
        if "active" in data:
            changes["active"] = bool(data["active"])
            changes["disabled_reason"] = None
            if data["active"]:
                changes["failures"] = 0
        return hook.update(**changes)

    @staticmethod
    def rotate_secret(hook: Webhook) -> str:
        secret = WebhookService.new_secret()
        hook.update(secret=secret)
        return secret

    @staticmethod
    def send_test(hook: Webhook) -> dict:
        """One synchronous, un-retried test delivery (bounded by the 5 s DEADLINE)."""
        payload = _pack("test", datetime.date.today())
        try:
            status = post_once(hook.url, hook.secret, payload)
            error = None
        except (OSError, WebhookUrlError, http.client.HTTPException) as exc:
            status, error = 0, str(exc)[:200]
        record_result(hook, status)
        db.session.commit()
        return {"delivered": 200 <= status < 300, "status": status, "error": error}

    # --- emitting -------------------------------------------------------------------

    @staticmethod
    def _dispatch(user_id: int, event: str, payload: dict) -> int:
        hooks = Webhook.query.filter_by(user_id=user_id, active=True).all()
        targets = [h for h in hooks if event in WebhookService.events_of(h)]
        app = current_app._get_current_object()
        sync = bool(app.config.get("WEBHOOK_SYNC"))
        for h in targets:
            args = (app, h.id, h.url, h.secret, dict(payload, id=uuid.uuid4().hex))
            if sync:
                _job(*args, own=False)
            else:
                POOL.submit(_job, *args)
        return len(targets)

    @staticmethod
    def emit(user_id: int, event: str, date: datetime.date | None, **extra) -> int:
        """Queue ``event`` for the user's subscribed webhooks. Never raises."""
        try:
            return WebhookService._dispatch(user_id, event, _pack(event, date, **extra))
        except Exception:
            current_app.logger.exception("webhook emit failed")
            db.session.rollback()
            return 0

    # --- time-driven events ---------------------------------------------------------

    @staticmethod
    def _claim(user: User, key: str, anchor: str) -> bool:
        """Mark ``key`` as sent for this cycle; False if someone else already did."""
        db.session.refresh(user)
        try:
            state = json.loads(user.webhook_state or "{}")
        except ValueError:
            state = {}
        if state.get(key) == anchor:
            return False
        old = user.webhook_state
        state[key] = anchor
        cond = (
            User.webhook_state.is_(None) if old is None else (User.webhook_state == old)
        )
        res = db.session.execute(
            update(User)
            .where(User.id == user.id, cond)
            .values(webhook_state=json.dumps(state, sort_keys=True))
        )
        db.session.commit()
        db.session.refresh(user)
        return res.rowcount == 1

    @staticmethod
    def tick_user(user: User, today: datetime.date | None = None) -> list[str]:
        """Emit due time-driven events for one user. Returns the events fired."""
        hooks = Webhook.query.filter_by(user_id=user.id, active=True).all()
        wanted = {e for h in hooks for e in WebhookService.events_of(h)}
        wanted &= {"period_expected_soon", "fertile_window_starting"}
        if not wanted:
            return []
        today = today or CalendarService.local_today(user)
        model = DateCheckService.load_model(user.id, today)
        fired: list[str] = []
        if model.last_start is None or model.overdue or model.ongoing:
            return fired
        anchor = model.last_start.isoformat()
        if "period_expected_soon" in wanted:
            p = HeadsUpService.p_start_within(model, SOON_DAYS)
            if p >= SOON_THRESHOLD and WebhookService._claim(user, "soon", anchor):
                bucket = "50-75%" if p < 0.75 else "75-100%"
                WebhookService.emit(
                    user.id,
                    "period_expected_soon",
                    model.today,
                    probability=bucket,
                )
                fired.append("period_expected_soon")
        if "fertile_window_starting" in wanted:
            hint = HeadsUpService.fertile_hint(model)
            if hint in (FERTILE_NOW, FERTILE_SOON):
                fw = model.forecast(horizon_days=1)["fertile_window"]
                if (fw["start"] - model.today).days <= 1 and WebhookService._claim(
                    user, "fertile", anchor
                ):
                    WebhookService.emit(user.id, "fertile_window_starting", fw["start"])
                    fired.append("fertile_window_starting")
        return fired

    @staticmethod
    def tick(today: datetime.date | None = None) -> dict[int, list[str]]:
        ids = [
            r[0]
            for r in db.session.query(Webhook.user_id)
            .filter(Webhook.active.is_(True))
            .distinct()
            .all()
        ]
        out = {}
        for uid in ids:
            user = db.session.get(User, uid)
            if user is None:
                continue
            try:
                fired = WebhookService.tick_user(user, today)
            except Exception:
                current_app.logger.exception("webhook tick failed")
                db.session.rollback()
                continue
            if fired:
                out[uid] = fired
        return out


def start_scheduler(app, seconds: int) -> None:
    """Optional in-process loop calling ``tick`` (dedupe makes several workers safe)."""

    def loop():
        while True:
            time.sleep(seconds)
            with app.app_context():
                try:
                    WebhookService.tick()
                finally:
                    db.session.remove()

    threading.Thread(target=loop, daemon=True, name="webhook-scheduler").start()
