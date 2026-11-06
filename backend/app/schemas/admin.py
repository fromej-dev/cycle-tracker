from apiflask import Schema, fields


class _Users(Schema):
    total = fields.Integer()
    new_7d = fields.Integer()
    new_30d = fields.Integer()
    active_30d = fields.Integer(
        metadata={"description": "Logged or changed something in the last 30 days"}
    )


class _Month(Schema):
    month = fields.String(metadata={"description": "YYYY-MM"})
    count = fields.Integer()


class _Data(Schema):
    periods = fields.Integer()
    ongoing_periods = fields.Integer()
    symptom_days = fields.Integer()
    planned_events = fields.Integer()
    webhooks = fields.Integer()
    webhooks_active = fields.Integer()
    webhooks_auto_disabled = fields.Integer()


class _Features(Schema):
    periods = fields.Integer()
    symptoms = fields.Integer()
    planned_events = fields.Integer()
    webhooks = fields.Integer()
    calendar_feed = fields.Integer()
    partner_share = fields.Integer()
    home_assistant = fields.Integer()


class _Cycles(Schema):
    users_with_cycles = fields.Integer()
    median_cycle_length = fields.Float(
        allow_none=True, metadata={"description": "null below min_group_size people"}
    )
    users_with_period_length = fields.Integer()
    median_period_length = fields.Float(allow_none=True)


class _Symptom(Schema):
    key = fields.String()
    users = fields.Integer()
    share = fields.Float(metadata={"description": "Share of people who log symptoms"})


class _Symptoms(Schema):
    users_logging = fields.Integer()
    top = fields.List(fields.Nested(_Symptom))


class AdminStatsSchema(Schema):
    """Aggregates only: no names, e-mail addresses, ids or per-person records."""

    generated_at = fields.DateTime()
    min_group_size = fields.Integer()
    users = fields.Nested(_Users)
    signups_by_month = fields.List(fields.Nested(_Month))
    data = fields.Nested(_Data)
    features = fields.Nested(_Features)
    cycles = fields.Nested(_Cycles)
    symptoms = fields.Nested(_Symptoms)
