import datetime

from app.models import PlannedEvent
from app.services.date_check_service import DateCheckService
from app.utils import ics
from app.utils.exceptions import NotFoundError, ValidationError

MAX_EVENTS_PER_USER = 200


class PlannedEventService:
    """CRUD for a user's planned events, enriched with live Date Check odds."""

    @staticmethod
    def _clean_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValidationError(payload={"name": ["Name cannot be blank."]})
        if len(name) > 120 or ics.has_forbidden_chars(name):
            raise ValidationError(
                payload={"name": ["Name is too long or has control characters."]}
            )
        return name

    @staticmethod
    def _get(user_id: int, event_id: int) -> PlannedEvent:
        event = PlannedEvent.query.filter_by(id=event_id, user_id=user_id).first()
        if event is None:
            raise NotFoundError(f"Event with ID {event_id} not found.")
        return event

    @staticmethod
    def with_odds(event: PlannedEvent, model) -> dict:
        """Event fields plus the current Date Check summary (model fitted once)."""
        if event.end_date < model.today:  # nothing to forecast for finished events
            return {
                "id": event.id,
                "name": event.name,
                "start_date": event.start_date,
                "end_date": event.end_date,
                "created_at": event.created_at,
                "updated_at": event.updated_at,
                "is_past": True,
                "probability_any": None,
                "most_likely_days": None,
                "confidence": None,
                "status": "past",
                "reason": None,
                "horizon_note": None,
            }
        check = DateCheckService.check_with_model(
            model, event.start_date, event.end_date
        )
        return {
            "id": event.id,
            "name": event.name,
            "start_date": event.start_date,
            "end_date": event.end_date,
            "created_at": event.created_at,
            "updated_at": event.updated_at,
            "is_past": event.end_date < model.today,
            "probability_any": check["probability_any"],
            "most_likely_days": check["most_likely_days"],
            "confidence": check["confidence"],
            "status": check["status"],
            "reason": check["reason"],
            "horizon_note": check["horizon_note"],
        }

    @staticmethod
    def list_for_user(user_id: int, today: datetime.date | None = None) -> list[dict]:
        """Upcoming/ongoing events by start ascending, then past ones, newest first."""
        today = today or datetime.date.today()
        events = PlannedEvent.query.filter_by(user_id=user_id).all()
        model = DateCheckService.load_model(user_id, today)
        current = [e for e in events if e.end_date >= today]
        if current:  # one engine warm-up for the farthest event, shared by all
            DateCheckService.prime(
                model, max(e.end_date for e in current) + datetime.timedelta(days=35)
            )
        upcoming = sorted(
            (e for e in events if e.end_date >= today),
            key=lambda e: (e.start_date, e.id),
        )
        past = sorted(
            (e for e in events if e.end_date < today),
            key=lambda e: (e.start_date, e.id),
            reverse=True,
        )
        return [PlannedEventService.with_odds(e, model) for e in upcoming + past]

    @staticmethod
    def get_for_user(
        user_id: int, event_id: int, today: datetime.date | None = None
    ) -> dict:
        today = today or datetime.date.today()
        event = PlannedEventService._get(user_id, event_id)
        return PlannedEventService.with_odds(
            event, DateCheckService.load_model(user_id, today)
        )

    @staticmethod
    def create(user_id: int, data: dict, today: datetime.date | None = None) -> dict:
        today = today or datetime.date.today()
        name = PlannedEventService._clean_name(data["name"])
        DateCheckService.validate_range(
            data["start_date"],
            data["end_date"],
            today,
            fields=("start_date", "end_date"),
        )
        if PlannedEvent.query.filter_by(user_id=user_id).count() >= MAX_EVENTS_PER_USER:
            raise ValidationError(
                payload={
                    "name": [f"You can have at most {MAX_EVENTS_PER_USER} events."]
                }
            )
        event = PlannedEvent(
            user_id=user_id,
            name=name,
            start_date=data["start_date"],
            end_date=data["end_date"],
        ).save()
        return PlannedEventService.with_odds(
            event, DateCheckService.load_model(user_id, today)
        )

    @staticmethod
    def update(
        user_id: int, event_id: int, data: dict, today: datetime.date | None = None
    ) -> dict:
        today = today or datetime.date.today()
        event = PlannedEventService._get(user_id, event_id)
        name = PlannedEventService._clean_name(data["name"])
        DateCheckService.validate_range(
            data["start_date"],
            data["end_date"],
            today,
            fields=("start_date", "end_date"),
        )
        event.update(
            name=name, start_date=data["start_date"], end_date=data["end_date"]
        )
        return PlannedEventService.with_odds(
            event, DateCheckService.load_model(user_id, today)
        )

    @staticmethod
    def delete(user_id: int, event_id: int, today: datetime.date | None = None) -> None:
        PlannedEventService._get(user_id, event_id).delete()
