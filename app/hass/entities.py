"""Entity state retrieval, filtering, and field selection."""

import logging
from typing import Dict, Any, Optional, List, Union

from cel import evaluate as cel_evaluate

from app.config import HA_URL, HA_TOKEN, get_ha_headers
from app.hass.client import _rate_limiter, get_client
from app.hass.constants import (
    DEFAULT_LEAN_FIELDS,
    DOMAIN_IMPORTANT_ATTRIBUTES,
)
from app.hass.decorators import handle_api_errors
from app.hass.validation import validate_entity_id, validate_ha_identifier, safe_url_path_segment

logger = logging.getLogger(__name__)


async def get_all_entity_states() -> Dict[str, Dict[str, Any]]:
    """Fetch all entity states from Home Assistant"""
    await _rate_limiter.acquire()
    client = await get_client()
    response = await client.get(f"{HA_URL}/api/states", headers=get_ha_headers())
    response.raise_for_status()
    entities = response.json()

    # Create a mapping for easier access
    return {entity["entity_id"]: entity for entity in entities}


def _coerce_state(state_value: str) -> Union[int, float, str]:
    """
    Coerce a state string to a numeric type if possible.

    Args:
        state_value: The raw state string from Home Assistant

    Returns:
        int, float, or the original string if not numeric
    """
    try:
        # Try int first (e.g., "25" -> 25)
        return int(state_value)
    except (ValueError, TypeError):
        pass
    try:
        # Try float (e.g., "72.5" -> 72.5)
        return float(state_value)
    except (ValueError, TypeError):
        pass
    return state_value


