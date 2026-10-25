import datetime

from app.extensions import db
from app.models import Period
from app.utils.exceptions import NotFoundError, PeriodLogicError


class PeriodService:
    """Service layer for period tracking logic."""

    @staticmethod
    def record_period_start(user_id: int, start_date: datetime.date) -> Period:
        """Records the start of a new period for a user."""
        # Optional: Check for overlaps or conflicts with existing periods if needed
        # existing = Period.query.filter_by(user_id=user_id).filter(
        #     (Period.start_date <= start_date) & (Period.end_date >= start_date)
        # ).first()
        # if existing:
        #    raise PeriodLogicError("New period overlaps with an existing one.")

        period = Period(user_id=user_id, start_date=start_date)
        try:
            return period.save()
        except Exception as e:
            db.session.rollback()
            # Log e
            raise PeriodLogicError(
                "Could not record period start due to database error."
            ) from e

    @staticmethod
    def update_period_end(
        user_id: int, period_id: int, end_date: datetime.date | None
    ) -> Period:
        """Updates the end date of an existing period.

        A None end_date reopens the period, which is only allowed for the user's
        most recent period (to undo ending it).
        """
        period = PeriodService.get_period_by_id_for_user(user_id, period_id)

        if not period:
            raise NotFoundError(f"Period with ID {period_id} not found for this user.")

        if end_date is None:
            latest = (
                Period.query.filter_by(user_id=user_id)
                .order_by(Period.start_date.desc())
                .first()
            )
            if latest.id != period.id:
                raise PeriodLogicError("Only your most recent period can be reopened.")
            period.end_date = None
            try:
                return period.save()
            except Exception as e:
                db.session.rollback()
                raise PeriodLogicError(f"Could not reopen period: {e}") from e

        if period.end_date:
            raise PeriodLogicError(f"Period {period_id} already has an end date.")

        if end_date < period.start_date:
            raise PeriodLogicError("End date cannot be before start date.")

        period.end_date = end_date
        try:
            return period.save()
        except Exception as e:
            db.session.rollback()
            # Log e
            raise PeriodLogicError(
                "Could not update period end date due to database error."
            ) from e

    @staticmethod
    def get_period_by_id_for_user(user_id: int, period_id: int) -> Period | None:
        """Gets a specific period by its ID, ensuring it belongs to the user."""
        return Period.query.filter_by(id=period_id, user_id=user_id).first()

    @staticmethod
    def get_all_periods_for_user(
        user_id: int, page: int = 1, per_page: int = 10
    ) -> list[Period]:
        """Gets a paginated list of all periods for a user, ordered by start date descending."""
        # Using paginate for better handling of large datasets
        pagination = (
            Period.query.filter_by(user_id=user_id)
            .order_by(Period.start_date.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        return pagination.items  # Or return the pagination object for more info

    @staticmethod
    def get_active_period_for_user(user_id: int):
        """Get the last active period for a user"""
        return Period.query.filter(
            Period.user_id == user_id, Period.end_date.is_(None)
        ).first()

    @staticmethod
    def delete_period_for_user(user_id: int, period_id: int) -> bool:
        """Deletes a period for a specific user."""
        period = PeriodService.get_period_by_id_for_user(user_id, period_id)
        if not period:
            raise NotFoundError(f"Period with ID {period_id} not found for this user.")

        try:
            period.delete()
            return True
        except Exception as e:
            db.session.rollback()
            # Log e
            raise PeriodLogicError(
                "Could not delete period due to database error."
            ) from e
