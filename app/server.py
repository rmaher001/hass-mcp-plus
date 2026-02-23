import functools
import logging
import json
import httpx
from typing import List, Dict, Any, Optional, Callable, Awaitable, TypeVar, cast

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from app.hass import (
    get_hass_version, get_entity_state,
    call_service as hass_call_service,
    get_entities,
    get_automations, restart_home_assistant,
    cleanup_client, filter_fields, summarize_domain, get_system_overview,
    get_hass_error_log, get_entity_history, get_entity_history_range,
    list_automation_traces as hass_list_automation_traces,
    get_automation_trace as hass_get_automation_trace,
    sanitize_for_logging, render_template,
    get_all_entity_states, evaluate_cel_filter,
    get_hass_core_logs, set_hass_log_level,
    remove_registry_entity, update_registry_entity,
    get_registry_entity as hass_get_registry_entity,
    list_registry_entities,
    # Context flooding prevention constants
    DEFAULT_HISTORY_LIMIT, MAX_HISTORY_LIMIT,
    DEFAULT_ERROR_LOG_LIMIT, MAX_ERROR_LOG_LIMIT,
    DEFAULT_CORE_LOG_LIMIT, MAX_CORE_LOG_LIMIT,
    DEFAULT_AUTOMATION_LIMIT, MAX_AUTOMATION_LIMIT,
    DEFAULT_ALL_ENTITIES_LIMIT, DEFAULT_DOMAIN_ENTITIES_LIMIT,
    VALID_SAMPLE_STRATEGIES,
    # Domain-specific attributes for lean formatting
    DOMAIN_IMPORTANT_ATTRIBUTES
)

# Type variable for generic functions
T = TypeVar('T')

# Create an MCP server
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server
import mcp.types as types
mcp = FastMCP("Hass-MCP")

