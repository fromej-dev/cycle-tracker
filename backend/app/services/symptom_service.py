"""Per-day symptom log: a fixed list of common cycle-related symptoms plus free text.

One row per user and day; saving an empty day removes the row. The preset keys are
stable identifiers (the app translates them); the English labels here are only used
in the doctor report.
"""

import datetime
import json
from collections import Counter

from app.extensions import db
from app.models import SymptomLog
from app.utils import ics
from app.utils.exceptions import ValidationError

# Ordered as the app groups them: pain, body, mood & sleep.
PRESETS: dict[str, str] = {
    "cramps": "Cramps",
    "headache": "Headache",
    "migraine": "Migraine",
    "back_pain": "Lower back pain",
    "breast_tenderness": "Breast tenderness",
    "pelvic_pain": "Pelvic pain",
    "ovulation_pain": "Ovulation pain",
    "heavy_bleeding": "Heavy bleeding",
    "spotting": "Spotting",
    "bloating": "Bloating",
    "digestion": "Bowel changes",
    "nausea": "Nausea",
    "fatigue": "Fatigue",
    "cravings": "Food cravings",
    "acne": "Acne",
    "dizziness": "Dizziness",
    "hot_flashes": "Hot flashes / night sweats",
    "discharge": "Discharge",
    "mood_swings": "Mood swings",
    "irritability": "Irritability",
    "anxiety": "Anxiety",
    "low_mood": "Low mood",
    "insomnia": "Poor sleep",
    "poor_focus": "Poor concentration",
}

MAX_CUSTOM_PER_DAY = 10
MAX_CUSTOM_LEN = 40
MAX_RANGE_DAYS = 400
FREQUENT_DAYS = 180
RECENT_CUSTOM_DAYS = 365


def _loads(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def as_dict(log: SymptomLog) -> dict:
    return {
        "date": log.date,
        "symptoms": _loads(log.symptoms),
        "custom": _loads(log.custom),
    }


class SymptomService:
    @staticmethod
    def _clean(symptoms: list[str], custom: list[str]) -> tuple[list[str], list[str]]:
        unknown = sorted({s for s in symptoms if s not in PRESETS})
        if unknown:
            raise ValidationError(
                payload={"symptoms": [f"Unknown symptom: {', '.join(unknown)}."]}
            )
        chosen = set(symptoms)
        keys = [k for k in PRESETS if k in chosen]  # canonical order, no duplicates

        labels: list[str] = []
        seen: set[str] = set()
        for raw in custom:
            label = " ".join((raw or "").split())  # trim and collapse whitespace
            if not label:
                continue
            if len(label) > MAX_CUSTOM_LEN or ics.has_forbidden_chars(label):
                raise ValidationError(
                    payload={
                        "custom": [
                            f"Keep each symptom under {MAX_CUSTOM_LEN} characters."
                        ]
                    }
                )
            if label.casefold() in seen:
                continue
            seen.add(label.casefold())
            labels.append(label)
        if len(labels) > MAX_CUSTOM_PER_DAY:
            raise ValidationError(
                payload={
                    "custom": [f"At most {MAX_CUSTOM_PER_DAY} own symptoms per day."]
                }
            )
        return keys, labels

    @staticmethod
    def list_range(
        user_id: int, start: datetime.date, end: datetime.date
    ) -> list[dict]:
        if end < start:
            raise ValidationError(payload={"end": ["End must not be before start."]})
        if (end - start).days >= MAX_RANGE_DAYS:
            raise ValidationError(
                payload={"end": [f"Ask for at most {MAX_RANGE_DAYS} days at once."]}
            )
        logs = (
            SymptomLog.query.filter(
                SymptomLog.user_id == user_id,
                SymptomLog.date >= start,
                SymptomLog.date <= end,
            )
            .order_by(SymptomLog.date)
            .all()
        )
        return [as_dict(log) for log in logs]

    @staticmethod
    def save_day(
        user_id: int,
        day: datetime.date,
        symptoms: list[str],
        custom: list[str],
        today: datetime.date | None = None,
    ) -> dict:
        """Replace the day's symptoms; an empty selection removes the day."""
        today = today or datetime.date.today()
        if day > today:
            raise ValidationError(
                payload={"date": ["Symptoms can only be logged up to today."]}
            )
        keys, labels = SymptomService._clean(symptoms, custom)
        log = SymptomLog.query.filter_by(user_id=user_id, date=day).first()
        if not keys and not labels:
            if log is not None:
                log.delete()
            return {"date": day, "symptoms": [], "custom": []}
        if log is None:
            log = SymptomLog(user_id=user_id, date=day)
            db.session.add(log)
        log.symptoms = json.dumps(keys)
        log.custom = json.dumps(labels, ensure_ascii=False)
        db.session.commit()
        return as_dict(log)

    @staticmethod
    def suggestions(user_id: int, today: datetime.date | None = None) -> dict:
        """The user's most logged presets and recently used own symptoms, for one-tap reuse."""
        today = today or datetime.date.today()
        since = today - datetime.timedelta(days=max(FREQUENT_DAYS, RECENT_CUSTOM_DAYS))
        logs = (
            SymptomLog.query.filter(
                SymptomLog.user_id == user_id, SymptomLog.date >= since
            )
            .order_by(SymptomLog.date.desc())
            .all()
        )
        frequent_since = today - datetime.timedelta(days=FREQUENT_DAYS)
        counts = Counter(
            key
            for log in logs
            if log.date >= frequent_since
            for key in _loads(log.symptoms)
            if key in PRESETS
        )
        recent: list[str] = []
        seen: set[str] = set()
        for log in logs:  # newest first
            for label in _loads(log.custom):
                if label.casefold() not in seen:
                    seen.add(label.casefold())
                    recent.append(label)
        return {
            "frequent": [k for k, _ in counts.most_common(8)],
            "recent_custom": recent[:12],
        }

    @staticmethod
    def rows_for_report(
        user_id: int, since: datetime.date, today: datetime.date
    ) -> list[tuple[datetime.date, list[str]]]:
        """(date, readable labels) for every logged day in the range, oldest first."""
        logs = (
            SymptomLog.query.filter(
                SymptomLog.user_id == user_id,
                SymptomLog.date >= since,
                SymptomLog.date <= today,
            )
            .order_by(SymptomLog.date)
            .all()
        )
        return [
            (
                log.date,
                [PRESETS[k] for k in _loads(log.symptoms) if k in PRESETS]
                + _loads(log.custom),
            )
            for log in logs
        ]
