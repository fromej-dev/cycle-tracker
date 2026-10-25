import os

from apiflask import APIFlask
from flask import jsonify, send_from_directory

from app.config import Config, config_by_name, get_config_name
from app.controllers import register_blueprints, register_error_handlers
from app.extensions import db, jwt, ma, migrate
from app.models import Period, User
from app.services import UserService


def create_app(config_name: str | None = None) -> APIFlask:
    """
    Application factory function.
    Creates and configures the APIFlask application instance.

    Args:
        config_name (Optional[str]): The name of the configuration to use
                                     (e.g., 'development', 'testing', 'production').
                                     Defaults to FLASK_ENV or 'default'.

    Returns:
        APIFlask: The configured APIFlask application instance.
    """
    app = APIFlask(
        __name__,
        title="Period Tracker",
        instance_relative_config=True,
        static_folder="static",
        static_url_path="/static",
    )
    app.security_scheme = {
        "type": "http",
        "scheme": "bearerAuth",
    }

    if config_name is None:
        config_name = get_config_name()

    # Load configuration
    config_object: type[Config] = config_by_name[config_name]
    app.config.from_object(config_object)

    # Ensure instance folder exists if not already created by config
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        app.logger.error(f"Could not create instance folder at {app.instance_path}")
        pass  # Handle error appropriately

    # Initialize extensions
    db.init_app(app)
    ma.init_app(app)
    # Pass db and model base class (or specific models) to Migrate
    migrate.init_app(app, db)
    jwt.init_app(app)

    # --- JWT User Loading Callback ---
    # This function is called whenever a protected endpoint is accessed,
    # and a valid token is found. It extracts the 'identity' from the token
    # and should return the user object associated with that identity.
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        """
        This function is called whenever a protected endpoint is accessed,
        and a valid JWT is present.
        The 'jwt_data' argument contains the payload of the JWT.
        The 'identity' is stored in the 'sub' claim by default.
        """
        identity = jwt_data["sub"]

        # Use the UserService to find the user by ID based on the identity
        user = UserService.get_user_by_id(identity)

        # Return the user object. If None is returned, the protected endpoint
        # will return a 401 Unauthorized response.
        if user is None:
            print(
                f"User with ID {identity} not found from token identity"
            )  # Log this event
            return None

        return user

    # --- Optional: JWT Error Handling Callbacks ---
    # You can customize the response returned when JWT errors occur.
    @jwt.invalid_token_loader
    def invalid_token_callback(callback_options):
        """Return JSON response for invalid tokens."""
        # callback_options typically contains error message like "Invalid signature"
        return {
            "message": "Signature verification failed or token is malformed.",
            "error": "invalid_token",
        }, 401

    @jwt.expired_token_loader
    def expired_token_callback(_jwt_header, _jwt_payload):
        """Return JSON response for expired tokens."""
        return {"message": "The token has expired.", "error": "token_expired"}, 401

    @jwt.unauthorized_loader
    def unauthorized_callback(callback_options):
        """Return JSON response when no token is present."""
        # callback_options typically contains message like "Missing JWT"
        return {
            "message": "Request does not contain an access token.",
            "error": "authorization_required",
        }, 401

    # Register blueprints
    register_blueprints(app)

    # Register error handlers
    register_error_handlers(app)

    # Webhook CLI (`flask webhooks tick`) and optional in-process scheduler
    @app.cli.group("webhooks")
    def webhooks_cli():
        """Outgoing webhook maintenance."""

    @webhooks_cli.command("tick")
    def webhooks_tick():
        """Fire due time-driven events (expected soon / fertile window)."""
        from app.services.webhook_service import WebhookService

        print(WebhookService.tick())

    seconds = app.config.get("WEBHOOK_SCHEDULER_SECONDS", 0)
    if seconds and not app.config.get("TESTING"):
        from app.services.webhook_service import start_scheduler

        start_scheduler(app, seconds)

    # Shell context for Flask CLI (optional)
    @app.shell_context_processor
    def make_shell_context():
        return {"db": db, "User": User, "Period": Period}  # Add models and db

    # Simple health check endpoint
    @app.route("/health")
    def health_check():
        return jsonify({"status": "healthy"}), 200

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_vue_app(path):
        # Construct the full path to the requested file within the static directory
        file_path = os.path.join(app.static_folder, path)

        # Check if the requested path exists as an actual file within the static folder
        # This handles requests for files placed at the static root by Vite build (like manifest.webmanifest)
        # Flask's default static handler at /static/ handles assets within subdirectories like /static/js/app.js
        if path != "" and os.path.exists(file_path):
            # If the file exists in the static directory, serve it directly
            # send_from_directory is safe and prevents directory traversal
            return send_from_directory(app.static_folder, path)
        elif path == "":
            # Handle the root path specifically by serving index.html
            return send_from_directory(app.static_folder, "index.html")
        else:
            # For any other path that was not an API route, not a /static/ asset,
            # and not a file explicitly found at the static root,
            # assume it's a client-side route and serve the index.html fallback.
            return send_from_directory(app.static_folder, "index.html")

    app.logger.info(f"App created with config: {config_name}")
    app.logger.info(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

    return app
