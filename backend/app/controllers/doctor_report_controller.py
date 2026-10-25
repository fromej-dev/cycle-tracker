from apiflask import APIBlueprint
from flask import Response, jsonify
from flask_jwt_extended import current_user, jwt_required

from app.controllers.report_controller import client_today
from app.models import Period
from app.schemas.integrations import DoctorQuerySchema
from app.services.doctor_report_service import DoctorReportService, jsonable

doctor_bp = APIBlueprint("doctor_report", __name__, url_prefix="/reports")


def _build(query: dict) -> dict:
    rows = (
        Period.query.filter_by(user_id=current_user.id)
        .order_by(Period.start_date)
        .all()
    )
    return DoctorReportService.build(
        current_user,
        [(p.start_date, p.end_date) for p in rows],
        months=query["months"],
        today=client_today(query),
        include_name=query["include_name"],
    )


@doctor_bp.route("/doctor", methods=["GET"])
@doctor_bp.input(DoctorQuerySchema, location="query", arg_name="query")
@doctor_bp.doc(
    security="bearerAuth",
    summary="Printable report for a doctor (self-contained HTML)",
    responses={200: "text/html"},
)
@jwt_required()
def doctor_report_html(query: dict):
    """Self-contained printable page: no external assets, works offline."""
    html = DoctorReportService.render_html(_build(query))
    resp = Response(html, mimetype="text/html")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; "
        "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@doctor_bp.route("/doctor.json", methods=["GET"])
@doctor_bp.input(DoctorQuerySchema, location="query", arg_name="query")
@doctor_bp.doc(security="bearerAuth", summary="Same data as /reports/doctor as JSON")
@jwt_required()
def doctor_report_json(query: dict):
    resp = jsonify(jsonable(_build(query)))
    resp.headers["Cache-Control"] = "no-store"
    return resp
