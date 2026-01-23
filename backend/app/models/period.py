from sqlalchemy import Date  # Use SQLAlchemy's Date type

from app.extensions import db
from app.models.base import BaseModel


class Period(BaseModel):
    """Period model for tracking menstrual cycles."""

    __tablename__ = "periods"

    start_date = db.Column(Date, nullable=False)
    end_date = db.Column(Date, nullable=True)  # Can be null if period is ongoing
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Relationship back to user
    user = db.relationship("User", back_populates="periods")

    def __repr__(self) -> str:
        return f"<Period {self.start_date} - {self.end_date or 'Ongoing'} for User {self.user_id}>"

    @property
    def duration(self) -> int | None:
        """Calculates the duration of the period in days (inclusive)."""
        if self.end_date:
            # Add 1 because duration includes both start and end days
            return (self.end_date - self.start_date).days + 1
        return None