def evaluate_cel_filter(
    entities: List[Dict[str, Any]],
    expression: Optional[str],
    domain: Optional[str] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Filter entities using a CEL (Common Expression Language) expression.

    Each entity is evaluated against the expression with a context containing:
    - entity_id: string
    - state: numeric if possible, otherwise string
    - domain: string (extracted from entity_id)
    - attributes: dict of entity attributes

    Args:
        entities: List of entity dicts from HA /api/states
        expression: CEL expression string, or None to return all
        domain: Optional domain pre-filter (applied before CEL evaluation)

    Returns:
        List of matching entity dicts, or {"error": "..."} on CEL parse error
    """
    # Domain pre-filter
    if domain:
        entities = [e for e in entities if e["entity_id"].startswith(f"{domain}.")]

    # No expression means return all (after domain filter)
    if not expression:
        return entities

    # Validate expression by parsing it once with a dummy context
    try:
        cel_evaluate(expression, {
            "entity_id": "",
            "state": "",
            "domain": "",
            "attributes": {},
        })
    except ValueError as e:
        error_msg = str(e)
        if "parse" in error_msg.lower() or "syntax" in error_msg.lower():
            return {"error": f"Invalid CEL expression: {error_msg}"}
        # Execution errors on dummy data are fine - expression is syntactically valid

    matched = []
    for entity in entities:
        entity_id = entity.get("entity_id", "")
        raw_state = entity.get("state", "")
        entity_domain = entity_id.split(".")[0] if entity_id else ""

        context = {
            "entity_id": entity_id,
            "state": _coerce_state(raw_state),
            "domain": entity_domain,
            "attributes": entity.get("attributes", {}),
        }

        try:
            if cel_evaluate(expression, context):
                matched.append(entity)
        except (ValueError, TypeError):
            # Type mismatch (e.g., comparing "unavailable" < 30) - skip entity
            continue

    return matched


def filter_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """
    Filter entity data to only include requested fields

    This function helps reduce token usage by returning only requested fields.

    Args:
        data: The complete entity data dictionary
        fields: List of fields to include in the result
               - "state": Include the entity state
               - "attributes": Include all attributes
               - "attr.X": Include only attribute X (e.g. "attr.brightness")
               - "context": Include context data
               - "last_updated"/"last_changed": Include timestamp fields

    Returns:
        A filtered dictionary with only the requested fields
    """
    if not fields:
        return data

    result = {"entity_id": data["entity_id"]}

    for field in fields:
        if field == "state":
            result["state"] = data.get("state")
        elif field == "attributes":
            result["attributes"] = data.get("attributes", {})
        elif field.startswith("attr.") and len(field) > 5:
            attr_name = field[5:]
            attributes = data.get("attributes", {})
            if attr_name in attributes:
                if "attributes" not in result:
                    result["attributes"] = {}
                result["attributes"][attr_name] = attributes[attr_name]
        elif field == "context":
            if "context" in data:
                result["context"] = data["context"]
        elif field in ["last_updated", "last_changed"]:
            if field in data:
                result[field] = data[field]

    return result


@handle_api_errors
async def get_entity_state(
    entity_id: str,
    fields: Optional[List[str]] = None,
    lean: bool = False,
) -> Dict[str, Any]:
    """
    Get the state of a Home Assistant entity

    Args:
        entity_id: The entity ID to get
        fields: Optional list of specific fields to include in the response
        lean: If True, returns a token-efficient version with minimal fields
              (overridden by fields parameter if provided)

    Returns:
        Entity state dictionary, optionally filtered to include only specified fields
    """
    validate_entity_id(entity_id)

    # Fetch directly
    await _rate_limiter.acquire()
    client = await get_client()
    response = await client.get(
        f"{HA_URL}/api/states/{safe_url_path_segment(entity_id)}",
        headers=get_ha_headers()
    )
    response.raise_for_status()
    entity_data = response.json()

    # Apply field filtering if requested
    if fields:
        # User-specified fields take precedence
        return filter_fields(entity_data, fields)
    elif lean:
        # Build domain-specific lean fields
        lean_fields = DEFAULT_LEAN_FIELDS.copy()

        # Add domain-specific important attributes
        domain = entity_id.split('.')[0]
        if domain in DOMAIN_IMPORTANT_ATTRIBUTES:
            for attr in DOMAIN_IMPORTANT_ATTRIBUTES[domain]:
                lean_fields.append(f"attr.{attr}")

        return filter_fields(entity_data, lean_fields)
    else:
        # Return full entity data
        return entity_data


@handle_api_errors
async def get_entities(
    domain: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 100,
    fields: Optional[List[str]] = None,
    lean: bool = True,
    compact: bool = False
) -> List[Dict[str, Any]]:
    """
    Get a list of all entities from Home Assistant with optional filtering and search

    Args:
        domain: Optional domain to filter entities by (e.g., 'light', 'switch')
        search_query: Optional case-insensitive search term to filter by entity_id, friendly_name or other attributes
        limit: Maximum number of entities to return (default: 100)
        fields: Optional list of specific fields to include in each entity
        lean: If True (default), returns token-efficient versions with minimal fields
        compact: If True, returns minimal output (entity_id, state, friendly_name only).
                 Takes precedence over lean and fields.

    Returns:
        List of entity dictionaries, optionally filtered by domain and search terms,
        and optionally limited to specific fields
    """
    # Validate domain if provided (defense in depth — used for filtering, not in URL)
    if domain:
        validate_ha_identifier(domain, "domain")

    # Get all entities directly
    await _rate_limiter.acquire()
    client = await get_client()
    response = await client.get(f"{HA_URL}/api/states", headers=get_ha_headers())
    response.raise_for_status()
    entities = response.json()

    # Filter by domain if specified
    if domain:
        entities = [entity for entity in entities if entity["entity_id"].startswith(f"{domain}.")]

    # Search if query is provided
    if search_query and search_query.strip():
        search_term = search_query.lower().strip()
        filtered_entities = []

        for entity in entities:
            # Search in entity_id
            if search_term in entity["entity_id"].lower():
                filtered_entities.append(entity)
                continue

            # Search in friendly_name
            friendly_name = entity.get("attributes", {}).get("friendly_name", "").lower()
            if friendly_name and search_term in friendly_name:
                filtered_entities.append(entity)
                continue

            # Search in other common attributes (state, area_id, etc.)
            if search_term in entity.get("state", "").lower():
                filtered_entities.append(entity)
                continue

            # Search in other attributes
            for attr_name, attr_value in entity.get("attributes", {}).items():
                # Check if attribute value can be converted to string
                if isinstance(attr_value, (str, int, float, bool)):
                    if search_term in str(attr_value).lower():
                        filtered_entities.append(entity)
                        break

        entities = filtered_entities

    # Apply the limit
    if limit > 0 and len(entities) > limit:
        entities = entities[:limit]

    # Apply field filtering based on mode (compact takes precedence)
    if compact:
        # Compact mode: only entity_id, state, friendly_name
        result = []
        for entity in entities:
            compact_entity = {
                "entity_id": entity["entity_id"],
                "state": entity.get("state"),
                "friendly_name": entity.get("attributes", {}).get("friendly_name", entity["entity_id"])
            }
            result.append(compact_entity)
        return result
    elif fields:
        # Use explicit field list when provided
        return [filter_fields(entity, fields) for entity in entities]
    elif lean:
        # Apply domain-specific lean fields to each entity
        result = []
        for entity in entities:
            # Get the entity's domain
            entity_domain = entity["entity_id"].split('.')[0]

            # Start with basic lean fields
            lean_fields = DEFAULT_LEAN_FIELDS.copy()

            # Add domain-specific important attributes
            if entity_domain in DOMAIN_IMPORTANT_ATTRIBUTES:
                for attr in DOMAIN_IMPORTANT_ATTRIBUTES[entity_domain]:
                    lean_fields.append(f"attr.{attr}")

            # Filter and add to result
            result.append(filter_fields(entity, lean_fields))

        return result
    else:
        # Return full entities
        return entities
