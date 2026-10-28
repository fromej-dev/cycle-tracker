import datetime

from sqlalchemy import Date

from app.extensions import db
from app.models.base import BaseModel


class SymptomLog(BaseModel):
    """The symptoms a user noted for one day (at most one row per user and date)."""

    __tablename__ = "symptom_logs"
    __table_args__ = (
        db.UniqueConstraint("user_id", "date", name="uq_symptom_logs_user_date"),
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = db.Column(Date, nullable=False)
    symptoms = db.Column(db.Text, nullable=False, default="[]")  # JSON list of keys
    custom = db.Column(db.Text, nullable=False, default="[]")  # JSON list of free text
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    user = db.relationship("User", back_populates="symptom_logs")

    def __repr__(self) -> str:
        return f"<SymptomLog {self.date} for User {self.user_id}>"
