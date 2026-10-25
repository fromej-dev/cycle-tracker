from apiflask import Schema, fields
from marshmallow import ValidationError, validate

from app.utils import ics


class UserSchema(Schema):
    """Schema for serializing User data (excluding password)."""

    # Explicitly define fields for clarity or customization if needed
    id = fields.Integer(dump_only=True)
    username = fields.String(required=True, validate=validate.Length(min=3, max=80))
    email = fields.Email(required=True, validate=validate.Length(max=120))
    created_at = fields.DateTime(dump_only=True)


class UserUpdateSchema(Schema):
    """Schema for serializing User update data"""

    username = fields.String(validate=validate.Length(min=3, max=80))
    email = fields.Email(validate=validate.Length(max=120))


class ChangePasswordSchema(Schema):
    """Schema for changing password."""

    current_password = fields.String(required=True)
    new_password = fields.String(required=True)


def _no_control_chars(value: str | None) -> None:
    if value and ics.has_forbidden_chars(value):
        raise ValidationError(
            "Label cannot contain control, bidi/format or line-separator characters."
        )


class CalendarFeedSchema(Schema):
    """Calendar feed settings (never contains the token)."""

    enabled = fields.Boolean(required=True)
    label = fields.String(
        required=True, metadata={"description": "Event title; default is a moon emoji"}
    )
    include_fertile = fields.Boolean(required=True)
    fertile_label = fields.String(
        allow_none=True, metadata={"description": "null = same title as periods"}
    )
    mark_estimates = fields.Boolean(required=True)
    timezone = fields.String(
        allow_none=True, metadata={"description": "IANA zone used for the feed's today"}
    )


class CalendarFeedCreateSchema(Schema):
    """Optional body of POST /users/me/calendar-feed."""

    timezone = fields.String(
        allow_none=True,
        validate=validate.Length(max=64),
        metadata={"description": "IANA zone, e.g. from Intl.DateTimeFormat()"},
    )


class CalendarFeedCreatedSchema(Schema):
    """Returned once when a feed URL is created."""

    path = fields.String(
        required=True,
        metadata={"description": "Feed path; prefix with your site origin. Shown once"},
    )
    url = fields.String(
        allow_none=True,
        metadata={"description": "Absolute URL, only when PUBLIC_BASE_URL is set"},
    )


class CalendarFeedUpdateSchema(Schema):
    label = fields.String(
        allow_none=True,
        validate=[validate.Length(max=40), _no_control_chars],
        metadata={"description": "Blank or null resets to the discreet default"},
    )
    include_fertile = fields.Boolean()
    fertile_label = fields.String(
        allow_none=True,
        validate=[validate.Length(max=40), _no_control_chars],
        metadata={"description": "Title of fertile events; blank/null = like periods"},
    )
    mark_estimates = fields.Boolean(
        metadata={"description": "Append a discreet ~ to predicted events"}
    )
    timezone = fields.String(
        allow_none=True,
        validate=validate.Length(max=64),
        metadata={"description": "IANA zone; blank/null = server (UTC) date"},
    )
