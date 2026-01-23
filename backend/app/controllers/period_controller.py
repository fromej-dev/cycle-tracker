from apiflask import APIBlueprint, EmptySchema, abort
from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.schemas import PeriodCreateSchema, PeriodSchema, PeriodUpdateSchema
from app.services import PeriodService
from app.utils.exceptions import NotFoundError, PeriodLogicError, ValidationError

period_bp = APIBlueprint("periods", __name__, url_prefix="/periods")


@period_bp.route("", methods=["POST"])
@period_bp.input(PeriodCreateSchema, arg_name="validated_data")
@period_bp.output(PeriodSchema, 201)
@period_bp.doc(security="bearer")
@jwt_required()
def create_period(validated_data: dict):
    """
    Record the start of a new period for the logged-in user.
    ---
    Security: JWT Bearer Token required.
    Body (application/json):
        Required: start_date (YYYY-MM-DD)
    Responses:
        201: Period recorded successfully. Returns the created period data.
        400: Invalid data or period logic error.
        401: Unauthorized (missing or invalid token).
        422: Validation error.
    """
    user_id = get_jwt_identity()
    try:
        return PeriodService.record_period_start(user_id, validated_data["start_date"])
    except PeriodLogicError as e:
        return abort(e.status_code, message=str(e), detail={"error": str(e)})
    except ValidationError as e:
        return abort(e.status_code, message=str(e), detail={"error": str(e)})


@period_bp.route("/<int:period_id>", methods=["PUT"])
@period_bp.input(PeriodUpdateSchema, arg_name="validated_data")
@period_bp.output(PeriodSchema)
@period_bp.doc(security="bearerAuth")
@jwt_required()
def update_period(validated_data: dict, period_id: int):
    """
    Update the end date of a specific period for the logged-in user.
    ---
    Security: JWT Bearer Token required.
    Path Parameters:
        period_id: ID of the period to update.
    Body (application/json):
        Required: end_date (YYYY-MM-DD)
    Responses:
        200: Period updated successfully. Returns the updated period data.
        400: Invalid data or period logic error (e.g., end_date < start_date, already has end date).
        401: Unauthorized.
        404: Period not found for this user.
        422: Validation error.
    """
    user_id = get_jwt_identity()
    try:
        # Additional validation might be needed here or in service:
        # Ensure end_date >= period.start_date
        # The service layer is often a better place for this kind of logic check
        return PeriodService.update_period_end(
            user_id, period_id, validated_data["end_date"]
        )
    except (PeriodLogicError, NotFoundError, ValidationError) as e:
        return abort(e.status_code, message=str(e), detail={"error": str(e)})


@period_bp.route("", methods=["GET"])
@period_bp.output(PeriodSchema(many=True))
@period_bp.doc(security="bearerAuth")
@jwt_required()
def get_periods():
    """
    Get a list of all periods for the logged-in user.
    Supports pagination via query parameters 'page' and 'per_page'.
    ---
    Security: JWT Bearer Token required.
    Query Parameters:
        page (int, optional): Page number (default: 1).
        per_page (int, optional): Items per page (default: 10).
    Responses:
        200: List of periods returned successfully.
        401: Unauthorized.
    """
    user_id = get_jwt_identity()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    return PeriodService.get_all_periods_for_user(user_id, page=page, per_page=per_page)


@period_bp.route("/<int:period_id>", methods=["GET"])
@period_bp.output(PeriodSchema)
@period_bp.doc(security="bearerAuth")
@jwt_required()
def get_period(period_id: int):
    """
    Get details of a specific period for the logged-in user.
    ---
    Security: JWT Bearer Token required.
    Path Parameters:
        period_id: ID of the period to retrieve.
    Responses:
        200: Period details returned successfully.
        401: Unauthorized.
        404: Period not found for this user.
    """
    user_id = get_jwt_identity()
    period = PeriodService.get_period_by_id_for_user(user_id, period_id)
    if not period:
        return abort(
            404,
            message=f"Period with ID {period_id} not found.",
            detail={"error": f"Period with ID {period_id} not found."},
        )
    return period


@period_bp.route("/active", methods=["GET"])
@period_bp.output(PeriodSchema)
@period_bp.doc(security="bearerAuth")
@jwt_required()
def get_active_period():
    """
    Get last active period for the logged-in user.
    ---
    Security: JWT Bearer Token required.
    Responses:
        200: Period details returned successfully.
        401: Unauthorized.
        404: Period not found for this user.
    """
    user_id = get_jwt_identity()
    return PeriodService.get_active_period_for_user(user_id)


@period_bp.route("/<int:period_id>", methods=["DELETE"])
@period_bp.output(EmptySchema, status_code=204)
@period_bp.doc(security="bearerAuth")
@jwt_required()
def delete_period(period_id: int):
    """
    Delete a specific period for the logged-in user.
    ---
    Security: JWT Bearer Token required.
    Path Parameters:
        period_id: ID of the period to delete.
    Responses:
        204: Period deleted successfully (No Content).
        401: Unauthorized.
        404: Period not found for this user.
        400: Error during deletion.
    """
    user_id = get_jwt_identity()
    try:
        deleted = PeriodService.delete_period_for_user(user_id, period_id)
        if deleted:
            return
        else:
            # Should be caught by NotFoundError, but as a fallback
            return abort(
                404,
                message=f"Period with ID {period_id} not found.",
                detail={"error": f"Period with ID {period_id} not found."},
            )
    except NotFoundError as e:
        return abort(e.status_code, message=str(e), detail={"error": str(e)})
    except PeriodLogicError as e:  # Catch potential DB errors during delete
        return abort(e.status_code, message=str(e), detail={"error": str(e)})
