import time
from datetime import timedelta

from flask import url_for
from flask_jwt_extended import decode_token

from app.models import User


# Helper function (optional, but can make tests cleaner)
def login_user_and_get_tokens(client, login_identifier, password):
    response = client.post(
        url_for("auth.login"),
        json={"login": login_identifier, "password": password},
    )
    return response


def test_register_success(client, db):
    """Test successful user registration."""
    response = client.post(
        url_for("auth.register"),
        json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["username"] == "newuser"
    assert data["email"] == "new@example.com"
    assert "id" in data
    assert "password_hash" not in data  # Ensure password is not returned

    # Verify user exists in db
    user = User.find_by_email("new@example.com")
    assert user is not None
    assert user.username == "newuser"


def test_register_username_taken(client, test_user):
    """Test registration with an existing username."""
    response = client.post(
        url_for("auth.register"),
        json={
            "username": test_user.username,  # Existing username
            "email": "another@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data["detail"]
    assert test_user.username in data["detail"]["error"]


def test_register_email_taken(client, test_user):
    """Test registration with an existing email."""
    response = client.post(
        url_for("auth.register"),
        json={
            "username": "anotheruser",
            "email": test_user.email,  # Existing email
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400
    assert test_user.email in response.get_json()["detail"]["error"]


def test_register_password_mismatch(client, db):
    """Test registration with mismatched passwords."""
    response = client.post(
        url_for("auth.register"),
        json={
            "username": "user3",
            "email": "user3@example.com",
            "password": "password123",
            "confirm_password": "password456",  # Mismatch
        },
    )
    assert response.status_code == 422  # Validation error from schema
    data = response.get_json()
    assert "message" in data
    assert "Validation error" in data["message"]
    assert "Passwords do not match" in data["detail"]["json"]["_schema"][0]


def test_login_success_email(client, test_user):
    """Test successful login using email."""
    response = client.post(
        url_for("auth.login"),
        json={
            "login": test_user.email,
            "password": "password",  # The correct password set in fixture
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_success_username(client, test_user):
    """Test successful login using username."""
    response = client.post(
        url_for("auth.login"),
        json={"login": test_user.username, "password": "password"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_refresh_token_success(client, test_user, app):
    """Test successful token refresh."""
    # 1. Login to get a refresh token
    login_response = login_user_and_get_tokens(client, test_user.username, "password")
    assert login_response.status_code == 200
    login_data = login_response.get_json()
    original_access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]

    # 2. Use the refresh token to get a new access token
    refresh_response = client.post(
        url_for("auth.refresh"), headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert refresh_response.status_code == 200
    refresh_data = refresh_response.get_json()
    assert "access_token" in refresh_data
    assert (
        "refresh_token" not in refresh_data
    )  # Typically, refresh endpoint only returns new access token

    new_access_token = refresh_data["access_token"]
    assert new_access_token != original_access_token


def test_login_wrong_password(client, test_user):
    """Test login with incorrect password."""
    response = client.post(
        url_for("auth.login"),
        json={"login": test_user.email, "password": "wrongpassword"},
    )
    assert response.status_code == 401  # AuthenticationError
    data = response.get_json()
    assert "error" in data["detail"]
    assert "Invalid credentials" in data["detail"]["error"]


def test_login_user_not_found(client):
    """Test login with non-existent user."""
    response = client.post(
        url_for("auth.login"),
        json={"login": "nosuchuser@example.com", "password": "password"},
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.get_json()["detail"]["error"]


def test_refresh_with_access_token_fails(client, test_user, app):
    """Test attempting to refresh using an access token (should fail)."""
    login_response = login_user_and_get_tokens(client, test_user.username, "password")
    assert login_response.status_code == 200
    access_token = login_response.get_json()["access_token"]

    with app.app_context():  # Need app context for decode_token
        decoded_access_token = decode_token(access_token)
        assert decoded_access_token["type"] == "access"

    refresh_response = client.post(
        url_for("auth.refresh"), headers={"Authorization": f"Bearer {access_token}"}
    )

    assert refresh_response.status_code == 401
    data = refresh_response.get_json()
    assert "message" in data
    assert "Signature verification failed or token is malformed." in data["message"]


def test_refresh_with_invalid_token_signature(client):
    """Test refreshing with a structurally valid but cryptographically invalid token."""
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTY3ODg4NjQwMCwianRpIjoiYWJjIiwiZXhwIjoxNjc4ODg3NDAwLCJzdWIiOiIxMjMiLCJ0eXBlIjoicmVmcmVzaCJ9.thisisabadsignature"
    response = client.post(
        url_for("auth.refresh"), headers={"Authorization": f"Bearer {invalid_token}"}
    )

    assert response.status_code == 401
    data = response.get_json()
    assert "message" in data
    assert "Signature verification failed or token is malformed." in data["message"]


def test_refresh_with_malformed_token(client):
    """Test refreshing with a malformed token string."""
    malformed_token = "this.is.not.a.jwt"
    response = client.post(
        url_for("auth.refresh"), headers={"Authorization": f"Bearer {malformed_token}"}
    )

    assert response.status_code == 401
    data = response.get_json()
    assert "message" in data
    assert "Signature verification failed or token is malformed." in data["message"]


def test_refresh_without_token(client):
    """Test refreshing without providing any token."""
    response = client.post(url_for("auth.refresh"))

    assert response.status_code == 401
    data = response.get_json()
    assert "message" in data
    assert "Request does not contain an access token." in data["message"]


def test_refresh_with_expired_refresh_token(client, test_user, app):
    """Test refreshing with an expired refresh token."""
    with app.app_context():
        original_expiry = app.config.get("JWT_REFRESH_TOKEN_EXPIRES")
        app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(seconds=1)

        login_response = login_user_and_get_tokens(
            client, test_user.username, "password"
        )
        assert login_response.status_code == 200
        refresh_token = login_response.get_json()["refresh_token"]

        time.sleep(2)  # Wait for the token to expire

        refresh_response = client.post(
            url_for("auth.refresh"),
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert refresh_response.status_code == 401
        data = refresh_response.get_json()
        assert "message" in data
        assert "The token has expired." in data["message"]

        # Restore original config if necessary, though app context teardown might handle it
        if original_expiry is not None:
            app.config["JWT_REFRESH_TOKEN_EXPIRES"] = original_expiry
        else:
            # If it wasn't set before, remove it or set to a default
            # For testing, it's often better to let fixtures handle app setup/teardown per test.
            pass
