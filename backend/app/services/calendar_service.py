"""Private calendar feed (ICS subscription URL) for predicted periods.

Privacy model
-------------
* The URL contains a random token (``secrets.token_urlsafe(32)``, 256 bits). Only its
  SHA-256 hash is stored, so a database leak does not reveal working feed URLs. The
  token is returned exactly once, on creation.
* Calendars are often shared at work, so the default is discreet: the event title is
  just a moon emoji (or the label the user chose), there is no description, events are
  CLASS:PRIVATE and TRANSP:TRANSPARENT (never block free/busy). Fertile-window events
  are opt-in.

What an event covers
--------------------
* The last two logged periods (so subscribers see a period they are in or just had).
* Up to three predicted periods. Each is ONE all-day event spanning the narrowest
  window holding 50% of that cycle's start probability (from the engine's per-cycle
  start distribution, so late, skipping and long-cycle users are handled like Date
  Check handles them) plus the typical period length (2..8 days). A cycle is only
  published if (a) its event is at most min(21 days, mean cycle) long, (b) it starts
  at least ``MIN_GAP`` days after the previous event ends, and (c) Date Check itself
  rates the *exact* event dates (never clipped) at >= 50% with no "far ahead / flat"
  note. The first failure ends the list. Hysteresis, keyed by event identity: an event
  that is already published only needs ``KEEP_MASS`` (40%) to stay and may grow to
  ``KEEP_MAX_DAYS``; if it fails anyway it keeps its last dates for up to
  ``GRACE_POLLS`` days (still marked as an estimate when the user opted in), so it can
  briefly lag Date Check. A prediction that moves more than ``JUMP_DAYS`` gets a new
  identity instead of being moved.
* Optional fertile windows (opt-in): ovulation is ~14 days before the start (as in the
  engine), fertile window = ovulation -5..+1, derived from the same cycle window. They
  are published only when at most ``FERTILE_MAX_DAYS`` long, never entirely in the
  past, when no period event overlaps them, and when Date Check's P(any bleeding) in
  the window is below ``FERTILE_MAX_BLEED``.
Users with no data or a lapsed history ("overdue") get only their logged periods.

An empty calendar is deliberate: RFC 5545 3.6 asks for at least one component, but
Google, Apple and Outlook accept an empty VCALENDAR, and a placeholder event would
clutter a calendar that is often shared at work.

Identity and revisions
----------------------
UIDs are opaque (``<hex>@feed``, an HMAC under a random per-feed key stored in
``users.calendar_uid_key`` and regenerated on rotation), so they reveal nothing about
the user, the app's SECRET_KEY or the event kind; the PRODID is neutral: nothing in
the file names this app. A small JSON state on the user (updated with a
compare-and-swap, never on HEAD) keeps (a) predicted "slots": the next predicted
period keeps its UID when it is logged (it is *adopted* by the new period), so users'
alarms and notes survive; spotting merged into a previous bleed never adopts a slot,
and deleting an adopted period hands its UID back; (b) per-event content hash,
SEQUENCE and last-change time, so only an event that really changed is revised.
Removed events are kept as tombstones (up to ``TOMBSTONES``) so a returning UID
continues its SEQUENCE. DTSTAMP equals LAST-MODIFIED, the event's last revision.
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import hmac
import json
import re
import secrets
import zoneinfo

from sqlalchemy import update

from app.extensions import db
from app.models import Period, User
from app.services.date_check_service import (
    DateCheckService,
    cycle_start_pmfs,
    narrowest_window,
)
from app.services.forecast_service import MIN_CYCLE, ForecastService
from app.utils import ics

DEFAULT_LABEL = "🌙"
PREDICTED_CYCLES = 3
LOGGED_KEPT = 2
WINDOW_MASS = 0.5
KEEP_MASS = 0.4  # hysteresis for events that are already published
TOMBSTONES = 40
JUMP_DAYS = 14  # a prediction carried further than this gets a new identity
GRACE_POLLS = 7  # a failing published event keeps its dates this many polls
KEEP_MAX_DAYS = 25  # published events may grow to this before being dropped
MIN_GAP = 3  # days between one event's last day and the next one's first
MAX_EVENT_DAYS = 21
FERTILE_MAX_DAYS = 10
FERTILE_MAX_BLEED = 0.2
PREDICTION_HORIZON_DAYS = 160
FERTILE_SUFFIX = " ·"
ESTIMATE_MARK = " ~"
PRODID = "-//private-feed//EN"
_NOT_ZONES = frozenset({"localtime", "posixrules", "Factory"})
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_DUMMY_HASH = hashlib.sha256(b"cycle-tracker-no-such-token").hexdigest()

TD = datetime.timedelta


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CalendarService:
    """Feed credentials, settings and ICS rendering."""

    # --- credentials ----------------------------------------------------------------

    @staticmethod
    def rotate_token(user: User) -> str:
        """Create a new token (invalidating any previous one). Returned once."""
        token = secrets.token_urlsafe(32)
        # A new subscription gets a new secret for its event identifiers.
        user.update(
            calendar_token_hash=hash_token(token),
            calendar_uid_key=secrets.token_hex(32),
            calendar_state=None,
        )
        return token

    @staticmethod
    def revoke_token(user: User) -> None:
        user.update(calendar_token_hash=None)

    @staticmethod
    def find_user_by_token(token: str) -> User | None:
        """Look the user up by token hash; constant-time compare, no enumeration."""
        candidate = hash_token(token) if TOKEN_RE.match(token) else _DUMMY_HASH
        user = User.query.filter_by(calendar_token_hash=candidate).first()
        stored = user.calendar_token_hash if user else _DUMMY_HASH
        # compare_digest on every path so hits and misses cost about the same
        if hmac.compare_digest(stored, candidate) and user is not None:
            return user
        return None

    @staticmethod
    def feed_path(token: str) -> str:
        return f"/calendar/{token}.ics"

    # --- settings -------------------------------------------------------------------

    @staticmethod
    def display_label(user: User) -> str:
        return user.calendar_label or DEFAULT_LABEL

    @staticmethod
    def settings(user: User) -> dict:
        return {
            "enabled": user.calendar_token_hash is not None,
            "label": CalendarService.display_label(user),
            "include_fertile": bool(user.calendar_include_fertile),
            "fertile_label": user.calendar_fertile_label,
            "mark_estimates": bool(user.calendar_mark_estimate),
            "timezone": user.calendar_timezone,
        }

    @staticmethod
    def update_settings(user: User, data: dict) -> dict:
        changes = {}
        if "label" in data:
            label = (data["label"] or "").strip()
            changes["calendar_label"] = label or None  # blank -> discreet default
        if "fertile_label" in data:
            fl = (data["fertile_label"] or "").strip()
            changes["calendar_fertile_label"] = fl or None
        if "mark_estimates" in data:
            changes["calendar_mark_estimate"] = bool(data["mark_estimates"])
        if "timezone" in data:
            tz = (data["timezone"] or "").strip()
            changes["calendar_timezone"] = tz or None
        if "include_fertile" in data:
            changes["calendar_include_fertile"] = bool(data["include_fertile"])
        if changes:
            user.update(**changes)
        return CalendarService.settings(user)

    # --- time zone ------------------------------------------------------------------

    @staticmethod
    @functools.cache
    def _zone_names() -> frozenset[str]:
        return frozenset(zoneinfo.available_timezones()) - _NOT_ZONES

    @staticmethod
    def valid_timezone(name: str) -> bool:
        """True for a real IANA zone name (no paths, no localtime/posixrules/Factory)."""
        if not name or len(name) > 64 or name in _NOT_ZONES:
            return False
        names = CalendarService._zone_names()
        if names:
            return name in names
        try:  # no tz database enumeration available: fall back to a strict lookup
            zoneinfo.ZoneInfo(name)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
            return False
        return re.fullmatch(r"[A-Za-z0-9_+\-/]+", name) is not None

    @staticmethod
    def local_today(user: User) -> datetime.date:
        name = user.calendar_timezone
        tz = (
            zoneinfo.ZoneInfo(name)
            if name and CalendarService.valid_timezone(name)
            else None
        )
        return datetime.datetime.now(tz or datetime.UTC).date()

    # --- state ----------------------------------------------------------------------

    @staticmethod
    def _load_state(raw: str | None) -> dict:
        state = {
            "counter": 0,
            "slots": [],
            "adopted": {},
            "from_slots": [],
            "events": {},
        }
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    state.update({k: loaded[k] for k in state if k in loaded})
            except ValueError:
                pass
        return state

    @staticmethod
    def _dump_state(state: dict) -> str:
        return json.dumps(state, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _uid(key: str, n: int, kind: str) -> str:
        """Opaque event id: HMAC under the feed's own random secret (not SECRET_KEY),
        so it reveals neither the user, the counter nor the kind of event."""
        msg = f"{n}:{kind}".encode()
        return (
            hmac.new(bytes.fromhex(key), msg, hashlib.sha256).hexdigest()[:32] + "@feed"
        )

    @staticmethod
    def _uid_key(user: User, persist: bool) -> str:
        key = user.calendar_uid_key
        if key:
            return key
        key = secrets.token_hex(32)
        if persist:  # first render of a feed created before the key existed
            db.session.execute(
                update(User)
                .where(User.id == user.id, User.calendar_uid_key.is_(None))
                .values(calendar_uid_key=key)
            )
            db.session.commit()
            db.session.refresh(user)
            key = user.calendar_uid_key or key
        return key

    @staticmethod
    def _compare_and_swap(user: User, old: str | None, new: str) -> bool:
        cond = (
            User.calendar_state.is_(None)
            if old is None
            else (User.calendar_state == old)
        )
        result = db.session.execute(
            update(User).where(User.id == user.id, cond).values(calendar_state=new)
        )
        db.session.commit()
        db.session.refresh(user)
        return result.rowcount == 1

    # --- events ---------------------------------------------------------------------

    @staticmethod
    def _events(
        user: User, today: datetime.date, state: dict, key: str | None = None
    ) -> list[dict]:
        """Event dicts (kind, uid, first, last, estimate). Mutates ``state``."""
        key = key or user.calendar_uid_key or "00" * 32

        def mint() -> int:
            state["counter"] += 1
            return state["counter"]

        rows = Period.query.filter_by(user_id=user.id).order_by(Period.start_date).all()
        slots: list[int] = list(state["slots"])
        adopted: dict[str, int] = state["adopted"]
        from_slots: list[int] = state.setdefault("from_slots", [])

        # --- a deleted period gives its id back to the prediction it came from -----
        existing = {str(r.id) for r in rows}
        for rid, n in list(adopted.items()):
            if rid in existing:
                continue
            del adopted[rid]
            if n in from_slots:
                from_slots.remove(n)
                if all(n > m for m in from_slots):  # only the most recent adoption
                    slots.insert(0, n)
                    del slots[PREDICTED_CYCLES:]

        # --- recently logged periods; a real new period adopts the first slot ------
        # Rows starting < MIN_CYCLE days after the previous bleed are merged into it by
        # the model (spotting, double logs): they never take a prediction's identity.
        merged: set[int] = set()
        prev_start = None
        for row in rows:
            if (
                prev_start is not None
                and (row.start_date - prev_start).days < MIN_CYCLE
            ):
                merged.add(row.id)
            else:
                prev_start = row.start_date
        real = [r for r in rows if r.id not in merged][-LOGGED_KEPT:]
        shown = rows[rows.index(real[0]) :] if real else []
        # (merged rows after the first shown period are shown too, so a spotting log
        # never pushes a real period out of the feed)
        for row in shown:
            if str(row.id) in adopted:
                continue
            if row.id in merged or not slots:
                n = mint()
            else:
                n = slots.pop(0)
                from_slots.append(n)
            adopted[str(row.id)] = n
        state["from_slots"] = [n for n in from_slots if n in adopted.values()]
        while len(slots) < PREDICTED_CYCLES:
            slots.append(mint())
        state["slots"] = slots

        model = ForecastService.fit([(p.start_date, p.end_date) for p in rows], today)
        if model.last_start is None:
            return []  # state["events"] stays: it becomes tombstones (SEQUENCE kept)
        typical = min(max(round(model.duration_post.mu), 2), 8)
        published = state["events"]
        events: list[dict] = []
        for row in shown:
            if row.end_date is not None:
                last = row.end_date
            elif row is rows[-1] and model.ongoing:
                last = max(row.start_date + TD(days=typical - 1), today)
            else:
                last = row.start_date + TD(days=typical - 1)
            events.append(
                {
                    "kind": "period",
                    "uid": CalendarService._uid(key, adopted[str(row.id)], "p"),
                    "first": row.start_date,
                    "last": last,
                    "estimate": False,
                }
            )
        if model.overdue:
            return CalendarService._finish(events, state)

        # --- predicted cycles -------------------------------------------------------
        s0 = model.last_start
        horizon = (today - s0).days + PREDICTION_HORIZON_DAYS
        pmfs = cycle_start_pmfs(model, PREDICTED_CYCLES, horizon)
        max_len = min(MAX_EVENT_DAYS, max(round(model.mean_cycle), 1))
        prev_last = max(e["last"] for e in events)
        for k, pmf in enumerate(pmfs, start=1):
            uid = CalendarService._uid(key, slots[k - 1], "p")
            rec = published.get(uid)
            kept = bool(rec) and not rec.get("x")

            def evaluate(is_kept: bool, pmf=pmf, prev_last=prev_last):
                return CalendarService._window(
                    model, pmf, s0, typical, today, prev_last, max_len, is_kept
                )

            res = evaluate(kept)
            if res and rec and rec.get("a"):
                moved = abs((res[0] - datetime.date.fromisoformat(rec["a"])).days)
                if moved > JUMP_DAYS:
                    # the forecast carried this prediction far away (or it comes back
                    # after a pause far from where it was): a different event, not
                    # the old one "moving" by weeks
                    again = evaluate(False) if kept else res
                    if again:
                        slots[k - 1] = mint()
                        uid = CalendarService._uid(key, slots[k - 1], "p")
                        res, kept, rec = again, False, None
                    else:
                        res = None
            if res is None:
                # grace counts days, not renders: same-day polls must agree
                prior = (rec or {}).get("g", 0)
                same_day = (rec or {}).get("gd") == today.isoformat()
                grace = prior if same_day else prior + 1
                if kept and rec.get("a") and grace <= GRACE_POLLS:
                    first = datetime.date.fromisoformat(rec["a"])
                    last = datetime.date.fromisoformat(rec["b"])
                    if last >= today:  # hold the old dates for a few polls
                        events.append(
                            {
                                "kind": "period",
                                "uid": uid,
                                "first": first,
                                "last": last,
                                "estimate": True,
                                "grace": grace,
                            }
                        )
                        prev_last = last
                        continue
                break
            first, last, lo, hi = res
            events.append(
                {
                    "kind": "period",
                    "uid": uid,
                    "first": first,
                    "last": last,
                    "estimate": True,
                }
            )
            prev_last = last
            if user.calendar_include_fertile:
                fertile = CalendarService._fertile(
                    key, model, today, slots[k - 1], s0, lo, hi, events
                )
                if fertile:
                    events.append(fertile)
        return CalendarService._finish(events, state)

    @staticmethod
    def _window(model, pmf, s0, typical, today, prev_last, max_len, kept):
        """(first, last, lo, hi) of one publishable predicted period, else None.

        Hysteresis: a published event (``kept``) may be wider, closer to its
        predecessor and a little less probable than a new one.
        """
        win = narrowest_window(pmf, WINDOW_MASS)
        if win is None and kept:
            win = narrowest_window(pmf, KEEP_MASS)
        if win is None:
            return None
        lo, hi, _ = win
        first = s0 + TD(days=lo)
        last = s0 + TD(days=hi) + TD(days=typical - 1)
        width_cap = max(max_len, KEEP_MAX_DAYS) if kept else max_len
        min_first = prev_last + TD(days=2 if kept else MIN_GAP + 1)
        if last < today or (last - first).days + 1 > width_cap or first < min_first:
            return None
        # the gate sees the exact event dates (first >= today for predictions)
        check = DateCheckService.check_with_model(model, first, last)
        threshold = KEEP_MASS if kept else WINDOW_MASS
        if (check["probability_any"] or 0.0) < threshold or check["horizon_note"]:
            return None
        return first, last, lo, hi

    @staticmethod
    def _fertile(key, model, today, slot, s0, lo, hi, events) -> dict | None:
        """Fertile window for one cycle: ovulation = start - 14, window -5..+1."""
        first = s0 + TD(days=lo - 19)
        last = s0 + TD(days=hi - 13)
        if (last - first).days + 1 > FERTILE_MAX_DAYS or last < today:
            return None
        first = max(first, today)
        if any(first <= e["last"] and e["first"] <= last for e in events):
            return None
        # the bar is P(any bleeding in the window), not the largest single day
        check = DateCheckService.check_with_model(model, first, last)
        if (check["probability_any"] or 0.0) >= FERTILE_MAX_BLEED:
            return None
        return {
            "kind": "fertile",
            "uid": CalendarService._uid(key, slot, "f"),
            "first": first,
            "last": last,
            "estimate": True,
        }

    @staticmethod
    def _finish(events: list[dict], state: dict) -> list[dict]:
        events.sort(key=lambda e: (e["first"], e["kind"], e["uid"]))
        return events

    @staticmethod
    def predicted_events(
        user: User, today: datetime.date, state: dict | None = None
    ) -> list[dict]:
        """Events as they would be published now (read-only: nothing is stored)."""
        state = state or CalendarService._load_state(user.calendar_state)
        key = CalendarService._uid_key(user, persist=False)
        return CalendarService._events(user, today, copy_state(state), key)

    # --- rendering --------------------------------------------------------------------

    @staticmethod
    def build_ics(
        user: User,
        today: datetime.date | None = None,
        now: datetime.datetime | None = None,
        persist: bool = True,
    ) -> str:
        """Render the feed. ``persist=False`` (HEAD) never writes."""
        today = today or CalendarService.local_today(user)
        now = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        label = CalendarService.display_label(user)
        fertile_label = user.calendar_fertile_label or f"{label}{FERTILE_SUFFIX}"
        mark = ESTIMATE_MARK if user.calendar_mark_estimate else ""
        key = CalendarService._uid_key(user, persist)
        for _attempt in range(3):
            old = user.calendar_state
            state = CalendarService._load_state(old)
            events = CalendarService._events(user, today, state, key)
            body = []
            seen = {}
            for ev in events:
                summary = label if ev["kind"] == "period" else fertile_label
                if ev["estimate"]:
                    summary += mark
                dtstart = ics.date_value(ev["first"])
                dtend = ics.date_value(ev["last"] + TD(days=1))
                digest = hashlib.sha256(
                    f"{dtstart}|{dtend}|{summary}".encode()
                ).hexdigest()[:16]
                prev = state["events"].get(ev["uid"])
                span = {"a": ev["first"].isoformat(), "b": ev["last"].isoformat()}
                grace = ev.get("grace", 0)
                if prev is None:
                    rec = {
                        "h": digest,
                        "s": 0,
                        "t": ics.datetime_utc_value(now),
                        **span,
                    }
                elif prev["h"] != digest or prev.get("x"):
                    rec = {
                        "h": digest,
                        "s": prev["s"] + 1,
                        "t": ics.datetime_utc_value(now),
                        **span,
                    }
                else:
                    rec = {k_: v for k_, v in prev.items() if k_ != "g"}
                    rec.update(span)
                rec.pop("gd", None)
                if grace:
                    rec["g"] = grace
                    rec["gd"] = today.isoformat()
                seen[ev["uid"]] = rec
                body.append((ev["uid"], dtstart, dtend, summary, rec))
            # Keep a few tombstones so a UID that comes back continues its SEQUENCE.
            old_events = state["events"]
            gone = [(u, {**r, "x": 1}) for u, r in old_events.items() if u not in seen]
            gone.sort(key=lambda item: item[1]["t"], reverse=True)
            state["events"] = {**dict(gone[:TOMBSTONES]), **seen}
            new = CalendarService._dump_state(state)
            canonical_old = CalendarService._dump_state(
                CalendarService._load_state(old)
            )
            if not persist or new == canonical_old:
                break
            if CalendarService._compare_and_swap(user, old, new):
                break
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:{PRODID}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{ics.escape_text(label)}",
            "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
            "X-PUBLISHED-TTL:PT12H",
        ]
        for uid, dtstart, dtend, summary, rec in body:
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{rec['t']}",
                f"LAST-MODIFIED:{rec['t']}",
                f"SEQUENCE:{rec['s']}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"DTEND;VALUE=DATE:{dtend}",
                f"SUMMARY:{ics.escape_text(summary)}",
                "TRANSP:TRANSPARENT",
                "CLASS:PRIVATE",
                "X-MICROSOFT-CDO-BUSYSTATUS:FREE",
                "END:VEVENT",
            ]
        lines.append("END:VCALENDAR")
        return ics.serialize(lines)


def copy_state(state: dict) -> dict:
    return json.loads(json.dumps(state))
