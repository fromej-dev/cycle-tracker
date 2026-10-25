from app.extensions import db
from app.models.base import BaseModel


class Webhook(BaseModel):
    """An outgoing webhook registered by a user (signed with an HMAC secret)."""

    __tablename__ = "webhooks"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.Text, nullable=False)  # JSON list of event names
    # The HMAC key must be readable to sign, so it is stored as-is (shown once).
    secret = db.Column(db.String(64), nullable=False)
    active = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.true()
    )
    last_status = db.Column(db.Integer)  # HTTP status of the last attempt, 0 = error
    last_attempt_at = db.Column(db.DateTime)
    failures = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )  # consecutive failed deliveries
    # Why the hook was switched off automatically (None when active or switched off by hand)
    disabled_reason = db.Column(db.String(200))

    user = db.relationship("User", back_populates="webhooks")
