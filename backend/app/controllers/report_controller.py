import datetime

from apiflask import APIBlueprint, abort
from flask_jwt_extended import current_user, get_jwt_identity, jwt_required

from app.models import User
from app.schemas import CycleStatsSchema, PeriodStatsSchema
from app.schemas.date_check import DateCheckQuerySchema, DateCheckSchema
from app.schemas.report import (
    CycleContextSchema,
    ForecastSchema,
    OvulationWindowSchema,
    PredictionSchema,
    TodayQuerySchema,
)
from app.services import ForecastService, ReportService
from app.services.date_check_service import DateCheckService
from app.utils.exceptions import ValidationError

report_bp = APIBlueprint("reports", __name__, url_prefix="/reports")


def client_today(query: dict) -> datetime.date | None:
    """The client's local date (``?today=YYYY-MM-DD``), if sent.

    Servers and users live in different time zones, so "today" is the client's. It
    must be within one day of the server date to rule out clock errors.
    """
    value = query.get("today")
    if value is None:
        return None
    if abs((value - datetime.date.today()).days) > 1:
        abort(
            422,
            message="Validation error",
            detail={"query": {"today": ["must be within one day of the server date"]}},
        )
    return value


@report_bp.route("/period-stats", methods=["GET"])
@report_bp.output(PeriodStatsSchema)
@jwt_required()
def get_period_statistics():
    """
    Get statistics about the logged-in user's period durations.
    Calculates min, max, and average duration based on completed periods.
    ---
    Security: JWT Bearer Token required.
    Responses:
        200: Statistics returned successfully.
        401: Unauthorized.
    """
    user_id = get_jwt_identity()
    return ReportService.get_period_stats(user_id)


@report_bp.route("/cycle-stats", methods=["GET"])
@report_bp.output(CycleStatsSchema)
@jwt_required()
def get_cycle_statistics():
    """
    Get statistics about the logged-in user's cycle lengths.
    Calculates min, max, and average cycle length (start date to next start date).
    ---
    Security: JWT Bearer Token required.
    Responses:
        200: Statistics returned successfully.
        401: Unauthorized.
    """
    user_id = get_jwt_identity()
    return ReportService.get_cycle_stats(user_id)


@report_bp.route("/predicted-next-period", methods=["GET"])
@report_bp.input(TodayQuerySchema, location="query", arg_name="query")
@report_bp.output(PredictionSchema)
@jwt_required()
def get_predicted_next_period(query: dict):
    """
    Most likely next period start (the same value as /reports/forecast).
    """
    user_id = get_jwt_identity()
    date = ReportService.get_predicted_next_period(user_id, client_today(query))
    if not date:
        return {"predicted_start": None}
    return {"predicted_start": date}


@report_bp.route("/ovulation-window", methods=["GET"])
@report_bp.input(TodayQuerySchema, location="query", arg_name="query")
@report_bp.output(OvulationWindowSchema)
@jwt_required()
def get_ovulation_window(query: dict):
    """
    Estimate ovulation date and fertile window based on predicted next period.
    """
    user_id = get_jwt_identity()
    window = ReportService.get_estimated_ovulation(user_id, client_today(query))
    if not window:
        return {}
    return window


@report_bp.route("/cycle-context", methods=["GET"])
@report_bp.input(TodayQuerySchema, location="query", arg_name="query")
@report_bp.output(CycleContextSchema)
@jwt_required()
def get_cycle_context(query: dict):
    """
    Provide a comprehensive snapshot of the user's current cycle context.
    Includes status (in period or not), cycle day, progress, ovulation estimate, etc.
    """
    user_id = get_jwt_identity()
    context = ReportService.get_cycle_context(user_id, client_today(query))
    if not context:
        return {}  # Empty object if no periods exist yet
    return context


@report_bp.route("/forecast", methods=["GET"])
@report_bp.input(TodayQuerySchema, location="query", arg_name="query")
@report_bp.output(ForecastSchema)
@jwt_required()
def get_forecast(query: dict):
    """
    Probabilistic forecast of the next period start.
    Returns the most likely date, 50% and 80% intervals, per-day probabilities of
    starting, bleeding and being fertile for the next ~45 days, and a confidence
    label. The forecast is conditioned on today: if the period is late, the
    probability mass shifts forward.
    """
    user_id = get_jwt_identity()
    return ForecastService.forecast(user_id, client_today(query))


@report_bp.route("/date-check", methods=["GET"])
@jwt_required()
@report_bp.input(DateCheckQuerySchema, location="query", arg_name="query")
@report_bp.output(DateCheckSchema)
@report_bp.doc(security="bearerAuth")
def get_date_check(query: dict):
    """
    Chance of a period during a date range ("Lisbon trip, 3-10 May").
    Returns the probability of at least one bleeding day in the range, per-day
    probabilities, the most likely days and the forecast confidence. Overdue or
    brand-new users get status "overdue"/"no_data" with a null probability.
    Range: max 60 days, start at most 366 days ahead; past dates are allowed.
    """
    try:
        return DateCheckService.check(
            current_user.id, query["start"], query["end"], client_today(query)
        )
    except ValidationError as e:
        return abort(422, message="Validation error", detail={"query": e.payload})


@report_bp.route("/general", methods=["GET"])
def get_app_stats():
    return {"number_of_users": User.query.count()}
