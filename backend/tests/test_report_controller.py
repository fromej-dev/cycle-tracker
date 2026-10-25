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


def test_get_predicted_next_period(auth_client, test_user, db):
    """Test prediction of next period start date using average cycle length."""
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 1),
        end_date=datetime.date(2023, 1, 5),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 29),
        end_date=datetime.date(2023, 2, 2),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 2, 27),
        end_date=datetime.date(2023, 3, 3),
    ).save()

    response = auth_client.get(url_for("reports.get_predicted_next_period"))
    assert response.status_code == 200
    data = response.get_json()

    # Avg cycle length = 28.0, last period = Feb 27 => next start = Feb 27 + 28 = Mar 27
    assert data["predicted_start"] == "2023-03-27"


def test_get_ovulation_window(auth_client, test_user, db):
    """Test estimation of ovulation and fertile window."""
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 1),
        end_date=datetime.date(2023, 1, 5),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 29),
        end_date=datetime.date(2023, 2, 2),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 2, 27),
        end_date=datetime.date(2023, 3, 3),
    ).save()

    response = auth_client.get(url_for("reports.get_ovulation_window"))
    assert response.status_code == 200
    data = response.get_json()

    # Last period = Feb 27, next predicted = Mar 27
    # Ovulation = Mar 13, fertile = Mar 9 - 14
    assert data["ovulation_date"] == "2023-03-13"
    assert data["fertile_window_start"] == "2023-03-09"
    assert data["fertile_window_end"] == "2023-03-14"


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
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 1),
        end_date=datetime.date(2023, 1, 5),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 29),
        end_date=datetime.date(2023, 2, 2),
    ).save()
    Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 2, 27),
        end_date=datetime.date(2023, 3, 3),
    ).save()

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
