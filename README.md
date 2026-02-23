# Hass-MCP-Plus

[![PyPI version](https://img.shields.io/pypi/v/hass-mcp-plus)](https://pypi.org/project/hass-mcp-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/rmaher001/hass-mcp-plus)](https://hub.docker.com/r/rmaher001/hass-mcp-plus)
[![Tests](https://img.shields.io/badge/tests-167%20passed-brightgreen)](https://github.com/rmaher001/hass-mcp-plus)

A complete rewrite of [voska/hass-mcp](https://github.com/voska/hass-mcp) — an MCP server for Home Assistant built for token efficiency, security hardening, and context flooding prevention. Thanks to [Matt Voska](https://github.com/voska) for the original project.

**Features:**
- 24 tools covering entity control, registry management, statistics, logs, and automation debugging
- CEL expression filtering for complex entity queries (e.g., "all battery sensors below 20%")
- Entity registry management with safe two-phase delete
- Long-term statistics with hourly/daily/weekly/monthly aggregation and date range support
- Core journal log access with debug-level and integration filtering
- Automation trace inspection for debugging failed runs
- Configurable output formats (lean/compact/detailed)
- Input validation, error sanitization, and context flooding prevention across all calls
- Works with Claude Desktop, Claude Code, Cursor, and other MCP clients

## Installation

```bash
# PyPI
pip install hass-mcp-plus

# Docker
docker pull rmaher001/hass-mcp-plus:latest
```

### Prerequisites

- Home Assistant instance with Long-Lived Access Token
- One of the following:
  - Docker (recommended)
  - Python 3.13+ and [uv](https://github.com/astral-sh/uv)

## Setting Up With Claude Desktop

### Docker Installation (Recommended)

1. Pull the Docker image:

   ```bash
   docker pull rmaher001/hass-mcp-plus:latest
   ```

2. Add the MCP server to Claude Desktop:

   a. Open Claude Desktop and go to Settings
   b. Navigate to Developer > Edit Config
   c. Add the following configuration to your `claude_desktop_config.json` file:

   ```json
   {
     "mcpServers": {
       "hass-mcp-plus": {
         "command": "docker",
         "args": [
           "run",
           "-i",
           "--rm",
           "-e",
           "HA_URL",
           "-e",
           "HA_TOKEN",
           "rmaher001/hass-mcp-plus"
         ],
         "env": {
           "HA_URL": "http://homeassistant.local:8123",
           "HA_TOKEN": "YOUR_LONG_LIVED_TOKEN"
         }
       }
     }
   }
   ```

   d. Replace `YOUR_LONG_LIVED_TOKEN` with your actual Home Assistant long-lived access token
   e. Update the `HA_URL`:

   - If running Home Assistant on the same machine: use `http://host.docker.internal:8123` (Docker Desktop on Mac/Windows)
   - If running Home Assistant on another machine: use the actual IP or hostname

   f. Save the file and restart Claude Desktop

3. The "Hass-MCP-Plus" tool should now appear in your Claude Desktop tools menu

> **Note**: If you're running Home Assistant in Docker on the same machine, you may need to add `--network host` to the Docker args for the container to access Home Assistant. Alternatively, use the IP address of your machine instead of `host.docker.internal`.

### uv/uvx

1. Install uv on your system.

2. Add the MCP server to Claude Desktop:

   a. Open Claude Desktop and go to Settings
   b. Navigate to Developer > Edit Config
   c. Add the following configuration to your `claude_desktop_config.json` file:

   ```json
   {
     "mcpServers": {
       "hass-mcp-plus": {
         "command": "uvx",
         "args": ["hass-mcp-plus"],
         "env": {
           "HA_URL": "http://homeassistant.local:8123",
           "HA_TOKEN": "YOUR_LONG_LIVED_TOKEN"
         }
       }
     }
   }
   ```

   d. Replace `YOUR_LONG_LIVED_TOKEN` with your actual Home Assistant long-lived access token
   e. Update the `HA_URL`:

   - If running Home Assistant on the same machine: use `http://host.docker.internal:8123` (Docker Desktop on Mac/Windows)
   - If running Home Assistant on another machine: use the actual IP or hostname

   f. Save the file and restart Claude Desktop

3. The "Hass-MCP-Plus" tool should now appear in your Claude Desktop tools menu

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HA_URL` | Yes | Home Assistant URL (e.g., `http://192.168.1.100:8123`) |
| `HA_TOKEN` | Yes | Home Assistant Long-Lived Access Token |
| `HA_VERIFY_SSL` | No | Set to `true` to enable SSL certificate verification (default: `false`). Useful when using HTTPS with self-signed certificates. |
| `TZ` | No | Timezone (e.g., `America/Los_Angeles`) |

## Other MCP Clients

### Cursor

1. Go to Cursor Settings > MCP > Add New MCP Server
2. Fill in the form:
   - Name: `Hass-MCP-Plus`
   - Type: `command`
   - Command:
     ```
     docker run -i --rm -e HA_URL=http://homeassistant.local:8123 -e HA_TOKEN=YOUR_LONG_LIVED_TOKEN rmaher001/hass-mcp-plus
     ```
   - Replace `YOUR_LONG_LIVED_TOKEN` with your actual Home Assistant token
   - Update the HA_URL to match your Home Assistant instance address
3. Click "Add" to save

### Claude Code (CLI)

To use with Claude Code CLI, you can add the MCP server directly using the `mcp add` command:

**Using Docker (recommended):**

```bash
claude mcp add hass-mcp-plus -e HA_URL=http://homeassistant.local:8123 -e HA_TOKEN=YOUR_LONG_LIVED_TOKEN -- docker run -i --rm -e HA_URL -e HA_TOKEN rmaher001/hass-mcp-plus
```

Replace `YOUR_LONG_LIVED_TOKEN` with your actual Home Assistant token and update the HA_URL to match your Home Assistant instance address.

## Usage Examples

Here are some examples of prompts you can use with Claude once Hass-MCP-Plus is set up:

- "What's the current state of my living room lights?"
- "Turn off all the lights in the kitchen"
- "Find all battery sensors below 20%"
- "Give me a summary of my climate entities"
- "Show me the hourly temperature statistics for the last week"
- "Why didn't my motion sensor automation fire last night?"
- "List all unavailable or unknown entities"
- "Disable the orphaned sensor that no longer exists"
- "Show me the debug logs for the MQTT integration"
- "Search for entities related to my living room"

## Available Tools

Hass-MCP-Plus provides 24 tools for interacting with Home Assistant:

### Entity Management
- `get_entity`: Get the state of a specific entity with optional field filtering
- `entity_action`: Perform actions on entities (turn on, off, toggle) with domain-specific parameters
- `list_entities`: Get entities with domain filtering, search, and output format options (lean/compact/detailed)
- `search_entities`: Search for entities matching a query string across IDs, names, and attributes
- `query_entities`: Filter entities using CEL expressions with numeric comparisons and boolean logic
- `domain_summary`: Get a summary of a domain's entities with state distribution and examples
- `system_overview`: Get a comprehensive overview of the entire Home Assistant system

### Entity Registry
- `get_entity_registry`: Get detailed registry entry for a single entity (platform, device, area, status)
- `list_entity_registry`: List all registry entries with optional domain filter (for auditing and bulk management)
- `update_entity`: Update entity properties — rename, change icon, assign area, disable/enable, hide/unhide
- `remove_entity`: Remove an entity from the registry (requires explicit `confirm=True` flag)

### Automation & Debugging
- `list_automations`: Get all automations with pagination support
- `list_automation_traces`: Get recent execution traces for a specific automation
- `get_automation_trace`: Get detailed trace for a specific automation run (trigger, conditions, actions, errors)
- `get_error_log`: Get the Home Assistant error log with integration/level filtering
- `get_core_logs`: Get core journal logs (DEBUG/INFO/WARNING/ERROR) with integration/pattern filtering
- `set_log_level`: Set log level for any integration (enable debug logging, then read with `get_core_logs`)

### Historical Data
- `get_history`: Get raw state change history with automatic pagination and sampling
- `get_history_range`: Get state changes for a specific date/time range with sampling strategies
- `get_statistics`: Get aggregated statistics (mean, min, max) with configurable periods (5min/hour/day/week/month)
- `get_statistics_range`: Get long-term statistics for any date range — the best tool for historical analysis

### System
- `get_version`: Get the Home Assistant version
- `call_service`: Call any Home Assistant service (low-level API access)
- `restart_ha`: Restart Home Assistant

## Available Resources

Hass-MCP-Plus provides the following resource endpoints:

- `hass://entities/{entity_id}`: Get the state of a specific entity
- `hass://entities/{entity_id}/detailed`: Get detailed information about an entity with all attributes
- `hass://entities`: List all Home Assistant entities grouped by domain
- `hass://entities/domain/{domain}`: Get a list of entities for a specific domain
- `hass://search/{query}/{limit}`: Search for entities matching a query with custom result limit

## Development

### Running Tests

```bash
uv run pytest tests/ -v
```

## License

[MIT License](LICENSE)
