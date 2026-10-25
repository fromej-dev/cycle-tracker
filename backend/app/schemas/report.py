from apiflask import Schema, fields


class PeriodStatsSchema(Schema):
    """Schema for period statistics report."""

    count = fields.Integer(
        required=True,
    )
    min_duration = fields.Integer(
        allow_none=True,
    )
    max_duration = fields.Integer(
        allow_none=True,
    )
    average_duration = fields.Float(
        allow_none=True,
    )


class CycleStatsSchema(Schema):
    """Schema for cycle statistics report."""

    count = fields.Integer(
        required=True,
    )
    min_length = fields.Integer(
        allow_none=True,
    )
    max_length = fields.Integer(
        allow_none=True,
    )
    average_length = fields.Float(
        allow_none=True,
    )


class PredictionSchema(Schema):
    predicted_start = fields.Date(required=True)


class FertileWindowSchema(Schema):
    start = fields.Date(allow_none=True)
    end = fields.Date(allow_none=True)


class CycleContextSchema(Schema):
    status = fields.String(required=True)  # "period" or "waiting"
    current_period_id = fields.Integer(allow_none=True)
    days_running = fields.Integer(allow_none=True)
    cycle_day = fields.Integer(allow_none=True)
    cycle_length = fields.Float(allow_none=True)
    progress_percent = fields.Float(allow_none=True)
    predicted_start = fields.Date(allow_none=True)
    days_until_next_period = fields.Integer(allow_none=True)
    ovulation_date = fields.Date(allow_none=True)
    fertile_window = fields.Nested(FertileWindowSchema, required=True)
    is_today_ovulation = fields.Boolean(required=True)
    is_in_fertile_window = fields.Boolean(required=True)
    is_late = fields.Boolean(load_default=False)
    confidence = fields.String(allow_none=True)


class OvulationWindowSchema(Schema):
    ovulation_date = fields.Date(required=True)
    fertile_window_start = fields.Date(required=True)
    fertile_window_end = fields.Date(required=True)


class DateIntervalSchema(Schema):
    start = fields.Date(allow_none=True)
    end = fields.Date(allow_none=True)


class ForecastDaySchema(Schema):
    date = fields.Date(required=True)
    p_start = fields.Float(required=True)
    p_bleeding = fields.Float(required=True)
    p_fertile = fields.Float(required=True)


class ForecastFertileWindowSchema(Schema):
    start = fields.Date(allow_none=True)
    end = fields.Date(allow_none=True)
    ovulation_date = fields.Date(allow_none=True)
    ovulation_interval_80 = fields.Nested(DateIntervalSchema, allow_none=True)


class SecondaryWindowSchema(Schema):
    start = fields.Date(allow_none=True)
    end = fields.Date(allow_none=True)
    probability = fields.Float(allow_none=True)


class ForecastSchema(Schema):
    """Probabilistic forecast of the next period start."""

    most_likely_start = fields.Date(allow_none=True)
    median_start = fields.Date(allow_none=True)
    secondary_window = fields.Nested(
        SecondaryWindowSchema,
        allow_none=True,
        metadata={
            "description": "Another distinct possibility when the forecast is multimodal "
            "(e.g. a forgotten log: roughly two cycles); most_likely_start is then the "
            "median and the intervals are contiguous around it."
        },
    )
    interval_50 = fields.Nested(DateIntervalSchema, allow_none=True)
    interval_80 = fields.Nested(DateIntervalSchema, allow_none=True)
    probability_next_3_days = fields.Float(allow_none=True)
    confidence = fields.String(
        required=True,
        metadata={"description": "learning, regular, variable or irregular"},
    )
    predictive_sd_days = fields.Float(allow_none=True)
    cycles_used = fields.Integer(required=True)
    days = fields.List(fields.Nested(ForecastDaySchema), required=True)
    fertile_window = fields.Nested(ForecastFertileWindowSchema, allow_none=True)
    is_late = fields.Boolean(required=True)


class TodayQuerySchema(Schema):
    """Optional client-local date; forecasts are conditioned on it."""

    today = fields.Date(load_default=None)
