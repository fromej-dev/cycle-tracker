from flask import Flask, jsonify, request
from marshmallow import ValidationError as MarshmallowValidationError

from app.utils.exceptions import BaseAppException
from app.utils.exceptions import ValidationError as CustomValidationError

from .auth_controller import auth_bp
from .calendar_controller import calendar_bp
from .events_controller import events_bp
from .period_controller import period_bp
from .report_controller import report_bp
from .users_controller import users_bp


def register_blueprints(app: Flask) -> None:
    """Registers all blueprints with the Flask app."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(period_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(users_bp)


def register_error_handlers(app: Flask) -> None:
    """Registers custom error handlers."""

    @app.errorhandler(CustomValidationError)
    def handle_validation_error(error: CustomValidationError):
        """Handles custom validation errors."""
        app.logger.warning(f"Validation Error: {error.to_dict()}")
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(MarshmallowValidationError)
    def handle_marshmallow_validation_error(error: MarshmallowValidationError):
        """Handles Marshmallow validation errors directly if decorator isn't used."""
        app.logger.warning(f"Marshmallow Validation Error: {error.messages}")
        # Wrap it in our standard format
        custom_error = CustomValidationError(payload=error.messages)
        return jsonify(custom_error.to_dict()), custom_error.status_code

    @app.errorhandler(BaseAppException)
    def handle_app_exception(error: BaseAppException):
        """Handles custom application exceptions."""
        app.logger.error(
            f"Application Exception [{error.status_code}]: {error.args[0]}",
            exc_info=True,
        )
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(404)
    def handle_not_found(error):
        """Handles generic 404 errors."""
        app.logger.warning(f"Not Found: {request.path}")
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(Exception)
    def handle_generic_exception(error: Exception):
        """Handles unexpected server errors."""
        # Log the full traceback for unexpected errors
        app.logger.error(f"Unhandled Exception: {error}", exc_info=True)
        # Avoid leaking internal details in production
        if app.config["DEBUG"]:
            response = {
                "error": "An unexpected internal server error occurred.",
                "details": str(error),
            }
        else:
            response = {"error": "An unexpected internal server error occurred."}
        return jsonify(response), 500
