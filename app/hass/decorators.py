"""Error handling decorators and logging sanitization."""

import functools
import inspect
import ssl
import logging
from typing import Any, TypeVar, Callable, Awaitable, cast

from app.config import HA_URL, HA_TOKEN

import httpx

from app.hass.constants import SENSITIVE_KEYS

logger = logging.getLogger(__name__)

# Define a generic type for our API function return values
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Awaitable[Any]])


def sanitize_for_logging(data: Any) -> Any:
    """
    Sanitize data for safe logging by redacting sensitive fields.

    Args:
        data: The data to sanitize (dict, list, or primitive)

    Returns:
        Sanitized copy of the data with sensitive values redacted
    """
    if isinstance(data, dict):
        return {
            k: "***REDACTED***" if k.lower() in SENSITIVE_KEYS else sanitize_for_logging(v)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [sanitize_for_logging(item) for item in data]
    else:
        return data


def handle_api_errors(func: F) -> F:
    """
    Decorator to handle common error cases for Home Assistant API calls.

    Security: Error messages returned to clients never include internal
    details such as HA_URL, stack traces, or raw exception messages.
    Full details are logged server-side for debugging.

    Args:
        func: The async function to decorate

    Returns:
        Wrapped function that handles errors
    """
    # Import here to avoid circular imports (validation imports constants,
    # decorators imports constants — no cycle, but keep locality clear)
    from app.hass.validation import ValidationError

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Determine return type from function annotation
        return_type = inspect.signature(func).return_annotation
        is_dict_return = 'Dict' in str(return_type)
        is_list_return = 'List' in str(return_type)

        # Prepare error formatters based on return type
        def format_error(msg: str) -> Any:
            if is_dict_return:
                return {"error": msg}
            elif is_list_return:
                return [{"error": msg}]
            else:
                return msg

        try:
            # Check if token is available
            if not HA_TOKEN:
                return format_error("No Home Assistant token provided. Please set HA_TOKEN in .env file.")

            # Call the original function
            return await func(*args, **kwargs)
        except ValidationError as e:
            # Validation errors contain safe, user-facing messages
            return format_error(str(e))
        except httpx.ConnectError as e:
            # Walk the exception chain to find SSL errors
            cause = e.__cause__
            while cause is not None:
                if isinstance(cause, ssl.SSLError):
                    logger.error("SSL certificate error connecting to Home Assistant at %s: %s", HA_URL, cause)
                    return format_error(
                        "SSL certificate error connecting to Home Assistant. "
                        "If using a self-signed certificate, set HA_VERIFY_SSL=false"
                    )
                cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)
            logger.error("Connection error to Home Assistant at %s: %s", HA_URL, e)
            return format_error("Connection error: Cannot connect to Home Assistant")
        except httpx.TimeoutException:
            logger.error("Timeout connecting to Home Assistant at %s", HA_URL)
            return format_error("Timeout error: Home Assistant did not respond in time")
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error from Home Assistant: %s %s", e.response.status_code, e.response.reason_phrase)
            return format_error(f"HTTP error: {e.response.status_code} - {e.response.reason_phrase}")
        except httpx.RequestError as e:
            logger.error("Request error connecting to Home Assistant at %s: %s", HA_URL, e)
            return format_error("Error connecting to Home Assistant")
        except Exception as e:
            logger.error("Unexpected error in %s: %s", func.__name__, e, exc_info=True)
            return format_error("An unexpected error occurred")

    return cast(F, wrapper)
