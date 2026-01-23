import datetime

from flask import url_for

from app.models import Period


# Use the 'auth_client' fixture which provides a client with a valid JWT
def test_create_period_success(auth_client, db, test_user):
    """Test successfully creating a period start."""
    start_date_str = "2023-03-15"
    response = auth_client.post(
        url_for("periods.create_period"), json={"start_date": start_date_str}
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["start_date"] == start_date_str
    assert data["end_date"] is None
    assert data["user_id"] == test_user.id
    assert "id" in data

    # Verify in DB
    period = Period.query.filter_by(
        user_id=test_user.id, start_date=datetime.date.fromisoformat(start_date_str)
    ).first()
    assert period is not None


def test_create_period_missing_data(auth_client):
    """Test creating period with missing start date."""
    response = auth_client.post(url_for("periods.create_period"), json={})
    assert response.status_code == 422  # Validation Error
    assert "start_date" in response.get_json()["detail"]["json"].keys()


def test_create_period_invalid_date_format(auth_client):
    response = auth_client.post(
        url_for("periods.create_period"),
        json={"start_date": "15-03-2023"},  # Invalid format
    )
    assert response.status_code == 422
    assert "start_date" in response.get_json()["detail"]["json"].keys()


def test_create_period_unauthorized(client):
    """Test creating period without JWT token."""
    response = client.post(
        url_for("periods.create_period"), json={"start_date": "2023-03-15"}
    )
    assert response.status_code == 401  # Unauthorized


def test_update_period_end_success(auth_client, db, test_user):
    """Test successfully updating a period's end date."""
    # Create a period without an end date first
    start_date = datetime.date(2023, 4, 1)
    period = Period(user_id=test_user.id, start_date=start_date)
    db.session.add(period)
    db.session.commit()

    end_date_str = "2023-04-05"
    response = auth_client.put(
        url_for("periods.update_period", period_id=period.id),
        json={"end_date": end_date_str},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == period.id
    assert data["end_date"] == end_date_str
    assert data["start_date"] == start_date.isoformat()
    assert data["duration"] == 5  # (5 - 1) + 1

    # Verify in DB
    updated_period = Period.get_by_id(period.id)
    assert updated_period.end_date == datetime.date.fromisoformat(end_date_str)


def test_update_period_end_date_before_start(auth_client, test_period):
    """Test updating end date to be before start date."""
    end_date_str = (test_period.start_date - datetime.timedelta(days=1)).isoformat()
    response = auth_client.put(
        url_for("periods.update_period", period_id=test_period.id),
        json={"end_date": end_date_str},
    )
    # This validation might happen in the service or schema
    # Expecting 400 Bad Request (PeriodLogicError) or 422 (Schema validation)
    assert response.status_code in [400, 422]
    assert "message" in response.get_json()
    assert (
        response.get_json()["detail"]["error"]
        == f"Period {test_period.id} already has an end date."
    )


def test_update_period_not_found(auth_client):
    """Test updating a non-existent period."""
    response = auth_client.put(
        url_for("periods.update_period", period_id=9999),
        json={"end_date": "2023-04-05"},
    )
    assert response.status_code == 404  # NotFoundError
    assert (
        response.get_json()["message"] == "Period with ID 9999 not found for this user."
    )


def test_update_period_unauthorized(client, test_period):
    """Test updating period without JWT."""
    response = client.put(
        url_for("periods.update_period", period_id=test_period.id),
        json={"end_date": "2023-01-06"},
    )
    assert response.status_code == 401


# --- Tests for GET and DELETE ---
def test_get_periods_success(auth_client, test_period, test_user):
    """Test getting list of periods."""
    # Add another period
    period2 = Period(user_id=test_user.id, start_date=datetime.date(2023, 2, 1))
    test_period.save()  # Make sure fixture period is saved
    period2.save()

    response = auth_client.get(url_for("periods.get_periods"))
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 2
    # Check if periods are ordered by start_date desc (default in service)
    assert data[0]["start_date"] == period2.start_date.isoformat()
    assert data[1]["start_date"] == test_period.start_date.isoformat()


def test_get_active_period(auth_client, test_period, test_user):
    """Test getting list of periods."""
    response = auth_client.get(url_for("periods.get_active_period"))

    assert response.status_code == 200
    data = response.get_json()
    assert data == {}

    # Add another period
    period2 = Period(user_id=test_user.id, start_date=datetime.date(2023, 2, 1))
    test_period.save()  # Make sure fixture period is saved
    period2.save()

    response = auth_client.get(url_for("periods.get_active_period"))
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, dict)
    assert data["id"] == period2.id
    # Check if periods are ordered by start_date desc (default in service)
    assert data["start_date"] == period2.start_date.isoformat()
    assert not data["end_date"]


def test_get_periods_pagination(auth_client, test_user, db):
    """Test pagination for getting periods."""
    # Create several periods
    for i in range(15):
        p = Period(
            user_id=test_user.id,
            start_date=datetime.date(2023, 1, 1) + datetime.timedelta(days=i * 10),
        )
        db.session.add(p)
    db.session.commit()

    # Get page 1, 5 per page
    response = auth_client.get(url_for("periods.get_periods", page=1, per_page=5))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 5

    # Get page 2, 5 per page
    response = auth_client.get(url_for("periods.get_periods", page=2, per_page=5))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 5

    # Get page 4, 5 per page (should have 0 items as 15 total)
    response = auth_client.get(url_for("periods.get_periods", page=4, per_page=5))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 0


def test_get_specific_period_success(auth_client, test_period):
    """Test getting a single period by ID."""
    response = auth_client.get(url_for("periods.get_period", period_id=test_period.id))
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == test_period.id
    assert data["start_date"] == test_period.start_date.isoformat()


def test_get_specific_period_not_found(auth_client):
    """Test getting a non-existent period ID."""
    response = auth_client.get(url_for("periods.get_period", period_id=9999))
    assert response.status_code == 404


def test_get_period_unauthorized(client, test_period):
    response = client.get(url_for("periods.get_period", period_id=test_period.id))
    assert response.status_code == 401


def test_delete_period_success(auth_client, test_period):
    """Test successfully deleting a period."""
    period_id_to_delete = test_period.id
    response = auth_client.delete(
        url_for("periods.delete_period", period_id=period_id_to_delete)
    )
    assert response.status_code == 204  # No Content

    # Verify it's gone from DB
    deleted_period = Period.get_by_id(period_id_to_delete)
    assert deleted_period is None


def test_delete_period_not_found(auth_client):
    """Test deleting a non-existent period."""
    response = auth_client.delete(url_for("periods.delete_period", period_id=9999))
    assert response.status_code == 404


def test_delete_period_unauthorized(client, test_period):
    response = client.delete(url_for("periods.delete_period", period_id=test_period.id))
    assert response.status_code == 401
