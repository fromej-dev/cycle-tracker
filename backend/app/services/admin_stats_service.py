"""App-wide statistics for the admin page.

Everything returned here is an aggregate: counts, medians and shares. No usernames,
e-mail addresses, ids, dates of individual periods, free-text symptoms or anything
else that belongs to one person ever leaves this module.

Health aggregates (cycle and period length, symptom shares) describe intimate data,
so they are only reported once at least ``MIN_GROUP`` people contribute to them; with
fewer, a "median" is little more than one person's numbers. Below that threshold the
value is ``None`` and the page says there is not enough data yet.
"""

import datetime
import itertools
import json
import statistics
from collections import Counter, defaultdict

from sqlalchemy import func

from app.extensions import db
from app.models import Period, PlannedEvent, SymptomLog, User, Webhook
from app.services.forecast_service import MAX_CYCLE, MIN_CYCLE
from app.services.symptom_service import PRESETS

MIN_GROUP = 5  # fewest contributors before a health aggregate is shown
ACTIVE_DAYS = 30
SIGNUP_MONTHS = 12
MAX_PERIOD_DAYS = 15  # longer closed "periods" are data-entry slips
TOP_SYMPTOMS = 10


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _month_keys(today: datetime.date, months: int) -> list[str]:
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return keys[::-1]


class AdminStatsService:
    @staticmethod
    def stats(now: datetime.datetime | None = None) -> dict:
        now = now or datetime.datetime.utcnow()
        today = now.date()
        return {
            "generated_at": now.replace(microsecond=0),
            "min_group_size": MIN_GROUP,
            "users": AdminStatsService._users(now),
            "signups_by_month": AdminStatsService._signups(today),
            "data": AdminStatsService._data(),
            "features": AdminStatsService._features(),
            "cycles": AdminStatsService._cycles(),
            "symptoms": AdminStatsService._symptoms(),
        }

    # -- people ------------------------------------------------------------------

    @staticmethod
    def _users(now: datetime.datetime) -> dict:
        def created_since(days: int) -> int:
            since = now - datetime.timedelta(days=days)
            return User.query.filter(User.created_at >= since).count()

        since = now - datetime.timedelta(days=ACTIVE_DAYS)
        active: set[int] = set()
        for q in (
            db.session.query(Period.user_id).filter(Period.created_at >= since),
            db.session.query(SymptomLog.user_id).filter(
                func.coalesce(SymptomLog.updated_at, SymptomLog.created_at) >= since
            ),
            db.session.query(PlannedEvent.user_id).filter(
                func.coalesce(PlannedEvent.updated_at, PlannedEvent.created_at) >= since
            ),
        ):
            active.update(uid for (uid,) in q.distinct())

        return {
            "total": User.query.count(),
            "new_7d": created_since(7),
            "new_30d": created_since(30),
            "active_30d": len(active),
        }

    @staticmethod
    def _signups(today: datetime.date) -> list[dict]:
        keys = _month_keys(today, SIGNUP_MONTHS)
        y, m = map(int, keys[0].split("-"))
        start = datetime.datetime(y, m, 1)
        counts = Counter(
            f"{c.year:04d}-{c.month:02d}"
            for (c,) in db.session.query(User.created_at).filter(
                User.created_at >= start
            )
            if c
        )
        return [{"month": k, "count": counts.get(k, 0)} for k in keys]

    # -- volume and features -----------------------------------------------------

    @staticmethod
    def _data() -> dict:
        return {
            "periods": Period.query.count(),
            "ongoing_periods": Period.query.filter(Period.end_date.is_(None)).count(),
            "symptom_days": SymptomLog.query.count(),
            "planned_events": PlannedEvent.query.count(),
            "webhooks": Webhook.query.count(),
            "webhooks_active": Webhook.query.filter(Webhook.active.is_(True)).count(),
            "webhooks_auto_disabled": Webhook.query.filter(
                Webhook.disabled_reason.isnot(None)
            ).count(),
        }

    @staticmethod
    def _features() -> dict:
        def users_with(model) -> int:
            return db.session.query(func.count(func.distinct(model.user_id))).scalar()

        return {
            "periods": users_with(Period),
            "symptoms": users_with(SymptomLog),
            "planned_events": users_with(PlannedEvent),
            "webhooks": users_with(Webhook),
            "calendar_feed": User.query.filter(
                User.calendar_token_hash.isnot(None)
            ).count(),
            "partner_share": User.query.filter(
                User.partner_share_token_hash.isnot(None)
            ).count(),
            "home_assistant": User.query.filter(User.ha_token_hash.isnot(None)).count(),
        }

    # -- health aggregates (thresholded) -----------------------------------------

    @staticmethod
    def _cycles() -> dict:
        starts: dict[int, list[datetime.date]] = defaultdict(list)
        durations: dict[int, list[int]] = defaultdict(list)
        rows = db.session.query(Period.user_id, Period.start_date, Period.end_date)
        for uid, start, end in rows:
            starts[uid].append(start)
            if end is not None:
                days = (end - start).days + 1
                if 1 <= days <= MAX_PERIOD_DAYS:
                    durations[uid].append(days)

        # One median per person first, so heavy loggers don't dominate.
        cycle_medians = []
        for dates in starts.values():
            dates.sort()
            gaps = [
                (b - a).days
                for a, b in itertools.pairwise(dates)
                if MIN_CYCLE <= (b - a).days <= MAX_CYCLE
            ]
            if gaps:
                cycle_medians.append(statistics.median(gaps))
        period_medians = [statistics.median(d) for d in durations.values() if d]

        enough_cycles = len(cycle_medians) >= MIN_GROUP
        enough_periods = len(period_medians) >= MIN_GROUP
        return {
            "users_with_cycles": len(cycle_medians),
            "median_cycle_length": _median(cycle_medians) if enough_cycles else None,
            "users_with_period_length": len(period_medians),
            "median_period_length": (
                _median(period_medians) if enough_periods else None
            ),
        }

    @staticmethod
    def _symptoms() -> dict:
        users_per_key: dict[str, set[int]] = defaultdict(set)
        loggers: set[int] = set()
        for uid, raw in db.session.query(SymptomLog.user_id, SymptomLog.symptoms):
            try:
                keys = json.loads(raw or "[]")
            except ValueError:
                continue
            if not isinstance(keys, list):
                continue
            loggers.add(uid)
            for k in keys:
                if isinstance(k, str) and k in PRESETS:  # never free text
                    users_per_key[k].add(uid)

        top = []
        if len(loggers) >= MIN_GROUP:
            ranked = sorted(
                ((k, len(u)) for k, u in users_per_key.items() if len(u) >= MIN_GROUP),
                key=lambda kv: (-kv[1], kv[0]),
            )
            top = [
                {"key": k, "users": n, "share": round(n / len(loggers), 3)}
                for k, n in ranked[:TOP_SYMPTOMS]
            ]
        return {"users_logging": len(loggers), "top": top}
