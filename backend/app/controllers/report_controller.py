from apiflask import APIBlueprint
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models import User
from app.schemas import CycleStatsSchema, PeriodStatsSchema
from app.schemas.report import (
    CycleContextSchema,
    ForecastSchema,
    OvulationWindowSchema,
    PredictionSchema,
)
from app.services import ForecastService, ReportService

report_bp = APIBlueprint("reports", __name__, url_prefix="/reports")


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
@report_bp.output(PredictionSchema)
@jwt_required()
def get_predicted_next_period():
    """
    Predict the user's next period start date using average cycle length.
    """
    user_id = get_jwt_identity()
    date = ReportService.get_predicted_next_period(user_id)
    if not date:
        return {"predicted_start": None}
    return {"predicted_start": date}


@report_bp.route("/ovulation-window", methods=["GET"])
@report_bp.output(OvulationWindowSchema)
@jwt_required()
def get_ovulation_window():
    """
    Estimate ovulation date and fertile window based on predicted next period.
    """
    user_id = get_jwt_identity()
    window = ReportService.get_estimated_ovulation(user_id)
    if not window:
        return {}
    return window


@report_bp.route("/cycle-context", methods=["GET"])
@report_bp.output(CycleContextSchema)
@jwt_required()
def get_cycle_context():
    """
    Provide a comprehensive snapshot of the user's current cycle context.
    Includes status (in period or not), cycle day, progress, ovulation estimate, etc.
    """
    user_id = get_jwt_identity()
    context = ReportService.get_cycle_context(user_id)
    if not context:
        return {}  # Empty object if no periods exist yet
    return context


@report_bp.route("/forecast", methods=["GET"])
@report_bp.output(ForecastSchema)
@jwt_required()
def get_forecast():
    """
    Probabilistic forecast of the next period start.
    Returns the most likely date, 50% and 80% intervals, per-day probabilities of
    starting, bleeding and being fertile for the next ~45 days, and a confidence
    label. The forecast is conditioned on today: if the period is late, the
    probability mass shifts forward.
    """
    user_id = get_jwt_identity()
    return ForecastService.forecast(user_id)


@report_bp.route("/general", methods=["GET"])
def get_app_stats():
    return {"number_of_users": User.query.count()}
