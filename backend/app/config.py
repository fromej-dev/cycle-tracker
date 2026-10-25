import logging
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

# Load environment variables from .env file
basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / ".env")


class Config:
    """Base configuration class."""

    # Secrets are resolved (and validated) at app creation by ``apply_runtime_config``;
    # there is deliberately no usable default here.
    SECRET_KEY = None
    JWT_SECRET_KEY = None
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES", 30))
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


# --- Runtime resolution (reads the environment at app-creation time) ---------------

MIN_SECRET_LENGTH = 32
DEV_SECRET_KEY = "dev-only-secret-key-do-not-use-in-production"
DEV_JWT_SECRET_KEY = "dev-only-jwt-secret-do-not-use-in-production"
KNOWN_DEFAULT_SECRETS = frozenset(
    {
        "you-will-never-guess",
        "super-secret-jwt",
        "test-secret-key",
        "test-jwt-secret",
        DEV_SECRET_KEY,
        DEV_JWT_SECRET_KEY,
        "changeme",
        "change-me",
        "secret",
    }
)
_GENERATE_HINT = 'python -c "import secrets;print(secrets.token_hex(32))"'


class InsecureConfigError(RuntimeError):
    """Raised at startup when production secrets are missing or weak."""


def secret_problem(value: str | None) -> str | None:
    """Return why ``value`` is unacceptable as a production secret, else None."""
    if value is None or not value.strip():
        return "missing or empty"
    if value in KNOWN_DEFAULT_SECRETS or value.strip() in KNOWN_DEFAULT_SECRETS:
        return "a known default value"
    if len(value) < MIN_SECRET_LENGTH:
        return f"shorter than {MIN_SECRET_LENGTH} characters"
    return None


def normalize_database_url(url: str) -> str:
    """Turn a Railway/Heroku style URL into one SQLAlchemy + psycopg2 accepts."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix) :]
    return url


def redact_database_uri(uri: str) -> str:
    """Database URI safe for logging (password hidden)."""
    try:
        return make_url(uri).render_as_string(hide_password=True)
    except Exception:
        return "<unparseable database uri>"


def apply_runtime_config(app, config_name: str) -> None:
    """Resolve secrets, database and public URL from the environment.

    Outside development/testing the app refuses to start without strong secrets.
    """
    log = logging.getLogger(__name__)
    env = os.environ
    is_dev = config_name in ("development", "default")
    is_test = config_name == "testing"

    if not is_test:
        problems = []
        values = {}
        for name, dev_default in (
            ("SECRET_KEY", DEV_SECRET_KEY),
            ("JWT_SECRET_KEY", DEV_JWT_SECRET_KEY),
        ):
            value = env.get(name)
            if is_dev:
                if not value or not value.strip():
                    log.warning(
                        "%s is not set: using an INSECURE development default. "
                        "Never run like this in production.",
                        name,
                    )
                    value = dev_default
                elif secret_problem(value):
                    log.warning("%s is weak (%s).", name, secret_problem(value))
            else:
                why = secret_problem(value)
                if why:
                    problems.append(f"  - {name}: {why}")
            values[name] = value
        if problems:
            raise InsecureConfigError(
                "Refusing to start: insecure secrets in the "
                f"'{config_name}' configuration.\n"
                + "\n".join(problems)
                + "\nSet SECRET_KEY and JWT_SECRET_KEY to different random values of "
                f"at least {MIN_SECRET_LENGTH} characters. Generate each with:\n"
                f"  {_GENERATE_HINT}"
            )
        app.config["SECRET_KEY"] = values["SECRET_KEY"]
        app.config["JWT_SECRET_KEY"] = values["JWT_SECRET_KEY"]

    # Public base URL: explicit setting wins, else Railway's server-side domain.
    public = (env.get("PUBLIC_BASE_URL") or "").strip()
    if not public:
        railway = (env.get("RAILWAY_PUBLIC_DOMAIN") or "").strip()
        if railway:
            public = f"https://{railway}"
    app.config["PUBLIC_BASE_URL"] = public or None

    if is_test:
        return

    database_url = (env.get("DATABASE_URL") or "").strip()
    if database_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(database_url)
    elif config_name == "production" and app.config[
        "SQLALCHEMY_DATABASE_URI"
    ].startswith("sqlite"):
        log.warning(
            "Production is using SQLite without DATABASE_URL. Data is LOST on every "
            "redeploy unless the database file lives on a persistent volume "
            "(set SQLITE_PATH to an absolute path on the volume, or attach "
            "PostgreSQL and set DATABASE_URL)."
        )
