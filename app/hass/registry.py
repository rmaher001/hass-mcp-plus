"""Entity registry management via WebSocket API."""

import logging
from typing import Dict, Any, Optional

from app.hass.constants import (
    MAX_ENTITY_NAME_LENGTH,
    VALID_DISABLED_BY,
    VALID_HIDDEN_BY,
    DEFAULT_REGISTRY_LIMIT,
    MAX_REGISTRY_LIMIT,
)
from app.hass.decorators import handle_api_errors
from app.hass.validation import (
    ValidationError,
    validate_entity_id,
    validate_ha_identifier,
)
from app.hass.websocket import call_websocket_api

logger = logging.getLogger(__name__)

# Sentinel to distinguish "not provided" from None (which is a valid value
# for fields like disabled_by, hidden_by, name, icon, area_id).
_UNSET = object()


@handle_api_errors
async def remove_registry_entity(entity_id: str, confirm: bool = False) -> Dict[str, Any]:
    """
    Remove an entity from the Home Assistant entity registry.

    By default returns a preview of what would be deleted. Set confirm=True
    to actually perform the removal.

    Args:
        entity_id: The entity ID to remove (e.g., 'light.living_room')
        confirm: If False (default), return a preview. If True, delete.

    Returns:
        Preview dict (confirm=False) or success dict with removed entity details (confirm=True).
    """
    validate_entity_id(entity_id)

    # Always fetch entity details first (preview + audit trail)
    entity_details = await call_websocket_api(
        "config/entity_registry/get",
        entity_id=entity_id,
    )

    if not confirm:
        platform = entity_details.get("platform", "unknown")
        return {
            "action": "preview",
            "entity_id": entity_id,
            "entity_details": entity_details,
            "warning": (
                f"This will permanently remove the entity registry entry. "
                f"The entity may reappear if its integration ({platform}) "
                f"recreates it on restart."
            ),
            "suggestion": (
                "Consider using update_entity with disabled_by='user' "
                "to disable instead of removing."
            ),
            "confirm_required": True,
        }

    # Confirmed — proceed with deletion
    await call_websocket_api(
        "config/entity_registry/remove",
        entity_id=entity_id,
    )

    return {
        "success": True,
        "entity_id": entity_id,
        "removed_entity": entity_details,
    }


@handle_api_errors
async def update_registry_entity(
    entity_id: str,
    *,
    name: Any = _UNSET,
    icon: Any = _UNSET,
    disabled_by: Any = _UNSET,
    hidden_by: Any = _UNSET,
    area_id: Any = _UNSET,
    new_entity_id: Any = _UNSET,
    options: Any = _UNSET,
) -> Dict[str, Any]:
    """
    Update properties of an entity in the registry.

    Args:
        entity_id: The entity ID to update (e.g., 'light.living_room')
        name: Custom friendly name (str or None to clear)
        icon: Custom icon (str or None to clear)
        disabled_by: Set to 'user' to disable, None to enable
        hidden_by: Set to 'user' to hide, None to unhide
        area_id: Assign to an area (str or None to clear)
        new_entity_id: Rename the entity ID itself
        options: Entity platform options dict

    Returns:
        Dictionary with success status and updated entity entry, or error.
    """
    validate_entity_id(entity_id)

    # Build kwargs dict with only provided fields
    ws_kwargs: Dict[str, Any] = {}

    if name is not _UNSET:
        if name is not None:
            if not isinstance(name, str) or len(name) > MAX_ENTITY_NAME_LENGTH:
                raise ValidationError(
                    f"Entity name too long (maximum {MAX_ENTITY_NAME_LENGTH} characters)"
                )
        ws_kwargs["name"] = name

    if icon is not _UNSET:
        if icon is not None:
            if not isinstance(icon, str) or len(icon) > MAX_ENTITY_NAME_LENGTH:
                raise ValidationError(
                    f"Icon too long (maximum {MAX_ENTITY_NAME_LENGTH} characters)"
                )
        ws_kwargs["icon"] = icon

    if disabled_by is not _UNSET:
        if disabled_by is not None and disabled_by not in VALID_DISABLED_BY:
            raise ValidationError(
                f"Invalid disabled_by value: '{disabled_by}'. "
                f"Must be one of: {', '.join(sorted(VALID_DISABLED_BY))} or null"
            )
        ws_kwargs["disabled_by"] = disabled_by

    if hidden_by is not _UNSET:
        if hidden_by is not None and hidden_by not in VALID_HIDDEN_BY:
            raise ValidationError(
                f"Invalid hidden_by value: '{hidden_by}'. "
                f"Must be one of: {', '.join(sorted(VALID_HIDDEN_BY))} or null"
            )
        ws_kwargs["hidden_by"] = hidden_by

    if area_id is not _UNSET:
        ws_kwargs["area_id"] = area_id

    if new_entity_id is not _UNSET:
        if new_entity_id is not None:
            validate_entity_id(new_entity_id)
        ws_kwargs["new_entity_id"] = new_entity_id

    if options is not _UNSET:
        ws_kwargs["options"] = options

    if not ws_kwargs:
        raise ValidationError("No update fields provided")

    result = await call_websocket_api(
        "config/entity_registry/update",
        entity_id=entity_id,
        **ws_kwargs,
    )

    return {
        "success": True,
        "entity_id": entity_id,
        "result": result,
    }


@handle_api_errors
async def get_registry_entity(entity_id: str) -> Dict[str, Any]:
    """
    Get detailed registry entry for a single entity.

    Args:
        entity_id: The entity ID to look up (e.g., 'light.living_room')

    Returns:
        The full registry entry dict, or error.
    """
    validate_entity_id(entity_id)

    result = await call_websocket_api(
        "config/entity_registry/get",
        entity_id=entity_id,
    )

    return result


@handle_api_errors
async def list_registry_entities(
    limit: int = DEFAULT_REGISTRY_LIMIT,
    domain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List entity registry entries with optional domain filter.

    Args:
        limit: Maximum number of entities to return (default: 100)
        domain: Optional domain filter (e.g., 'light', 'sensor')

    Returns:
        Dictionary with entities list, count, total_available, truncated.
    """
    # Validate domain if provided
    if domain is not None:
        validate_ha_identifier(domain, "domain")

    # Enforce limit bounds
    limit = max(1, min(limit, MAX_REGISTRY_LIMIT))

    entries = await call_websocket_api("config/entity_registry/list")

    # Ensure entries is a list
    if not isinstance(entries, list):
        entries = []

    # Apply domain filter client-side
    if domain is not None:
        prefix = f"{domain}."
        entries = [e for e in entries if e.get("entity_id", "").startswith(prefix)]

    total_available = len(entries)
    truncated = total_available > limit
    limited = entries[:limit] if truncated else entries

    return {
        "entities": limited,
        "count": len(limited),
        "total_available": total_available,
        "truncated": truncated,
    }
