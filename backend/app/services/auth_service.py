from typing import Any

from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db
from app.models import User
from app.services.user_service import UserService
from app.utils.exceptions import AuthenticationError, RegistrationError


class AuthService:
    """Service layer for authentication logic."""

    @staticmethod
    def register_user(user_data: dict[str, Any]) -> User:
        """Registers a new user."""
        username = user_data["username"]
        email = user_data["email"]
        password = user_data["password"]

        # Check if username or email already exists
        if UserService.get_user_by_username(username):
            raise RegistrationError(f"Username '{username}' is already taken.")
        if UserService.get_user_by_email(email):
            raise RegistrationError(f"Email '{email}' is already registered.")

        # Create and save the new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)

        try:
            return new_user.save()
        except Exception as e:
            db.session.rollback()
            # Log the exception e
            raise RegistrationError(
                "Could not register user due to a database error."
            ) from e

    @staticmethod
    def login_user(login_data: dict[str, Any]) -> dict[str, str]:
        """Logs in a user and returns an access token."""
        login_identifier = login_data["login"]  # Can be username or email
        password = login_data["password"]

        user = UserService.get_user_by_login(login_identifier)

        if user and user.check_password(password):
            # Identity can be user ID or any unique identifier
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(
                identity=str(user.id)
            )  # Create refresh token
            return {"access_token": access_token, "refresh_token": refresh_token}
        else:
            raise AuthenticationError("Invalid credentials.")

    @staticmethod
    def refresh_access_token(identity: str) -> str:
        """Generates a new access token for the given identity."""
        user = UserService.get_user_by_id(int(identity))

        if user:
            new_access_token = create_access_token(identity=identity)
            return new_access_token
        else:
            raise AuthenticationError("Invalid refresh token.")
