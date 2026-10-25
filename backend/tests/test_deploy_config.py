import pytest

from app import create_app
from app.config import (
    InsecureConfigError,
    normalize_database_url,
    redact_database_uri,
    secret_problem,
)

GOOD_A = "a" * 16 + "b" * 16 + "c" * 16
GOOD_B = "d" * 16 + "e" * 16 + "f" * 16

ENV_VARS = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "DATABASE_URL",
    "PUBLIC_BASE_URL",
    "RAILWAY_PUBLIC_DOMAIN",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def prod(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return create_app("production")


def good(**extra):
    return dict(SECRET_KEY=GOOD_A, JWT_SECRET_KEY=GOOD_B, **extra)


def test_production_with_good_secrets(monkeypatch):
    app = prod(monkeypatch, **good())
    assert app.config["SECRET_KEY"] == GOOD_A
    assert app.config["JWT_SECRET_KEY"] == GOOD_B


def test_production_missing_secrets_names_variables(monkeypatch):
    with pytest.raises(InsecureConfigError) as exc:
        prod(monkeypatch)
    msg = str(exc.value)
    assert "SECRET_KEY" in msg and "JWT_SECRET_KEY" in msg
    assert "secrets.token_hex(32)" in msg


@pytest.mark.parametrize(
    "bad", ["", "   ", "short", "x" * 31, "you-will-never-guess", "super-secret-jwt"]
)
@pytest.mark.parametrize("which", ["SECRET_KEY", "JWT_SECRET_KEY"])
def test_production_rejects_bad_secret(monkeypatch, which, bad):
    env = good()
    env[which] = bad
    with pytest.raises(InsecureConfigError) as exc:
        prod(monkeypatch, **env)
    assert which in str(exc.value)


def test_production_rejects_missing_one(monkeypatch):
    with pytest.raises(InsecureConfigError) as exc:
        prod(monkeypatch, SECRET_KEY=GOOD_A)
    assert "JWT_SECRET_KEY" in str(exc.value)


def test_default_and_unknown_config_names_are_not_trusted(monkeypatch):
    # Any non-dev/test name must be strict (staging etc. would KeyError anyway).
    assert secret_problem("super-secret-jwt")
    assert secret_problem(GOOD_A) is None


def test_development_works_without_env_and_warns(monkeypatch, caplog):
    with caplog.at_level("WARNING"):
        app = create_app("development")
    assert app.config["SECRET_KEY"] and app.config["JWT_SECRET_KEY"]
    assert "INSECURE" in caplog.text


def test_testing_works_without_env():
    app = create_app("testing")
    assert app.config["SECRET_KEY"] == "test-secret-key"


def test_refresh_token_expiry_reads_own_variable(monkeypatch):
    import importlib

    import app.config as cfg

    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRES", "100")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRES", "7")
    try:
        importlib.reload(cfg)
        assert cfg.Config.JWT_REFRESH_TOKEN_EXPIRES.days == 7
        assert cfg.Config.JWT_ACCESS_TOKEN_EXPIRES.total_seconds() == 100
    finally:
        monkeypatch.undo()
        importlib.reload(cfg)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg2://u:p@h:5432/d"),
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg2://u:p@h:5432/d"),
        ("postgresql+psycopg2://u:p@h/d", "postgresql+psycopg2://u:p@h/d"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


def test_database_url_takes_precedence(monkeypatch):
    app = prod(
        monkeypatch,
        **good(DATABASE_URL="postgres://u:pw@db.internal:5432/rail", DB_TYPE="sqlite"),
    )
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert uri == "postgresql+psycopg2://u:pw@db.internal:5432/rail"


def test_redact_database_uri():
    out = redact_database_uri("postgresql+psycopg2://u:secretpw@h:5432/d")
    assert "secretpw" not in out


def test_database_url_password_not_logged(monkeypatch, caplog):
    with caplog.at_level("INFO"):
        prod(monkeypatch, **good(DATABASE_URL="postgres://u:topsecretpw@h:5432/d"))
    assert "topsecretpw" not in caplog.text


def test_production_sqlite_warns(monkeypatch, caplog):
    with caplog.at_level("WARNING"):
        app = prod(monkeypatch, **good())
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")
    assert "LOST on every redeploy" in caplog.text


def test_production_with_database_url_does_not_warn(monkeypatch, caplog):
    with caplog.at_level("WARNING"):
        prod(monkeypatch, **good(DATABASE_URL="postgres://u:p@h:5432/d"))
    assert "LOST" not in caplog.text


def test_public_base_url_explicit_wins(monkeypatch):
    app = prod(
        monkeypatch,
        **good(
            PUBLIC_BASE_URL="https://me.example",
            RAILWAY_PUBLIC_DOMAIN="x.up.railway.app",
        ),
    )
    assert app.config["PUBLIC_BASE_URL"] == "https://me.example"


def test_public_base_url_from_railway_domain(monkeypatch):
    app = prod(monkeypatch, **good(RAILWAY_PUBLIC_DOMAIN="x.up.railway.app"))
    assert app.config["PUBLIC_BASE_URL"] == "https://x.up.railway.app"


def test_public_base_url_unset(monkeypatch):
    app = prod(monkeypatch, **good())
    assert app.config["PUBLIC_BASE_URL"] is None
