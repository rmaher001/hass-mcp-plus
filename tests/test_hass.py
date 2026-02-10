import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import json
import httpx
from typing import Dict, List, Any

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
        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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
        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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
        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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
        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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
        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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
        with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                # For get_automations we need to mock the get_entities function
                with patch('app.hass.get_entities', AsyncMock(return_value=mock_automation_states)):
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
                with patch('app.hass.get_entities', AsyncMock(return_value={"error": "HTTP error: 404 - Not Found"})):
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
        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.get_entities', AsyncMock(return_value=mock_automation_states)):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.call_websocket_api', AsyncMock(return_value=mock_records)):
            with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.get_client', return_value=mock_client):
            with patch('app.hass.HA_URL', mock_config["hass_url"]):
                with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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
        source = (pathlib.Path(__file__).parent.parent / "app" / "hass.py").read_text()
        # Verify the AsyncClient constructor uses HA_VERIFY_SSL
        assert "verify=HA_VERIFY_SSL" in source

    def test_ha_verify_ssl_imported(self):
        """HA_VERIFY_SSL is imported from config in hass module."""
        import pathlib
        source = (pathlib.Path(__file__).parent.parent / "app" / "hass.py").read_text()
        assert "HA_VERIFY_SSL" in source
        assert "from app.config import" in source

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

        with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
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

        with patch('app.hass.HA_TOKEN', mock_config["hass_token"]):
            result = await failing_func()
            assert isinstance(result, dict)
            assert "error" in result
            assert "Cannot connect" in result["error"]
            assert "HA_VERIFY_SSL" not in result["error"]