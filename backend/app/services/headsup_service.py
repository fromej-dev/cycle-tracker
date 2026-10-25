"""Coarse "heads-up" status shared by the partner page and the Home Assistant sensor.

Privacy: this is the ONLY place where the forecast is turned into something that
leaves the owner's account through a credential-less URL. It returns just a state, a
coarse day bucket and (opt-in) a coarse fertile hint: never a date, a past value, a
cycle length or an exact probability.
"""

from __future__ import annotations

import datetime
import hmac

from flask import current_app

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


def bucket_for(days: int) -> str:
    if days <= 2:
        return "0-2"
    if days <= 7:
        return "3-7"
    if days <= 14:
        return "8-14"
    return "15+"


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
    ) -> dict:
        """``{"state", "days_bucket", "fertile"}`` (fertile is None unless opted in)."""
        today = today or CalendarService.local_today(user)
        model = model or DateCheckService.load_model(user.id, today)
        result = {"state": STATE_NONE, "days_bucket": None, "fertile": None}
        if model.last_start is None or model.overdue:
            return result
        if model.ongoing:
            result["state"] = STATE_PERIOD
            return result
        dist = model.next_start_distribution()
        cum = 0.0
        d50 = None
        for d in sorted(dist):
            cum += dist[d]
            if cum >= 0.5:
                d50 = max((d - model.today).days, 0)
                break
        if d50 is not None:
            result["days_bucket"] = bucket_for(d50)
        if HeadsUpService.p_start_within(model, window_days) >= 0.5:
            result["state"] = STATE_SOON
        if fertile:
            result["fertile"] = HeadsUpService.fertile_hint(model)
        return result

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