def async_handler(command_type: str):
    """
    Simple decorator that logs the command
    
    Args:
        command_type: The type of command (for logging)
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            logger.info(f"Executing command: {command_type}")
            return await func(*args, **kwargs)
        return cast(Callable[..., Awaitable[T]], wrapper)
    return decorator


def _simplify_entity(entity: dict) -> dict:
    """Create a simplified entity dict with domain-specific key attributes."""
    domain = entity["entity_id"].split(".")[0]
    attrs = entity.get("attributes", {})
    simplified = {
        "entity_id": entity["entity_id"],
        "state": entity["state"],
        "domain": domain,
        "friendly_name": attrs.get("friendly_name", entity["entity_id"]),
    }
    if domain == "light" and "brightness" in attrs:
        simplified["brightness"] = attrs["brightness"]
    elif domain == "sensor" and "unit_of_measurement" in attrs:
        simplified["unit"] = attrs["unit_of_measurement"]
    elif domain == "climate" and "temperature" in attrs:
        simplified["temperature"] = attrs["temperature"]
    elif domain == "media_player" and "media_title" in attrs:
        simplified["media_title"] = attrs["media_title"]
    return simplified


@mcp.tool()
@async_handler("get_version")
async def get_version() -> str:
    """
    Get the Home Assistant version
    
    Returns:
        A string with the Home Assistant version (e.g., "2025.3.0")
    """
    logger.info("Getting Home Assistant version")
    return await get_hass_version()

@mcp.tool()
@async_handler("get_entity")
async def get_entity(entity_id: str, fields: Optional[List[str]] = None, detailed: bool = False) -> dict:
    """
    Get the state of a Home Assistant entity with optional field filtering
    
    Args:
        entity_id: The entity ID to get (e.g. 'light.living_room')
        fields: Optional list of fields to include (e.g. ['state', 'attr.brightness'])
        detailed: If True, returns all entity fields without filtering
                
    Examples:
        entity_id="light.living_room" - basic state check
        entity_id="light.living_room", fields=["state", "attr.brightness"] - specific fields
        entity_id="light.living_room", detailed=True - all details
    """
    logger.info(f"Getting entity state: {entity_id}")
    if detailed:
        # Return all fields
        return await get_entity_state(entity_id, lean=False)
    elif fields:
        # Return only the specified fields
        return await get_entity_state(entity_id, fields=fields)
    else:
        # Return lean format with essential fields
        return await get_entity_state(entity_id, lean=True)

@mcp.tool()
@async_handler("entity_action")
async def entity_action(entity_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> dict:
    """
    Perform an action on a Home Assistant entity (on, off, toggle)
    
    Args:
        entity_id: The entity ID to control (e.g. 'light.living_room')
        action: The action to perform ('on', 'off', 'toggle')
        params: Optional dictionary of additional parameters for the service call
    
    Returns:
        The response from Home Assistant
    
    Examples:
        entity_id="light.living_room", action="on", params={"brightness": 255}
        entity_id="switch.garden_lights", action="off"
        entity_id="climate.living_room", action="on", params={"temperature": 22.5}
    
    Domain-Specific Parameters:
        - Lights: brightness (0-255), color_temp, rgb_color, transition, effect
        - Covers: position (0-100), tilt_position
        - Climate: temperature, target_temp_high, target_temp_low, hvac_mode
        - Media players: source, volume_level (0-1)
    """
    if action not in ["on", "off", "toggle"]:
        return {"error": f"Invalid action: {action}. Valid actions are 'on', 'off', 'toggle'"}
    
    # Map action to service name
    service = action if action == "toggle" else f"turn_{action}"
    
    # Extract the domain from the entity_id
    domain = entity_id.split(".")[0]
    
    # Prepare service data
    data = {"entity_id": entity_id, **(params or {})}
    
    logger.info(f"Performing action '{action}' on entity: {entity_id} with params: {sanitize_for_logging(params)}")
    return await hass_call_service(domain, service, data)

@mcp.resource("hass://entities/{entity_id}")
@async_handler("get_entity_resource")
async def get_entity_resource(entity_id: str) -> str:
    """
    Get the state of a Home Assistant entity as a resource
    
    This endpoint provides a standard view with common entity information.
    For comprehensive attribute details, use the /detailed endpoint.
    
    Args:
        entity_id: The entity ID to get information for
    """
    logger.info(f"Getting entity resource: {entity_id}")
    
    # Get the entity state with caching (using lean format for token efficiency)
    state = await get_entity_state(entity_id, lean=True)
    
    # Check if there was an error
    if "error" in state:
        return f"# Entity: {entity_id}\n\nError retrieving entity: {state['error']}"
    
    # Format the entity as markdown
    result = f"# Entity: {entity_id}\n\n"
    
    # Get friendly name if available
    friendly_name = state.get("attributes", {}).get("friendly_name")
    if friendly_name and friendly_name != entity_id:
        result += f"**Name**: {friendly_name}\n\n"
    
    # Add state
    result += f"**State**: {state.get('state')}\n\n"
    
    # Add domain info
    domain = entity_id.split(".")[0]
    result += f"**Domain**: {domain}\n\n"
    
    # Add key attributes based on domain type
    attributes = state.get("attributes", {})
    
    # Add a curated list of important attributes
    important_attrs = []
    
    # Common attributes across many domains
    common_attrs = ["device_class", "unit_of_measurement", "friendly_name"]
    
    # Domain-specific important attributes
    if domain == "light":
        important_attrs = ["brightness", "color_temp", "rgb_color", "supported_features", "supported_color_modes"] 
    elif domain == "sensor":
        important_attrs = ["unit_of_measurement", "device_class", "state_class"]
    elif domain == "climate":
        important_attrs = ["hvac_mode", "hvac_action", "temperature", "current_temperature", "target_temp_*"]
    elif domain == "media_player":
        important_attrs = ["media_title", "media_artist", "source", "volume_level", "media_content_type"]
    elif domain == "switch" or domain == "binary_sensor":
        important_attrs = ["device_class", "is_on"]
    
    # Combine with common attributes
    important_attrs.extend(common_attrs)
    
    # Deduplicate the list while preserving order
    important_attrs = list(dict.fromkeys(important_attrs))
    
    # Create and add the important attributes section
    result += "## Key Attributes\n\n"
    
    # Display only the important attributes that exist
    displayed_attrs = 0
    for attr_name in important_attrs:
        # Handle wildcard attributes (e.g., target_temp_*)
        if attr_name.endswith("*"):
            prefix = attr_name[:-1]
            matching_attrs = [name for name in attributes if name.startswith(prefix)]
            for name in matching_attrs:
                result += f"- **{name}**: {attributes[name]}\n"
                displayed_attrs += 1
        # Regular attribute match
        elif attr_name in attributes:
            attr_value = attributes[attr_name]
            if isinstance(attr_value, (list, dict)) and len(str(attr_value)) > 100:
                result += f"- **{attr_name}**: *[Complex data]*\n"
            else:
                result += f"- **{attr_name}**: {attr_value}\n"
            displayed_attrs += 1
    
    # If no important attributes were found, show a message
    if displayed_attrs == 0:
        result += "No key attributes found for this entity type.\n\n"
    
    # Add attribute count and link to detailed view
    total_attr_count = len(attributes)
    if total_attr_count > displayed_attrs:
        hidden_count = total_attr_count - displayed_attrs
        result += f"\n**Note**: Showing {displayed_attrs} of {total_attr_count} total attributes. "
        result += f"{hidden_count} additional attributes are available in the [detailed view](/api/resource/hass://entities/{entity_id}/detailed).\n\n"
    
    # Add last updated time if available
    if "last_updated" in state:
        result += f"**Last Updated**: {state['last_updated']}\n"
    
    return result

@mcp.tool()
@async_handler("list_entities")
async def list_entities(
    domain: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 100,
    fields: Optional[List[str]] = None,
    detailed: bool = False,
    compact: bool = False
) -> List[Dict[str, Any]]:
    """
    Get a list of Home Assistant entities with optional filtering

    Args:
        domain: Optional domain to filter by (e.g., 'light', 'switch', 'sensor')
        search_query: Optional search term to filter entities by name, id, or attributes
                     (Note: Does not support wildcards. To get all entities, leave this empty)
        limit: Maximum number of entities to return (default: 100)
        fields: Optional list of specific fields to include in each entity
        detailed: If True, returns all entity fields without filtering
        compact: If True, returns minimal output (entity_id, state, friendly_name only).
                 Takes precedence over detailed and fields. Best for large result sets.

    Returns:
        A list of entity dictionaries with lean formatting by default

    Examples:
        domain="light" - get all lights
        search_query="kitchen", limit=20 - search entities
        domain="sensor", detailed=True - full sensor details
        compact=True - minimal output for token efficiency

    Best Practices:
        - Use compact=True when you need many entities but minimal detail
        - Use lean format (default) for most operations
        - Prefer domain filtering over no filtering
        - For domain overviews, use domain_summary instead of list_entities
        - Only request detailed=True when necessary for full attribute inspection
        - To get all entity types/domains, use list_entities without a domain filter,
          then extract domains from entity_ids
    """
    log_message = "Getting entities"
    if domain:
        log_message += f" for domain: {domain}"
    if search_query:
        log_message += f" matching: '{search_query}'"
    if limit != 100:
        log_message += f" (limit: {limit})"
    if compact:
        log_message += " (compact format)"
    elif detailed:
        log_message += " (detailed format)"
    elif fields:
        log_message += f" (custom fields: {fields})"
    else:
        log_message += " (lean format)"

    logger.info(log_message)

    # Handle special case where search_query is a wildcard/asterisk - just ignore it
    if search_query == "*":
        search_query = None
        logger.info("Converting '*' search query to None (retrieving all entities)")

    # Use the updated get_entities function with field filtering
    return await get_entities(
        domain=domain,
        search_query=search_query,
        limit=limit,
        fields=fields,
        lean=not detailed,  # Use lean format unless detailed is requested
        compact=compact
    )

@mcp.resource("hass://entities")
@async_handler("get_all_entities_resource")
async def get_all_entities_resource() -> str:
    """
    Get a list of Home Assistant entities as a resource (LIMITED to prevent context flooding)

    CONTEXT FLOODING PREVENTION:
    - Output is LIMITED to 200 entities by default
    - For full entity lists, use the list_entities tool with pagination

    Returns:
        A markdown formatted string listing entities grouped by domain

    Examples:
        ```
        # Get entities (limited)
        entities = mcp.get_resource("hass://entities")
        ```

    Best Practices:
        - Prefer domain-filtered endpoints: hass://entities/domain/{domain}
        - For overview information, use domain summaries instead of full entity lists
        - Use the list_entities tool for more control over results
    """
    logger.info("Getting all entities as a resource (limited)")

    # Get all entities first to count total, but use compact mode
    all_entities = await get_entities(limit=0, compact=True)  # limit=0 means no limit

    # Check if there was an error
    if isinstance(all_entities, dict) and "error" in all_entities:
        return f"Error retrieving entities: {all_entities['error']}"
    if len(all_entities) == 1 and isinstance(all_entities[0], dict) and "error" in all_entities[0]:
        return f"Error retrieving entities: {all_entities[0]['error']}"

    total_count = len(all_entities)
    truncated = total_count > DEFAULT_ALL_ENTITIES_LIMIT

    # Apply limit
    entities = all_entities[:DEFAULT_ALL_ENTITIES_LIMIT] if truncated else all_entities

    # Format the entities as a string
    result = "# Home Assistant Entities\n\n"

    if truncated:
        result += f"⚠️ **TRUNCATED**: Showing {len(entities)} of {total_count} entities\n\n"
        result += "To see more entities, use:\n"
        result += "- `list_entities` tool with higher limit\n"
        result += "- Domain-filtered endpoints: `hass://entities/domain/{domain}`\n\n"
    else:
        result += f"Total entities: {total_count}\n\n"

    result += "**Tip**: For better token efficiency, consider using:\n"
    result += "- Domain filtering: `hass://entities/domain/{domain}`\n"
    result += "- Domain summaries: `hass://entities/domain/{domain}/summary`\n"
    result += "- Entity search: `hass://search/{query}`\n\n"

    # Group entities by domain for better organization
    domains = {}
    for entity in entities:
        domain = entity["entity_id"].split(".")[0]
        if domain not in domains:
            domains[domain] = []
        domains[domain].append(entity)

    # Build the string with entities grouped by domain
    for domain in sorted(domains.keys()):
        domain_count = len(domains[domain])
        result += f"## {domain.capitalize()} ({domain_count})\n\n"
        for entity in sorted(domains[domain], key=lambda e: e["entity_id"]):
            # Get a friendly name if available (compact mode has friendly_name at top level)
            friendly_name = entity.get("friendly_name", "")
            result += f"- **{entity['entity_id']}**: {entity['state']}"
            if friendly_name and friendly_name != entity["entity_id"]:
                result += f" ({friendly_name})"
            result += "\n"
        result += "\n"

    return result

@mcp.tool()
@async_handler("search_entities")
async def search_entities(query: str, limit: int = 20) -> Dict[str, Any]:
    """
    Search for entities matching a query string
    
    Args:
        query: The search query to match against entity IDs, names, and attributes.
              (Note: Does not support wildcards. To get all entities, leave this blank or use list_entities tool)
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        A dictionary containing search results and metadata:
        - count: Total number of matching entities found
        - results: List of matching entities with essential information
        - domains: Map of domains with counts (e.g. {"light": 3, "sensor": 2})
        
    Examples:
        query="temperature" - find temperature entities
        query="living room", limit=10 - find living room entities
        query="", limit=500 - list all entity types
        
    """
    logger.info(f"Searching for entities matching: '{query}' with limit: {limit}")
    
    # Special case - treat "*" as empty query to just return entities without filtering
    if query == "*":
        query = ""
        logger.info("Converting '*' to empty query (retrieving all entities up to limit)")
    
    # Handle empty query as a special case to just return entities up to the limit
    if not query or not query.strip():
        logger.info(f"Empty query - retrieving up to {limit} entities without filtering")
        entities = await get_entities(limit=limit, lean=True)
        
        # Check if there was an error
        if isinstance(entities, dict) and "error" in entities:
            return {"error": entities["error"], "count": 0, "results": [], "domains": {}}
        
        # No query, but we'll return a structured result anyway
        domains_count = {}
        simplified_entities = []
        
        for entity in entities:
            simplified = _simplify_entity(entity)
            domain = simplified["domain"]
            if domain not in domains_count:
                domains_count[domain] = 0
            domains_count[domain] += 1
            simplified_entities.append(simplified)

        # Return structured response for empty query
        return {
            "count": len(simplified_entities),
            "results": simplified_entities,
            "domains": domains_count,
            "query": "all entities (no filtering)"
        }
    
    # Normal search with non-empty query
    entities = await get_entities(search_query=query, limit=limit, lean=True)
    
    # Check if there was an error
    if isinstance(entities, dict) and "error" in entities:
        return {"error": entities["error"], "count": 0, "results": [], "domains": {}}
    
    # Prepare the results
    domains_count = {}
    simplified_entities = []
    
    for entity in entities:
        simplified = _simplify_entity(entity)
        domain = simplified["domain"]
        if domain not in domains_count:
            domains_count[domain] = 0
        domains_count[domain] += 1
        simplified_entities.append(simplified)

    # Return structured response
    return {
        "count": len(simplified_entities),
        "results": simplified_entities,
        "domains": domains_count,
        "query": query
    }
    
@mcp.resource("hass://search/{query}/{limit}")
@async_handler("search_entities_resource_with_limit")
async def search_entities_resource_with_limit(query: str, limit: str) -> str:
    """
    Search for entities matching a query string with a specified result limit
    
    This endpoint extends the basic search functionality by allowing you to specify
    a custom limit on the number of results returned. It's useful for both broader
    searches (larger limit) and more focused searches (smaller limit).
    
    Args:
        query: The search query to match against entity IDs, names, and attributes
        limit: Maximum number of entities to return (as a string, will be converted to int)
    
    Returns:
        A markdown formatted string with search results and a JSON summary
        
    Examples:
        ```
        # Search with a larger limit (up to 50 results)
        results = mcp.get_resource("hass://search/sensor/50")
        
        # Search with a smaller limit for focused results
        results = mcp.get_resource("hass://search/kitchen/5")
        ```
        
    Best Practices:
        - Use smaller limits (5-10) for focused searches where you need just a few matches
        - Use larger limits (30-50) for broader searches when you need more comprehensive results
        - Balance larger limits against token usage - more results means more tokens
        - Consider domain-specific searches for better precision: "light kitchen" instead of just "kitchen"
    """
    try:
        limit_int = int(limit)
        if limit_int <= 0:
            limit_int = 20
    except ValueError:
        limit_int = 20
        
    logger.info(f"Searching for entities matching: '{query}' with custom limit: {limit_int}")
    
    if not query or not query.strip():
        return "# Entity Search\n\nError: No search query provided"
    
    entities = await get_entities(search_query=query, limit=limit_int, lean=True)
    
    # Check if there was an error
    if isinstance(entities, dict) and "error" in entities:
        return f"# Entity Search\n\nError retrieving entities: {entities['error']}"
    
    # Format the search results
    result = f"# Entity Search Results for '{query}' (Limit: {limit_int})\n\n"
    
    if not entities:
        result += "No entities found matching your search query.\n"
        return result
    
    result += f"Found {len(entities)} matching entities:\n\n"
    
    # Group entities by domain for better organization
    domains = {}
    for entity in entities:
        domain = entity["entity_id"].split(".")[0]
        if domain not in domains:
            domains[domain] = []
        domains[domain].append(entity)
    
    # Build the string with entities grouped by domain
    for domain in sorted(domains.keys()):
        result += f"## {domain.capitalize()}\n\n"
        for entity in sorted(domains[domain], key=lambda e: e["entity_id"]):
            # Get a friendly name if available
            friendly_name = entity.get("attributes", {}).get("friendly_name", entity["entity_id"])
            result += f"- **{entity['entity_id']}**: {entity['state']}"
            if friendly_name != entity["entity_id"]:
                result += f" ({friendly_name})"
            result += "\n"
        result += "\n"
    
    # Add a more structured summary section for easy LLM processing
    result += "## Summary in JSON format\n\n"
    result += "```json\n"
    
    # Create a simplified JSON representation with only essential fields
    simplified_entities = [_simplify_entity(entity) for entity in entities]
    
    result += json.dumps(simplified_entities, indent=2)
    result += "\n```\n"
    
    return result

# The domain_summary is already implemented, no need to duplicate it

@mcp.tool()
@async_handler("domain_summary")
async def domain_summary(domain: str, example_limit: int = 3) -> Dict[str, Any]:
    """
    Get a summary of entities in a specific domain
    
    Args:
        domain: The domain to summarize (e.g., 'light', 'switch', 'sensor')
        example_limit: Maximum number of examples to include for each state
    
    Returns:
        A dictionary containing:
        - total_count: Number of entities in the domain
        - state_distribution: Count of entities in each state
        - examples: Sample entities for each state
        - common_attributes: Most frequently occurring attributes
        
    Examples:
        domain="light" - get light summary
        domain="climate", example_limit=5 - climate summary with more examples
    Best Practices:
        - Use this before retrieving all entities in a domain to understand what's available    """
    logger.info(f"Getting domain summary for: {domain}")
    return await summarize_domain(domain, example_limit)

