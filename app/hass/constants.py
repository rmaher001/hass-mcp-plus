"""Constants for context flooding prevention, domain attributes, and validation."""

import re

# ============================================================================
# Input Validation Patterns and Limits
# ============================================================================

# Entity ID: domain.object_id (e.g., light.living_room, sensor.0x00158d_temp)
# HA normalizes all entity IDs to lowercase, so we enforce lowercase-only.
ENTITY_ID_PATTERN = re.compile(r'^[a-z][a-z0-9_]*\.[a-z0-9_]+$')

# HA identifier (domain name, service name): lowercase letters, digits, underscores
HA_IDENTIFIER_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')

# Automation/script item ID: letters, digits, underscores, hyphens
AUTOMATION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')

# Trace run ID: timestamp-like (e.g., "1700000000.123456")
RUN_ID_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')

# Valid domains for trace API
VALID_TRACE_DOMAINS = frozenset(["automation", "script"])

# Service call payload size limit (bytes)
MAX_SERVICE_PAYLOAD_BYTES = 1_048_576  # 1 MB

# Template string maximum length (characters)
MAX_TEMPLATE_LENGTH = 65_536  # 64 KB

# Hard cap on records parsed from history API response (memory exhaustion protection)
MAX_HISTORY_RAW_RECORDS = 10_000

# Default field sets for different verbosity levels
# Lean fields for standard requests (optimized for token efficiency)
DEFAULT_LEAN_FIELDS = ["entity_id", "state", "attr.friendly_name"]

# Common fields that are typically needed for entity operations
DEFAULT_STANDARD_FIELDS = ["entity_id", "state", "attributes", "last_updated"]

# Domain-specific important attributes to include in lean responses
DOMAIN_IMPORTANT_ATTRIBUTES = {
    "light": ["brightness", "color_temp", "rgb_color", "supported_color_modes"],
    "switch": ["device_class"],
    "binary_sensor": ["device_class"],
    "sensor": ["device_class", "unit_of_measurement", "state_class"],
    "climate": ["hvac_mode", "current_temperature", "temperature", "hvac_action"],
    "media_player": ["media_title", "media_artist", "source", "volume_level"],
    "cover": ["current_position", "current_tilt_position"],
    "fan": ["percentage", "preset_mode"],
    "camera": ["entity_picture"],
    "automation": ["last_triggered"],
    "scene": [],
    "script": ["last_triggered"],
}

# Sensitive keys that should be redacted in logs
SENSITIVE_KEYS = frozenset([
    "token", "password", "api_key", "secret", "access_token",
    "authorization", "auth", "credential", "key", "pin", "code",
    "bearer", "refresh_token", "client_secret", "private_key",
    "passphrase", "session", "cookie"
])

# ============================================================================
# Context Flooding Prevention - Pagination and Limit Constants
# ============================================================================

# History limits
MAX_HISTORY_LIMIT = 500
DEFAULT_HISTORY_LIMIT = 100

# Error log limits
MAX_ERROR_LOG_LIMIT = 100
DEFAULT_ERROR_LOG_LIMIT = 50

# Core log limits (Supervisor journal API)
MAX_CORE_LOG_LIMIT = 200
DEFAULT_CORE_LOG_LIMIT = 50
DEFAULT_CORE_LOG_LINES = 500
MAX_CORE_LOG_MESSAGE_LENGTH = 500
DEFAULT_CORE_LOG_TRACE_LINES = 3

# Valid log levels for set_log_level
VALID_LOG_LEVELS = frozenset(["debug", "info", "warning", "error"])

# Automation limits
DEFAULT_AUTOMATION_LIMIT = 50
MAX_AUTOMATION_LIMIT = 200

# Resource limits (for MCP resources)
DEFAULT_ALL_ENTITIES_LIMIT = 200
DEFAULT_DOMAIN_ENTITIES_LIMIT = 100

# Stacktrace truncation
DEFAULT_STACKTRACE_LINES = 3

# Valid sampling strategies for history
VALID_SAMPLE_STRATEGIES = frozenset(["recent", "first", "even"])

# Entity registry constants
MAX_ENTITY_NAME_LENGTH = 256
VALID_DISABLED_BY = frozenset(["user"])
VALID_HIDDEN_BY = frozenset(["user"])
DEFAULT_REGISTRY_LIMIT = 100
MAX_REGISTRY_LIMIT = 5000
