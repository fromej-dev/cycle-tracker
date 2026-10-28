import datetime

from apiflask import APIBlueprint, abort
from flask_jwt_extended import current_user, jwt_required

from app.controllers.report_controller import client_today
from app.schemas.report import TodayQuerySchema
from app.schemas.symptom import (
    SymptomDayInputSchema,
    SymptomDaySchema,
    SymptomRangeQuerySchema,
    SymptomSuggestionsSchema,
)
from app.services.symptom_service import SymptomService
from app.utils.exceptions import ValidationError

symptoms_bp = APIBlueprint("symptoms", __name__, url_prefix="/symptoms")


@symptoms_bp.route("", methods=["GET"])
@jwt_required()
@symptoms_bp.input(SymptomRangeQuerySchema, location="query", arg_name="query")
@symptoms_bp.output(SymptomDaySchema(many=True))
@symptoms_bp.doc(security="bearerAuth")
def list_symptoms(query: dict):
    """Logged symptom days between ``start`` and ``end`` (inclusive, max 400 days)."""
    try:
        return SymptomService.list_range(current_user.id, query["start"], query["end"])
    except ValidationError as e:
        return abort(422, message="Validation error", detail={"query": e.payload})


@symptoms_bp.route("/suggestions", methods=["GET"])
@jwt_required()
@symptoms_bp.input(TodayQuerySchema, location="query", arg_name="query")
@symptoms_bp.output(SymptomSuggestionsSchema)
@symptoms_bp.doc(security="bearerAuth")
def symptom_suggestions(query: dict):
    """The user's most logged symptoms and recently used own symptoms."""
    return SymptomService.suggestions(current_user.id, client_today(query))


@symptoms_bp.route("/<string:day>", methods=["PUT"])
@jwt_required()
@symptoms_bp.input(TodayQuerySchema, location="query", arg_name="query")
@symptoms_bp.input(SymptomDayInputSchema, arg_name="data")
@symptoms_bp.output(SymptomDaySchema)
@symptoms_bp.doc(security="bearerAuth")
def save_symptoms(day: str, query: dict, data: dict):
    """Replace the symptoms of one day (YYYY-MM-DD); an empty body clears the day."""
    try:
        date = datetime.date.fromisoformat(day)
    except ValueError:
        return abort(404, message="Not a date.", detail={"error": "Not a date."})
    try:
        return SymptomService.save_day(
            current_user.id,
            date,
            data["symptoms"],
            data["custom"],
            client_today(query),
        )
    except ValidationError as e:
        return abort(422, message="Validation error", detail={"json": e.payload})