@mcp.tool()
@async_handler("system_overview")
async def system_overview() -> Dict[str, Any]:
    """
    Get a comprehensive overview of the entire Home Assistant system
    
    Returns:
        A dictionary containing:
        - total_entities: Total count of all entities
        - domains: Dictionary of domains with their entity counts and state distributions
        - domain_samples: Representative sample entities for each domain (2-3 per domain)
        - domain_attributes: Common attributes for each domain
        - area_distribution: Entities grouped by area (if available)
        
    Examples:
        Returns domain counts, sample entities, and common attributes
    Best Practices:
        - Use this as the first call when exploring an unfamiliar Home Assistant instance
        - Perfect for building context about the structure of the smart home
        - After getting an overview, use domain_summary to dig deeper into specific domains
    """
    logger.info("Generating complete system overview")
    return await get_system_overview()

@mcp.resource("hass://entities/{entity_id}/detailed")
@async_handler("get_entity_resource_detailed")
async def get_entity_resource_detailed(entity_id: str) -> str:
    """
    Get detailed information about a Home Assistant entity as a resource
    
    Use this detailed view selectively when you need to:
    - Understand all available attributes of an entity
    - Debug entity behavior or capabilities
    - See comprehensive state information
    
    For routine operations where you only need basic state information,
    prefer the standard entity endpoint or specify fields in the get_entity tool.
    
    Args:
        entity_id: The entity ID to get information for
    """
    logger.info(f"Getting detailed entity resource: {entity_id}")
    
    # Get all fields, no filtering (detailed view explicitly requests all data)
    state = await get_entity_state(entity_id, lean=False)
    
    # Check if there was an error
    if "error" in state:
        return f"# Entity: {entity_id}\n\nError retrieving entity: {state['error']}"
    
    # Format the entity as markdown
    result = f"# Entity: {entity_id} (Detailed View)\n\n"
    
    # Get friendly name if available
    friendly_name = state.get("attributes", {}).get("friendly_name")
    if friendly_name and friendly_name != entity_id:
        result += f"**Name**: {friendly_name}\n\n"
    
    # Add state
    result += f"**State**: {state.get('state')}\n\n"
    
    # Add domain and entity type information
    domain = entity_id.split(".")[0]
    result += f"**Domain**: {domain}\n\n"
    
    # Add usage guidance
    result += "## Usage Note\n"
    result += "This is the detailed view showing all entity attributes. For token-efficient interactions, "
    result += "consider using the standard entity endpoint or the get_entity tool with field filtering.\n\n"
    
    # Add all attributes with full details
    attributes = state.get("attributes", {})
    if attributes:
        result += "## Attributes\n\n"
        
        # Sort attributes for better organization
        sorted_attrs = sorted(attributes.items())
        
        # Format each attribute with complete information
        for attr_name, attr_value in sorted_attrs:
            # Format the attribute value
            if isinstance(attr_value, (list, dict)):
                attr_str = json.dumps(attr_value, indent=2)
                result += f"- **{attr_name}**:\n```json\n{attr_str}\n```\n"
            else:
                result += f"- **{attr_name}**: {attr_value}\n"
    
    # Add context data section
    result += "\n## Context Data\n\n"
    
    # Add last updated time if available
    if "last_updated" in state:
        result += f"**Last Updated**: {state['last_updated']}\n"
    
    # Add last changed time if available
    if "last_changed" in state:
        result += f"**Last Changed**: {state['last_changed']}\n"
    
    # Add entity ID and context information
    if "context" in state:
        context = state["context"]
        result += f"**Context ID**: {context.get('id', 'N/A')}\n"
        if "parent_id" in context:
            result += f"**Parent Context**: {context['parent_id']}\n"
        if "user_id" in context:
            result += f"**User ID**: {context['user_id']}\n"
    
    # Add related entities suggestions
    related_domains = []
    if domain == "light":
        related_domains = ["switch", "scene", "automation"]
    elif domain == "sensor":
        related_domains = ["binary_sensor", "input_number", "utility_meter"]
    elif domain == "climate":
        related_domains = ["sensor", "switch", "fan"]
    elif domain == "media_player":
        related_domains = ["remote", "switch", "sensor"]
    
    if related_domains:
        result += "\n## Related Entity Types\n\n"
        result += "You may want to check entities in these related domains:\n"
        for related in related_domains:
            result += f"- {related}\n"
    
    return result

