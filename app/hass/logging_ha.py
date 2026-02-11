"""Home Assistant log parsing, fetching, and log level management."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple, Union

from app.config import HA_URL, get_ha_headers
from app.hass.client import _rate_limiter, get_client
from app.hass.constants import (
    DEFAULT_ERROR_LOG_LIMIT,
    MAX_ERROR_LOG_LIMIT,
    DEFAULT_CORE_LOG_LIMIT,
    MAX_CORE_LOG_LIMIT,
    DEFAULT_CORE_LOG_LINES,
    MAX_CORE_LOG_MESSAGE_LENGTH,
    DEFAULT_CORE_LOG_TRACE_LINES,
    DEFAULT_STACKTRACE_LINES,
    VALID_LOG_LEVELS,
)
from app.hass.decorators import handle_api_errors
from app.hass.services import call_service
from app.hass.websocket import call_websocket_api

logger = logging.getLogger(__name__)


# Regex for HA log lines: "2026-02-10 10:00:00.123 ERROR (MainThread) [logger.name] message"
_LOG_LINE_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+'  # timestamp
    r'(DEBUG|INFO|WARNING|ERROR)\s+'                        # level
    r'\(([^)]+)\)\s+'                                       # thread
    r'\[([^\]]+)\]\s+'                                      # logger
    r'(.*)'                                                 # message
)


def _truncate_stacktrace(message: Union[str, List[str]], max_lines: int = DEFAULT_STACKTRACE_LINES) -> Union[str, List[str]]:
    """
    Truncate a stacktrace to a maximum number of lines.

    Args:
        message: The log message potentially containing a stacktrace (string or list of strings)
        max_lines: Maximum lines to keep from the stacktrace

    Returns:
        Truncated message in the same format as input (string or list)
    """
    if not message:
        return message

    # Handle list input (Home Assistant system_log format)
    if isinstance(message, list):
        if len(message) <= max_lines:
            return message
        truncated = message[:max_lines]
        remaining = len(message) - max_lines
        truncated.append(f"... [{remaining} more lines truncated]")
        return truncated

    # Handle string input
    lines = message.split('\n')
    if len(lines) <= max_lines:
        return message

    # Keep first max_lines and add truncation indicator
    truncated = lines[:max_lines]
    remaining = len(lines) - max_lines
    truncated.append(f"... [{remaining} more lines truncated]")
    return '\n'.join(truncated)


def _parse_log_text(raw: str) -> List[Dict[str, Any]]:
    """
    Parse raw text from the Supervisor journal API into structured log records.

    Each record contains: timestamp, level, logger, message, integration (if extractable).
    Continuation lines (stacktraces) are appended to the previous record's message.

    Args:
        raw: Raw log text from the Supervisor journal API or /api/error_log

    Returns:
        List of parsed log record dicts
    """
    if not raw or not raw.strip():
        return []

    records: List[Dict[str, Any]] = []

    for line in raw.splitlines():
        if not line.strip():
            continue

        match = _LOG_LINE_RE.match(line)
        if match:
            timestamp, level, _thread, logger_name, message = match.groups()

            # Extract integration from logger path
            integration = None
            if "homeassistant.components." in logger_name:
                integration = logger_name.split("homeassistant.components.")[1].split(".")[0]
            elif "custom_components." in logger_name:
                integration = logger_name.split("custom_components.")[1].split(".")[0]

            records.append({
                "timestamp": timestamp,
                "level": level,
                "logger": logger_name,
                "message": message,
                "integration": integration,
            })
        elif records:
            # Continuation line — append to previous record's message
            records[-1]["message"] += "\n" + line

    return records


async def _fetch_log_text(lines: int = DEFAULT_CORE_LOG_LINES) -> Tuple[str, str]:
    """
    Fetch log text from Home Assistant.

    Primary: Supervisor journal API (HAOS/Supervised installs)
    Fallback: /api/error_log (Docker/Core installs)

    Args:
        lines: Number of lines to request from the journal API

    Returns:
        Tuple of (raw_text, source) where source is "supervisor", "error_log", or "none"
    """
    client = await get_client()

    # Primary: Supervisor journal API
    try:
        await _rate_limiter.acquire()
        response = await client.get(
            f"{HA_URL}/api/hassio/core/logs",
            headers=get_ha_headers(),
            params={"no_colors": "", "lines": str(lines)},
        )
        if response.status_code == 200 and response.text.strip():
            return response.text, "supervisor"
    except Exception as e:
        logger.debug(f"Supervisor log API failed: {e}")

    # Fallback: /api/error_log
    try:
        await _rate_limiter.acquire()
        response = await client.get(
            f"{HA_URL}/api/error_log",
            headers=get_ha_headers(),
        )
        if response.status_code == 200 and response.text.strip():
            return response.text, "error_log"
    except Exception as e:
        logger.debug(f"Error log API failed: {e}")

    return "", "none"


@handle_api_errors
async def get_hass_error_log(
    limit: int = DEFAULT_ERROR_LOG_LIMIT,
    integration: Optional[str] = None,
    level: Optional[str] = None,
    since_minutes: Optional[int] = None,
    truncate_traces: bool = True
) -> Dict[str, Any]:
    """
    Get the Home Assistant error log for troubleshooting using WebSocket API.

    Includes filtering and stacktrace truncation to prevent context flooding.

    Args:
        limit: Maximum number of records to return (1-100, default: 50)
        integration: Filter by integration name (e.g., "mqtt", "zwave")
        level: Filter by log level ("ERROR", "WARNING", or None for both)
        since_minutes: Only return errors from the last N minutes
        truncate_traces: Truncate stacktraces to 3 lines (default: True)

    Returns:
        A dictionary containing records, count, total_available, etc.
    """
    try:
        # Enforce limit bounds
        limit = max(1, min(limit, MAX_ERROR_LOG_LIMIT))

        # Use WebSocket API to retrieve system_log records
        all_records = await call_websocket_api("system_log/list")

        if not all_records or not isinstance(all_records, list):
            return {
                "error": "Failed to retrieve system log records",
                "records": [],
                "count": 0,
                "total_available": 0,
                "truncated": False,
                "traces_truncated": truncate_traces,
                "filters_applied": {},
                "error_count": 0,
                "warning_count": 0,
                "integration_mentions": {}
            }

        total_available = len(all_records)
        filters_applied = {}

        # Apply filters
        filtered_records = all_records

        # Filter by level
        if level:
            level_upper = level.upper()
            if level_upper in ("ERROR", "WARNING"):
                filtered_records = [r for r in filtered_records if r.get("level") == level_upper]
                filters_applied["level"] = level_upper

        # Filter by integration
        if integration:
            integration_lower = integration.lower()
            filtered_records = [
                r for r in filtered_records
                if integration_lower in r.get("name", "").lower()
            ]
            filters_applied["integration"] = integration

        # Filter by time (since_minutes)
        if since_minutes and since_minutes > 0:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            time_filtered = []
            for r in filtered_records:
                if r.get("timestamp"):
                    try:
                        ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
                        if ts >= cutoff_time:
                            time_filtered.append(r)
                    except (ValueError, TypeError):
                        # Skip records with invalid timestamps
                        continue
            filtered_records = time_filtered
            filters_applied["since_minutes"] = since_minutes

        # Count errors and warnings in filtered set
        error_count = sum(1 for r in filtered_records if r.get("level") == "ERROR")
        warning_count = sum(1 for r in filtered_records if r.get("level") == "WARNING")

        # Extract integration mentions from all filtered records
        integration_mentions = {}
        for record in filtered_records:
            logger_name = record.get("name", "")
            # Extract integration name from logger like "homeassistant.components.mqtt"
            if "homeassistant.components." in logger_name:
                integ = logger_name.split("homeassistant.components.")[1].split(".")[0]
                integration_mentions[integ] = integration_mentions.get(integ, 0) + 1

        # Apply limit (take most recent records - they're typically newest first)
        truncated = len(filtered_records) > limit
        limited_records = filtered_records[:limit]

        # Truncate stacktraces if requested (create copies to avoid mutating originals)
        if truncate_traces:
            truncated_records = []
            for record in limited_records:
                record_copy = record.copy()
                if "message" in record_copy:
                    record_copy["message"] = _truncate_stacktrace(record_copy["message"])
                if "exception" in record_copy:
                    record_copy["exception"] = _truncate_stacktrace(record_copy["exception"])
                truncated_records.append(record_copy)
            limited_records = truncated_records

        return {
            "records": limited_records,
            "count": len(limited_records),
            "total_available": total_available,
            "truncated": truncated,
            "traces_truncated": truncate_traces,
            "filters_applied": filters_applied,
            "error_count": error_count,
            "warning_count": warning_count,
            "integration_mentions": integration_mentions
        }
    except Exception as e:
        logger.error(f"Error retrieving Home Assistant error log: {str(e)}")
        return {
            "error": "Error retrieving error log",
            "records": [],
            "count": 0,
            "total_available": 0,
            "truncated": False,
            "traces_truncated": truncate_traces,
            "filters_applied": {},
            "error_count": 0,
            "warning_count": 0,
            "integration_mentions": {}
        }


@handle_api_errors
async def get_hass_core_logs(
    limit: int = DEFAULT_CORE_LOG_LIMIT,
    level: Optional[str] = None,
    integration: Optional[str] = None,
    pattern: Optional[str] = None,
    since_minutes: Optional[int] = None,
    lines: int = DEFAULT_CORE_LOG_LINES,
    truncate_traces: bool = True,
) -> Dict[str, Any]:
    """
    Get Home Assistant core logs from the Supervisor journal API.

    Fetches log lines, parses them into structured records, and applies filters.

    Args:
        limit: Maximum records to return (1-200, default: 50)
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR)
        integration: Filter by integration name (e.g., "mqtt", "llmvision")
        pattern: Case-insensitive substring match on message content
        since_minutes: Only return logs from the last N minutes
        lines: Number of lines to request from journal API (default: 500)
        truncate_traces: Truncate stacktraces in messages (default: True)

    Returns:
        Dict with records, count, total_parsed, source, truncated, filters_applied
    """
    # Enforce limit bounds
    limit = max(1, min(limit, MAX_CORE_LOG_LIMIT))
    lines = max(1, min(lines, 10000))

    # Fetch raw log text
    raw_text, source = await _fetch_log_text(lines=lines)

    if not raw_text:
        return {
            "error": "Could not retrieve logs from Home Assistant. "
                     "Supervisor journal API and /api/error_log both unavailable.",
            "records": [],
            "count": 0,
            "total_parsed": 0,
            "source": source,
            "truncated": False,
            "filters_applied": {},
        }

    # Parse raw text into structured records
    all_records = _parse_log_text(raw_text)
    total_parsed = len(all_records)
    filters_applied: Dict[str, Any] = {}

    # Apply filters
    filtered = all_records

    if level:
        level_upper = level.upper()
        filtered = [r for r in filtered if r["level"] == level_upper]
        filters_applied["level"] = level_upper

    if integration:
        integration_lower = integration.lower()
        filtered = [r for r in filtered if r.get("integration", "") and
                    r["integration"].lower() == integration_lower]
        filters_applied["integration"] = integration

    if pattern:
        pattern_lower = pattern.lower()
        filtered = [r for r in filtered if pattern_lower in r["message"].lower()]
        filters_applied["pattern"] = pattern

    if since_minutes and since_minutes > 0:
        cutoff = datetime.now() - timedelta(minutes=since_minutes)
        time_filtered = []
        for r in filtered:
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
                if ts >= cutoff:
                    time_filtered.append(r)
            except (ValueError, KeyError):
                continue
        filtered = time_filtered
        filters_applied["since_minutes"] = since_minutes

    # Take most recent records (tail of the list)
    truncated = len(filtered) > limit
    limited = filtered[-limit:] if truncated else filtered

    # Post-process: truncate messages and traces
    for record in limited:
        msg = record["message"]

        if truncate_traces:
            # Split into first line + continuation
            msg_lines = msg.split("\n")
            if len(msg_lines) > 1:
                first_line = msg_lines[0]
                continuation = msg_lines[1:]
                if len(continuation) > DEFAULT_CORE_LOG_TRACE_LINES:
                    remaining = len(continuation) - DEFAULT_CORE_LOG_TRACE_LINES
                    continuation = continuation[:DEFAULT_CORE_LOG_TRACE_LINES]
                    continuation.append(f"... [{remaining} more lines truncated]")
                record["message"] = first_line + "\n" + "\n".join(continuation)

        # Truncate long messages
        if len(record["message"]) > MAX_CORE_LOG_MESSAGE_LENGTH:
            record["message"] = record["message"][:MAX_CORE_LOG_MESSAGE_LENGTH] + "... [truncated]"

    return {
        "records": limited,
        "count": len(limited),
        "total_parsed": total_parsed,
        "source": source,
        "truncated": truncated,
        "filters_applied": filters_applied,
    }


@handle_api_errors
async def set_hass_log_level(
    integration: str,
    level: str,
    custom_component: bool = False,
) -> Dict[str, Any]:
    """
    Set the log level for a Home Assistant integration.

    Calls the logger.set_level service to toggle debug logging.

    Args:
        integration: Integration name (e.g., "mqtt", "llmvision")
        level: Log level: "debug", "info", "warning", "error"
        custom_component: If True, uses custom_components prefix instead of homeassistant.components

    Returns:
        Dict with success, integration, level, logger_name, or error
    """
    level_lower = level.lower()
    if level_lower not in VALID_LOG_LEVELS:
        return {
            "error": f"Invalid log level: {level_lower}. Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}",
            "success": False,
        }

    # Validate integration name (alphanumeric, underscore, hyphen only)
    if not re.match(r'^[a-zA-Z0-9_-]+$', integration):
        return {
            "error": f"Invalid integration name. Must contain only alphanumeric characters, underscores, and hyphens.",
            "success": False,
        }

    # Build the logger name
    if custom_component:
        logger_name = f"custom_components.{integration}"
    else:
        logger_name = f"homeassistant.components.{integration}"

    # Call logger.set_level service
    result = await call_service("logger", "set_level", {logger_name: level_lower})

    if isinstance(result, dict) and "error" in result:
        return {
            "error": result["error"],
            "success": False,
            "integration": integration,
            "level": level_lower,
            "logger_name": logger_name,
        }

    return {
        "success": True,
        "integration": integration,
        "level": level_lower,
        "logger_name": logger_name,
    }
