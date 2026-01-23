from functools import wraps

from flask import request
from marshmallow import Schema
from marshmallow import ValidationError as MarshmallowValidationError

from app.utils.exceptions import ValidationError  # Your custom validation error


def validate_schema(schema: Schema):
    """
    Decorator to validate request JSON data against a Marshmallow schema.
    Handles Marshmallow's validation errors and raises a custom ValidationError.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # load() validates and deserializes data
                # Pass context if needed by schema validators
                schema.load(request.get_json(), context=request.get_json())
                # Optionally pass validated data to the route function
                # kwargs['validated_data'] = loaded_data
            except MarshmallowValidationError as err:
                # Raise your custom exception, passing Marshmallow's error messages
                raise ValidationError(payload=err.messages) from err
            except Exception as e:
                # Handle cases where JSON is missing or malformed
                if isinstance(e, (TypeError, ValueError)):  # common errors for bad JSON
                    raise ValidationError(message="Invalid JSON data provided.") from e
                raise  # Re-raise other unexpected errors
            return f(*args, **kwargs)  # Pass original args/kwargs

        return decorated_function

    return decorator


def validate_schema_with_data(schema: Schema):
    """
    Decorator like validate_schema, but passes the validated data
    as the first argument to the decorated function.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                loaded_data = schema.load(
                    request.get_json(), context=request.get_json()
                )
            except MarshmallowValidationError as err:
                raise ValidationError(payload=err.messages) from err
            except Exception as e:
                if isinstance(e, (TypeError, ValueError)):
                    raise ValidationError(message="Invalid JSON data provided.") from e
                raise
            # Pass loaded_data as the first arg, followed by others
            return f(loaded_data, *args, **kwargs)

        return decorated_function

    return decorator