@mcp.resource("hass://entities/domain/{domain}")
@async_handler("list_states_by_domain_resource")
async def list_states_by_domain_resource(domain: str) -> str:
    """
    Get a list of entities for a specific domain as a resource (LIMITED to prevent context flooding)

    CONTEXT FLOODING PREVENTION:
    - Output is LIMITED to 100 entities per domain
    - For more entities, use the list_entities tool with domain filter

    Args:
        domain: The domain to filter by (e.g., 'light', 'switch', 'sensor')

    Returns:
        A markdown formatted string with entities in the specified domain

    Examples:
        ```
        # Get lights (limited)
        lights = mcp.get_resource("hass://entities/domain/light")

        # Get sensors (limited)
        sensors = mcp.get_resource("hass://entities/domain/sensor")
        ```

    Best Practices:
        - For a concise overview, use the domain summary: hass://entities/domain/{domain}/summary
        - Use the list_entities tool with domain filter for more control
        - For high-count domains (sensor, binary_sensor), use search to narrow results
    """
    logger.info(f"Getting entities for domain: {domain} (limited)")

    # Get all entities for the specified domain first to count (using compact for efficiency)
    all_entities = await get_entities(domain=domain, limit=0, compact=True)

    # Check if there was an error
    if isinstance(all_entities, dict) and "error" in all_entities:
        return f"Error retrieving entities: {all_entities['error']}"

    total_count = len(all_entities)
    truncated = total_count > DEFAULT_DOMAIN_ENTITIES_LIMIT

    # Apply limit
    entities = all_entities[:DEFAULT_DOMAIN_ENTITIES_LIMIT] if truncated else all_entities

    # Format the entities as a string
    result = f"# {domain.capitalize()} Entities\n\n"

    if truncated:
        result += f"⚠️ **TRUNCATED**: Showing {len(entities)} of {total_count} {domain} entities\n\n"
        result += "To see more, use:\n"
        result += f"- `list_entities(domain=\"{domain}\", limit=200)` tool\n"
        result += f"- Domain summary: `hass://entities/domain/{domain}/summary`\n\n"
    else:
        result += f"Total: {total_count} entities\n\n"

    # List the entities
    for entity in sorted(entities, key=lambda e: e["entity_id"]):
        # Get a friendly name if available (compact mode has friendly_name at top level)
        friendly_name = entity.get("friendly_name", entity["entity_id"])
        result += f"- **{entity['entity_id']}**: {entity['state']}"
        if friendly_name != entity["entity_id"]:
            result += f" ({friendly_name})"
        result += "\n"

    # Add link to summary
    result += f"\n## Related Resources\n\n"
    result += f"- [View domain summary](/api/resource/hass://entities/domain/{domain}/summary)\n"

    return result

# Automation management MCP tools
@mcp.tool()
@async_handler("list_automations")
async def list_automations(limit: int = DEFAULT_AUTOMATION_LIMIT) -> Dict[str, Any]:
    """
    Get a list of all automations from Home Assistant with pagination

    This function retrieves automations configured in Home Assistant,
    including their IDs, entity IDs, state, and display names.

    Args:
        limit: Maximum number of automations to return (1-200, default: 50)

    Returns:
        A dictionary containing:
        - automations: List of automation dictionaries (id, entity_id, state, alias)
        - count: Number of automations returned
        - total_available: Total automations before limiting
        - truncated: Whether results were truncated

    Examples:
        limit=50 - get first 50 automations (default)
        limit=200 - get up to 200 automations

    """
    logger.info(f"Getting automations (limit: {limit})")
    try:
        # Get automations with limit
        result = await get_automations(limit=limit)

        # Handle error responses
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"Error getting automations: {result['error']}")
            return {
                "automations": [],
                "count": 0,
                "total_available": 0,
                "truncated": False,
                "error": result["error"]
            }

        return result
    except Exception as e:
        logger.error(f"Error in list_automations: {str(e)}")
        return {
            "automations": [],
            "count": 0,
            "total_available": 0,
            "truncated": False,
            "error": "Error listing automations"
        }


@mcp.tool()
@async_handler("list_automation_traces")
async def list_automation_traces(
    automation_id: str,
    domain: str = "automation",
    limit: int = 10
) -> Dict[str, Any]:
    """
    List recent execution traces for a specific automation

    Args:
        automation_id: REQUIRED - The automation ID (e.g., 'motion_light' or 'automation.motion_light')
        domain: Domain to query ('automation' or 'script'). Default: 'automation'
        limit: Maximum traces to return (default: 10, max: 50)

    Returns:
        Dictionary with:
        - traces: List of lean summaries (run_id, timestamp, trigger, state, outcome)
        - automation_id: The automation queried
        - domain: The domain queried
        - count: Number of traces returned

    Examples:
        automation_id="motion_light" - get last 10 traces
        automation_id="kitchen_lights", limit=5 - get last 5 traces

    Best Practices:
        - Use run_id with get_automation_trace to get full details
        - Check 'outcome' field: 'finished', 'failed_conditions', 'aborted'
        - 'state: running' means automation still executing
    """
    logger.info(f"Listing traces for automation: {automation_id}, limit: {limit}")
    return await hass_list_automation_traces(automation_id, domain, limit)


