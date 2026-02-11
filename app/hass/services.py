"""Home Assistant service calls and system operations."""

import logging
from typing import Dict, Any, Optional

from app.config import HA_URL, get_ha_headers
from app.hass.client import _rate_limiter, get_client
from app.hass.decorators import handle_api_errors
from app.hass.validation import (
    validate_ha_identifier,
    validate_service_payload,
    safe_url_path_segment,
)

logger = logging.getLogger(__name__)


@handle_api_errors
async def call_service(domain: str, service: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call a Home Assistant service"""
    validate_ha_identifier(domain, "domain")
    validate_ha_identifier(service, "service")

    if data is None:
        data = {}
    else:
        validate_service_payload(data)

    await _rate_limiter.acquire()
    client = await get_client()
    response = await client.post(
        f"{HA_URL}/api/services/{safe_url_path_segment(domain)}/{safe_url_path_segment(service)}",
        headers=get_ha_headers(),
        json=data
    )
    response.raise_for_status()

    result = response.json()

    # Handle list responses from Home Assistant
    # Service calls return lists (empty or with changed entity data)
    if isinstance(result, list):
        result = {"result": result} if result else {}

    return result


@handle_api_errors
async def get_hass_version() -> str:
    """Get the Home Assistant version from the API"""
    await _rate_limiter.acquire()
    client = await get_client()
    response = await client.get(f"{HA_URL}/api/config", headers=get_ha_headers())
    response.raise_for_status()
    data = response.json()
    return data.get("version", "unknown")


@handle_api_errors
async def reload_automations() -> Dict[str, Any]:
    """Reload all automations in Home Assistant"""
    return await call_service("automation", "reload", {})


@handle_api_errors
async def restart_home_assistant() -> Dict[str, Any]:
    """Restart Home Assistant"""
    return await call_service("homeassistant", "restart", {})
