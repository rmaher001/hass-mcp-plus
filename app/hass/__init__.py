"""
Home Assistant API client package.

Re-exports all public functions and constants so that existing imports
like ``from app.hass import get_entities`` continue to work unchanged.
"""

# Re-export config values that tests patch via app.hass.HA_URL etc.
from app.config import HA_URL, HA_TOKEN, HA_VERIFY_SSL  # noqa: F401

# --- constants ---
from app.hass.constants import (  # noqa: F401
    DEFAULT_LEAN_FIELDS,
    DEFAULT_STANDARD_FIELDS,
    DOMAIN_IMPORTANT_ATTRIBUTES,
    SENSITIVE_KEYS,
    MAX_HISTORY_LIMIT,
    DEFAULT_HISTORY_LIMIT,
    MAX_ERROR_LOG_LIMIT,
    DEFAULT_ERROR_LOG_LIMIT,
    MAX_CORE_LOG_LIMIT,
    DEFAULT_CORE_LOG_LIMIT,
    DEFAULT_CORE_LOG_LINES,
    MAX_CORE_LOG_MESSAGE_LENGTH,
    DEFAULT_CORE_LOG_TRACE_LINES,
    VALID_LOG_LEVELS,
    DEFAULT_AUTOMATION_LIMIT,
    MAX_AUTOMATION_LIMIT,
    DEFAULT_ALL_ENTITIES_LIMIT,
    DEFAULT_DOMAIN_ENTITIES_LIMIT,
    DEFAULT_STACKTRACE_LINES,
    VALID_SAMPLE_STRATEGIES,
    ENTITY_ID_PATTERN,
    HA_IDENTIFIER_PATTERN,
    AUTOMATION_ID_PATTERN,
    RUN_ID_PATTERN,
    VALID_TRACE_DOMAINS,
    MAX_SERVICE_PAYLOAD_BYTES,
    MAX_TEMPLATE_LENGTH,
    MAX_HISTORY_RAW_RECORDS,
)

# --- validation ---
from app.hass.validation import (  # noqa: F401
    ValidationError,
    validate_entity_id,
    validate_ha_identifier,
    validate_automation_id,
    validate_run_id,
    validate_trace_domain,
    validate_service_payload,
    validate_template,
    safe_url_path_segment,
)

# Keep the old name available for any code referencing _SENSITIVE_KEYS
_SENSITIVE_KEYS = SENSITIVE_KEYS

# --- decorators ---
from app.hass.decorators import (  # noqa: F401
    sanitize_for_logging,
    handle_api_errors,
)

# --- client ---
from app.hass.client import (  # noqa: F401
    RateLimiter,
    get_client,
    cleanup_client,
    _rate_limiter,
    _timeout_config,
)

# --- websocket ---
from app.hass.websocket import call_websocket_api  # noqa: F401

# --- entities ---
from app.hass.entities import (  # noqa: F401
    get_all_entity_states,
    get_entity_state,
    get_entities,
    evaluate_cel_filter,
    filter_fields,
    _coerce_state,
)

# --- services ---
from app.hass.services import (  # noqa: F401
    call_service,
    get_hass_version,
    reload_automations,
    restart_home_assistant,
)

# --- automations ---
from app.hass.automations import (  # noqa: F401
    get_automations,
    list_automation_traces,
    get_automation_trace,
)

# --- history ---
from app.hass.history import (  # noqa: F401
    parse_datetime,
    get_entity_history,
    get_entity_history_range,
    get_entity_statistics,
    get_entity_statistics_range,
    _sample_history_records,
)

# --- logging ---
from app.hass.logging_ha import (  # noqa: F401
    _parse_log_text,
    _fetch_log_text,
    _truncate_stacktrace,
    _LOG_LINE_RE,
    get_hass_error_log,
    get_hass_core_logs,
    set_hass_log_level,
)

# --- summary ---
from app.hass.summary import (  # noqa: F401
    summarize_domain,
    get_system_overview,
)

# --- templates ---
from app.hass.templates import render_template  # noqa: F401