@mcp.tool()
@async_handler("get_automation_trace")
async def get_automation_trace(
    automation_id: str,
    run_id: str,
    domain: str = "automation"
) -> Dict[str, Any]:
    """
    Get detailed trace for a specific automation run

    Retrieves complete execution details including trigger info, condition
    evaluation results, action execution steps, variables, and any errors.

    Args:
        automation_id: The automation ID (e.g., 'motion_light' or 'automation.motion_light')
        run_id: The specific run/trace ID from list_automation_traces
        domain: Domain ('automation' or 'script'). Default: 'automation'

    Returns:
        Dictionary with:
        - trace: Complete trace data including:
          * trigger: What triggered the automation
          * condition: Condition evaluation results (if any)
          * action: Step-by-step action execution
          * variables: Variables at each step
          * error: Error details if the run failed
        - automation_id: The automation queried
        - run_id: The run ID queried
        - domain: The domain

    Examples:
        automation_id="motion_light", run_id="1700000000.123456"
        automation_id="automation.bedtime_routine", run_id="1700000000.789"

    Best Practices:
        - First use list_automation_traces to find the run_id
        - Check 'trace.trace' for step-by-step execution path
        - Look for 'result' fields to see what each step returned
        - Examine 'error' fields for failure details
    """
    logger.info(f"Getting trace for automation: {automation_id}, run_id: {run_id}")
    return await hass_get_automation_trace(automation_id, run_id, domain)


@mcp.tool()
@async_handler("restart_ha")
async def restart_ha() -> Dict[str, Any]:
    """
    Restart Home Assistant
    
    ⚠️ WARNING: Temporarily disrupts all Home Assistant operations
    
    Returns:
        Result of restart operation
    """
    logger.info("Restarting Home Assistant")
    return await restart_home_assistant()

