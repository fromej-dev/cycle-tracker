"""Owner-side management of partner share, Home Assistant token and webhooks."""

import secrets

from apiflask import APIBlueprint, EmptySchema, abort
from flask_jwt_extended import current_user, jwt_required

from app.models import Webhook
from app.schemas.integrations import (
    HomeAssistantInSchema,
    HomeAssistantSchema,
    PartnerShareCreateSchema,
    PartnerShareSchema,
    PathCreatedSchema,
    WebhookCreateSchema,
    WebhookSchema,
    WebhookUpdateSchema,
)
from app.services.calendar_service import hash_token
from app.services.headsup_service import public_url
from app.services.partner_share_service import PartnerShareService
from app.services.webhook_service import WebhookService, WebhookUrlError

integrations_bp = APIBlueprint("integrations", __name__, url_prefix="/users/me")
NO_STORE = {"Cache-Control": "no-store"}


def _created(path: str):
    return {"path": path, "url": public_url(path)}, 201, NO_STORE


# --- partner share ------------------------------------------------------------------


@integrations_bp.route("/partner-share", methods=["GET"])
@integrations_bp.output(PartnerShareSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def get_partner_share():
    """Partner share settings (the token is never returned here)."""
    return PartnerShareService.settings(current_user)


@integrations_bp.route("/partner-share", methods=["POST"])
@integrations_bp.input(PartnerShareCreateSchema, arg_name="data")
@integrations_bp.output(PathCreatedSchema, 201)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def create_partner_share(data: dict):
    """Create (or rotate) the read-only partner link. Shown once; old link dies."""
    PartnerShareService.update_settings(
        current_user, name=data.get("name"), scope=data.get("scope")
    )
    token = PartnerShareService.rotate(current_user)
    return _created(PartnerShareService.path(token))


@integrations_bp.route("/partner-share", methods=["PATCH"])
@integrations_bp.input(PartnerShareCreateSchema(partial=True), arg_name="data")
@integrations_bp.output(PartnerShareSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def update_partner_share(data: dict):
    """Change the display name or scope without changing the link."""
    return PartnerShareService.update_settings(
        current_user, name=data.get("name"), scope=data.get("scope")
    )


@integrations_bp.route("/partner-share", methods=["DELETE"])
@integrations_bp.output(EmptySchema, 204)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def revoke_partner_share():
    """Revoke the partner link (404 immediately)."""
    PartnerShareService.revoke(current_user)
    return None


# --- Home Assistant sensor token ------------------------------------------------------


@integrations_bp.route("/home-assistant", methods=["GET"])
@integrations_bp.output(HomeAssistantSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def get_home_assistant():
    return {
        "enabled": current_user.ha_token_hash is not None,
        "include_fertile": bool(current_user.ha_include_fertile),
    }


@integrations_bp.route("/home-assistant", methods=["POST"])
@integrations_bp.input(HomeAssistantInSchema, arg_name="data")
@integrations_bp.output(PathCreatedSchema, 201)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def create_home_assistant(data: dict):
    """Create (or rotate) the secret /ha/<token>/state URL for a RESTful sensor."""
    token = secrets.token_urlsafe(32)
    current_user.update(
        ha_token_hash=hash_token(token),
        ha_include_fertile=bool(data.get("include_fertile", False)),
    )
    return _created(f"/ha/{token}/state")


@integrations_bp.route("/home-assistant", methods=["PATCH"])
@integrations_bp.input(HomeAssistantInSchema, arg_name="data")
@integrations_bp.output(HomeAssistantSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def update_home_assistant(data: dict):
    if "include_fertile" in data:
        current_user.update(ha_include_fertile=bool(data["include_fertile"]))
    return {
        "enabled": current_user.ha_token_hash is not None,
        "include_fertile": bool(current_user.ha_include_fertile),
    }


@integrations_bp.route("/home-assistant", methods=["DELETE"])
@integrations_bp.output(EmptySchema, 204)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def revoke_home_assistant():
    current_user.update(ha_token_hash=None)
    return None


# --- webhooks -------------------------------------------------------------------------


def _own_hook(hook_id: int) -> Webhook:
    hook = Webhook.query.filter_by(id=hook_id, user_id=current_user.id).first()
    if hook is None:
        abort(404, message="Webhook not found.")
    return hook


def _url_error(exc: WebhookUrlError):
    abort(
        422,
        message="Validation error",
        detail={"json": {"url": [str(exc)]}},
    )


@integrations_bp.route("/webhooks", methods=["GET"])
@integrations_bp.output(WebhookSchema(many=True))
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def list_webhooks():
    hooks = Webhook.query.filter_by(user_id=current_user.id).order_by(Webhook.id).all()
    return [WebhookService.to_dict(h) for h in hooks]


@integrations_bp.route("/webhooks", methods=["POST"])
@integrations_bp.input(WebhookCreateSchema, arg_name="data")
@integrations_bp.output(WebhookSchema, 201)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def create_webhook(data: dict):
    """Register a webhook. The HMAC signing secret is returned only here."""
    try:
        hook, secret = WebhookService.create(
            current_user, data["url"], data.get("events")
        )
    except WebhookUrlError as exc:
        _url_error(exc)
    return {**WebhookService.to_dict(hook), "secret": secret}, 201, NO_STORE


@integrations_bp.route("/webhooks/<int:hook_id>", methods=["GET"])
@integrations_bp.output(WebhookSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def get_webhook(hook_id: int):
    return WebhookService.to_dict(_own_hook(hook_id))


@integrations_bp.route("/webhooks/<int:hook_id>", methods=["PATCH"])
@integrations_bp.input(WebhookUpdateSchema, arg_name="data")
@integrations_bp.output(WebhookSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def update_webhook(hook_id: int, data: dict):
    hook = _own_hook(hook_id)
    try:
        WebhookService.update(hook, data)
    except WebhookUrlError as exc:
        _url_error(exc)
    return WebhookService.to_dict(hook)


@integrations_bp.route("/webhooks/<int:hook_id>", methods=["DELETE"])
@integrations_bp.output(EmptySchema, 204)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def delete_webhook(hook_id: int):
    _own_hook(hook_id).delete()
    return None


@integrations_bp.route("/webhooks/<int:hook_id>/rotate-secret", methods=["POST"])
@integrations_bp.output(WebhookSchema)
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def rotate_webhook_secret(hook_id: int):
    hook = _own_hook(hook_id)
    secret = WebhookService.rotate_secret(hook)
    return {**WebhookService.to_dict(hook), "secret": secret}, 200, NO_STORE


@integrations_bp.route("/webhooks/<int:hook_id>/test", methods=["POST"])
@integrations_bp.doc(security="bearerAuth")
@jwt_required()
def test_webhook(hook_id: int):
    """Send a signed `test` event now (single attempt, 2 s timeout)."""
    return WebhookService.send_test(_own_hook(hook_id))
