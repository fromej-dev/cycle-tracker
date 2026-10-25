import datetime
from statistics import StatisticsError, mean

from app.models import Period
from app.services.forecast_service import ForecastService


class ReportService:
    """Service layer for generating cycle and period statistics."""

    @staticmethod
    def get_period_stats(user_id: int) -> dict[str, float | int | None]:
        """Calculates statistics about period durations for a user."""
        periods_with_duration: list[Period] = (
            Period.query.filter(
                Period.user_id == user_id,
                Period.end_date.isnot(None),  # Only consider completed periods
            )
            .order_by(Period.start_date)
            .all()
        )
        count = Period.query.filter(Period.user_id == user_id).count()

        durations: list[int] = [
            p.duration for p in periods_with_duration if p.duration is not None
        ]

        if not durations:
            return {
                "count": count,
                "min_duration": None,
                "max_duration": None,
                "average_duration": None,
            }

        try:
            avg_duration = round(mean(durations), 2)
        except StatisticsError:
            avg_duration = None  # Should not happen if durations list is not empty, but safety first

        return {
            "count": count,
            "min_duration": min(durations),
            "max_duration": max(durations),
            "average_duration": avg_duration,
        }

    @staticmethod
    def get_cycle_stats(user_id: int) -> dict[str, float | int | None]:
        """
        Calculates statistics about cycle lengths for a user.
        Cycle length is defined as the time from the start of one period
        to the start of the next period.
        """
        # Fetch all periods sorted by start date to calculate intervals
        periods: list[Period] = (
            Period.query.filter_by(user_id=user_id)
            .order_by(Period.start_date.asc())
            .all()
        )

        if len(periods) < 2:
            # Need at least two periods to calculate one cycle length
            return {
                "count": 0,
                "min_length": None,
                "max_length": None,
                "average_length": None,
            }

        cycle_lengths: list[int] = []
        for i in range(len(periods) - 1):
            start_date_current = periods[i].start_date
            start_date_next = periods[i + 1].start_date
            length = (start_date_next - start_date_current).days
            if length > 0:  # Basic sanity check
                cycle_lengths.append(length)

        if not cycle_lengths:
            return {
                "count": 0,
                "min_length": None,
                "max_length": None,
                "average_length": None,
            }

        try:
            avg_length = round(mean(cycle_lengths))
        except StatisticsError:
            avg_length = None

        return {
            "count": len(cycle_lengths),
            "min_length": min(cycle_lengths),
            "max_length": max(cycle_lengths),
            "average_length": avg_length,
        }

    @staticmethod
    def _forecast(user_id: int, today: datetime.date | None = None) -> dict:
        return ForecastService.forecast(user_id, today, horizon_days=1)

    @staticmethod
    def get_predicted_next_period(
        user_id: int, today: datetime.date | None = None
    ) -> datetime.date | None:
        """Most likely next period start, from the probabilistic forecast.

        Same value as ``/reports/forecast`` (including the prior-only "learning"
        forecast after a single logged period). None only without any period or
        when the user is overdue (no reliable forecast).
        """
        return ReportService._forecast(user_id, today)["most_likely_start"]

    @staticmethod
    def _ovulation_from(forecast: dict) -> dict[str, datetime.date] | None:
        window = forecast["fertile_window"]
        if not window:
            return None
        return {
            "ovulation_date": window["ovulation_date"],
            "fertile_window_start": window["start"],
            "fertile_window_end": window["end"],
        }

    @staticmethod
    def get_estimated_ovulation(
        user_id: int, today: datetime.date | None = None
    ) -> dict[str, datetime.date] | None:
        """Estimates ovulation day and fertile window (from the forecast)."""
        return ReportService._ovulation_from(ReportService._forecast(user_id, today))

    @staticmethod
    def get_cycle_context(
        user_id: int, today: datetime.date | None = None
    ) -> dict[str, any] | None:
        """
        Returns contextual information about the user's current menstrual cycle.

        This includes whether a period is ongoing, how many days it has lasted,
        the current cycle day, progress through the cycle based on average length,
        and predictions such as next period start, ovulation date, and fertile window.

        Args:
            user_id (int): The ID of the user whose cycle context is being requested.

        Returns:
            dict or None: A dictionary containing the following keys if data is available:

            - status (str): The current phase of the cycle. One of:
                * "period" — the user is currently on their period.
                * "waiting" — the user is not currently on their period.

            - days_running (int or None): If currently on a period, the number of days the period has lasted so far (including today).

            - cycle_day (int or None): If not currently on a period, the number of days since the last period started.

            - cycle_length (float or None): The user's typical cycle length (days) from the forecast model, which ignores forgotten-log gaps.

            - progress_percent (float or None): If not currently on a period and average cycle length is known,
              an estimate of how far the user is through their current cycle (as a percentage).

            - predicted_start (str or None): Predicted date for the next period to begin (ISO 8601 format).

            - days_until_next_period (int or None): The number of days until the predicted next period starts.
              Returns 0 if the predicted date is today or in the past. None if prediction is not possible.

            - ovulation_date (str or None): Estimated ovulation date (ISO 8601 format).

            - fertile_window (dict): Contains:
                * "start" (str or None): Start date of the fertile window (ISO 8601 format).
                * "end" (str or None): End date of the fertile window (ISO 8601 format).

            - is_today_ovulation (bool): Whether today is predicted to be the ovulation day.

            - is_in_fertile_window (bool): Whether today falls within the estimated fertile window.

        Returns None if there is no period history for the user.
        """
        today = today or datetime.date.today()
        periods = ForecastService._load(user_id)
        if not periods:
            return None

        # One fit serves every field, so this endpoint always agrees with
        # /reports/forecast (including "ongoing", which expires for stale open periods).
        model = ForecastService.fit(periods, today)
        today = model.today  # may be shifted by a day if the client clock is ahead
        forecast = model.forecast(horizon_days=1)
        predicted_start = forecast["most_likely_start"]
        ovulation = ReportService._ovulation_from(forecast)

        last_period = (
            Period.query.filter_by(user_id=user_id)
            .order_by(Period.start_date.desc())
            .first()
        )
        last_start = model.last_start

        days_running = None
        status = "waiting"
        current_period_id = None
        days_until_next_period = None
        if model.ongoing:
            days_running = model.age + 1
            status = "period"
            current_period_id = last_period.id if last_period else None
        elif predicted_start:
            days_until_next_period = max((predicted_start - today).days, 0)

        cycle_day = (today - last_start).days + 1 if today > last_start else 1
        cycle_length = model.mean_cycle if model.cycles_used else None
        progress_percent = None
        if cycle_length:
            progress_percent = float(min(round(cycle_day / cycle_length * 100), 100))

        return {
            "status": status,
            "current_period_id": current_period_id,
            "days_running": days_running,
            "cycle_day": cycle_day,
            "cycle_length": round(cycle_length, 1) if cycle_length else None,
            "progress_percent": progress_percent,
            "predicted_start": predicted_start,
            "days_until_next_period": days_until_next_period,
            "ovulation_date": ovulation.get("ovulation_date") if ovulation else None,
            "fertile_window": {
                "start": ovulation.get("fertile_window_start") if ovulation else None,
                "end": ovulation.get("fertile_window_end") if ovulation else None,
            },
            "is_today_ovulation": bool(
                ovulation and ovulation["ovulation_date"] == today
            ),
            "is_in_fertile_window": bool(
                ovulation
                and ovulation["fertile_window_start"]
                <= today
                <= ovulation["fertile_window_end"]
            ),
            "is_late": forecast["is_late"],
            "confidence": forecast["confidence"],
        }
