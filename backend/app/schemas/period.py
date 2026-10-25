from apiflask import Schema, fields
from marshmallow import ValidationError, validates_schema


class PeriodSchema(Schema):
    """Schema for serializing/deserializing Period data."""

    # Explicit field definitions for better control and validation
    id = fields.Integer(dump_only=True)
    user_id = fields.Integer(dump_only=True)  # Don't allow user_id in request body
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=False, allow_none=True)  # Optional
    created_at = fields.DateTime(dump_only=True)
    duration = fields.Integer(dump_only=True)  # Calculated property

    @validates_schema
    def validate_dates(self, data, **kwargs):
        """Ensure end_date is not before start_date."""
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and end < start:
            raise ValidationError(
                "End date cannot be before start date.", field_name="end_date"
            )


class PeriodCreateSchema(Schema):
    """Schema specifically for creating a new period (only start_date)."""

    start_date = fields.Date(required=True)


class PeriodUpdateSchema(Schema):
    """Schema specifically for updating a period (only end_date).

    A null end_date reopens the period (used to undo "period ended").
    """

    end_date = fields.Date(required=True, allow_none=True)

    @validates_schema
    def validate_end_date(self, data, **kwargs):
        # This requires context to access the original period's start_date
        # Or, this validation should be done in the service layer after fetching the period
        # Service layer approach is generally cleaner for cross-field validation on updates
        pass
