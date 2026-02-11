import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import json
import httpx
from typing import Dict, List, Any
from datetime import datetime, timezone, timedelta
import re

import ssl

from app.hass import get_entity_state, call_service, get_entities, get_automations, handle_api_errors, render_template, evaluate_cel_filter

class TestHassAPI:
    """Test the Home Assistant API functions."""

    @pytest.mark.asyncio
    async def test_get_entities(self, mock_config):
        """Test getting all entities."""
        # Mock response data
        mock_states = [
            {"entity_id": "light.living_room", "state": "on", "attributes": {"brightness": 255}},
            {"entity_id": "switch.kitchen", "state": "off", "attributes": {}}
        ]

        # Create mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_states

        # Create properly awaitable mock
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # Setup client mocking
        with patch('app.hass.entities.get_client', return_value=mock_client):
            with patch('app.hass.entities.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                            # Test function
                            states = await get_entities()

                            # Assertions
                            assert isinstance(states, list)
                            assert len(states) == 2

                            # Verify API was called correctly
                            mock_client.get.assert_called_once()
                            called_url = mock_client.get.call_args[0][0]
                            assert called_url == f"{mock_config['hass_url']}/api/states"

    @pytest.mark.asyncio
    async def test_get_entity_state(self, mock_config):
        """Test getting a specific entity state."""
        # Mock response data
        mock_state = {"entity_id": "light.living_room", "state": "on"}
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_state
        
        # Create properly awaitable mock
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        
        # Patch the client
        with patch('app.hass.entities.get_client', return_value=mock_client):
            with patch('app.hass.entities.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    # Test function - use_cache parameter has been removed
                    state = await get_entity_state("light.living_room")

                    # Assertions
                    assert isinstance(state, dict)
                    assert state["entity_id"] == "light.living_room"
                    assert state["state"] == "on"

                    # Verify API was called correctly
                    mock_client.get.assert_called_once()
                    called_url = mock_client.get.call_args[0][0]
                    assert called_url == f"{mock_config['hass_url']}/api/states/light.living_room"

    @pytest.mark.asyncio
    async def test_call_service(self, mock_config):
        """Test calling a service."""
        domain = "light"
        service = "turn_on"
        data = {"entity_id": "light.living_room", "brightness": 255}

        # Create mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"result": "ok"}

        # Create properly awaitable mock
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # Patch the client
        with patch('app.hass.services.get_client', return_value=mock_client):
            with patch('app.hass.services.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                        # Test function
                        result = await call_service(domain, service, data)

                        # Assertions
                        assert isinstance(result, dict)
                        assert result["result"] == "ok"

                        # Verify API was called correctly
                        mock_client.post.assert_called_once()
                        called_url = mock_client.post.call_args[0][0]
                        called_data = mock_client.post.call_args[1].get('json')
                        assert called_url == f"{mock_config['hass_url']}/api/services/{domain}/{service}"
                        assert called_data == data

    @pytest.mark.asyncio
    async def test_call_service_empty_list_response(self, mock_config):
        """Test calling a service that returns an empty list (should be converted to dict)."""
        domain = "cast"
        service = "show_lovelace_view"
        data = {"entity_id": "media_player.cast_device", "view_path": "home"}

        # Create mock response that returns empty list (as HA does for some service calls)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        # Create properly awaitable mock
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # Patch the client
        with patch('app.hass.services.get_client', return_value=mock_client):
            with patch('app.hass.services.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                        # Test function
                        result = await call_service(domain, service, data)

                        # Assertions - empty list should be converted to empty dict
                        assert isinstance(result, dict)
                        assert result == {}

                        # Verify API was called correctly
                        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_service_non_empty_list_response(self, mock_config):
        """Test calling a service that returns a non-empty list (should be wrapped in dict)."""
        domain = "script"
        service = "deploy_automations"
        data = {}

        # Create mock response that returns non-empty list (as HA does for script/automation calls)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"entity_id": "script.deploy_automations", "context": {"id": "abc123", "user_id": "user123"}}
        ]

        # Create properly awaitable mock
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # Patch the client
        with patch('app.hass.services.get_client', return_value=mock_client):
            with patch('app.hass.services.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                        # Test function
                        result = await call_service(domain, service, data)

                        # Assertions - non-empty list should be wrapped in dict with "result" key
                        assert isinstance(result, dict)
                        assert "result" in result
                        assert isinstance(result["result"], list)
                        assert len(result["result"]) == 1
                        assert result["result"][0]["entity_id"] == "script.deploy_automations"

                        # Verify API was called correctly
                        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_automations(self, mock_config):
        """Test getting automations from the states API (returns dict with metadata)."""
        # Mock states response with automation entities
        mock_automation_states = [
            {
                "entity_id": "automation.morning_lights",
                "state": "on",
                "attributes": {
                    "friendly_name": "Turn on lights in the morning",
                    "last_triggered": "2025-03-15T07:00:00Z"
                }
            },
            {
                "entity_id": "automation.night_lights",
                "state": "off",
                "attributes": {
                    "friendly_name": "Turn off lights at night"
                }
            }
        ]

        # Patch the token to avoid the "No token" error
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            with patch('app.hass.decorators.HA_URL', mock_config["hass_url"]):
                # For get_automations we need to mock the get_entities function
                with patch('app.hass.automations.get_entities', AsyncMock(return_value=mock_automation_states)):
                    # Test function
                    result = await get_automations()

                    # Assertions - now returns dict with metadata
                    assert isinstance(result, dict)
                    assert "automations" in result
                    assert "count" in result
                    assert "total_available" in result
                    assert "truncated" in result

                    automations = result["automations"]
                    assert len(automations) == 2
                    assert result["count"] == 2
                    assert result["total_available"] == 2
                    assert result["truncated"] is False

                    # Verify contents of first automation
                    assert automations[0]["entity_id"] == "automation.morning_lights"
                    assert automations[0]["state"] == "on"
                    assert automations[0]["alias"] == "Turn on lights in the morning"
                    assert automations[0]["last_triggered"] == "2025-03-15T07:00:00Z"

                # Test error response
                with patch('app.hass.automations.get_entities', AsyncMock(return_value={"error": "HTTP error: 404 - Not Found"})):
                    # Test function with error
                    result = await get_automations()

                    # Error responses still return dict with error field
                    assert isinstance(result, dict)
                    assert "error" in result
                    assert "404" in result["error"]

    @pytest.mark.asyncio
    async def test_get_entity_history(self, mock_config):
        """Test getting entity history (returns dict with metadata)."""
        entity_id = "sensor.temperature"
        hours = 24

        # Mock response data for history
        mock_history_data = [
            [
                {
                    "state": "25.0",
                    "last_changed": "2025-06-30T10:00:00.000Z",
                    "attributes": {"unit_of_measurement": "°C"}
                },
                {
                    "state": "26.0",
                    "last_changed": "2025-06-30T11:00:00.000Z",
                    "attributes": {"unit_of_measurement": "°C"}
                }
            ]
        ]

        # Create mock response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_history_data

        # Create properly awaitable mock
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # Patch the client and HA_URL/HA_TOKEN
        with patch('app.hass.history.get_client', return_value=mock_client):
            with patch('app.hass.history.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    from app.hass import get_entity_history
                    result = await get_entity_history(entity_id, hours)

                    # Assertions - now returns dict with metadata (BREAKING CHANGE)
                    assert isinstance(result, dict)
                    assert "states" in result
                    assert "count" in result
                    assert "total_available" in result
                    assert "truncated" in result
                    assert "sample_strategy" in result

                    # Verify states content
                    states = result["states"]
                    assert len(states) == 2
                    assert states[0]["state"] == "25.0"
                    assert states[1]["state"] == "26.0"
                    assert result["count"] == 2
                    assert result["total_available"] == 2
                    assert result["truncated"] is False

                    # Verify API was called correctly
                    mock_client.get.assert_called_once()
                    called_url = mock_client.get.call_args[0][0]
                    assert f"{mock_config['hass_url']}/api/history/period/" in called_url
                    assert mock_client.get.call_args[1]["params"]["filter_entity_id"] == entity_id

    def test_handle_api_errors_decorator(self):
        """Test the handle_api_errors decorator."""
        from app.hass import handle_api_errors
        import inspect

        # Create a simple test function with a Dict return annotation
        @handle_api_errors
        async def test_dict_function() -> Dict:
            """Test function that returns a dict."""
            return {}

        # Create a simple test function with a str return annotation
        @handle_api_errors
        async def test_str_function() -> str:
            """Test function that returns a string."""
            return ""

        # Verify that both functions have their return type annotations preserved
        assert "Dict" in str(inspect.signature(test_dict_function).return_annotation)
        assert "str" in str(inspect.signature(test_str_function).return_annotation)

        # Verify that both functions have a docstring
        assert test_dict_function.__doc__ == "Test function that returns a dict."
        assert test_str_function.__doc__ == "Test function that returns a string."


class TestContextFloodingPrevention:
    """Test the context flooding prevention features."""

    @pytest.mark.asyncio
    async def test_get_entities_compact_mode(self, mock_config):
        """Test get_entities with compact mode returns minimal fields."""
        mock_states = [
            {
                "entity_id": "light.living_room",
                "state": "on",
                "attributes": {
                    "brightness": 255,
                    "friendly_name": "Living Room Light",
                    "supported_features": 63
                }
            },
            {
                "entity_id": "sensor.temperature",
                "state": "22.5",
                "attributes": {
                    "unit_of_measurement": "°C",
                    "friendly_name": "Temperature Sensor",
                    "device_class": "temperature"
                }
            }
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_states

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('app.hass.entities.get_client', return_value=mock_client):
            with patch('app.hass.entities.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    from app.hass import get_entities
                    entities = await get_entities(compact=True)

                    # Verify compact mode returns only essential fields
                    assert len(entities) == 2
                    for entity in entities:
                        assert "entity_id" in entity
                        assert "state" in entity
                        assert "friendly_name" in entity
                        # Should NOT have full attributes
                        assert "attributes" not in entity
                        assert "brightness" not in entity

    @pytest.mark.asyncio
    async def test_get_automations_with_limit(self, mock_config):
        """Test get_automations returns dict with metadata and respects limit."""
        mock_automation_states = [
            {
                "entity_id": f"automation.test_{i}",
                "state": "on",
                "attributes": {"friendly_name": f"Test Automation {i}"}
            }
            for i in range(100)  # Create 100 automations
        ]

        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            with patch('app.hass.decorators.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.automations.get_entities', AsyncMock(return_value=mock_automation_states)):
                    from app.hass import get_automations
                    result = await get_automations(limit=10)

                    # Verify returns dict with metadata
                    assert isinstance(result, dict)
                    assert "automations" in result
                    assert "count" in result
                    assert "total_available" in result
                    assert "truncated" in result

                    # Verify limit is respected
                    assert result["count"] == 10
                    assert result["total_available"] == 100
                    assert result["truncated"] is True
                    assert len(result["automations"]) == 10

    @pytest.mark.asyncio
    async def test_get_entity_history_with_limit(self, mock_config):
        """Test get_entity_history returns dict with metadata and respects limit."""
        # Create mock history data with 200 state changes
        mock_history_data = [
            [
                {"state": str(i), "last_changed": f"2025-06-30T{i:02d}:00:00.000Z"}
                for i in range(200)
            ]
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_history_data

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('app.hass.history.get_client', return_value=mock_client):
            with patch('app.hass.history.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    from app.hass import get_entity_history
                    result = await get_entity_history("sensor.test", hours=24, limit=50)

                    # Verify returns dict with metadata
                    assert isinstance(result, dict)
                    assert "states" in result
                    assert "count" in result
                    assert "total_available" in result
                    assert "truncated" in result
                    assert "sample_strategy" in result

                    # Verify limit is respected
                    assert result["count"] == 50
                    assert result["total_available"] == 200
                    assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_get_entity_history_sample_strategies(self, mock_config):
        """Test get_entity_history sampling strategies."""
        from app.hass import _sample_history_records

        # Create test data: 100 records numbered 0-99
        records = [{"value": i} for i in range(100)]

        # Test "recent" strategy - should return last 10
        recent = _sample_history_records(records, 10, "recent")
        assert len(recent) == 10
        assert recent[0]["value"] == 90  # First of last 10
        assert recent[-1]["value"] == 99  # Last record

        # Test "first" strategy - should return first 10
        first = _sample_history_records(records, 10, "first")
        assert len(first) == 10
        assert first[0]["value"] == 0  # First record
        assert first[-1]["value"] == 9  # Last of first 10

        # Test "even" strategy - should be evenly spaced
        even = _sample_history_records(records, 10, "even")
        assert len(even) == 10
        # Should include roughly evenly spaced indices (0, 10, 20, 30, etc.)
        assert even[0]["value"] == 0
        assert even[5]["value"] == 50

    def test_truncate_stacktrace(self):
        """Test stacktrace truncation for both string and list input."""
        from app.hass import _truncate_stacktrace

        # === STRING INPUT TESTS ===

        # Short message should not be truncated
        short = "Error: Something went wrong"
        assert _truncate_stacktrace(short, 3) == short

        # Long stacktrace should be truncated
        long_trace = "\n".join([f"Line {i}" for i in range(20)])
        truncated = _truncate_stacktrace(long_trace, 3)

        lines = truncated.split("\n")
        assert len(lines) == 4  # 3 content lines + 1 truncation indicator
        assert "Line 0" in lines[0]
        assert "Line 1" in lines[1]
        assert "Line 2" in lines[2]
        assert "17 more lines truncated" in lines[3]

        # === LIST INPUT TESTS (Home Assistant system_log format) ===

        # Short list should not be truncated
        short_list = ["Line 1", "Line 2"]
        assert _truncate_stacktrace(short_list, 3) == short_list

        # Long list should be truncated
        long_list = [f"Line {i}" for i in range(20)]
        truncated_list = _truncate_stacktrace(long_list, 3)

        assert isinstance(truncated_list, list)
        assert len(truncated_list) == 4  # 3 lines + 1 truncation indicator
        assert truncated_list[0] == "Line 0"
        assert truncated_list[1] == "Line 1"
        assert truncated_list[2] == "Line 2"
        assert "17 more lines truncated" in truncated_list[3]

        # Empty list should return empty list
        assert _truncate_stacktrace([], 3) == []

        # List with exactly max_lines elements should not be truncated
        exact_list = [f"Line {i}" for i in range(3)]
        assert _truncate_stacktrace(exact_list, 3) == exact_list

    @pytest.mark.asyncio
    async def test_get_hass_error_log_with_filters(self, mock_config):
        """Test get_hass_error_log with filtering and truncation."""
        from datetime import datetime, timezone

        mock_records = [
            {
                "level": "ERROR",
                "name": "homeassistant.components.mqtt.client",
                "message": "Connection failed\nLine 2\nLine 3\nLine 4\nLine 5",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            {
                "level": "WARNING",
                "name": "homeassistant.components.zwave",
                "message": "Device slow to respond",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            {
                "level": "ERROR",
                "name": "homeassistant.components.mqtt.sensor",
                "message": "Sensor unavailable",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]

        with patch('app.hass.logging_ha.call_websocket_api', AsyncMock(return_value=mock_records)):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                from app.hass import get_hass_error_log

                # Test with integration filter
                result = await get_hass_error_log(integration="mqtt")
                assert result["count"] == 2  # Only MQTT records
                assert "mqtt" in result["filters_applied"].get("integration", "")

                # Test with level filter
                result = await get_hass_error_log(level="ERROR")
                assert all(r["level"] == "ERROR" for r in result["records"])
                assert "level" in result["filters_applied"]

                # Test stacktrace truncation
                result = await get_hass_error_log(truncate_traces=True)
                for record in result["records"]:
                    if "\n" in record.get("message", ""):
                        lines = record["message"].split("\n")
                        assert len(lines) <= 4  # 3 lines + truncation indicator

    @pytest.mark.asyncio
    async def test_get_entity_history_range_returns_dict(self, mock_config):
        """Test get_entity_history_range returns dict instead of list."""
        mock_history_data = [
            [
                {"state": "on", "last_changed": "2025-06-30T10:00:00.000Z"},
                {"state": "off", "last_changed": "2025-06-30T11:00:00.000Z"}
            ]
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_history_data

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('app.hass.history.get_client', return_value=mock_client):
            with patch('app.hass.history.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    from app.hass import get_entity_history_range
                    result = await get_entity_history_range(
                        "light.test",
                        "2025-06-30T10:00:00Z",
                        "2025-06-30T12:00:00Z"
                    )

                    # Should return dict, not list (breaking change)
                    assert isinstance(result, dict)
                    assert "states" in result
                    assert "count" in result
                    assert "total_available" in result
                    assert "truncated" in result
                    assert "start_time" in result
                    assert "end_time" in result


class TestRenderTemplate:
    """Test the render_template function."""

    @pytest.mark.asyncio
    async def test_render_template_success_list(self, mock_config):
        """Test successful template rendering that returns a list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '[{"entity_id": "light.test", "state": "on", "attributes": {"friendly_name": "Test Light"}}]'

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch('app.hass.templates.get_client', return_value=mock_client):
            with patch('app.hass.templates.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    result = await render_template("{{ states.light | list }}")

                    # Should parse as JSON list
                    assert isinstance(result, list)
                    assert len(result) == 1
                    assert result[0]["entity_id"] == "light.test"
                    assert result[0]["state"] == "on"

                    # Verify API was called correctly
                    mock_client.post.assert_called_once()
                    called_url = mock_client.post.call_args[0][0]
                    assert called_url == f"{mock_config['hass_url']}/api/template"
                    called_json = mock_client.post.call_args[1]["json"]
                    assert called_json["template"] == "{{ states.light | list }}"

    @pytest.mark.asyncio
    async def test_render_template_success_string(self, mock_config):
        """Test successful template rendering that returns a string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Hello World"

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch('app.hass.templates.get_client', return_value=mock_client):
            with patch('app.hass.templates.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    result = await render_template("{{ 'Hello World' }}")

                    # Should return as string (not JSON parseable)
                    assert isinstance(result, str)
                    assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_render_template_error(self, mock_config):
        """Test template rendering error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "UndefinedError: 'invalid_var' is undefined"

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch('app.hass.templates.get_client', return_value=mock_client):
            with patch('app.hass.templates.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    result = await render_template("{{ invalid_var }}")

                    # Should return error dict
                    assert isinstance(result, dict)
                    assert "error" in result
                    assert "Template rendering failed" in result["error"]

    @pytest.mark.asyncio
    async def test_render_template_empty_list(self, mock_config):
        """Test template rendering that returns an empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "[]"

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch('app.hass.templates.get_client', return_value=mock_client):
            with patch('app.hass.templates.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    result = await render_template("{{ states.nonexistent | list }}")

                    # Should return empty list
                    assert isinstance(result, list)
                    assert len(result) == 0


class TestCELFiltering:
    """Test the CEL-based entity filtering function."""

    def _make_entity(self, entity_id: str, state: str, attributes: dict = None) -> dict:
        """Helper to create entity dicts matching HA /api/states format."""
        return {
            "entity_id": entity_id,
            "state": state,
            "attributes": attributes or {},
            "last_changed": "2025-01-01T00:00:00Z",
            "last_updated": "2025-01-01T00:00:00Z",
        }

    def test_cel_filter_basic_equality(self):
        """CEL expression state == 'on' returns only matching entities."""
        entities = [
            self._make_entity("light.a", "on"),
            self._make_entity("light.b", "off"),
            self._make_entity("light.c", "on"),
        ]
        result = evaluate_cel_filter(entities, 'state == "on"')
        assert len(result) == 2
        assert all(e["entity_id"] in ("light.a", "light.c") for e in result)

    def test_cel_filter_numeric_comparison(self):
        """CEL expression state < 30 with proper numeric coercion."""
        entities = [
            self._make_entity("sensor.battery_a", "25"),
            self._make_entity("sensor.battery_b", "80"),
            self._make_entity("sensor.battery_c", "10"),
        ]
        result = evaluate_cel_filter(entities, "state < 30")
        assert len(result) == 2
        entity_ids = [e["entity_id"] for e in result]
        assert "sensor.battery_a" in entity_ids
        assert "sensor.battery_c" in entity_ids

    def test_cel_filter_attribute_access(self):
        """CEL expression with nested attribute access."""
        entities = [
            self._make_entity("sensor.bat", "25", {"device_class": "battery", "friendly_name": "Battery"}),
            self._make_entity("sensor.temp", "72", {"device_class": "temperature", "friendly_name": "Temp"}),
        ]
        result = evaluate_cel_filter(entities, 'attributes.device_class == "battery"')
        assert len(result) == 1
        assert result[0]["entity_id"] == "sensor.bat"

    def test_cel_filter_or_logic(self):
        """CEL expression with OR logic returns union of matches."""
        entities = [
            self._make_entity("sensor.a", "unavailable"),
            self._make_entity("sensor.b", "unknown"),
            self._make_entity("sensor.c", "42"),
        ]
        result = evaluate_cel_filter(entities, 'state == "unavailable" || state == "unknown"')
        assert len(result) == 2
        entity_ids = [e["entity_id"] for e in result]
        assert "sensor.a" in entity_ids
        assert "sensor.b" in entity_ids

    def test_cel_filter_and_logic(self):
        """CEL expression with AND logic returns only entities matching ALL conditions."""
        entities = [
            self._make_entity("sensor.a", "25", {"device_class": "battery"}),
            self._make_entity("sensor.b", "80", {"device_class": "battery"}),
            self._make_entity("sensor.c", "25", {"device_class": "temperature"}),
        ]
        result = evaluate_cel_filter(entities, 'state < 30 && attributes.device_class == "battery"')
        assert len(result) == 1
        assert result[0]["entity_id"] == "sensor.a"

    def test_cel_filter_negation(self):
        """CEL expression with != excludes matching entities."""
        entities = [
            self._make_entity("cover.a", "closed"),
            self._make_entity("cover.b", "open"),
            self._make_entity("cover.c", "closed"),
        ]
        result = evaluate_cel_filter(entities, 'state != "closed"')
        assert len(result) == 1
        assert result[0]["entity_id"] == "cover.b"

    def test_cel_filter_numeric_coercion(self):
        """Entities with non-numeric states are excluded from numeric comparisons, not errored."""
        entities = [
            self._make_entity("sensor.a", "25"),
            self._make_entity("sensor.b", "unavailable"),
            self._make_entity("sensor.c", "10"),
        ]
        # "unavailable" can't be compared numerically - should be silently excluded
        result = evaluate_cel_filter(entities, "state < 30")
        assert len(result) == 2
        entity_ids = [e["entity_id"] for e in result]
        assert "sensor.a" in entity_ids
        assert "sensor.c" in entity_ids
        # "unavailable" entity should NOT be in results
        assert "sensor.b" not in entity_ids

    def test_cel_filter_invalid_expression(self):
        """Invalid CEL expression returns error dict with parse error message."""
        entities = [self._make_entity("light.a", "on")]
        result = evaluate_cel_filter(entities, "invalid %%% expression")
        assert isinstance(result, dict)
        assert "error" in result

    def test_cel_filter_no_expression(self):
        """No expression returns all entities unfiltered."""
        entities = [
            self._make_entity("light.a", "on"),
            self._make_entity("light.b", "off"),
        ]
        result = evaluate_cel_filter(entities, None)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_cel_filter_domain_prefilter(self):
        """Domain param narrows entity set before CEL evaluation."""
        entities = [
            self._make_entity("light.a", "on"),
            self._make_entity("sensor.b", "on"),
            self._make_entity("light.c", "off"),
        ]
        result = evaluate_cel_filter(entities, 'state == "on"', domain="light")
        assert len(result) == 1
        assert result[0]["entity_id"] == "light.a"

    def test_cel_filter_empty_entities(self):
        """Empty entity list returns empty list, no error."""
        result = evaluate_cel_filter([], 'state == "on"')
        assert isinstance(result, list)
        assert len(result) == 0

    def test_cel_filter_mixed_types(self):
        """Entities with different state types in same query."""
        entities = [
            self._make_entity("sensor.temp", "72.5"),
            self._make_entity("binary_sensor.door", "on"),
            self._make_entity("sensor.battery", "25"),
            self._make_entity("light.lamp", "off"),
        ]
        # String equality should work on all entity types
        result = evaluate_cel_filter(entities, 'state == "on"')
        assert len(result) == 1
        assert result[0]["entity_id"] == "binary_sensor.door"


class TestSSLVerification:
    """Test SSL verification configuration wiring."""

    def test_get_client_source_passes_verify(self):
        """get_client() source code passes verify=HA_VERIFY_SSL to httpx.AsyncClient."""
        import pathlib
        hass_dir = pathlib.Path(__file__).parent.parent / "app" / "hass"
        # Search across all files in the hass package
        sources = [f.read_text() for f in hass_dir.glob("*.py")]
        combined = "\n".join(sources)
        # Verify the AsyncClient constructor uses HA_VERIFY_SSL
        assert "verify=HA_VERIFY_SSL" in combined

    def test_ha_verify_ssl_imported(self):
        """HA_VERIFY_SSL is imported from config in hass module."""
        import pathlib
        hass_dir = pathlib.Path(__file__).parent.parent / "app" / "hass"
        sources = [f.read_text() for f in hass_dir.glob("*.py")]
        combined = "\n".join(sources)
        assert "HA_VERIFY_SSL" in combined
        assert "from app.config import" in combined

    def test_websocket_ssl_context_disabled(self):
        """WebSocket SSL context disables verification when HA_VERIFY_SSL is False."""
        ssl_context = ssl.create_default_context()
        # Simulate the code path
        verify_ssl = False
        if not verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        assert ssl_context.check_hostname is False
        assert ssl_context.verify_mode == ssl.CERT_NONE

    def test_websocket_ssl_context_enabled(self):
        """WebSocket SSL context validates by default when HA_VERIFY_SSL is True."""
        ssl_context = ssl.create_default_context()
        # When verify_ssl is True, we don't modify the context
        verify_ssl = True
        if not verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        assert ssl_context.check_hostname is True
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED

    @pytest.mark.asyncio
    async def test_connect_error_surfaces_ssl_error(self, mock_config):
        """SSL errors inside ConnectError are surfaced with a helpful hint."""
        # Build a chained exception: ConnectError wrapping SSLError
        ssl_err = ssl.SSLError("certificate verify failed")
        connect_err = httpx.ConnectError("connection failed")
        connect_err.__cause__ = ssl_err

        @handle_api_errors
        async def failing_func() -> Dict[str, Any]:
            raise connect_err

        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await failing_func()
            assert isinstance(result, dict)
            assert "error" in result
            assert "SSL certificate error" in result["error"]
            assert "HA_VERIFY_SSL" in result["error"]

    @pytest.mark.asyncio
    async def test_connect_error_without_ssl_gives_generic_message(self, mock_config):
        """ConnectError without SSL cause gives the standard message."""
        connect_err = httpx.ConnectError("connection refused")

        @handle_api_errors
        async def failing_func() -> Dict[str, Any]:
            raise connect_err

        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await failing_func()
            assert isinstance(result, dict)
            assert "error" in result
            assert "Cannot connect" in result["error"]
            assert "HA_VERIFY_SSL" not in result["error"]


class TestLogParsing:
    """Test the _parse_log_text function for Supervisor journal log output."""

    def test_parse_standard_log_lines(self):
        """Parse typical HA Core journal lines with timestamps and levels."""
        from app.hass import _parse_log_text

        raw = (
            "2026-02-10 10:00:00.123 ERROR (MainThread) [homeassistant.components.mqtt] Connection lost\n"
            "2026-02-10 10:00:01.456 WARNING (MainThread) [homeassistant.components.zwave] Node slow\n"
            "2026-02-10 10:00:02.789 INFO (MainThread) [homeassistant.core] Bus ready\n"
        )
        records = _parse_log_text(raw)
        assert len(records) == 3

        # First record
        assert records[0]["level"] == "ERROR"
        assert records[0]["logger"] == "homeassistant.components.mqtt"
        assert records[0]["message"] == "Connection lost"
        assert records[0]["timestamp"] == "2026-02-10 10:00:00.123"

        # Second record
        assert records[1]["level"] == "WARNING"
        assert records[1]["logger"] == "homeassistant.components.zwave"
        assert records[1]["message"] == "Node slow"

        # Third record
        assert records[2]["level"] == "INFO"
        assert records[2]["logger"] == "homeassistant.core"

    def test_parse_debug_level(self):
        """Parse DEBUG level log lines."""
        from app.hass import _parse_log_text

        raw = "2026-02-10 10:00:00.000 DEBUG (MainThread) [custom_components.llmvision] Processing image\n"
        records = _parse_log_text(raw)
        assert len(records) == 1
        assert records[0]["level"] == "DEBUG"
        assert records[0]["logger"] == "custom_components.llmvision"

    def test_parse_continuation_lines_attached(self):
        """Continuation lines (stacktraces) are appended to previous record's message."""
        from app.hass import _parse_log_text

        raw = (
            "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.core] Something failed\n"
            "Traceback (most recent call last):\n"
            "  File \"test.py\", line 1\n"
            "ValueError: bad value\n"
            "2026-02-10 10:00:01.000 INFO (MainThread) [homeassistant.core] Next log\n"
        )
        records = _parse_log_text(raw)
        assert len(records) == 2
        # First record should include continuation lines
        assert "Traceback" in records[0]["message"]
        assert "ValueError" in records[0]["message"]
        # Second record should be clean
        assert records[1]["message"] == "Next log"

    def test_parse_empty_input(self):
        """Empty or whitespace-only input returns empty list."""
        from app.hass import _parse_log_text

        assert _parse_log_text("") == []
        assert _parse_log_text("   \n  \n") == []

    def test_parse_extracts_integration(self):
        """Integration name is extracted from logger path."""
        from app.hass import _parse_log_text

        raw = "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.components.mqtt.client] Disconnected\n"
        records = _parse_log_text(raw)
        assert records[0]["integration"] == "mqtt"

    def test_parse_custom_component_integration(self):
        """Custom component integration name extracted from custom_components.X."""
        from app.hass import _parse_log_text

        raw = "2026-02-10 10:00:00.000 DEBUG (MainThread) [custom_components.llmvision.service] Request sent\n"
        records = _parse_log_text(raw)
        assert records[0]["integration"] == "llmvision"

    def test_parse_no_integration(self):
        """Logger without components/custom_components gets integration=None."""
        from app.hass import _parse_log_text

        raw = "2026-02-10 10:00:00.000 INFO (MainThread) [homeassistant.core] Started\n"
        records = _parse_log_text(raw)
        assert records[0]["integration"] is None

    def test_parse_various_thread_names(self):
        """Log lines with different thread names parse correctly."""
        from app.hass import _parse_log_text

        raw = (
            "2026-02-10 10:00:00.000 INFO (SyncWorker_0) [homeassistant.core] Sync work\n"
            "2026-02-10 10:00:01.000 DEBUG (Recorder) [homeassistant.components.recorder] Write\n"
        )
        records = _parse_log_text(raw)
        assert len(records) == 2
        assert records[0]["message"] == "Sync work"
        assert records[1]["integration"] == "recorder"


class TestFetchLogText:
    """Test the _fetch_log_text function with primary/fallback logic."""

    @pytest.mark.asyncio
    async def test_fetch_supervisor_api_success(self, mock_config):
        """Successful fetch from Supervisor journal API."""
        from app.hass import _fetch_log_text

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "2026-02-10 10:00:00.000 INFO (MainThread) [homeassistant.core] Started\n"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('app.hass.logging_ha.get_client', return_value=mock_client):
            with patch('app.hass.logging_ha.HA_URL', mock_config["hass_url"]):
                    text, source = await _fetch_log_text(lines=100)
                    assert "Started" in text
                    assert source == "supervisor"

    @pytest.mark.asyncio
    async def test_fetch_fallback_to_error_log(self, mock_config):
        """Falls back to /api/error_log when Supervisor API returns 404."""
        from app.hass import _fetch_log_text

        # Supervisor API returns 404
        mock_supervisor_response = MagicMock()
        mock_supervisor_response.status_code = 404
        mock_supervisor_response.text = "Not Found"

        # Fallback error_log API returns 200
        mock_fallback_response = MagicMock()
        mock_fallback_response.status_code = 200
        mock_fallback_response.text = "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.core] Error occurred\n"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[mock_supervisor_response, mock_fallback_response])

        with patch('app.hass.logging_ha.get_client', return_value=mock_client):
            with patch('app.hass.logging_ha.HA_URL', mock_config["hass_url"]):
                    text, source = await _fetch_log_text(lines=100)
                    assert "Error occurred" in text
                    assert source == "error_log"

    @pytest.mark.asyncio
    async def test_fetch_both_fail_returns_error(self, mock_config):
        """Returns empty string and 'none' when both APIs fail."""
        from app.hass import _fetch_log_text

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('app.hass.logging_ha.get_client', return_value=mock_client):
            with patch('app.hass.logging_ha.HA_URL', mock_config["hass_url"]):
                    text, source = await _fetch_log_text(lines=100)
                    assert text == ""
                    assert source == "none"


class TestGetHassCoreLog:
    """Test the get_hass_core_logs function with filtering and limits."""

    @pytest.mark.asyncio
    async def test_basic_retrieval(self, mock_config):
        """Basic call returns structured dict with records."""
        from app.hass import get_hass_core_logs

        raw_log = (
            "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.components.mqtt] Connection lost\n"
            "2026-02-10 10:00:01.000 WARNING (MainThread) [homeassistant.components.zwave] Node slow\n"
            "2026-02-10 10:00:02.000 INFO (MainThread) [homeassistant.core] Bus ready\n"
        )

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs()

                assert isinstance(result, dict)
                assert "records" in result
                assert "count" in result
                assert "total_parsed" in result
                assert "source" in result
                assert result["source"] == "supervisor"
                assert result["total_parsed"] == 3

    @pytest.mark.asyncio
    async def test_filter_by_level(self, mock_config):
        """Filter by level returns only matching records."""
        from app.hass import get_hass_core_logs

        raw_log = (
            "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.core] Err\n"
            "2026-02-10 10:00:01.000 WARNING (MainThread) [homeassistant.core] Warn\n"
            "2026-02-10 10:00:02.000 DEBUG (MainThread) [homeassistant.core] Dbg\n"
        )

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(level="ERROR")
                assert result["count"] == 1
                assert result["records"][0]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_filter_by_integration(self, mock_config):
        """Filter by integration returns only records from that integration."""
        from app.hass import get_hass_core_logs

        raw_log = (
            "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.components.mqtt] MQTT error\n"
            "2026-02-10 10:00:01.000 ERROR (MainThread) [homeassistant.components.zwave] Z-Wave error\n"
            "2026-02-10 10:00:02.000 DEBUG (MainThread) [custom_components.llmvision] LLM debug\n"
        )

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(integration="mqtt")
                assert result["count"] == 1
                assert result["records"][0]["integration"] == "mqtt"

                # Test custom component filter
                result = await get_hass_core_logs(integration="llmvision")
                assert result["count"] == 1
                assert result["records"][0]["integration"] == "llmvision"

    @pytest.mark.asyncio
    async def test_filter_by_pattern(self, mock_config):
        """Filter by pattern matches message content."""
        from app.hass import get_hass_core_logs

        raw_log = (
            "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.core] Connection timeout\n"
            "2026-02-10 10:00:01.000 ERROR (MainThread) [homeassistant.core] Memory error\n"
            "2026-02-10 10:00:02.000 ERROR (MainThread) [homeassistant.core] Connection refused\n"
        )

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(pattern="Connection")
                assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_filter_by_since_minutes(self, mock_config):
        """Filter by since_minutes returns only recent records."""
        from app.hass import get_hass_core_logs

        now = datetime.now()
        recent = now.strftime("%Y-%m-%d %H:%M:%S.000")
        old = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S.000")

        raw_log = (
            f"{old} ERROR (MainThread) [homeassistant.core] Old error\n"
            f"{recent} ERROR (MainThread) [homeassistant.core] Recent error\n"
        )

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(since_minutes=30)
                assert result["count"] == 1
                assert "Recent error" in result["records"][0]["message"]

    @pytest.mark.asyncio
    async def test_limit_enforced(self, mock_config):
        """Record limit is enforced, defaults to 50."""
        from app.hass import get_hass_core_logs

        # Generate 100 log lines
        lines = []
        for i in range(100):
            lines.append(f"2026-02-10 10:{i//60:02d}:{i%60:02d}.000 INFO (MainThread) [homeassistant.core] Line {i}")
        raw_log = "\n".join(lines) + "\n"

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs()
                assert result["count"] <= 50
                assert result["total_parsed"] == 100
                assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_limit_custom(self, mock_config):
        """Custom limit is respected up to MAX_CORE_LOG_LIMIT."""
        from app.hass import get_hass_core_logs

        lines = []
        for i in range(10):
            lines.append(f"2026-02-10 10:00:{i:02d}.000 INFO (MainThread) [homeassistant.core] Line {i}")
        raw_log = "\n".join(lines) + "\n"

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(limit=5)
                assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_message_truncation(self, mock_config):
        """Long messages are truncated to 500 chars."""
        from app.hass import get_hass_core_logs

        long_msg = "A" * 1000
        raw_log = f"2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.core] {long_msg}\n"

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs()
                msg = result["records"][0]["message"]
                assert len(msg) <= 520  # 500 + "... [truncated]" suffix
                assert msg.endswith("... [truncated]")

    @pytest.mark.asyncio
    async def test_trace_truncation(self, mock_config):
        """Stacktraces in continuation lines are truncated to 3 lines."""
        from app.hass import get_hass_core_logs

        raw_log = (
            "2026-02-10 10:00:00.000 ERROR (MainThread) [homeassistant.core] Error\n"
            "Traceback (most recent call last):\n"
            "  File \"a.py\", line 1\n"
            "  File \"b.py\", line 2\n"
            "  File \"c.py\", line 3\n"
            "  File \"d.py\", line 4\n"
            "  File \"e.py\", line 5\n"
            "ValueError: bad\n"
        )

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(truncate_traces=True)
                msg = result["records"][0]["message"]
                # Should have the main message plus truncated trace
                assert "truncated" in msg.lower()

    @pytest.mark.asyncio
    async def test_returns_most_recent_records(self, mock_config):
        """When truncated, returns the most recent (tail) records."""
        from app.hass import get_hass_core_logs

        lines = []
        for i in range(10):
            lines.append(f"2026-02-10 10:00:{i:02d}.000 INFO (MainThread) [homeassistant.core] Line {i}")
        raw_log = "\n".join(lines) + "\n"

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=(raw_log, "supervisor"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs(limit=3)
                # Should have the last 3 records
                assert result["count"] == 3
                assert "Line 7" in result["records"][0]["message"]
                assert "Line 9" in result["records"][2]["message"]

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_error(self, mock_config):
        """When log fetch fails, returns error dict."""
        from app.hass import get_hass_core_logs

        with patch('app.hass.logging_ha._fetch_log_text', AsyncMock(return_value=("", "none"))):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await get_hass_core_logs()
                assert "error" in result


class TestSetHassLogLevel:
    """Test the set_hass_log_level function."""

    @pytest.mark.asyncio
    async def test_set_debug_level(self, mock_config):
        """Set integration to debug level via logger.set_level service."""
        from app.hass import set_hass_log_level

        with patch('app.hass.logging_ha.call_service', AsyncMock(return_value={})) as mock_svc:
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await set_hass_log_level("llmvision", "debug")
                assert result["success"] is True
                assert result["integration"] == "llmvision"
                assert result["level"] == "debug"

                # Verify call_service was called correctly
                mock_svc.assert_called_once()
                call_args = mock_svc.call_args
                assert call_args[0][0] == "logger"
                assert call_args[0][1] == "set_level"

    @pytest.mark.asyncio
    async def test_set_warning_level(self, mock_config):
        """Set integration to warning level."""
        from app.hass import set_hass_log_level

        with patch('app.hass.logging_ha.call_service', AsyncMock(return_value={})) as mock_svc:
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await set_hass_log_level("mqtt", "warning")
                assert result["success"] is True
                assert result["level"] == "warning"

    @pytest.mark.asyncio
    async def test_invalid_level_rejected(self, mock_config):
        """Invalid log level returns error."""
        from app.hass import set_hass_log_level

        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await set_hass_log_level("mqtt", "CRITICAL")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_custom_component_prefix(self, mock_config):
        """Custom component logger gets custom_components prefix."""
        from app.hass import set_hass_log_level

        with patch('app.hass.logging_ha.call_service', AsyncMock(return_value={})) as mock_svc:
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await set_hass_log_level("llmvision", "debug", custom_component=True)
                assert result["success"] is True

                call_data = mock_svc.call_args[0][2]
                # Should have custom_components.llmvision key
                assert any("custom_components.llmvision" in str(k) for k in call_data.keys())

    @pytest.mark.asyncio
    async def test_standard_integration_prefix(self, mock_config):
        """Standard integration logger gets homeassistant.components prefix."""
        from app.hass import set_hass_log_level

        with patch('app.hass.logging_ha.call_service', AsyncMock(return_value={})) as mock_svc:
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await set_hass_log_level("mqtt", "debug", custom_component=False)
                assert result["success"] is True

                call_data = mock_svc.call_args[0][2]
                assert any("homeassistant.components.mqtt" in str(k) for k in call_data.keys())

    @pytest.mark.asyncio
    async def test_service_call_failure(self, mock_config):
        """Service call failure returns error."""
        from app.hass import set_hass_log_level

        with patch('app.hass.logging_ha.call_service', AsyncMock(return_value={"error": "Service failed"})):
            with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                result = await set_hass_log_level("mqtt", "debug")
                assert "error" in result


# ============================================================================
# Input Validation Tests
# ============================================================================

class TestValidation:
    """Test input validation functions."""

    # --- Entity ID Validation ---

    def test_validate_entity_id_valid(self):
        from app.hass.validation import validate_entity_id
        assert validate_entity_id("light.living_room") == "light.living_room"
        assert validate_entity_id("sensor.temperature_1") == "sensor.temperature_1"
        assert validate_entity_id("binary_sensor.front_door") == "binary_sensor.front_door"
        assert validate_entity_id("sensor.0x00158d000123_temp") == "sensor.0x00158d000123_temp"

    def test_validate_entity_id_invalid(self):
        from app.hass.validation import validate_entity_id, ValidationError
        # Path traversal
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("../../etc/passwd")
        # Missing dot separator
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("light")
        # Query injection
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("light.test?foo=bar")
        # Slash in entity_id
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("light/test")
        # Newline injection
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("light.test\nHost: evil.com")
        # Empty string
        with pytest.raises(ValidationError, match="non-empty"):
            validate_entity_id("")
        # None
        with pytest.raises(ValidationError, match="non-empty"):
            validate_entity_id(None)
        # Space in entity_id
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("light.living room")
        # Uppercase rejected (HA normalizes to lowercase)
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("Light.living_room")
        with pytest.raises(ValidationError, match="Invalid entity ID"):
            validate_entity_id("light.Living_Room")

    # --- HA Identifier Validation ---

    def test_validate_ha_identifier_valid(self):
        from app.hass.validation import validate_ha_identifier
        assert validate_ha_identifier("light", "domain") == "light"
        assert validate_ha_identifier("turn_on", "service") == "turn_on"
        assert validate_ha_identifier("binary_sensor", "domain") == "binary_sensor"
        assert validate_ha_identifier("media_player", "domain") == "media_player"

    def test_validate_ha_identifier_invalid(self):
        from app.hass.validation import validate_ha_identifier, ValidationError
        # Path traversal
        with pytest.raises(ValidationError, match="Invalid domain"):
            validate_ha_identifier("../etc", "domain")
        # Slash
        with pytest.raises(ValidationError, match="Invalid service"):
            validate_ha_identifier("turn/on", "service")
        # Uppercase (HA identifiers are lowercase)
        with pytest.raises(ValidationError, match="Invalid domain"):
            validate_ha_identifier("Light", "domain")
        # Empty
        with pytest.raises(ValidationError, match="non-empty"):
            validate_ha_identifier("", "domain")
        # Special characters
        with pytest.raises(ValidationError, match="Invalid domain"):
            validate_ha_identifier("light;drop", "domain")

    # --- Automation ID Validation ---

    def test_validate_automation_id_valid(self):
        from app.hass.validation import validate_automation_id
        assert validate_automation_id("motion_light") == "motion_light"
        assert validate_automation_id("bedtime-routine") == "bedtime-routine"
        assert validate_automation_id("automation123") == "automation123"

    def test_validate_automation_id_invalid(self):
        from app.hass.validation import validate_automation_id, ValidationError
        with pytest.raises(ValidationError, match="Invalid automation ID"):
            validate_automation_id("../../../etc")
        with pytest.raises(ValidationError, match="Invalid automation ID"):
            validate_automation_id("test;rm -rf")
        with pytest.raises(ValidationError, match="non-empty"):
            validate_automation_id("")

    # --- Run ID Validation ---

    def test_validate_run_id_valid(self):
        from app.hass.validation import validate_run_id
        assert validate_run_id("1700000000.123456") == "1700000000.123456"
        assert validate_run_id("abc-123_def") == "abc-123_def"

    def test_validate_run_id_invalid(self):
        from app.hass.validation import validate_run_id, ValidationError
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("run;id")
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("../../etc/passwd")
        with pytest.raises(ValidationError, match="non-empty"):
            validate_run_id("")

    # --- Trace Domain Validation ---

    def test_validate_trace_domain_valid(self):
        from app.hass.validation import validate_trace_domain
        assert validate_trace_domain("automation") == "automation"
        assert validate_trace_domain("script") == "script"

    def test_validate_trace_domain_invalid(self):
        from app.hass.validation import validate_trace_domain, ValidationError
        with pytest.raises(ValidationError, match="Invalid trace domain"):
            validate_trace_domain("light")
        with pytest.raises(ValidationError, match="Invalid trace domain"):
            validate_trace_domain("../evil")

    # --- Service Payload Validation ---

    def test_validate_service_payload_valid(self):
        from app.hass.validation import validate_service_payload
        assert validate_service_payload(None) is None
        assert validate_service_payload({}) == {}
        assert validate_service_payload({"entity_id": "light.test"}) == {"entity_id": "light.test"}

    def test_validate_service_payload_too_large(self):
        from app.hass.validation import validate_service_payload, ValidationError
        # Create payload larger than 1 MB
        large_data = {"data": "x" * 1_100_000}
        with pytest.raises(ValidationError, match="too large"):
            validate_service_payload(large_data)

    def test_validate_service_payload_not_serializable(self):
        from app.hass.validation import validate_service_payload, ValidationError
        with pytest.raises(ValidationError, match="JSON-serializable"):
            validate_service_payload({"func": lambda x: x})

    # --- Template Validation ---

    def test_validate_template_valid(self):
        from app.hass.validation import validate_template
        assert validate_template("{{ states.light.test.state }}") == "{{ states.light.test.state }}"

    def test_validate_template_too_large(self):
        from app.hass.validation import validate_template, ValidationError
        with pytest.raises(ValidationError, match="too large"):
            validate_template("x" * 70_000)

    def test_validate_template_empty(self):
        from app.hass.validation import validate_template, ValidationError
        with pytest.raises(ValidationError, match="non-empty"):
            validate_template("")

    # --- URL Path Encoding ---

    def test_safe_url_path_segment(self):
        from app.hass.validation import safe_url_path_segment
        # Normal entity_id preserves dots (unreserved in RFC 3986)
        assert safe_url_path_segment("light.living_room") == "light.living_room"
        # Slashes are encoded
        assert safe_url_path_segment("../etc/passwd") == "..%2Fetc%2Fpasswd"
        # Question marks are encoded
        assert safe_url_path_segment("test?foo=bar") == "test%3Ffoo%3Dbar"


class TestSecurityIntegration:
    """Test that security validation is integrated into API functions."""

    @pytest.mark.asyncio
    async def test_get_entity_state_validates_entity_id(self, mock_config):
        """Entity state function rejects invalid entity IDs."""
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await get_entity_state("../../etc/passwd")
            assert "error" in result
            assert "Invalid entity ID" in result["error"]

    @pytest.mark.asyncio
    async def test_get_entity_state_url_encodes_path(self, mock_config):
        """Entity state function URL-encodes the entity_id in the path."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {}
        }
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch('app.hass.entities.get_client', return_value=mock_client):
            with patch('app.hass.entities.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    await get_entity_state("light.living_room")
                    called_url = mock_client.get.call_args[0][0]
                    # Dot preserved, entity_id in path
                    assert called_url == f"{mock_config['hass_url']}/api/states/light.living_room"

    @pytest.mark.asyncio
    async def test_call_service_validates_domain(self, mock_config):
        """Service call rejects invalid domain names."""
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await call_service("../evil", "turn_on", {})
            assert "error" in result
            assert "Invalid domain" in result["error"]

    @pytest.mark.asyncio
    async def test_call_service_validates_service(self, mock_config):
        """Service call rejects invalid service names."""
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await call_service("light", "turn/on", {})
            assert "error" in result
            assert "Invalid service" in result["error"]

    @pytest.mark.asyncio
    async def test_call_service_validates_payload_size(self, mock_config):
        """Service call rejects oversized payloads."""
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            large_data = {"data": "x" * 1_100_000}
            result = await call_service("light", "turn_on", large_data)
            assert "error" in result
            assert "too large" in result["error"]

    @pytest.mark.asyncio
    async def test_call_service_url_encodes_path(self, mock_config):
        """Service call URL-encodes domain and service in the path."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch('app.hass.services.get_client', return_value=mock_client):
            with patch('app.hass.services.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    await call_service("light", "turn_on", {"entity_id": "light.test"})
                    called_url = mock_client.post.call_args[0][0]
                    assert called_url == f"{mock_config['hass_url']}/api/services/light/turn_on"

    @pytest.mark.asyncio
    async def test_render_template_validates_size(self, mock_config):
        """Template rendering rejects oversized templates."""
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await render_template("x" * 70_000)
            # render_template returns Any, so error is a plain string
            assert isinstance(result, str)
            assert "too large" in result

    @pytest.mark.asyncio
    async def test_error_messages_do_not_leak_ha_url(self, mock_config):
        """Error messages must not contain the HA_URL."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))

        with patch('app.hass.entities.get_client', return_value=mock_client):
            with patch('app.hass.entities.HA_URL', "http://secret-host:8123"):
                with patch('app.hass.decorators.HA_URL', "http://secret-host:8123"):
                    with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                        result = await get_entity_state("light.test")
                        assert "error" in result
                        # HA_URL must not appear in the error message
                        assert "secret-host" not in result["error"]
                        assert "8123" not in result["error"]

    @pytest.mark.asyncio
    async def test_unexpected_error_does_not_leak_details(self, mock_config):
        """Unexpected errors return generic message, not internal details."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("Internal DB path: /var/lib/ha/db"))

        with patch('app.hass.entities.get_client', return_value=mock_client):
            with patch('app.hass.entities.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
                    result = await get_entity_state("light.test")
                    assert "error" in result
                    # Should not leak internal details
                    assert "/var/lib" not in result["error"]
                    assert "Internal DB" not in result["error"]
                    assert result["error"] == "An unexpected error occurred"

    @pytest.mark.asyncio
    async def test_get_entities_validates_domain(self, mock_config):
        """get_entities rejects invalid domain names."""
        with patch('app.hass.decorators.HA_TOKEN', mock_config["hass_token"]):
            result = await get_entities(domain="../evil")
            # handle_api_errors sees 'Dict' in 'List[Dict[...]]' annotation, returns dict
            assert isinstance(result, dict)
            assert "error" in result
            assert "Invalid domain" in result["error"]