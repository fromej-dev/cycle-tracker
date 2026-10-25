import datetime

from sqlalchemy import Date

from app.extensions import db
from app.models.base import BaseModel


class PlannedEvent(BaseModel):
    """A trip, holiday or other dated event the user wants period odds for."""

    __tablename__ = "planned_events"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(Date, nullable=False)
    end_date = db.Column(Date, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    user = db.relationship("User", back_populates="planned_events")

    def __repr__(self) -> str:
        return f"<PlannedEvent {self.name!r} {self.start_date}..{self.end_date}>"
