from apiflask import APIBlueprint, abort
from flask_jwt_extended import current_user, jwt_required

from app.schemas.admin import AdminStatsSchema
from app.services.admin_stats_service import AdminStatsService

admin_bp = APIBlueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/stats")
@admin_bp.output(AdminStatsSchema)
@admin_bp.doc(security="bearerAuth")
@jwt_required()
def get_stats():
    """App-wide aggregate statistics (admins only). Contains no personal data."""
    if not current_user.is_admin:
        abort(403, message="Admins only.")
    return AdminStatsService.stats(), 200, {"Cache-Control": "no-store"}
