"""Automation listing and trace retrieval."""

import logging
from typing import Dict, Any

from app.hass.constants import (
    DEFAULT_AUTOMATION_LIMIT,
    MAX_AUTOMATION_LIMIT,
)
from app.hass.decorators import handle_api_errors
from app.hass.entities import get_entities
from app.hass.validation import (
    validate_automation_id,
    validate_trace_domain,
    validate_run_id,
)
from app.hass.websocket import call_websocket_api

logger = logging.getLogger(__name__)


@handle_api_errors
async def get_automations(limit: int = DEFAULT_AUTOMATION_LIMIT) -> Dict[str, Any]:
    """
    Get a list of all automations from Home Assistant with pagination.

    Args:
        limit: Maximum number of automations to return (1-200, default: 50)

    Returns:
        A dictionary containing:
        - automations: List of automation dictionaries
        - count: Number of automations returned
        - total_available: Total automations before limiting
        - truncated: Whether results were truncated
    """
    # Enforce limit bounds
    limit = max(1, min(limit, MAX_AUTOMATION_LIMIT))

    # Reuse the get_entities function with domain filtering (get all, limit later)
    automation_entities = await get_entities(domain="automation", limit=0, lean=False)

    # Check if we got an error response
    if isinstance(automation_entities, dict) and "error" in automation_entities:
        return {
            "error": automation_entities["error"],
            "automations": [],
            "count": 0,
            "total_available": 0,
            "truncated": False
        }

    # Process automation entities
    all_automations = []
    try:
        for entity in automation_entities:
            # Extract relevant information
            automation_info = {
                "id": entity["entity_id"].split(".")[1],
                "entity_id": entity["entity_id"],
                "state": entity["state"],
                "alias": entity.get("attributes", {}).get("friendly_name", entity["entity_id"]),
            }

            # Add any additional attributes that might be useful
            attrs = entity.get("attributes", {})
            if "last_triggered" in attrs:
                automation_info["last_triggered"] = attrs["last_triggered"]

            all_automations.append(automation_info)
    except (TypeError, KeyError) as e:
        logger.error("Error processing automation entities: %s", e)
        return {
            "error": "Error processing automation entities",
            "automations": [],
            "count": 0,
            "total_available": 0,
            "truncated": False
        }

    total_available = len(all_automations)
    truncated = total_available > limit

    # Apply limit
    limited_automations = all_automations[:limit] if truncated else all_automations

    return {
        "automations": limited_automations,
        "count": len(limited_automations),
        "total_available": total_available,
        "truncated": truncated
    }


@handle_api_errors
async def list_automation_traces(
    automation_id: str,
    domain: str = "automation",
    limit: int = 10
) -> Dict[str, Any]:
    """
    List recent execution traces for a specific automation.

    Token-efficient: Returns only essential fields, limited results.

    Args:
        automation_id: REQUIRED - The automation ID (e.g., 'motion_light' or 'automation.motion_light')
        domain: Domain to query ('automation' or 'script'). Default: 'automation'
        limit: Maximum traces to return (default: 10, max: 50)

    Returns:
        A dictionary containing:
        - traces: List of lean summaries (run_id, timestamp, trigger, state, outcome)
        - automation_id: The automation queried
        - domain: The domain queried
        - count: Number of traces returned
    """
    try:
        # Enforce limit bounds
        limit = min(max(1, limit), 50)

        # Validate domain
        validate_trace_domain(domain)

        # Strip domain prefix if present, then validate item ID
        if automation_id.startswith(f"{domain}."):
            automation_id = automation_id.split(".", 1)[1]

        validate_automation_id(automation_id)

        # Call trace/list WebSocket API with item_id filter
        traces = await call_websocket_api(
            "trace/list",
            domain=domain,
            item_id=automation_id
        )

        if not traces:
            return {
                "automation_id": automation_id,
                "domain": domain,
                "traces": [],
                "count": 0
            }

        # Extract traces for this automation
        raw_traces = []
        if isinstance(traces, dict) and automation_id in traces:
            raw_traces = traces[automation_id]
        elif isinstance(traces, list):
            raw_traces = traces

        # Build lean trace summaries - only essential fields
        # Traces are returned in chronological order (oldest first), so take last N for most recent
        lean_traces = []
        for trace in raw_traces[-limit:]:
            lean_trace = {
                "run_id": trace.get("run_id"),
                "timestamp": trace.get("timestamp", {}).get("start"),
                "trigger": trace.get("trigger"),
                "state": trace.get("state"),
            }
            # Include outcome if present
            if trace.get("script_execution"):
                lean_trace["outcome"] = trace["script_execution"]
            lean_traces.append(lean_trace)

        return {
            "automation_id": automation_id,
            "domain": domain,
            "traces": lean_traces,
            "count": len(lean_traces),
        }

    except Exception as e:
        logger.error("Error listing automation traces for %s: %s", automation_id, e)
        return {
            "automation_id": automation_id,
            "domain": domain,
            "traces": [],
            "count": 0,
            "error": "Error listing traces"
        }


@handle_api_errors
async def get_automation_trace(
    automation_id: str,
    run_id: str,
    domain: str = "automation"
) -> Dict[str, Any]:
    """
    Get detailed trace information for a specific automation run.

    Uses the WebSocket API to retrieve full execution details including
    trigger info, condition results, action execution, and any errors.

    Args:
        automation_id: The automation ID (e.g., 'motion_light' or 'automation.motion_light')
        run_id: The specific run/trace ID to retrieve
        domain: The domain ('automation' or 'script'). Default: 'automation'

    Returns:
        A dictionary containing the full trace with:
        - trace: Complete trace data including trigger, conditions, actions
        - automation_id: The automation ID
        - run_id: The run ID
        - domain: The domain
        - error: Error message if retrieval failed
    """
    try:
        # Validate inputs
        validate_trace_domain(domain)
        validate_run_id(run_id)

        # Strip domain prefix if present, then validate item ID
        if automation_id.startswith(f"{domain}."):
            automation_id = automation_id.split(".", 1)[1]

        validate_automation_id(automation_id)

        # Call trace/get WebSocket API
        trace = await call_websocket_api(
            "trace/get",
            domain=domain,
            item_id=automation_id,
            run_id=run_id
        )

        return {
            "automation_id": automation_id,
            "run_id": run_id,
            "domain": domain,
            "trace": trace
        }

    except Exception as e:
        logger.error("Error getting automation trace %s/%s: %s", automation_id, run_id, e)
        return {
            "automation_id": automation_id,
            "run_id": run_id,
            "domain": domain,
            "trace": None,
            "error": "Error getting trace"
        }
