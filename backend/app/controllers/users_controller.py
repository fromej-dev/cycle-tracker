from apiflask import APIBlueprint, EmptySchema, abort
from flask import current_app, request
from flask_jwt_extended import current_user, jwt_required

from app.schemas import UserSchema
from app.schemas.user import (
    CalendarFeedCreatedSchema,
    CalendarFeedSchema,
    CalendarFeedUpdateSchema,
    ChangePasswordSchema,
    UserUpdateSchema,
)
from app.services import UserService
from app.services.calendar_service import CalendarService

users_bp = APIBlueprint("users", __name__, url_prefix="/users")


@users_bp.route("/me")
@users_bp.output(UserSchema)
@jwt_required()
def get_own_user():
    return current_user


@users_bp.route("/me", methods=["PATCH"])
@users_bp.input(UserUpdateSchema)
@users_bp.output(UserSchema)
@jwt_required()
def patch_own_user(json_data: dict):
    user = None
    if "username" in json_data:
        user = UserService.get_user_by_username(json_data.get("username"))
    if "email" in json_data:
        user = UserService.get_user_by_email(json_data.get("email"))
    if user and user != current_user:
        abort(400, message="A user like that already exists")
    return UserService.update_user(current_user, json_data)


@users_bp.route("/me", methods=["DELETE"])
@users_bp.output(EmptySchema, 204)
@jwt_required()
def delete_own_user():
    return UserService.delete_user(current_user)


@users_bp.route("me/change-password", methods=["POST"])
@users_bp.input(ChangePasswordSchema, arg_name="data")
@users_bp.output(EmptySchema, 200)
@jwt_required()
def change_own_password(data):
    if not current_user.check_password(data["current_password"]):
        abort(
            400,
            message="Current password does not match",
            detail={"error": "password error"},
        )
    UserService.update_password(current_user, data["new_password"])
    return


@users_bp.route("/me/calendar-feed", methods=["GET"])
@users_bp.output(CalendarFeedSchema)
@users_bp.doc(security="bearerAuth")
@jwt_required()
def get_calendar_feed_settings():
    """Calendar feed settings. The token is never returned here."""
    return CalendarService.settings(current_user)


@users_bp.route("/me/calendar-feed", methods=["POST"])
@users_bp.output(CalendarFeedCreatedSchema, 201)
@users_bp.doc(security="bearerAuth")
@jwt_required()
def create_calendar_feed():
    """
    Create (or rotate) the private calendar feed URL.
    The URL is returned only once; any previous URL stops working immediately.
    """
    body = request.get_json(silent=True)
    tz = body.get("timezone") if isinstance(body, dict) else None
    if tz is not None and tz != "" and not CalendarService.valid_timezone(str(tz)):
        abort(
            422,
            message="Validation error",
            detail={"json": {"timezone": ["Unknown IANA time zone."]}},
        )
    if tz:
        CalendarService.update_settings(current_user, {"timezone": str(tz)})
    token = CalendarService.rotate_token(current_user)
    path = CalendarService.feed_path(token)
    # The Host header is attacker-influenced and proxies hide the public scheme, so
    # an absolute URL is only produced from explicit configuration. Otherwise the
    # client prefixes its own origin.
    base = current_app.config.get("PUBLIC_BASE_URL")
    response = {"path": path, "url": base.rstrip("/") + path if base else None}
    return response, 201, {"Cache-Control": "no-store"}


@users_bp.route("/me/calendar-feed", methods=["PATCH"])
@users_bp.input(CalendarFeedUpdateSchema, arg_name="data")
@users_bp.output(CalendarFeedSchema)
@users_bp.doc(security="bearerAuth")
@jwt_required()
def update_calendar_feed(data: dict):
    """Update the event label, fertile opt-in, estimate marker or time zone."""
    tz = (data.get("timezone") or "").strip()
    if tz and not CalendarService.valid_timezone(tz):
        abort(
            422,
            message="Validation error",
            detail={"json": {"timezone": ["Unknown IANA time zone."]}},
        )
    return CalendarService.update_settings(current_user, data)


@users_bp.route("/me/calendar-feed", methods=["DELETE"])
@users_bp.output(EmptySchema, 204)
@users_bp.doc(security="bearerAuth")
@jwt_required()
def revoke_calendar_feed():
    """Revoke the feed URL (it returns 404 afterwards)."""
    CalendarService.revoke_token(current_user)
    return None
