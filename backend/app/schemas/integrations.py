from apiflask import Schema, fields
from marshmallow import ValidationError, validate

from app.services.partner_share_service import MAX_WINDOW, MIN_WINDOW
from app.services.webhook_service import EVENTS
from app.utils import ics


def _plain(value: str | None) -> None:
    if value and ics.has_forbidden_chars(value):
        raise ValidationError("Cannot contain control, bidi/format or separator chars.")


class DoctorQuerySchema(Schema):
    months = fields.Integer(load_default=12, validate=validate.OneOf([6, 12, 24]))
    today = fields.Date(load_default=None)
    include_name = fields.Boolean(load_default=False)


class ShareScopeSchema(Schema):
    fertile = fields.Boolean(
        metadata={"description": "Also show a coarse fertile hint (default false)"}
    )
    window_days = fields.Integer(
        validate=validate.Range(min=MIN_WINDOW, max=MAX_WINDOW),
        metadata={"description": "Show 'period likely soon' within this many days"},
    )


class PartnerShareCreateSchema(Schema):
    scope = fields.Nested(ShareScopeSchema, load_default=dict)
    name = fields.String(allow_none=True, validate=[validate.Length(max=40), _plain])


class PartnerShareSchema(Schema):
    enabled = fields.Boolean(required=True)
    name = fields.String(required=True)
    scope = fields.Nested(ShareScopeSchema, required=True)


class PathCreatedSchema(Schema):
    path = fields.String(required=True, metadata={"description": "Shown only once"})
    url = fields.String(allow_none=True)


class HomeAssistantSchema(Schema):
    enabled = fields.Boolean(required=True)
    include_fertile = fields.Boolean(required=True)


class HomeAssistantInSchema(Schema):
    include_fertile = fields.Boolean()


class WebhookCreateSchema(Schema):
    url = fields.String(required=True, validate=validate.Length(min=8, max=500))
    events = fields.List(
        fields.String(validate=validate.OneOf(list(EVENTS))),
        validate=validate.Length(min=1, max=len(EVENTS)),
    )


class WebhookUpdateSchema(Schema):
    url = fields.String(validate=validate.Length(min=8, max=500))
    events = fields.List(
        fields.String(validate=validate.OneOf(list(EVENTS))),
        validate=validate.Length(min=1, max=len(EVENTS)),
    )
    active = fields.Boolean()


class WebhookSchema(Schema):
    id = fields.Integer(required=True)
    url = fields.String(required=True)
    events = fields.List(fields.String(), required=True)
    active = fields.Boolean(required=True)
    last_status = fields.Integer(allow_none=True)
    last_attempt_at = fields.DateTime(allow_none=True)
    failures = fields.Integer(required=True)
    secret = fields.String(
        dump_only=True, metadata={"description": "Present only when created/rotated"}
    )
