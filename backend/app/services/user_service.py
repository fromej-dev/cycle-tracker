from app.models import User


class UserService:
    """Service layer for user-related operations."""

    @staticmethod
    def get_user_by_id(user_id: int) -> User | None:
        """Finds a user by their ID."""
        return User.get_by_id(user_id)

    @staticmethod
    def get_user_by_email(email: str) -> User | None:
        """Finds a user by their email."""
        return User.find_by_email(email)

    @staticmethod
    def get_user_by_username(username: str) -> User | None:
        """Finds a user by their username."""
        return User.find_by_username(username)

    @staticmethod
    def get_user_by_login(login: str) -> User | None:
        """Finds a user by either email or username."""
        user = User.find_by_email(login)
        if not user:
            user = User.find_by_username(login)
        return user

    @staticmethod
    def update_user(user: User, data: dict) -> User:
        """Update a user"""
        return user.update(**data)

    @staticmethod
    def update_password(user: User, new_password: str) -> None:
        """Updates a user's password."""
        user.set_password(new_password)
        user.save()

    @staticmethod
    def delete_user(user: User) -> None:
        """Deletes a user."""
        user.delete()
