"""Coarse "heads-up" status shared by the partner page and the Home Assistant sensor.

Privacy: this is the ONLY place where the forecast is turned into something that
leaves the owner's account through a credential-less URL. It returns just a state, a
coarse day bucket and (opt-in) a coarse fertile hint: never a date, a past value, a
cycle length or an exact probability.

What repeated polling can still reveal (a watcher who polls every day sees a time
series, and a series leaks more than one snapshot):

* The day the bucket changes is when the forecast median crossed a threshold. Each
  link shifts its thresholds by a stable 0-2 days derived from the link, so the exact
  day is blurred by up to two days, but not hidden: the bucket sequence still tracks
  the true timeline to within a few days, and an observer can tell roughly when the
  next period is due.
* Hysteresis (a bucket moves further away only when the forecast is clearly later) only
  stops flip-flopping between buckets; it does not hide anything.
* When "soon" stops being shown (the period began) the day of that change reveals
  the start of a period to within a day or so, even when ``show_current`` is off.
  With ``show_current`` on, "Period now" shows the start and the end of every period
  exactly.
* Months of observation reveal the owner's typical cycle length.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json

from flask import current_app
from sqlalchemy import update

from app.extensions import db
from app.models import User
from app.services.calendar_service import (
    _DUMMY_HASH,
    TOKEN_RE,
    CalendarService,
    hash_token,
)
from app.services.date_check_service import DateCheckService

STATE_PERIOD = "period"
STATE_SOON = "expected_soon"
STATE_NONE = "none"

FERTILE_NOW = "now"
FERTILE_SOON = "soon"
FERTILE_NO = "no"


BUCKETS = ("0-2", "3-7", "8-14", "15+")
_LIMITS = (2, 7, 14)
JITTER_MAX = 2  # days
HYSTERESIS = 1  # days


def jitter_for(key: str | None) -> int:
    """Stable 0..JITTER_MAX day shift of the bucket thresholds for one link."""
    if not key:
        return 0
    digest = hashlib.sha256(b"heads-up-jitter:" + key.encode()).digest()
    return digest[0] % (JITTER_MAX + 1)


def bucket_index(days: int, jitter: int = 0) -> int:
    """Bucket number for ``days`` until the median start; thresholds shifted by jitter."""
    return sum(days > limit + jitter for limit in _LIMITS)


def bucket_for(days: int, jitter: int = 0) -> str:
    return BUCKETS[bucket_index(days, jitter)]


def lookup_user(column, token: str) -> User | None:
    """Find a user by the SHA-256 of a URL token in ``column``; constant-time compare."""
    candidate = hash_token(token) if TOKEN_RE.match(token) else _DUMMY_HASH
    user = User.query.filter(column == candidate).first()
    stored = getattr(user, column.key) if user else _DUMMY_HASH
    # compare_digest on every path so hits and misses cost about the same
    if hmac.compare_digest(stored or _DUMMY_HASH, candidate) and user is not None:
        return user
    return None


def public_url(path: str) -> str | None:
    """Absolute URL only from PUBLIC_BASE_URL (never the attacker-set Host header)."""
    base = current_app.config.get("PUBLIC_BASE_URL")
    return base.rstrip("/") + path if base else None


class HeadsUpService:
    @staticmethod
    def p_start_within(model, days: int) -> float:
        today = model.today
        dist = model.next_start_distribution()
        return sum(p for d, p in dist.items() if (d - today).days <= days)

    @staticmethod
    def compute(
        user: User,
        window_days: int = 7,
        fertile: bool = False,
        today: datetime.date | None = None,
        model=None,
        link_key: str | None = None,
        slot: str | None = None,
    ) -> dict:
        """``{"state", "days_bucket", "fertile"}`` (fertile is None unless opted in).

        ``link_key`` (the stored hash of the secret link) seeds a per-link 0-2 day shift
        of the bucket thresholds and of the "soon" window; ``slot`` names where the
        last shown bucket is remembered for hysteresis. Neither given: exact buckets.
        """
        today = today or CalendarService.local_today(user)
        model = model or DateCheckService.load_model(user.id, today)
        result = {"state": STATE_NONE, "days_bucket": None, "fertile": None}
        if model.last_start is None or model.overdue:
            HeadsUpService._remember(user, slot, None)
            return result
        if model.ongoing:
            result["state"] = STATE_PERIOD
            HeadsUpService._remember(user, slot, None)
            return result
        jitter = jitter_for(link_key)
        dist = model.next_start_distribution()
        cum = 0.0
        d50 = None
        for d in sorted(dist):
            cum += dist[d]
            if cum >= 0.5:
                d50 = max((d - model.today).days, 0)
                break
        if d50 is not None:
            idx = bucket_index(d50, jitter)
            prev = HeadsUpService._recall(user, slot)
            if prev is not None and idx > prev:
                # moving further away needs a clear margin, or the bucket flip-flops
                idx = max(prev, bucket_index(d50 - HYSTERESIS, jitter))
            result["days_bucket"] = BUCKETS[idx]
            HeadsUpService._remember(user, slot, BUCKETS[idx])
        else:
            HeadsUpService._remember(user, slot, None)
        if HeadsUpService.p_start_within(model, window_days + jitter) >= 0.5:
            result["state"] = STATE_SOON
        if fertile:
            result["fertile"] = HeadsUpService.fertile_hint(model)
        return result

    @staticmethod
    def _state(user: User) -> dict:
        try:
            data = json.loads(user.heads_up_state or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _recall(user: User, slot: str | None) -> int | None:
        value = HeadsUpService._state(user).get(slot) if slot else None
        return BUCKETS.index(value) if value in BUCKETS else None

    @staticmethod
    def _remember(user: User, slot: str | None, bucket: str | None) -> None:
        """Persist the shown bucket with a plain UPDATE, only when it changed."""
        if not slot:
            return
        data = HeadsUpService._state(user)
        if data.get(slot) == bucket:
            return
        if bucket is None:
            data.pop(slot, None)
        else:
            data[slot] = bucket
        try:
            db.session.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    heads_up_state=json.dumps(data, sort_keys=True) if data else None
                )
            )
            db.session.commit()
            db.session.refresh(user)
        except Exception:  # a failed memory write must never break a read
            db.session.rollback()

    @staticmethod
    def fertile_hint(model) -> str:
        if model.ongoing or model.last_start is None or model.overdue:
            return FERTILE_NO
        fw = model.forecast(horizon_days=1)["fertile_window"]
        if not fw:
            return FERTILE_NO
        if fw["start"] <= model.today <= fw["end"]:
            return FERTILE_NOW
        if 0 < (fw["start"] - model.today).days <= 7:
            return FERTILE_SOON
        return FERTILE_NO
