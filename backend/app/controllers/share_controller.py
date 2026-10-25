"""Credential-less, secret-URL endpoints: partner page and Home Assistant state."""

from apiflask import APIBlueprint
from flask import Response, jsonify

from app.models import User
from app.services.headsup_service import HeadsUpService, lookup_user
from app.services.partner_share_service import PartnerShareService

share_bp = APIBlueprint("share", __name__)

_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
}


def _harden(response: Response) -> Response:
    for k, v in _HEADERS.items():
        response.headers[k] = v
    return response


def _missing() -> Response:
    resp = jsonify({"error": "Resource not found."})
    resp.status_code = 404
    return _harden(resp)


@share_bp.route("/share/<token>", methods=["GET"])
@share_bp.doc(hide=True)
def partner_page(token: str):
    user = PartnerShareService.find_user(token)
    if user is None:
        return _missing()
    html = PartnerShareService.render_html(PartnerShareService.view(user))
    resp = Response(html, mimetype="text/html")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    )
    return _harden(resp)


@share_bp.route("/share/<token>.json", methods=["GET"])
@share_bp.doc(hide=True)
def partner_json(token: str):
    user = PartnerShareService.find_user(token)
    if user is None:
        return _missing()
    return _harden(jsonify(PartnerShareService.view(user)))


@share_bp.route("/ha/<token>/state", methods=["GET"])
@share_bp.doc(
    summary="Home Assistant RESTful sensor state",
    responses={200: "state + attributes", 404: "Unknown or revoked token"},
)
def home_assistant_state(token: str):
    """`{"state": "period"|"expected_soon"|"none", "attributes": {...}}`."""
    user = lookup_user(User.ha_token_hash, token)
    if user is None:
        return _missing()
    hu = HeadsUpService.compute(user, 7, bool(user.ha_include_fertile))
    attrs = {"days_until_likely_start": hu["days_bucket"]}
    if user.ha_include_fertile:
        attrs["fertile_window"] = hu["fertile"]
    return _harden(jsonify({"state": hu["state"], "attributes": attrs}))
