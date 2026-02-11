"""Entity history and statistics retrieval."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Union

from app.config import HA_URL, get_ha_headers
from app.hass.client import _rate_limiter, get_client
from app.hass.constants import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    MAX_HISTORY_RAW_RECORDS,
    VALID_SAMPLE_STRATEGIES,
)
from app.hass.decorators import handle_api_errors
from app.hass.validation import validate_entity_id, safe_url_path_segment
from app.hass.websocket import call_websocket_api

logger = logging.getLogger(__name__)


def parse_datetime(dt_input: Union[str, datetime]) -> datetime:
    """
    Parse datetime input to timezone-aware datetime object.
    Simple implementation supporting ISO 8601 and basic keywords.

    Supported formats:
    - ISO 8601: "2025-10-28T10:00:00Z", "2025-10-28T10:00:00+00:00"
    - Date only: "2025-10-28" (assumes start of day in UTC)
    - Keywords: "now", "today", "yesterday"

    Returns:
        datetime: Timezone-aware datetime in UTC
    """
    if isinstance(dt_input, datetime):
        return dt_input if dt_input.tzinfo else dt_input.replace(tzinfo=timezone.utc)

    dt_str = str(dt_input).strip()

    # Handle special keywords
    if dt_str.lower() == "now":
        return datetime.now(timezone.utc)
    if dt_str.lower() == "today":
        return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if dt_str.lower() == "yesterday":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return today - timedelta(days=1)

    # Handle date-only format (YYYY-MM-DD)
    if len(dt_str) == 10 and dt_str[4] == '-' and dt_str[7] == '-':
        dt = datetime.strptime(dt_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)

    # Handle ISO 8601
    if dt_str.endswith('Z'):
        dt_str = dt_str[:-1] + '+00:00'

    try:
        dt = datetime.fromisoformat(dt_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(
            f"Invalid datetime format: {dt_input}. "
            f"Use ISO 8601 (e.g., '2025-10-28T10:00:00Z'), "
            f"date only (e.g., '2025-10-28'), "
            f"or keywords: 'now', 'today', 'yesterday'"
        )


def _sample_history_records(
    records: List[Dict[str, Any]],
    limit: int,
    strategy: str = "recent"
) -> List[Dict[str, Any]]:
    """
    Sample history records to stay within limit while preserving useful data.

    Args:
        records: List of state change records
        limit: Maximum number of records to return
        strategy: Sampling strategy - "recent" (last N), "first" (first N), "even" (evenly spaced)

    Returns:
        Sampled list of records
    """
    if len(records) <= limit:
        return records

    if strategy == "recent":
        # Return most recent records
        return records[-limit:]
    elif strategy == "first":
        # Return oldest records
        return records[:limit]
    elif strategy == "even":
        # Evenly sample across the range
        step = len(records) / limit
        # Ensure indices never exceed bounds due to floating point rounding
        indices = [min(int(i * step), len(records) - 1) for i in range(limit)]
        return [records[i] for i in indices]
    else:
        # Default to recent if strategy is invalid
        return records[-limit:]


@handle_api_errors
async def get_entity_history_range(
    entity_id: str,
    start_time: Union[str, datetime],
    end_time: Optional[Union[str, datetime]] = None,
    minimal_response: bool = True,
    limit: int = DEFAULT_HISTORY_LIMIT,
    sample_strategy: str = "recent"
) -> Dict[str, Any]:
    """
    Get entity history for a specific date/time range with pagination.

    Args:
        entity_id: The entity ID to get history for
        start_time: ISO 8601 string or datetime object
        end_time: ISO 8601 string or datetime object (defaults to now)
        minimal_response: Reduce response size (default: True)
        limit: Maximum records to return (1-500, default: 100)
        sample_strategy: How to sample if over limit - "recent", "first", "even"

    Returns:
        A dictionary containing states, count, total_available, truncated, etc.
    """
    validate_entity_id(entity_id)

    await _rate_limiter.acquire()
    client = await get_client()

    # Enforce limit bounds
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))

    # Validate sample strategy
    if sample_strategy not in VALID_SAMPLE_STRATEGIES:
        sample_strategy = "recent"

    # Parse start_time
    start_dt = parse_datetime(start_time)

    # Parse end_time (default to now)
    if end_time is None:
        end_dt = datetime.now(timezone.utc)
    else:
        end_dt = parse_datetime(end_time)

    # Validate time range
    if start_dt >= end_dt:
        raise ValueError(f"start_time must be before end_time")

    # Format for API
    start_time_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Construct the API URL (URL-encode timestamp for defense in depth)
    url = f"{HA_URL}/api/history/period/{safe_url_path_segment(start_time_iso)}"

    # Set query parameters
    params = {
        "filter_entity_id": entity_id,
        "minimal_response": str(minimal_response).lower(),
        "end_time": end_time_iso,
    }

    # Make the API call
    response = await client.get(url, headers=get_ha_headers(), params=params)
    response.raise_for_status()

    # Parse the response (API returns list of lists)
    raw_data = response.json()

    # Flatten the nested list structure (capped to prevent memory exhaustion)
    all_states = []
    capped = False
    if raw_data and isinstance(raw_data, list):
        for state_list in raw_data:
            if isinstance(state_list, list):
                all_states.extend(state_list)
                if len(all_states) > MAX_HISTORY_RAW_RECORDS:
                    all_states = all_states[:MAX_HISTORY_RAW_RECORDS]
                    capped = True
                    break

    total_available = len(all_states)
    truncated = total_available > limit

    # Apply sampling if needed
    if truncated:
        sampled_states = _sample_history_records(all_states, limit, sample_strategy)
    else:
        sampled_states = all_states

    result = {
        "states": sampled_states,
        "count": len(sampled_states),
        "total_available": total_available,
        "truncated": truncated,
        "sample_strategy": sample_strategy,
        "start_time": start_time_iso,
        "end_time": end_time_iso
    }

    if truncated:
        result["note"] = f"Showing {len(sampled_states)} of {total_available}. Use get_statistics_range for aggregated data."

    return result


@handle_api_errors
async def get_entity_history(
    entity_id: str,
    hours: int = 24,
    limit: int = DEFAULT_HISTORY_LIMIT,
    sample_strategy: str = "recent"
) -> Dict[str, Any]:
    """
    Get the history of an entity's state changes from Home Assistant.

    Args:
        entity_id: The entity ID to get history for.
        hours: Number of hours of history to retrieve (default: 24).
        limit: Maximum records to return (1-500, default: 100).
        sample_strategy: How to sample if over limit - "recent", "first", "even".

    Returns:
        A dictionary containing states, count, total_available, truncated, etc.
    """
    validate_entity_id(entity_id)

    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    # Delegate to the range function
    return await get_entity_history_range(
        entity_id=entity_id,
        start_time=start_time,
        end_time=end_time,
        minimal_response=True,
        limit=limit,
        sample_strategy=sample_strategy
    )


@handle_api_errors
async def get_entity_statistics(
    entity_id: str,
    hours: int,
    period: str = "5minute"
) -> Dict[str, Any]:
    """
    Get statistical data for an entity for recent time period.

    Args:
        entity_id: The entity ID to get statistics for
        hours: Number of hours of statistics to retrieve
        period: Statistics period: "5minute" or "hour"

    Returns:
        A dictionary containing statistical data with aggregated values
    """
    validate_entity_id(entity_id)

    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    # Delegate to the range function
    return await get_entity_statistics_range(
        entity_id=entity_id,
        start_time=start_time,
        end_time=end_time,
        period=period
    )


@handle_api_errors
async def get_entity_statistics_range(
    entity_id: str,
    start_time: Union[str, datetime],
    end_time: Optional[Union[str, datetime]] = None,
    period: str = "hour"
) -> Dict[str, Any]:
    """
    Get statistical data for an entity for a specific date/time range.

    Args:
        entity_id: The entity ID to get statistics for
        start_time: ISO 8601 string or datetime object
        end_time: ISO 8601 string or datetime object (defaults to now)
        period: Statistics period: "5minute", "hour", "day", "week", or "month"

    Returns:
        A dictionary containing entity_id, period, start/end_time, statistics
    """
    validate_entity_id(entity_id)

    # Parse start_time
    start_dt = parse_datetime(start_time)

    # Parse end_time (default to now)
    if end_time is None:
        end_dt = datetime.now(timezone.utc)
    else:
        end_dt = parse_datetime(end_time)

    # Validate time range
    if start_dt >= end_dt:
        raise ValueError(f"start_time must be before end_time")

    # Format for API
    start_time_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Map our period names to HA's expected values
    period_map = {
        "5minute": "5minute",
        "hour": "hour",
        "day": "day",
        "week": "week",
        "month": "month"
    }

    if period not in period_map:
        raise ValueError(f"Invalid period: {period}. Must be one of: {list(period_map.keys())}")

    try:
        # Use WebSocket API to get statistics
        result = await call_websocket_api(
            "recorder/statistics_during_period",
            start_time=start_time_iso,
            end_time=end_time_iso,
            statistic_ids=[entity_id],
            period=period_map[period],
            types=["mean", "min", "max", "state", "sum"]
        )

        # Extract statistics from the response
        statistics = []
        if entity_id in result:
            statistics = result[entity_id]
        elif isinstance(result, dict) and len(result) > 0:
            # Sometimes returns with different key format
            first_key = list(result.keys())[0]
            statistics = result[first_key]

        return {
            "entity_id": entity_id,
            "period": period,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "statistics": statistics
        }

    except Exception as e:
        logger.error("Error getting statistics for %s: %s", entity_id, e)
        return {
            "entity_id": entity_id,
            "period": period,
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "statistics": [],
            "error": "Failed to retrieve statistics"
        }
