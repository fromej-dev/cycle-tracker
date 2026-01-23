import os

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db as _db
from app.models import Period, User  # Import models


@pytest.fixture(scope="session")
def app():
    """Session-wide test Flask application."""
    # Ensure instance folder exists for testing config
    instance_path = os.path.join(os.path.dirname(__file__), "..", "instance")
    os.makedirs(instance_path, exist_ok=True)

    _app = create_app(config_name="testing")

    # Establish an application context before running tests.
    ctx = _app.app_context()
    ctx.push()

    yield _app  # Use the app in tests

    ctx.pop()
    # Clean up test database file after session
    db_path = _app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")  # Use function scope for DB isolation
def db(app):
    """Session-wide test database."""
    _db.app = app  # Associate db with the test app
    _db.create_all()  # Create tables

    yield _db  # Use the db session in tests

    _db.session.remove()  # Clean up session
    _db.drop_all()  # Drop tables after each test function


@pytest.fixture(scope="function")
def client(app, db):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope="function")
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


# --- Test Data Fixtures ---


@pytest.fixture(scope="function")
def test_user(db):
    """Create a test user."""
    user = User(username="testuser", email="test@example.com")
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture(scope="function")
def auth_client(client, test_user):
    """A test client pre-authenticated with the test_user's JWT."""
    # Need app context to create token
    with client.application.app_context():
        access_token = create_access_token(identity=str(test_user.id))
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {access_token}"
    # Also set content type for POST/PUT requests often needed with JSON
    client.environ_base["CONTENT_TYPE"] = "application/json"
    yield client
    # Clean up authorization header after use
    del client.environ_base["HTTP_AUTHORIZATION"]
    if "CONTENT_TYPE" in client.environ_base:
        del client.environ_base["CONTENT_TYPE"]


@pytest.fixture(scope="function")
def test_period(db, test_user):
    """Create a test period for the test user."""
    import datetime

    period = Period(
        user_id=test_user.id,
        start_date=datetime.date(2023, 1, 1),
        end_date=datetime.date(2023, 1, 5),
    )
    db.session.add(period)
    db.session.commit()
    return period


# Add more fixtures as needed (e.g., multiple periods for reports)
