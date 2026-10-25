"""Read-only partner share: a secret link to a minimal "heads-up" page.

Privacy model (like the calendar feed): the URL token is 256 random bits, only its
SHA-256 is stored, it is shown once, and rotating/revoking makes the old link 404 at
once. The page shows ONE coarse sentence ("Period likely starts in about 3-7 days").
It never contains a date, a past period, a cycle length, symptoms or an exact
probability, and fertile info only if the owner explicitly enabled ``fertile``.
While a period is ongoing, and when nothing is expected, the page says the neutral
"Nothing to share right now" (true in both cases); "Period now" appears only if the
owner enabled ``show_current``.

Limits (see headsup_service for details): someone who polls the link daily sees a
time series. Bucket thresholds are shifted by a stable per-link 0-2 days and buckets
only move away with hysteresis, but the day "soon" appears or disappears still tells
roughly when the next period is due and when the last one began (to within a day or
so). With ``show_current`` the start and end of every period are visible exactly.
The page is titled with the owner-chosen name (default "Shared calendar"), never the
app's name, and is served noindex / no-store / no-referrer.
"""

from __future__ import annotations

import secrets
from html import escape

from app.models import User
from app.services.headsup_service import (
    FERTILE_NOW,
    FERTILE_SOON,
    STATE_PERIOD,
    STATE_SOON,
    HeadsUpService,
    lookup_user,
)

DEFAULT_NAME = "Shared calendar"
DEFAULT_WINDOW = 7
MIN_WINDOW, MAX_WINDOW = 2, 14

NOTHING_TEXT = "Nothing to share right now"
_SOON_TEXT = {
    "0-2": "Period likely starts within the next couple of days",
    "3-7": "Period likely starts in about 3–7 days",
    "8-14": "Period likely starts in about 1–2 weeks",
}
_FERTILE_TEXT = {
    FERTILE_NOW: "Fertile window: likely now",
    FERTILE_SOON: "Fertile window: likely within the next week",
}


class PartnerShareService:
    @staticmethod
    def path(token: str) -> str:
        return f"/share/{token}"

    @staticmethod
    def settings(user: User) -> dict:
        return {
            "enabled": user.partner_share_token_hash is not None,
            "name": user.partner_share_name or DEFAULT_NAME,
            "scope": {
                "fertile": bool(user.partner_share_fertile),
                "show_current": bool(user.partner_share_show_current),
                "window_days": user.partner_share_window_days or DEFAULT_WINDOW,
            },
        }

    @staticmethod
    def update_settings(user: User, name=None, scope: dict | None = None, **_) -> dict:
        changes = {}
        if name is not None:
            changes["partner_share_name"] = name.strip() or None
        if scope:
            if "fertile" in scope:
                changes["partner_share_fertile"] = bool(scope["fertile"])
            if "show_current" in scope:
                changes["partner_share_show_current"] = bool(scope["show_current"])
            if "window_days" in scope:
                changes["partner_share_window_days"] = int(scope["window_days"])
        if changes:
            user.update(**changes)
        return PartnerShareService.settings(user)

    @staticmethod
    def rotate(user: User) -> str:
        from app.services.calendar_service import hash_token

        token = secrets.token_urlsafe(32)
        user.update(partner_share_token_hash=hash_token(token))
        return token

    @staticmethod
    def revoke(user: User) -> None:
        user.update(partner_share_token_hash=None)

    @staticmethod
    def find_user(token: str) -> User | None:
        return lookup_user(User.partner_share_token_hash, token)

    @staticmethod
    def view(user: User, today=None) -> dict:
        """The complete, scope-limited content of the page and its JSON."""
        scope = PartnerShareService.settings(user)["scope"]
        hu = HeadsUpService.compute(
            user,
            scope["window_days"],
            scope["fertile"],
            today=today,
            link_key=user.partner_share_token_hash,
            slot="share",
        )
        if hu["state"] == STATE_PERIOD and scope["show_current"]:
            status, message, bucket = "period", "Period now", None
        elif hu["state"] == STATE_SOON:
            status = "soon"
            bucket = hu["days_bucket"]
            message = _SOON_TEXT.get(bucket, _SOON_TEXT["3-7"])
        else:
            status, message, bucket = "none", NOTHING_TEXT, None
        out = {
            "name": user.partner_share_name or DEFAULT_NAME,
            "status": status,
            "message": message,
            "days_bucket": bucket,
        }
        if scope["fertile"]:
            out["fertile"] = hu["fertile"]
            out["fertile_message"] = _FERTILE_TEXT.get(hu["fertile"])
        return out

    @staticmethod
    def render_html(view: dict) -> str:
        extra = ""
        if view.get("fertile_message"):
            extra = f"<p class=sub>{escape(view['fertile_message'])}</p>"
        return (
            "<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(view['name'])}</title>"
            "<meta name=robots content='noindex,nofollow,noarchive'>"
            "<meta name=referrer content=no-referrer>"
            "<meta name=color-scheme content='light dark'>"
            "<style>body{font:18px/1.5 system-ui,sans-serif;margin:0;display:grid;"
            "min-height:100vh;place-items:center;padding:16px;background:#fff;"
            "color:#222}main{max-width:28rem;text-align:center}h1{font-size:1rem;"
            "font-weight:600;opacity:.7}p{font-size:1.4rem;margin:.4em 0}"
            "p.sub{font-size:1.1rem;opacity:.8}@media(prefers-color-scheme:dark)"
            "{body{background:#111;color:#eee}}</style></head><body><main>"
            f"<h1>{escape(view['name'])}</h1><p>{escape(view['message'])}</p>"
            f"{extra}</main></body></html>"
        )
