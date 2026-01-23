from flask import url_for

from app.models import User


def test_delete_own_user(auth_client):
    """Test user trying to delete."""
    response = auth_client.delete(
        url_for("users.delete_own_user"),
    )

    assert response.status_code == 204


def test_get_own_user_success(auth_client, db):
    """Test successfully retrieving the currently authenticated user's information."""
    # Simulate authenticated request
    response = auth_client.get(
        url_for("users.get_own_user"),
    )

    assert response.status_code == 200
    data = response.get_json()
    assert "id" in data
    assert "created_at" in data


def test_get_own_user_unauthorized(client):
    """Test unauthorized access to user's information."""
    response = client.get(
        url_for("users.get_own_user"),
    )

    assert response.status_code == 401
    data = response.get_json()
    assert data["message"] == "Request does not contain an access token."


def test_delete_own_user_already_deleted(auth_client, db):
    """Test attempting to delete a user already deleted."""
    # Attempt deletion
    response = auth_client.delete(
        url_for("users.delete_own_user"),
    )

    assert response.status_code == 204

    # Attempt deletion again
    response = auth_client.delete(
        url_for("users.delete_own_user"),
    )

    assert response.status_code == 401


def test_patch_own_user_success(auth_client, db):
    """Test successfully updating the current user's information."""
    # Update user details
    new_data = {
        "username": "newusername",
        "email": "newemail@example.com",
    }

    response = auth_client.patch(
        url_for("users.patch_own_user"),
        json=new_data,
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["username"] == "newusername"
    assert data["email"] == "newemail@example.com"

    # Verify the database is updated
    updated_user = User.find_by_email("newemail@example.com")
    assert updated_user is not None
    assert updated_user.username == "newusername"


def test_patch_own_user_unauthorized(client):
    """Test unauthorized user trying to update their information."""
    new_data = {
        "username": "newusername",
        "email": "newemail@example.com",
    }

    response = client.patch(
        url_for("users.patch_own_user"),
        json=new_data,
    )

    assert response.status_code == 401
    data = response.get_json()
    assert data["message"] == "Request does not contain an access token."
