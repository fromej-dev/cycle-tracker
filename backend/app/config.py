import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / ".env")


class Config:
    """Base configuration class."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "you-will-never-guess"
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or "super-secret-jwt"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 30))
    )

    # Optional externally visible base URL (e.g. https://cycle.example.com) used when
    # building the calendar feed URL behind a reverse proxy.
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

    # Outgoing webhooks: deliveries run in a background thread unless WEBHOOK_SYNC.
    # ALLOW_PRIVATE_WEBHOOKS=1 (environment) allows private/loopback targets.
    WEBHOOK_SYNC = False
    WEBHOOK_BACKOFF = (0.0, 1.0, 3.0)
    WEBHOOK_SCHEDULER_SECONDS = int(os.environ.get("WEBHOOK_SCHEDULER_SECONDS", 0))

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Define database path (creates 'instance' folder if it doesn't exist)
    INSTANCE_FOLDER_PATH = basedir / "instance"
    INSTANCE_FOLDER_PATH.mkdir(exist_ok=True)

    DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()

    if DB_TYPE == "postgresql":
        POSTGRES_USER = os.environ.get("POSTGRES_USER")
        POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
        POSTGRES_DB = os.environ.get("POSTGRES_DB")
        POSTGRES_HOST = os.environ.get(
            "POSTGRES_HOST", "localhost"
        )  # Default for local dev outside docker
        POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
            f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        )
    else:  # Default to SQLite
        SQLITE_PATH = os.environ.get("SQLITE_PATH", "instance/app.db")
        # Ensure the path is absolute or relative to the instance folder
        db_path = Path(SQLITE_PATH)
        if not db_path.is_absolute():
            db_path = INSTANCE_FOLDER_PATH / SQLITE_PATH
            db_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists

        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path.resolve()}"

    # Add other configurations as needed
    PROPAGATE_EXCEPTIONS = True  # Let Flask-JWT-Extended handle its errors


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    FLASK_ENV = "development"


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = (
        # Separate test DB per process so parallel test runs don't collide
        f"sqlite:///{Config.INSTANCE_FOLDER_PATH / f'test-{os.getpid()}.db'}"
    )
    JWT_SECRET_KEY = "test-jwt-secret"
    SECRET_KEY = "test-secret-key"
    WEBHOOK_SYNC = True
    WEBHOOK_BACKOFF = (0.0, 0.0, 0.0)
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing forms if needed


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    FLASK_ENV = "production"
    # Ensure DATABASE_URL is set correctly in production environment
    # e.g., SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')


# Dictionary to access configurations by name
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config_name() -> str:
    """Returns the configuration name based on FLASK_ENV."""
    return os.getenv("FLASK_ENV", "default")
