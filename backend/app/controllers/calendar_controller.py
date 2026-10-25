from apiflask import APIBlueprint, abort
from flask import Response, request

from app.services.calendar_service import CalendarService

calendar_bp = APIBlueprint("calendar", __name__, url_prefix="/calendar")


@calendar_bp.route("/<token>.ics", methods=["GET"])
@calendar_bp.doc(
    summary="Private ICS calendar feed",
    responses={200: "text/calendar feed", 404: "Unknown or revoked token"},
)
def get_calendar_feed(token: str):
    """
    Subscribe-able iCalendar feed of predicted periods (and, if enabled, fertile
    windows). The secret token in the URL is the only credential; no JWT is used so
    Google/Apple/Outlook calendars can poll it.
    """
    user = CalendarService.find_user_by_token(token)
    if user is None:
        abort(404, message="Not found")
    # HEAD (and any non-GET) must never write
    body = CalendarService.build_ics(user, persist=request.method == "GET")
    response = Response(body, mimetype="text/calendar")
    response.headers["Content-Type"] = "text/calendar; charset=utf-8"
    response.headers["Content-Disposition"] = 'inline; filename="calendar.ics"'
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
