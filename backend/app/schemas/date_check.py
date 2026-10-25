from apiflask import Schema, fields
from marshmallow import ValidationError as MarshmallowValidationError
from marshmallow import validate, validates_schema

from app.utils import ics


def _clean_text(value: str) -> None:
    if ics.has_forbidden_chars(value):
        raise MarshmallowValidationError(
            "Cannot contain control, bidi/format or line-separator characters."
        )


class DateCheckQuerySchema(Schema):
    """Query string of GET /reports/date-check."""

    start = fields.Date(required=True, metadata={"description": "YYYY-MM-DD"})
    end = fields.Date(required=True, metadata={"description": "YYYY-MM-DD"})
    today = fields.Date(
        load_default=None, metadata={"description": "Client-local date (optional)"}
    )


class DateCheckDaySchema(Schema):
    date = fields.Date(required=True)
    p_bleeding = fields.Float(required=True)


class DateCheckSchema(Schema):
    """Chance of bleeding at some point during a date range."""

    start = fields.Date(required=True)
    end = fields.Date(required=True)
    probability_any = fields.Float(
        allow_none=True,
        metadata={
            "description": "P(at least one bleeding day in range); null if no forecast"
        },
    )
    days = fields.List(fields.Nested(DateCheckDaySchema), required=True)
    most_likely_days = fields.List(
        fields.Date(),
        allow_none=True,
        metadata={"description": "1-3 standout days, or null if none stands out"},
    )
    confidence = fields.String(
        required=True,
        metadata={"description": "learning, regular, variable, irregular or overdue"},
    )
    horizon_note = fields.String(allow_none=True)
    includes_past_dates = fields.Boolean(required=True)
    status = fields.String(
        required=True,
        validate=validate.OneOf(["ok", "learning", "overdue", "no_data"]),
    )
    reason = fields.String(
        allow_none=True, metadata={"description": "Why there is no/weak forecast"}
    )


class PlannedEventInputSchema(Schema):
    """Body of POST/PUT /events."""

    name = fields.String(
        required=True,
        validate=[validate.Length(min=1, max=120), _clean_text],
    )
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)

    @validates_schema
    def validate_dates(self, data, **kwargs):
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            raise MarshmallowValidationError(
                "End date cannot be before start date.", field_name="end_date"
            )


class PlannedEventSchema(Schema):
    """A planned event with its live period odds."""

    id = fields.Integer(dump_only=True)
    name = fields.String()
    start_date = fields.Date()
    end_date = fields.Date()
    created_at = fields.DateTime()
    updated_at = fields.DateTime(allow_none=True)
    is_past = fields.Boolean()
    probability_any = fields.Float(allow_none=True)
    most_likely_days = fields.List(fields.Date(), allow_none=True)
    confidence = fields.String()
    status = fields.String()
    reason = fields.String(allow_none=True)
    horizon_note = fields.String(allow_none=True)
