import functools
import logging
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
    sanitize_for_logging,
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
    VALID_SAMPLE_STRATEGIES,
    # Domain-specific attributes for lean formatting
    DOMAIN_IMPORTANT_ATTRIBUTES
)

# Type variable for generic functions
T = TypeVar('T')

# Create an MCP server
from mcp.server.fastmcp import FastMCP
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
    """Get the Home Assistant version."""
    logger.info("Getting Home Assistant version")
    return await get_hass_version()

@mcp.tool()
@async_handler("get_entity")
async def get_entity(entity_id: str, fields: Optional[List[str]] = None, detailed: bool = False) -> dict:
    """
    Get the state of a Home Assistant entity with optional field filtering.

    Args:
        entity_id: Entity ID (e.g. 'light.living_room')
        fields: Fields to include (e.g. ['state', 'attr.brightness'])
        detailed: If True, returns all fields unfiltered

    Examples: get_entity("light.living_room", fields=["state", "attr.brightness"])
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
    Perform an action on a Home Assistant entity (on, off, toggle).

    Args:
        entity_id: Entity ID to control (e.g. 'light.living_room')
        action: 'on', 'off', or 'toggle'
        params: Additional service parameters (e.g. {"brightness": 255, "temperature": 22.5})

    Domain-specific params:
        Lights: brightness (0-255), color_temp, rgb_color, transition, effect
        Covers: position (0-100), tilt_position
        Climate: temperature, target_temp_high, target_temp_low, hvac_mode
        Media players: source, volume_level (0-1)

    Examples: entity_action("light.living_room", "on", {"brightness": 255})
              entity_action("switch.garden_lights", "off")
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
    List Home Assistant entities with optional filtering.

    Args:
        domain: Domain filter (e.g. 'light', 'switch', 'sensor')
        search_query: Search by name, id, or attributes (no wildcards)
        limit: Max entities to return (default: 100)
        fields: Specific fields to include per entity
        detailed: If True, returns all fields unfiltered
        compact: If True, returns only entity_id/state/friendly_name (overrides detailed/fields)

    Examples: list_entities(domain="light")
              list_entities(search_query="kitchen", limit=20)
              list_entities(compact=True)
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

@mcp.tool()
@async_handler("search_entities")
async def search_entities(query: str, limit: int = 20) -> Dict[str, Any]:
    """
    Search for entities matching a query string across IDs, names, and attributes.

    Args:
        query: Search term (no wildcards; empty string returns all entities)
        limit: Max results (default: 20)

    Examples: search_entities("temperature")
              search_entities("living room", limit=10)
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


@mcp.tool()
@async_handler("domain_summary")
async def domain_summary(domain: str, example_limit: int = 3) -> Dict[str, Any]:
    """
    Get a summary of entities in a domain (counts, state distribution, examples).

    Args:
        domain: Domain to summarize (e.g. 'light', 'switch', 'sensor')
        example_limit: Max examples per state (default: 3)

    Examples: domain_summary("light")
              domain_summary("climate", example_limit=5)
    """
    logger.info(f"Getting domain summary for: {domain}")
    return await summarize_domain(domain, example_limit)

@mcp.tool()
@async_handler("system_overview")
async def system_overview() -> Dict[str, Any]:
    """
    Get a comprehensive overview of the Home Assistant system (domain counts, samples, areas).

    Good first call when exploring an unfamiliar instance. Use domain_summary to drill deeper.
    """
    logger.info("Generating complete system overview")
    return await get_system_overview()


# Automation management MCP tools
@mcp.tool()
@async_handler("list_automations")
async def list_automations(limit: int = DEFAULT_AUTOMATION_LIMIT) -> Dict[str, Any]:
    """
    List automations with their IDs, entity IDs, state, and aliases.

    Args:
        limit: Max automations to return (1-200, default: 50)

    Examples: list_automations()
              list_automations(limit=200)
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
    List recent execution traces for a specific automation.

    Args:
        automation_id: Automation ID (e.g. 'motion_light' or 'automation.motion_light')
        domain: 'automation' or 'script' (default: 'automation')
        limit: Max traces to return (default: 10, max: 50)

    Use run_id from results with get_automation_trace for full details.

    Examples: list_automation_traces("motion_light")
              list_automation_traces("kitchen_lights", limit=5)
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
    Get detailed trace for a specific automation run (trigger, conditions, actions, errors).

    Args:
        automation_id: Automation ID (e.g. 'motion_light')
        run_id: Run/trace ID from list_automation_traces
        domain: 'automation' or 'script' (default: 'automation')

    Examples: get_automation_trace("motion_light", "1700000000.123456")
    """
    logger.info(f"Getting trace for automation: {automation_id}, run_id: {run_id}")
    return await hass_get_automation_trace(automation_id, run_id, domain)


