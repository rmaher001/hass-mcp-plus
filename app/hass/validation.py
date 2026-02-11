"""Input validation for Home Assistant API parameters.

Centralizes all input validation to prevent injection, path traversal,
and resource exhaustion attacks.
"""

import json
import logging
from typing import Optional
from urllib.parse import quote as _url_quote

from app.hass.constants import (
    ENTITY_ID_PATTERN,
    HA_IDENTIFIER_PATTERN,
    AUTOMATION_ID_PATTERN,
    RUN_ID_PATTERN,
    VALID_TRACE_DOMAINS,
    MAX_SERVICE_PAYLOAD_BYTES,
    MAX_TEMPLATE_LENGTH,
)

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Raised when input validation fails.

    Messages from this exception are safe to return to clients
    (they contain no internal details like URLs or stack traces).
    """

    pass


def validate_entity_id(entity_id: str) -> str:
    """
    Validate and return a safe entity_id.

    Args:
        entity_id: The entity ID to validate (e.g., 'light.living_room')

    Returns:
        The validated entity_id

    Raises:
        ValidationError: If entity_id format is invalid
    """
    if not entity_id or not isinstance(entity_id, str):
        raise ValidationError("Entity ID must be a non-empty string")

    if not ENTITY_ID_PATTERN.match(entity_id):
        raise ValidationError(
            f"Invalid entity ID format: '{entity_id}'. "
            f"Expected format: domain.object_id (e.g., 'light.living_room')"
        )

    return entity_id


def validate_ha_identifier(value: str, name: str = "identifier") -> str:
    """
    Validate a Home Assistant identifier (domain, service name, etc.).

    Args:
        value: The identifier to validate
        name: Human-readable name for error messages (e.g., 'domain', 'service')

    Returns:
        The validated identifier

    Raises:
        ValidationError: If the identifier format is invalid
    """
    if not value or not isinstance(value, str):
        raise ValidationError(f"{name.capitalize()} must be a non-empty string")

    if not HA_IDENTIFIER_PATTERN.match(value):
        raise ValidationError(
            f"Invalid {name}: '{value}'. "
            f"Must contain only lowercase letters, numbers, and underscores."
        )

    return value


def validate_automation_id(automation_id: str) -> str:
    """
    Validate an automation/script item ID.

    Args:
        automation_id: The automation ID (e.g., 'motion_light')

    Returns:
        The validated automation_id

    Raises:
        ValidationError: If the automation ID format is invalid
    """
    if not automation_id or not isinstance(automation_id, str):
        raise ValidationError("Automation ID must be a non-empty string")

    if not AUTOMATION_ID_PATTERN.match(automation_id):
        raise ValidationError(
            f"Invalid automation ID: '{automation_id}'. "
            f"Must contain only letters, numbers, underscores, and hyphens."
        )

    return automation_id


def validate_run_id(run_id: str) -> str:
    """
    Validate a trace run ID.

    Args:
        run_id: The run/trace ID (e.g., '1700000000.123456')

    Returns:
        The validated run_id

    Raises:
        ValidationError: If the run ID format is invalid
    """
    if not run_id or not isinstance(run_id, str):
        raise ValidationError("Run ID must be a non-empty string")

    if not RUN_ID_PATTERN.match(run_id):
        raise ValidationError(
            f"Invalid run ID format: '{run_id}'. "
            f"Must contain only letters, numbers, dots, underscores, and hyphens."
        )

    return run_id


def validate_trace_domain(domain: str) -> str:
    """
    Validate a trace domain (automation or script).

    Args:
        domain: The domain to validate

    Returns:
        The validated domain

    Raises:
        ValidationError: If the domain is not valid
    """
    if domain not in VALID_TRACE_DOMAINS:
        raise ValidationError(
            f"Invalid trace domain: '{domain}'. "
            f"Must be one of: {', '.join(sorted(VALID_TRACE_DOMAINS))}"
        )
    return domain


def validate_service_payload(
    data: Optional[dict],
    max_bytes: int = MAX_SERVICE_PAYLOAD_BYTES,
) -> Optional[dict]:
    """
    Validate service call payload size.

    Args:
        data: The service call data payload
        max_bytes: Maximum allowed size in bytes

    Returns:
        The validated data

    Raises:
        ValidationError: If payload exceeds size limit or is not serializable
    """
    if data is None:
        return data

    try:
        payload_size = len(json.dumps(data))
    except (TypeError, ValueError):
        raise ValidationError("Service data must be JSON-serializable")

    if payload_size > max_bytes:
        raise ValidationError(
            f"Service data payload too large: {payload_size:,} bytes "
            f"(maximum: {max_bytes:,} bytes)"
        )

    return data


def validate_template(
    template: str,
    max_length: int = MAX_TEMPLATE_LENGTH,
) -> str:
    """
    Validate template string.

    Args:
        template: The template string to validate
        max_length: Maximum allowed length

    Returns:
        The validated template

    Raises:
        ValidationError: If template is invalid or too large
    """
    if not template or not isinstance(template, str):
        raise ValidationError("Template must be a non-empty string")

    if len(template) > max_length:
        raise ValidationError(
            f"Template too large: {len(template):,} characters "
            f"(maximum: {max_length:,} characters)"
        )

    return template


def safe_url_path_segment(segment: str) -> str:
    """
    URL-encode a path segment for safe inclusion in URLs.

    Defense in depth: even after validation, encode to prevent any bypass.
    Letters, digits, and ``_.-~`` are never encoded per RFC 3986.

    Args:
        segment: The path segment to encode

    Returns:
        URL-encoded segment safe for path inclusion
    """
    return _url_quote(segment, safe="")
