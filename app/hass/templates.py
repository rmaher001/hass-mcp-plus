"""Home Assistant template rendering."""

import json
import logging
from typing import Any

from app.config import HA_URL, get_ha_headers
from app.hass.client import _rate_limiter, get_client
from app.hass.decorators import handle_api_errors
from app.hass.validation import validate_template

logger = logging.getLogger(__name__)


@handle_api_errors
async def render_template(template: str) -> Any:
    """
    Render a Jinja2 template using Home Assistant's template API.

    This leverages HA's powerful built-in template engine for flexible
    entity filtering using selectattr, area_entities, label_entities, etc.

    Security Note:
        Home Assistant's template engine uses a sandboxed Jinja2 environment
        that does not allow arbitrary Python code execution. The sandbox
        restricts access to only HA-specific functions and filters.
        Users with MCP access already have full HA API access via their token.

    Args:
        template: Jinja2 template string (HA Jinja2 syntax, not Python)

    Returns:
        The rendered result (can be string, list, dict, etc.)
        Returns {"error": "..."} if template rendering fails
    """
    validate_template(template)

    await _rate_limiter.acquire()
    client = await get_client()

    response = await client.post(
        f"{HA_URL}/api/template",
        headers=get_ha_headers(),
        json={"template": template}
    )

    if response.status_code != 200:
        logger.error("Template rendering failed: %s - %s", response.status_code, response.text)
        return {"error": f"Template rendering failed with status {response.status_code}"}

    # Response is the rendered result as text
    result = response.text

    # Try to parse as JSON if it looks like a list/dict
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        # Return as-is if not JSON (could be a simple string result)
        return result