@mcp.tool()
@async_handler("restart_ha")
async def restart_ha() -> Dict[str, Any]:
    """Restart Home Assistant. WARNING: Temporarily disrupts all operations."""
    logger.info("Restarting Home Assistant")
    return await restart_home_assistant()

@mcp.tool()
@async_handler("call_service")
async def call_service(domain: str, service: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Call any Home Assistant service directly (low-level API).

    Args:
        domain: Service domain (e.g. 'light', 'automation')
        service: Service name (e.g. 'turn_on', 'reload')
        data: Service data (e.g. {'entity_id': 'light.x', 'brightness': 255})

    Examples: call_service("light", "turn_on", {"entity_id": "light.x", "brightness": 255})
              call_service("automation", "reload")
    """
    logger.info(f"Calling Home Assistant service: {domain}.{service} with data: {sanitize_for_logging(data)}")
    return await hass_call_service(domain, service, data or {})

@mcp.tool()
@async_handler("get_history")
async def get_history(
    entity_id: str,
    hours: int = 24,
    limit: int = DEFAULT_HISTORY_LIMIT,
    sample_strategy: str = "recent"
) -> Dict[str, Any]:
    """
    Get raw state changes for an entity. For aggregated trends, use get_statistics instead.

    Best for: exact state change timestamps, infrequently-changing entities (doors, switches),
    short time periods. NOT for: long ranges on frequently-updating sensors — use get_statistics.

    Args:
        entity_id: Entity ID to get history for
        hours: Hours of history (default: 24)
        limit: Max records (1-500, default: 100)
        sample_strategy: 'recent' (default), 'first', or 'even' — how to sample if over limit

    Examples: get_history("binary_sensor.front_door")
              get_history("sensor.temperature", hours=1, limit=50)
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
    Get raw state changes for a specific date/time range. For aggregated trends, use get_statistics_range.

    Best for: exact timestamps, short precise windows, infrequently-changing entities.
    NOT for: multi-day ranges or frequently-updating sensors — use get_statistics_range.

    Args:
        entity_id: Entity ID to get history for
        start_time: ISO 8601, date only, or 'yesterday'/'today'
        end_time: End time (default: 'now')
        minimal_response: Reduce response size (default: true)
        limit: Max records (1-500, default: 100)
        sample_strategy: 'recent' (default), 'first', or 'even' — how to sample if over limit

    Examples: get_history_range("sensor.temp", "2025-10-28T10:00:00Z", "2025-10-28T11:00:00Z")
              get_history_range("light.living_room", "yesterday", "today", limit=50)
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
    Get aggregated statistics (mean/min/max) for an entity. Token-efficient alternative to raw history.

    Args:
        entity_id: Entity ID to get statistics for
        hours: Hours of data (default: 24)
        period: Aggregation period (default: 'hour'):
            '5minute' (~12 points/hr), 'hour' (24/day), 'day' (monthly views),
            'week' (quarterly), 'month' (yearly). Match period to time range.

    Examples: get_statistics("sensor.temperature", hours=24, period="hour")
              get_statistics("sensor.power_usage", hours=168, period="day")
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
    Get aggregated statistics (mean/min/max) for a date/time range. Best tool for historical data — no token limits.

    Handles any range efficiently (days, months, years). If get_history_range hits token limits,
    use this tool with the same range instead.

    Args:
        entity_id: Entity ID to get statistics for
        start_time: ISO 8601, date only, or 'yesterday'/'today'
        end_time: End time (default: 'now')
        period: Aggregation period (default: 'hour'):
            '5minute' (~12 points/hr), 'hour' (24/day), 'day' (monthly views),
            'week' (quarterly), 'month' (yearly). Match period to time range.

    Examples: get_statistics_range("sensor.temperature", "2024-10-01", "2024-10-31", period="day")
              get_statistics_range("sensor.humidity", "yesterday", period="5minute")
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
    Get the Home Assistant error log (WebSocket API). Stacktraces truncated by default.

    Args:
        limit: Max records (1-100, default: 50)
        integration: Filter by integration (e.g. "mqtt", "zwave")
        level: Filter by level: "ERROR" or "WARNING"
        since_minutes: Only errors from last N minutes
        truncate_traces: Truncate stacktraces to 3 lines (default: True)

    Examples: get_error_log(integration="mqtt")
              get_error_log(level="ERROR", since_minutes=60)
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
    Get Home Assistant core logs (all levels) from the Supervisor journal, with fallback to error log.

    Args:
        limit: Max records (1-200, default: 50)
        level: Filter: "DEBUG", "INFO", "WARNING", or "ERROR"
        integration: Filter by integration (e.g. "mqtt", "llmvision")
        pattern: Case-insensitive substring match on message
        since_minutes: Only logs from last N minutes
        lines: Journal lines to request (default: 500)
        truncate_traces: Truncate stacktraces to 3 lines (default: True)

    Use set_log_level to enable DEBUG before reading debug logs; reset to WARNING after.

    Examples: get_core_logs(level="DEBUG", integration="llmvision")
              get_core_logs(pattern="timeout", since_minutes=60)
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
    Set the log level for a Home Assistant integration.

    Args:
        integration: Integration name (e.g. "mqtt", "llmvision")
        level: "debug", "info", "warning", or "error"
        custom_component: If True, targets custom_components.X (for HACS integrations)

    Examples: set_log_level("mqtt", "debug")
              set_log_level("llmvision", "debug", custom_component=True)
              set_log_level("mqtt", "warning")  # reset to normal
    """
    logger.info(f"Setting log level for {integration} to {level}")
    return await set_hass_log_level(integration, level, custom_component)


@mcp.tool()
@async_handler("remove_entity")
async def remove_entity(entity_id: str, confirm: bool = False) -> Dict[str, Any]:
    """
    Remove an entity from the entity registry. Two-phase safety: preview first, then confirm.

    By default returns a preview. Set confirm=True to actually delete.
    Entity may reappear if integration recreates it; consider disable instead.

    Args:
        entity_id: Entity ID to remove (e.g. 'light.old_device')
        confirm: False=preview (default), True=permanently remove

    Examples: remove_entity("light.orphaned_device")         # preview
              remove_entity("light.orphaned_device", confirm=True)  # delete
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
    Update entity registry properties (name, icon, area, disable/enable, hide/unhide, rename).

    For fields that can be cleared, pass "none" as the string value to set to null.

    Args:
        entity_id: Entity ID to update
        name: Friendly name (or "none" to clear)
        icon: Icon (e.g. 'mdi:lamp', or "none" to clear)
        disabled_by: "user" to disable, "none" to re-enable
        hidden_by: "user" to hide, "none" to unhide
        area_id: Area ID (or "none" to remove)
        new_entity_id: Rename entity ID (e.g. 'light.new_name')
        options: Platform options dict

    Examples: update_entity("sensor.old", disabled_by="user")
              update_entity("sensor.old", disabled_by="none")  # re-enable
              update_entity("light.x", name="Living Room Lamp", area_id="kitchen")
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
    Get the full entity registry entry (platform, config, device, disabled/hidden, area).

    Args:
        entity_id: Entity ID to look up (e.g. 'light.living_room')

    Examples: get_entity_registry("light.living_room")
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
    List entity registry entries (platform, config, disabled/hidden, area). Not states — use list_entities for states.

    Args:
        domain: Domain filter (e.g. 'light', 'sensor')
        limit: Max entries (default: 100, max: 5000)

    Examples: list_entity_registry(domain="light")
              list_entity_registry(domain="sensor", limit=50)
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
    Query entities using CEL (Common Expression Language) expressions.

    CEL context: entity_id (string), state (numeric if possible, else string),
    domain (string), attributes (dict).

    Args:
        domain: Domain pre-filter (e.g. "sensor", "light")
        expression: CEL filter expression
        limit: Max entities (default: 50)
        lean: Minimal fields with domain-specific attrs (default: True)
        compact: Only entity_id/state/friendly_name (default: False)

    CEL examples:
        domain="sensor", expression='state < 30 && attributes.device_class == "battery"'
        domain="light", expression='state == "on" && attributes.brightness < 50'
        expression='state == "unavailable" || state == "unknown"'
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
