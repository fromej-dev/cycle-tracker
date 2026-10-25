from apiflask import APIBlueprint, EmptySchema, abort
from flask_jwt_extended import current_user, jwt_required

from app.controllers.report_controller import client_today
from app.schemas.date_check import PlannedEventInputSchema, PlannedEventSchema
from app.schemas.report import TodayQuerySchema
from app.services.planned_event_service import PlannedEventService
from app.utils.exceptions import NotFoundError, ValidationError

events_bp = APIBlueprint("events", __name__, url_prefix="/events")


def _not_found(e: NotFoundError):
    return abort(404, message=str(e), detail={"error": str(e)})


def _invalid(e: ValidationError):
    """Same 422 shape as schema validation: {"message", "detail": {<location>: ...}}.

    Locations are accurate: body problems under ``json`` (this module), query-string
    problems (``start``/``end``/``today``) under ``query`` (Date Check, ``today``)."""
    return abort(422, message="Validation error", detail={"json": e.payload})


@events_bp.route("", methods=["GET"])
@jwt_required()
@events_bp.input(TodayQuerySchema, location="query", arg_name="query")
@events_bp.output(PlannedEventSchema(many=True))
@events_bp.doc(security="bearerAuth")
def list_events(query: dict):
    """
    List the user's planned events (trips etc.) with live period odds.
    Upcoming and ongoing events come first (soonest first), then past events.
    """
    return PlannedEventService.list_for_user(current_user.id, client_today(query))


@events_bp.route("/<int:event_id>", methods=["GET"])
@jwt_required()
@events_bp.input(TodayQuerySchema, location="query", arg_name="query")
@events_bp.output(PlannedEventSchema)
@events_bp.doc(security="bearerAuth")
def get_event(event_id: int, query: dict):
    """One of the user's planned events with its live period odds."""
    try:
        return PlannedEventService.get_for_user(
            current_user.id, event_id, client_today(query)
        )
    except NotFoundError as e:
        return _not_found(e)


@events_bp.route("", methods=["POST"])
@jwt_required()
@events_bp.input(TodayQuerySchema, location="query", arg_name="query")
@events_bp.input(PlannedEventInputSchema, arg_name="data")
@events_bp.output(PlannedEventSchema, 201)
@events_bp.doc(security="bearerAuth")
def create_event(query: dict, data: dict):
    """Create a planned event (max 60 days, start at most 366 days ahead)."""
    try:
        return PlannedEventService.create(current_user.id, data, client_today(query))
    except ValidationError as e:
        return _invalid(e)


@events_bp.route("/<int:event_id>", methods=["PUT"])
@jwt_required()
@events_bp.input(TodayQuerySchema, location="query", arg_name="query")
@events_bp.input(PlannedEventInputSchema, arg_name="data")
@events_bp.output(PlannedEventSchema)
@events_bp.doc(security="bearerAuth")
def update_event(event_id: int, query: dict, data: dict):
    """Replace name and dates of one of the user's events."""
    try:
        return PlannedEventService.update(
            current_user.id, event_id, data, client_today(query)
        )
    except NotFoundError as e:
        return _not_found(e)
    except ValidationError as e:
        return _invalid(e)


@events_bp.route("/<int:event_id>", methods=["DELETE"])
@jwt_required()
@events_bp.output(EmptySchema, status_code=204)
@events_bp.doc(security="bearerAuth")
def delete_event(event_id: int):
    """Delete one of the user's events."""
    try:
        PlannedEventService.delete(current_user.id, event_id)
    except NotFoundError as e:
        return _not_found(e)
    return None
