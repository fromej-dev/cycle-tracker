from apiflask import Schema, fields, validators


class SymptomRangeQuerySchema(Schema):
    """Inclusive date range of symptom days to return."""

    start = fields.Date(required=True)
    end = fields.Date(required=True)


class SymptomDayInputSchema(Schema):
    """Replace one day's symptoms: preset keys plus free-text ones."""

    symptoms = fields.List(
        fields.String(validate=validators.Length(max=40)),
        load_default=list,
        validate=validators.Length(max=50),
    )
    custom = fields.List(
        fields.String(validate=validators.Length(max=200)),
        load_default=list,
        validate=validators.Length(max=50),
    )


class SymptomDaySchema(Schema):
    date = fields.Date()
    symptoms = fields.List(fields.String())
    custom = fields.List(fields.String())


class SymptomSuggestionsSchema(Schema):
    frequent = fields.List(fields.String())
    recent_custom = fields.List(fields.String())
