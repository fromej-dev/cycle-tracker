import datetime

from flask import url_for

from app.models import Period


def test_get_period_stats_success(auth_client, test_user, db):
    """Test period stats report with data."""
    # Add periods with durations
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 1),
        end_date=datetime.date(2023, 1, 5),
    ).save()  # Duration 5
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 2, 1),
        end_date=datetime.date(2023, 2, 4),
    ).save()  # Duration 4
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 3, 1),
        end_date=datetime.date(2023, 3, 6),
    ).save()  # Duration 6
    # Add one ongoing period (should be ignored by stats)
    Period(user_id=test_user.id, start_date=datetime.date(2023, 4, 1)).save()

    response = auth_client.get(url_for("reports.get_period_statistics"))
    assert response.status_code == 200
    data = response.get_json()

    assert data["count"] == 4
    assert data["min_duration"] == 4
    assert data["max_duration"] == 6
    assert data["average_duration"] == (5 + 4 + 6) / 3  # 5.0


def test_get_period_stats_no_completed_periods(auth_client, test_user, db):
    """Test period stats when only ongoing periods exist."""
    Period(user_id=test_user.id, start_date=datetime.date(2023, 4, 1)).save()

    response = auth_client.get(url_for("reports.get_period_statistics"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 1
    assert data["min_duration"] is None
    assert data["max_duration"] is None
    assert data["average_duration"] is None


def test_get_period_stats_no_periods(auth_client):
    """Test period stats when no periods exist."""
    response = auth_client.get(url_for("reports.get_period_statistics"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 0
    assert data["min_duration"] is None
    assert data["max_duration"] is None
    assert data["average_duration"] is None


def test_get_cycle_stats_success(auth_client, test_user, db):
    """Test cycle stats report with data."""
    # Need at least two periods, sorted by date
    p1_start = datetime.date(2023, 1, 1)
    p2_start = datetime.date(2023, 1, 30)  # Cycle 1 length = 29 days
    p3_start = datetime.date(2023, 3, 2)  # Cycle 2 length = 31 days
    p4_start = datetime.date(2023, 4, 1)  # Cycle 3 length = 30 days

    Period(
        user_id=test_user.id,
        start_date=p1_start,
        end_date=p1_start + datetime.timedelta(days=4),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=p2_start,
        end_date=p2_start + datetime.timedelta(days=3),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=p3_start,
        end_date=p3_start + datetime.timedelta(days=5),
    ).save()
    Period(
        user_id=test_user.id, start_date=p4_start
    ).save()  # Ongoing, still counts for start date

    response = auth_client.get(url_for("reports.get_cycle_statistics"))
    assert response.status_code == 200
    data = response.get_json()

    assert data["count"] == 3
    assert data["min_length"] == 29
    assert data["max_length"] == 31
    expected_avg = round((29 + 31 + 30) / 3, 2)
    assert data["average_length"] == expected_avg  # 30.0


def test_get_cycle_stats_insufficient_data(auth_client, test_user, db):
    """Test cycle stats with less than two periods."""
    Period(user_id=test_user.id, start_date=datetime.date(2023, 1, 1)).save()

    response = auth_client.get(url_for("reports.get_cycle_statistics"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 0
    assert data["min_length"] is None
    assert data["max_length"] is None
    assert data["average_length"] is None


def test_get_cycle_stats_no_periods(auth_client):
    """Test cycle stats with no periods."""
    response = auth_client.get(url_for("reports.get_cycle_statistics"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 0
    assert data["min_length"] is None
    assert data["max_length"] is None
    assert data["average_length"] is None


def test_get_reports_unauthorized(client):
    """Test accessing reports without JWT."""
    response_period = client.get(url_for("reports.get_period_statistics"))
    response_cycle = client.get(url_for("reports.get_cycle_statistics"))
    assert response_period.status_code == 401
    assert response_cycle.status_code == 401


def _three_regular_periods(user_id, days_since_last=3):
    """Three 28-day cycles whose last period started ``days_since_last`` ago."""
    last = datetime.date.today() - datetime.timedelta(days=days_since_last)
    for k in (2, 1, 0):
        start = last - datetime.timedelta(days=28 * k)
        Period(
            user_id=user_id,
            start_date=start,
            end_date=start + datetime.timedelta(days=4),
        ).save()
    return last


def test_get_predicted_next_period(auth_client, test_user, db):
    """Next start is exactly one cycle after the last start (no off-by-one)."""
    last = _three_regular_periods(test_user.id)

    response = auth_client.get(url_for("reports.get_predicted_next_period"))
    assert response.status_code == 200
    data = response.get_json()

    assert data["predicted_start"] == (last + datetime.timedelta(days=28)).isoformat()


def test_get_ovulation_window(auth_client, test_user, db):
    """Ovulation is 14 days before the predicted start; fertile window -5..+1."""
    last = _three_regular_periods(test_user.id)
    ovulation = last + datetime.timedelta(days=14)

    response = auth_client.get(url_for("reports.get_ovulation_window"))
    assert response.status_code == 200
    data = response.get_json()

    assert data["ovulation_date"] == ovulation.isoformat()
    assert (
        data["fertile_window_start"]
        == (ovulation - datetime.timedelta(days=5)).isoformat()
    )
    assert (
        data["fertile_window_end"]
        == (ovulation + datetime.timedelta(days=1)).isoformat()
    )


def test_get_predicted_next_period_insufficient_data(auth_client, test_user, db):
    """Test prediction fails gracefully with not enough data."""
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 4, 1),
        end_date=datetime.date(2023, 4, 5),
    ).save()

    response = auth_client.get(url_for("reports.get_predicted_next_period"))
    assert response.status_code == 200
    data = response.get_json()
    assert data["predicted_start"] is None


def test_get_cycle_context_success(auth_client, test_user, db):
    """Test complete cycle context report when enough data is available."""
    _three_regular_periods(test_user.id)

    response = auth_client.get(url_for("reports.get_cycle_context"))
    assert response.status_code == 200
    data = response.get_json()

    assert data["status"] in ["period", "waiting"]
    assert isinstance(data["cycle_day"], int)
    assert isinstance(data["progress_percent"], float)
    assert isinstance(data["predicted_start"], str)
    assert isinstance(data["ovulation_date"], str)
    assert "fertile_window" in data
    assert "start" in data["fertile_window"]
    assert "end" in data["fertile_window"]
    assert isinstance(data["is_today_ovulation"], bool)
    assert isinstance(data["is_in_fertile_window"], bool)


def test_get_cycle_context_insufficient_data(auth_client, test_user, db):
    """Should handle gracefully when there's not enough data."""
    # Only one completed period
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 3, 1),
        end_date=datetime.date(2023, 3, 4),
    ).save()

    response = auth_client.get(url_for("reports.get_cycle_context"))
    assert response.status_code == 200
    data = response.get_json()

    # The endpoint will return None or partial data
    assert "status" in data
    assert data["predicted_start"] is None
    assert data["ovulation_date"] is None
    assert data["fertile_window"]["start"] is None
    assert data["fertile_window"]["end"] is None


def test_get_cycle_context_no_periods(auth_client):
    """Should return empty dict when no period data is available."""
    response = auth_client.get(url_for("reports.get_cycle_context"))
    assert response.status_code == 200
    data = response.get_json()

    assert data == {}


def test_get_cycle_context_unauthorized(client):
    """Should return 401 without a JWT token."""
    response = client.get(url_for("reports.get_cycle_context"))
    assert response.status_code == 401
