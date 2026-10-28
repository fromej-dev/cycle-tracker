from typing import Optional

from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import BaseModel


class User(BaseModel):
    """User model for storing user accounts."""

    __tablename__ = "users"

    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # Increased length

    # Private calendar feed (ICS subscription). Only the SHA-256 hash of the secret
    # URL token is stored; the token itself is shown to the user once.
    calendar_token_hash = db.Column(db.String(64), unique=True, index=True)
    calendar_label = db.Column(db.String(40))  # None -> discreet default label
    calendar_fertile_label = db.Column(db.String(40))  # None -> same as calendar_label
    calendar_mark_estimate = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    # IANA time zone of the subscriber, so the feed's "today" is theirs.
    calendar_timezone = db.Column(db.String(64))
    # JSON bookkeeping for stable event identities / per-event SEQUENCE (see
    # CalendarService); updated with compare-and-swap, never by the ORM flush.
    calendar_state = db.Column(db.Text)
    # Random per-feed secret behind the opaque event UIDs (independent of SECRET_KEY).
    calendar_uid_key = db.Column(db.String(64))
    calendar_include_fertile = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )

    # Read-only partner share (heads-up page). Only the token hash is stored.
    partner_share_token_hash = db.Column(db.String(64), unique=True, index=True)
    partner_share_name = db.Column(db.String(40))  # page title; None -> neutral default
    partner_share_fertile = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    partner_share_window_days = db.Column(
        db.Integer, nullable=False, default=7, server_default="7"
    )

    # Opt-in: show "Period now" on the partner page (off: neutral text instead).
    partner_share_show_current = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    # JSON {"share": bucket, "ha": bucket}: last coarse bucket shown, for hysteresis.
    heads_up_state = db.Column(db.Text)

    # Home Assistant state endpoint (/ha/<token>/state); hash only.
    ha_token_hash = db.Column(db.String(64), unique=True, index=True)
    ha_include_fertile = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )

    # JSON dedupe bookkeeping for outgoing webhook events (see WebhookService).
    webhook_state = db.Column(db.Text)

    # Relationship to periods (one-to-many)
    periods = db.relationship(
        "Period", back_populates="user", lazy=True, cascade="all, delete-orphan"
    )

    webhooks = db.relationship(
        "Webhook", back_populates="user", lazy=True, cascade="all, delete-orphan"
    )

    planned_events = db.relationship(
        "PlannedEvent", back_populates="user", lazy=True, cascade="all, delete-orphan"
    )

    symptom_logs = db.relationship(
        "SymptomLog", back_populates="user", lazy=True, cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        """Hashes and sets the user's password."""
        if not password:
            raise ValueError("Password cannot be empty.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Checks if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    @classmethod
    def find_by_username(cls, username: str) -> Optional["User"]:
        """Finds a user by their username."""
        return cls.query.filter(func.lower(User.username) == username.lower()).first()

    @classmethod
    def find_by_email(cls, email: str) -> Optional["User"]:
        """Finds a user by their email address."""
        return cls.query.filter_by(email=email).first()

    def __repr__(self) -> str:
        return f"<User {self.username}>"