@mcp.tool()
@async_handler("call_service")
async def call_service(domain: str, service: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Call any Home Assistant service (low-level API access)
    
    Args:
        domain: The domain of the service (e.g., 'light', 'switch', 'automation')
        service: The service to call (e.g., 'turn_on', 'turn_off', 'toggle')
        data: Optional data to pass to the service (e.g., {'entity_id': 'light.living_room'})
    
    Returns:
        The response from Home Assistant (usually empty for successful calls)
    
    Examples:
        domain='light', service='turn_on', data={'entity_id': 'light.x', 'brightness': 255}
        domain='automation', service='reload'
        domain='fan', service='set_percentage', data={'entity_id': 'fan.x', 'percentage': 50}
    
    """
    logger.info(f"Calling Home Assistant service: {domain}.{service} with data: {sanitize_for_logging(data)}")
    return await hass_call_service(domain, service, data or {})
# Documentation endpoint
@mcp.tool()
@async_handler("get_history")
async def get_history(
    entity_id: str,
    hours: int = 24,
    limit: int = DEFAULT_HISTORY_LIMIT,
    sample_strategy: str = "recent"
) -> Dict[str, Any]:
    """
    Get state changes for an entity with automatic pagination

    CONTEXT FLOODING PREVENTION:
    - Results are LIMITED to prevent token overflow (default: 100 records)
    - Use sample_strategy to control which records are returned
    - For aggregated data, use get_statistics instead

    When to use this tool:
    - You need exact timestamps of state changes
    - Entity changes infrequently (e.g., doors, switches)
    - Short time periods relative to the sensor's update frequency

    When NOT to use this tool:
    - You only need trends or aggregated values → use get_statistics
    - Long time periods for frequently-updating sensors

    Args:
        entity_id: The entity ID to get history for
        hours: Number of hours of history to retrieve (default: 24)
        limit: Maximum records to return (1-500, default: 100)
        sample_strategy: How to sample if over limit:
            - "recent" (default): Most recent records
            - "first": Oldest records
            - "even": Evenly spaced across time range

    Returns:
        A dictionary containing:
        - entity_id: The entity ID requested
        - states: List of state objects with timestamps (possibly sampled)
        - count: Number of states returned
        - total_available: Total states before limiting
        - truncated: Whether results were truncated
        - sample_strategy: Strategy used for sampling
        - first_changed: Timestamp of earliest state change
        - last_changed: Timestamp of most recent state change
        - note: Guidance message if truncated

    Examples:
        entity_id="binary_sensor.front_door" - door open/close events
        entity_id="sensor.temperature", hours=1, limit=50 - limited temperature readings

    Note: If truncated=True, consider using get_statistics for aggregated data.
    """
    logger.info(f"Getting history for entity: {entity_id}, hours: {hours}, limit: {limit}")

    try:
        # Call the updated hass function (now returns dict with metadata)
        result = await get_entity_history(entity_id, hours, limit, sample_strategy)

        # Check for errors from the API call
        if isinstance(result, dict) and "error" in result:
            return {
                "entity_id": entity_id,
                "error": result["error"],
                "states": [],
                "count": 0,
                "total_available": 0,
                "truncated": False,
                "sample_strategy": sample_strategy
            }

        # The hass function now returns structured data
        states = result.get("states", [])

        if not states:
            return {
                "entity_id": entity_id,
                "states": [],
                "count": 0,
                "total_available": result.get("total_available", 0),
                "truncated": False,
                "sample_strategy": sample_strategy,
                "first_changed": None,
                "last_changed": None,
                "note": "No state changes found in the specified timeframe."
            }

        # Extract first and last changed timestamps
        first_changed = states[0].get("last_changed") if states else None
        last_changed = states[-1].get("last_changed") if states else None

        response = {
            "entity_id": entity_id,
            "states": states,
            "count": result.get("count", len(states)),
            "total_available": result.get("total_available", len(states)),
            "truncated": result.get("truncated", False),
            "sample_strategy": result.get("sample_strategy", sample_strategy),
            "first_changed": first_changed,
            "last_changed": last_changed
        }

        if result.get("note"):
            response["note"] = result["note"]

        return response
    except Exception as e:
        logger.error(f"Error processing history for {entity_id}: {str(e)}")
        return {
            "entity_id": entity_id,
            "error": "Error processing history",
            "states": [],
            "count": 0,
            "total_available": 0,
            "truncated": False,
            "sample_strategy": sample_strategy
        }

@mcp.tool()
@async_handler("get_history_range")
async def get_history_range(
    entity_id: str,
    start_time: str,
    end_time: Optional[str] = None,
    minimal_response: bool = True,
    limit: int = DEFAULT_HISTORY_LIMIT,
    sample_strategy: str = "recent"
) -> Dict[str, Any]:
    """
    Get state changes for a specific date/time range with automatic pagination

    CONTEXT FLOODING PREVENTION:
    - Results are LIMITED to prevent token overflow (default: 100 records)
    - Use sample_strategy to control which records are returned
    - For aggregated data, use get_statistics_range instead

    When to use this tool:
    - You need exact timestamps of specific state changes
    - Short, precise time windows
    - Entities with infrequent state changes

    When NOT to use this tool:
    - Date ranges spanning days → use get_statistics_range
    - Frequently-updating sensors → use get_statistics_range
    - You only need aggregated values → use get_statistics_range

    Args:
        entity_id: The entity ID to get history for
        start_time: Start time (ISO 8601, date only, or 'yesterday'/'today')
        end_time: End time (optional, defaults to 'now')
        minimal_response: Reduce response size (default: true)
        limit: Maximum records to return (1-500, default: 100)
        sample_strategy: How to sample if over limit:
            - "recent" (default): Most recent records
            - "first": Oldest records
            - "even": Evenly spaced across time range

    Returns:
        A dictionary containing:
        - entity_id: The entity ID requested
        - states: List of state objects with timestamps (possibly sampled)
        - count: Number of states returned
        - total_available: Total states before limiting
        - truncated: Whether results were truncated
        - sample_strategy: Strategy used for sampling
        - start_time: Actual start time used
        - end_time: Actual end time used
        - first_changed: Timestamp of earliest state change
        - last_changed: Timestamp of most recent state change
        - note: Guidance message if truncated

    Examples:
        entity_id="sensor.temperature", start_time="2025-10-28T10:00:00Z", end_time="2025-10-28T11:00:00Z"
        entity_id="light.living_room", start_time="yesterday", end_time="today", limit=50

    Note: If truncated=True, consider using get_statistics_range for aggregated data.
    """
    logger.info(f"Getting history range for entity: {entity_id}, start: {start_time}, end: {end_time}, limit: {limit}")

    try:
        # Get history using the updated range function (now returns dict with metadata)
        result = await get_entity_history_range(
            entity_id, start_time, end_time, minimal_response, limit, sample_strategy
        )

        # Check for errors from the API call
        if isinstance(result, dict) and "error" in result:
            return {
                "entity_id": entity_id,
                "error": result["error"],
                "states": [],
                "count": 0,
                "total_available": 0,
                "truncated": False,
                "sample_strategy": sample_strategy,
                "start_time": start_time,
                "end_time": end_time or "now"
            }

        # The hass function now returns structured data
        states = result.get("states", [])

        if not states:
            return {
                "entity_id": entity_id,
                "states": [],
                "count": 0,
                "total_available": result.get("total_available", 0),
                "truncated": False,
                "sample_strategy": sample_strategy,
                "start_time": result.get("start_time", start_time),
                "end_time": result.get("end_time", end_time or "now"),
                "first_changed": None,
                "last_changed": None,
                "note": "No state changes found in the specified range"
            }

        # Extract first and last changed timestamps
        first_changed = states[0].get("last_changed") if states else None
        last_changed = states[-1].get("last_changed") if states else None

        response = {
            "entity_id": entity_id,
            "states": states,
            "count": result.get("count", len(states)),
            "total_available": result.get("total_available", len(states)),
            "truncated": result.get("truncated", False),
            "sample_strategy": result.get("sample_strategy", sample_strategy),
            "start_time": result.get("start_time", start_time),
            "end_time": result.get("end_time", end_time or "now"),
            "first_changed": first_changed,
            "last_changed": last_changed
        }

        if result.get("note"):
            response["note"] = result["note"]

        return response
    except ValueError as e:
        # Handle date parsing errors
        logger.error(f"Date parsing error for {entity_id}: {str(e)}")
        return {
            "entity_id": entity_id,
            "error": "Invalid date/time format. Use ISO 8601, date only, or keywords: now, today, yesterday",
            "states": [],
            "count": 0,
            "total_available": 0,
            "truncated": False,
            "sample_strategy": sample_strategy,
            "start_time": start_time,
            "end_time": end_time or "now"
        }
    except Exception as e:
        logger.error(f"Error processing history range for {entity_id}: {str(e)}")
        return {
            "entity_id": entity_id,
            "error": "Error processing history",
            "states": [],
            "count": 0,
            "total_available": 0,
            "truncated": False,
            "sample_strategy": sample_strategy,
            "start_time": start_time,
            "end_time": end_time or "now"
        }

@mcp.tool()
@async_handler("get_statistics")
async def get_statistics(
    entity_id: str,
    hours: int = 24,
    period: str = "hour"
) -> Dict[str, Any]:
    """
    Get AGGREGATED statistics for an entity (mean, min, max values)

    TOKEN EFFICIENT - Returns aggregated data instead of raw states
    - Uses Home Assistant's pre-calculated statistics via WebSocket
    - Much smaller response size than raw history
    - Perfect for trends, graphs, and analysis

    When to use this tool:
    - You need trends or patterns over time
    - Large time ranges (days, weeks, months)
    - Frequently-updating sensors
    - You don't need exact state change timestamps

    Aggregation Periods:
    - "5minute": Most detailed, ~12 points per hour
    - "hour": Good for daily views, 24 points per day
    - "day": For monthly views
    - "week": For quarterly views
    - "month": For yearly views

    Args:
        entity_id: The entity ID to get statistics for
        hours: Number of hours of statistics to retrieve (default: 24)
        period: Statistics period: "5minute", "hour", "day", "week", "month" (default: "hour")

    Returns:
        A dictionary containing:
        - entity_id: The entity ID requested
        - period: The period used
        - statistics: List of data points, each with:
          * start: Timestamp (milliseconds)
          * end: Timestamp (milliseconds)
          * mean: Average value in period
          * min: Minimum value in period
          * max: Maximum value in period
        - count: Number of statistical data points

    Examples:
        entity_id="sensor.temperature", hours=24, period="hour" - hourly averages for 24h
        entity_id="sensor.power_usage", hours=168, period="day" - daily averages for 7 days

    Note: Returns empty statistics if entity doesn't support long-term statistics
    """
    logger.info(f"Getting statistics for entity: {entity_id}, hours: {hours}, period: {period}")

    try:
        from app.hass import get_entity_statistics

        # Get statistics using the API function
        stats_data = await get_entity_statistics(entity_id, hours, period)

        # Check for errors from the API call
        if isinstance(stats_data, dict) and "error" in stats_data:
            return stats_data

        # Extract statistics count
        stats_list = stats_data.get("statistics", [])

        return {
            "entity_id": entity_id,
            "period": period,
            "hours_requested": hours,
            "statistics": stats_list,
            "count": len(stats_list)
        }
    except Exception as e:
        logger.error(f"Error getting statistics for {entity_id}: {str(e)}")
        return {
            "entity_id": entity_id,
            "error": "Error retrieving statistics",
            "statistics": [],
            "count": 0
        }

@mcp.tool()
@async_handler("get_statistics_range")
async def get_statistics_range(
    entity_id: str,
    start_time: str,
    end_time: Optional[str] = None,
    period: str = "hour"
) -> Dict[str, Any]:
    """
    Get AGGREGATED statistics for a specific date/time range

    BEST TOOL FOR HISTORICAL DATA - No token limits!
    - Retrieves Home Assistant's long-term statistics via WebSocket
    - Can handle ANY date range efficiently (days, months, years)
    - Returns aggregated data (mean/min/max) instead of raw states

    When to use this tool:
    - ANY date range query (especially multi-day)
    - Historical data analysis
    - Frequently-updating sensors over long periods
    - When raw history exceeds token limits

    Aggregation Periods:
    - "5minute": For detailed recent data (last 10 days)
    - "hour": Best for daily/weekly ranges
    - "day": Best for monthly ranges
    - "week": Best for quarterly ranges
    - "month": Best for yearly ranges

    Args:
        entity_id: The entity ID to get statistics for
        start_time: Start time (ISO 8601, date only, or 'yesterday'/'today')
        end_time: End time (optional, defaults to 'now')
        period: Statistics period: "5minute", "hour", "day", "week", "month" (default: "hour")

    Returns:
        A dictionary containing:
        - entity_id: The entity ID requested
        - period: The period used
        - start_time: The actual start time used
        - end_time: The actual end time used
        - statistics: List of data points, each with:
          * start: Timestamp (milliseconds)
          * end: Timestamp (milliseconds)
          * mean: Average value in period
          * min: Minimum value in period
          * max: Maximum value in period
        - count: Number of statistical data points

    Examples:
        entity_id="sensor.temperature", start_time="2024-10-01", end_time="2024-10-31", period="day"
        entity_id="sensor.power", start_time="2024-01-01", end_time="2024-12-31", period="month"
        entity_id="sensor.humidity", start_time="yesterday", period="5minute"

    Pro Tip: If get_history_range returns a token error, use this tool with
    the same date range to get the aggregated data instead.
    """
    logger.info(f"Getting statistics range for entity: {entity_id}, start: {start_time}, end: {end_time}, period: {period}")

    try:
        from app.hass import get_entity_statistics_range

        # Get statistics using the API function
        stats_data = await get_entity_statistics_range(entity_id, start_time, end_time, period)

        # Check for errors from the API call
        if isinstance(stats_data, dict) and "error" in stats_data:
            return stats_data

        # Extract statistics count
        stats_list = stats_data.get("statistics", [])

        return {
            "entity_id": entity_id,
            "period": period,
            "start_time": stats_data.get("start_time", start_time),
            "end_time": stats_data.get("end_time", end_time or "now"),
            "statistics": stats_list,
            "count": len(stats_list)
        }
    except ValueError as e:
        # Handle date parsing errors
        logger.error(f"Date parsing error for {entity_id}: {str(e)}")
        return {
            "entity_id": entity_id,
            "error": "Invalid date/time format. Use ISO 8601, date only, or keywords: now, today, yesterday",
            "statistics": [],
            "count": 0,
            "start_time": start_time,
            "end_time": end_time or "now"
        }
    except Exception as e:
        logger.error(f"Error getting statistics range for {entity_id}: {str(e)}")
        return {
            "entity_id": entity_id,
            "error": "Error retrieving statistics",
            "statistics": [],
            "count": 0,
            "start_time": start_time,
            "end_time": end_time or "now"
        }

@mcp.tool()
@async_handler("get_error_log")
async def get_error_log(
    limit: int = DEFAULT_ERROR_LOG_LIMIT,
    integration: Optional[str] = None,
    level: Optional[str] = None,
    since_minutes: Optional[int] = None,
    truncate_traces: bool = True
) -> Dict[str, Any]:
    """
    Get the Home Assistant error log for troubleshooting using WebSocket API

    CONTEXT FLOODING PREVENTION:
    - Stacktraces are TRUNCATED to 3 lines by default (set truncate_traces=False for full traces)
    - Results are LIMITED to prevent token overflow (default: 50 records)
    - Use filters to narrow down results

    Args:
        limit: Maximum number of records to return (1-100, default: 50)
        integration: Filter by integration name (e.g., "mqtt", "zwave", "hue")
        level: Filter by log level ("ERROR" or "WARNING")
        since_minutes: Only return errors from the last N minutes
        truncate_traces: Truncate stacktraces to 3 lines (default: True)

    Returns:
        A dictionary containing:
        - records: List of error/warning log records (potentially truncated)
        - count: Number of records returned
        - total_available: Total records before filtering/limiting
        - truncated: Whether the result was truncated
        - traces_truncated: Whether stacktraces were truncated
        - filters_applied: Dict of filters that were applied
        - error_count: Number of ERROR entries in returned records
        - warning_count: Number of WARNING entries in returned records
        - integration_mentions: Map of integration names to mention counts
        - error: Error message if retrieval failed

    Examples:
        get_error_log() - default 50 recent errors with truncated traces
        get_error_log(integration="mqtt") - only MQTT errors
        get_error_log(level="ERROR", since_minutes=60) - only ERRORs from last hour
        get_error_log(truncate_traces=False) - full stacktraces (may be large!)

    Best Practices:
        - Use integration filter for focused troubleshooting
        - Use since_minutes to narrow to recent issues
        - Only disable truncate_traces when you need full stacktrace details
        - Check integration_mentions to identify problematic integrations
    """
    logger.info(f"Getting Home Assistant error log (limit: {limit}, integration: {integration}, level: {level})")
    return await get_hass_error_log(
        limit=limit,
        integration=integration,
        level=level,
        since_minutes=since_minutes,
        truncate_traces=truncate_traces
    )


@mcp.tool()
@async_handler("get_core_logs")
async def get_core_logs(
    limit: int = DEFAULT_CORE_LOG_LIMIT,
    level: Optional[str] = None,
    integration: Optional[str] = None,
    pattern: Optional[str] = None,
    since_minutes: Optional[int] = None,
    lines: int = 500,
    truncate_traces: bool = True
) -> Dict[str, Any]:
    """
    Get Home Assistant core logs (DEBUG/INFO/WARNING/ERROR) from the journal

    Fetches from the Supervisor journal API (HAOS/Supervised) with automatic
    fallback to /api/error_log (Docker/Core installs).

    CONTEXT FLOODING PREVENTION:
    - Default 50 records (max 200)
    - Stacktraces truncated to 3 lines by default
    - Messages truncated to 500 chars
    - Use filters to narrow results

    Args:
        limit: Maximum records to return (1-200, default: 50)
        level: Filter by log level ("DEBUG", "INFO", "WARNING", "ERROR")
        integration: Filter by integration name (e.g., "mqtt", "llmvision")
        pattern: Case-insensitive substring match on message content
        since_minutes: Only return logs from the last N minutes
        lines: Lines to request from journal API (default: 500)
        truncate_traces: Truncate stacktraces to 3 lines (default: True)

    Returns:
        Dictionary containing:
        - records: List of log records (timestamp, level, logger, message, integration)
        - count: Number of records returned
        - total_parsed: Total records parsed before filtering
        - source: "supervisor", "error_log", or "none"
        - truncated: Whether results were truncated
        - filters_applied: Dict of active filters

    Examples:
        get_core_logs() - recent 50 log entries
        get_core_logs(level="DEBUG", integration="llmvision") - debug logs for llmvision
        get_core_logs(pattern="timeout", since_minutes=60) - timeout errors in last hour
        get_core_logs(level="ERROR", limit=10) - last 10 errors

    Best Practices:
        - Use set_log_level to enable DEBUG first, then get_core_logs to read them
        - Combine level + integration for focused debugging
        - Use pattern for keyword search across all log levels
        - Remember to reset log level to WARNING after debugging
    """
    logger.info(f"Getting core logs (limit: {limit}, level: {level}, integration: {integration})")
    return await get_hass_core_logs(
        limit=limit,
        level=level,
        integration=integration,
        pattern=pattern,
        since_minutes=since_minutes,
        lines=lines,
        truncate_traces=truncate_traces,
    )


@mcp.tool()
@async_handler("set_log_level")
async def set_log_level(
    integration: str,
    level: str,
    custom_component: bool = False
) -> Dict[str, Any]:
    """
    Set the log level for a Home Assistant integration

    Calls the logger.set_level service to enable/disable debug logging.

    Args:
        integration: Integration name (e.g., "mqtt", "zwave", "llmvision")
        level: Log level to set: "debug", "info", "warning", "error"
        custom_component: If True, targets custom_components.X instead of homeassistant.components.X

    Returns:
        Dictionary containing:
        - success: Whether the level was set successfully
        - integration: The integration name
        - level: The level that was set
        - logger_name: The full logger path that was configured
        - error: Error message if failed

    Examples:
        set_log_level("llmvision", "debug", custom_component=True) - enable debug for llmvision
        set_log_level("mqtt", "debug") - enable debug for MQTT
        set_log_level("mqtt", "warning") - reset MQTT to normal logging

    Best Practices:
        - Enable debug: set_log_level("integration", "debug")
        - Read logs: get_core_logs(integration="integration", level="DEBUG")
        - Reset: set_log_level("integration", "warning")
        - Use custom_component=True for HACS/custom integrations
    """
    logger.info(f"Setting log level for {integration} to {level}")
    return await set_hass_log_level(integration, level, custom_component)


@mcp.tool()
@async_handler("remove_entity")
async def remove_entity(entity_id: str, confirm: bool = False) -> Dict[str, Any]:
    """
    Remove an entity from the Home Assistant entity registry

    SAFETY: By default returns a preview of what would be deleted.
    Set confirm=True to actually perform the removal.

    The entity may reappear if its integration recreates it on restart.
    Consider using update_entity with disabled_by="user" to disable instead.

    Args:
        entity_id: The entity ID to remove (e.g., 'light.old_device')
        confirm: If False (default), returns preview with entity details.
                 If True, permanently removes the entity registry entry.

    Returns:
        Preview dict (confirm=False) or success dict with removed entity details (confirm=True)

    Examples:
        entity_id="light.orphaned_device" - preview what would be deleted
        entity_id="light.orphaned_device", confirm=True - actually delete
    """
    logger.info(f"Removing entity from registry: {entity_id} (confirm={confirm})")
    return await remove_registry_entity(entity_id, confirm=confirm)


@mcp.tool()
@async_handler("update_entity")
async def update_entity(
    entity_id: str,
    name: Optional[str] = None,
    icon: Optional[str] = None,
    disabled_by: Optional[str] = None,
    hidden_by: Optional[str] = None,
    area_id: Optional[str] = None,
    new_entity_id: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Update properties of an entity in the Home Assistant entity registry

    Allows changing entity metadata such as friendly name, icon, area assignment,
    disabling/enabling, hiding/unhiding, or renaming the entity ID.

    Args:
        entity_id: The entity ID to update (e.g., 'light.living_room')
        name: Custom friendly name. Set to "none" to clear custom name
        icon: Custom icon (e.g., 'mdi:lamp'). Set to "none" to clear custom icon
        disabled_by: Set to "user" to disable, "none" to enable (re-enable a disabled entity)
        hidden_by: Set to "user" to hide from UI, "none" to unhide
        area_id: Assign entity to an area by area ID. Set to "none" to remove area
        new_entity_id: Rename the entity ID itself (e.g., 'light.new_name')
        options: Entity platform options dictionary

    Returns:
        Dictionary with success status and updated entity entry, or error

    Examples:
        entity_id="light.living_room", name="Living Room Lamp" - rename
        entity_id="sensor.old", disabled_by="user" - disable entity
        entity_id="sensor.old", disabled_by="none" - re-enable disabled entity
        entity_id="light.test", new_entity_id="light.bedroom" - change entity ID
        entity_id="switch.plug", area_id="kitchen" - assign to area
        entity_id="switch.plug", hidden_by="none" - unhide entity
    """
    logger.info(f"Updating entity in registry: {entity_id}")

    # Build kwargs, only passing fields that were explicitly provided.
    # MCP protocol cannot distinguish "omitted" from None, so we use the
    # string "none" as a sentinel to mean "clear this field" (set to None).
    kwargs: Dict[str, Any] = {}
    if name is not None:
        kwargs["name"] = None if name.lower() == "none" else name
    if icon is not None:
        kwargs["icon"] = None if icon.lower() == "none" else icon
    if disabled_by is not None:
        kwargs["disabled_by"] = None if disabled_by.lower() == "none" else disabled_by
    if hidden_by is not None:
        kwargs["hidden_by"] = None if hidden_by.lower() == "none" else hidden_by
    if area_id is not None:
        kwargs["area_id"] = None if area_id.lower() == "none" else area_id
    if new_entity_id is not None:
        kwargs["new_entity_id"] = new_entity_id
    if options is not None:
        kwargs["options"] = options

    return await update_registry_entity(entity_id, **kwargs)


@mcp.tool()
@async_handler("get_entity_registry")
async def get_entity_registry(entity_id: str) -> Dict[str, Any]:
    """
    Get detailed registry entry for a single entity

    Returns the full entity registry entry including platform, config entry,
    device info, disabled/hidden status, area assignment, and more.

    Args:
        entity_id: The entity ID to look up (e.g., 'light.living_room')

    Returns:
        The full entity registry entry, or error

    Examples:
        entity_id="light.living_room" - get registry details
        entity_id="sensor.temperature" - check platform and device info
    """
    logger.info(f"Getting entity registry entry: {entity_id}")
    return await hass_get_registry_entity(entity_id)


@mcp.tool()
@async_handler("list_entity_registry")
async def list_entity_registry(
    domain: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List all entity registry entries with optional domain filter

    Returns registry entries (not states) including platform, config entry,
    disabled/hidden status, and area assignments. Useful for auditing entities,
    finding orphaned entries, or bulk management.

    Args:
        domain: Optional domain filter (e.g., 'light', 'sensor')
        limit: Maximum number of entities to return (default: 100, max: 5000)

    Returns:
        Dictionary containing:
        - entities: List of registry entries
        - count: Number returned
        - total_available: Total matching entries
        - truncated: Whether results were limited

    Examples:
        domain="light" - list all light registry entries
        limit=500 - get more entries
        domain="sensor", limit=50 - sensor entries with limit
    """
    logger.info(f"Listing entity registry (domain={domain}, limit={limit})")
    return await list_registry_entities(limit=limit, domain=domain)


@mcp.tool()
@async_handler("query_entities")
async def query_entities(
    domain: Optional[str] = None,
    expression: Optional[str] = None,
    limit: int = 50,
    lean: bool = True,
    compact: bool = False
) -> Dict[str, Any]:
    """
    Query entities using CEL (Common Expression Language) expressions

    Fetches all entity states from Home Assistant and filters them
    client-side using CEL expressions. Supports proper numeric comparison,
    OR/AND/NOT logic, and nested attribute access.

    Args:
        domain: Optional domain pre-filter (e.g., "sensor", "light", "cover")
        expression: CEL expression for filtering entities
        limit: Maximum entities to return (default: 50)
        lean: Return minimal fields per entity with domain-specific attributes (default: True)
        compact: Return only entity_id, state, friendly_name (default: False)

    CEL Expression Examples:
        Low battery sensors:
            domain="sensor", expression='state < 30 && attributes.device_class == "battery"'

        Lights that are on:
            domain="light", expression='state == "on"'

        Unavailable OR unknown entities:
            expression='state == "unavailable" || state == "unknown"'

        NOT closed covers:
            domain="cover", expression='state != "closed"'

        Temperature sensors above 80 OR below 32:
            domain="sensor",
            expression='attributes.device_class == "temperature" && (state > 80 || state < 32)'

        Lights on and dim:
            domain="light", expression='state == "on" && attributes.brightness < 50'

    CEL Context Per Entity:
        - entity_id: string (e.g., "sensor.battery_level")
        - state: numeric if possible, otherwise string
        - domain: string (e.g., "sensor")
        - attributes: dict with all entity attributes

    Returns:
        Dictionary containing:
        - count: Number of entities returned
        - total_matched: Total entities matching (before limit)
        - truncated: Whether results were limited
        - entities: List of matching entities
        - error: Error message if expression is invalid or API fails
    """
    logger.info(f"Querying entities with domain={domain}, expression={expression}")

    try:
        # Fetch all entity states from HA
        all_states = await get_all_entity_states()

        # Handle API errors
        if isinstance(all_states, dict) and "error" in all_states:
            return {
                "count": 0,
                "total_matched": 0,
                "truncated": False,
                "entities": [],
                "error": all_states["error"]
            }

        # Convert from {entity_id: entity_dict} to list for CEL filtering
        entities_list = list(all_states.values())

        # Apply CEL filtering (handles domain pre-filter and expression)
        filtered = evaluate_cel_filter(entities_list, expression, domain=domain)

        # Handle CEL parse errors
        if isinstance(filtered, dict) and "error" in filtered:
            return {
                "count": 0,
                "total_matched": 0,
                "truncated": False,
                "entities": [],
                "error": filtered["error"]
            }

        total_matched = len(filtered)
        truncated = total_matched > limit
        entities = filtered[:limit]

        # Apply output formatting
        if compact:
            entities = [
                {
                    "entity_id": e.get("entity_id"),
                    "state": e.get("state"),
                    "friendly_name": e.get("attributes", {}).get("friendly_name")
                }
                for e in entities
            ]
        elif lean:
            formatted = []
            for entity in entities:
                entity_id = entity.get("entity_id", "")
                ent_domain = entity_id.split(".")[0] if entity_id else ""
                lean_entity = {
                    "entity_id": entity_id,
                    "state": entity.get("state"),
                    "friendly_name": entity.get("attributes", {}).get("friendly_name")
                }
                attrs = entity.get("attributes", {})
                important_attrs = DOMAIN_IMPORTANT_ATTRIBUTES.get(ent_domain, [])
                for attr in important_attrs:
                    if attr in attrs:
                        lean_entity[attr] = attrs[attr]
                formatted.append(lean_entity)
            entities = formatted

        return {
            "count": len(entities),
            "total_matched": total_matched,
            "truncated": truncated,
            "entities": entities
        }

    except Exception as e:
        logger.error(f"Error in query_entities: {str(e)}", exc_info=True)
        return {
            "count": 0,
            "total_matched": 0,
            "truncated": False,
            "entities": [],
            "error": "Error querying entities"
        }
