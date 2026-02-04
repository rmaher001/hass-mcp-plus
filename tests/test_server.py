import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import os
import sys
import uuid

# Add the app directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
app_dir = os.path.join(parent_dir, "app")
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

class TestMCPServer:
    """Test the MCP server functionality."""
    
    def test_server_version(self):
        """Test that the server has a version attribute."""
        # Import the server module directly without mocking
        # This ensures we're testing the actual code
        from app.server import mcp
        
        # All MCP servers should have a name, and it should be "Hass-MCP"
        assert hasattr(mcp, "name")
        assert mcp.name == "Hass-MCP"

    def test_async_handler_decorator(self):
        """Test the async_handler decorator."""
        # Import the decorator
        from app.server import async_handler
        
        # Create a test async function
        async def test_func(arg1, arg2=None):
            return f"{arg1}_{arg2}"
        
        # Apply the decorator
        decorated_func = async_handler("test_command")(test_func)
        
        # Run the decorated function
        result = asyncio.run(decorated_func("val1", arg2="val2"))
        
        # Verify the result
        assert result == "val1_val2"
    
    def test_tool_functions_exist(self):
        """Test that tool functions exist in the server module."""
        # Import the server module directly
        import app.server
        
        # List of expected tool functions
        expected_tools = [
            "get_version",
            "get_entity", 
            "list_entities",
            "entity_action",
            "domain_summary_tool",  # Domain summaries tool
            "call_service_tool",
            "restart_ha",
            "list_automations"
        ]
        
        # Check that each expected tool function exists
        for tool_name in expected_tools:
            assert hasattr(app.server, tool_name)
            assert callable(getattr(app.server, tool_name))
    
    def test_resource_functions_exist(self):
        """Test that resource functions exist in the server module."""
        # Import the server module directly
        import app.server
        
        # List of expected resource functions - Use only the ones actually in server.py
        expected_resources = [
            "get_entity_resource", 
            "get_entity_resource_detailed",
            "get_all_entities_resource", 
            "list_states_by_domain_resource",     # Domain-specific resource
            "search_entities_resource_with_limit"  # Search resource with limit parameter
        ]
        
        # Check that each expected resource function exists
        for resource_name in expected_resources:
            assert hasattr(app.server, resource_name)
            assert callable(getattr(app.server, resource_name))
            
    @pytest.mark.asyncio
    async def test_list_automations_error_handling(self):
        """Test that list_automations handles errors properly."""
        from app.server import list_automations

        # Mock the get_automations function with different scenarios
        with patch("app.server.get_automations") as mock_get_automations:
            # Case 1: Test with dict error response
            mock_get_automations.return_value = {"error": "HTTP error: 404 - Not Found"}

            # Should return a dict with empty automations list and error
            result = await list_automations()
            assert isinstance(result, dict)
            assert result["automations"] == []
            assert "error" in result

            # Case 2: Test with unexpected error (exception)
            mock_get_automations.side_effect = Exception("Unexpected error")

            # Should return a dict with empty automations list and error
            result = await list_automations()
            assert isinstance(result, dict)
            assert result["automations"] == []
            assert "error" in result
            assert "Unexpected error" in result["error"]

            # Case 3: Test with successful response (new dict format)
            mock_automations = {
                "automations": [
                    {
                        "id": "morning_lights",
                        "entity_id": "automation.morning_lights",
                        "state": "on",
                        "alias": "Turn on lights in the morning"
                    }
                ],
                "count": 1,
                "total_available": 1,
                "truncated": False
            }
            mock_get_automations.side_effect = None
            mock_get_automations.return_value = mock_automations

            # Should return the automations dict
            result = await list_automations()
            assert isinstance(result, dict)
            assert len(result["automations"]) == 1
            assert result["automations"][0]["id"] == "morning_lights"
            assert result["count"] == 1
            
    def test_tools_have_proper_docstrings(self):
        """Test that tool functions have proper docstrings"""
        # Import the server module directly
        import app.server
        
        # List of expected tool functions
        tool_functions = [
            "get_version",
            "get_entity", 
            "list_entities",
            "entity_action",
            "domain_summary_tool",
            "call_service_tool",
            "restart_ha",
            "list_automations",
            "search_entities_tool", 
            "system_overview",
            "get_error_log"
        ]
        
        # Check that each tool function has a proper docstring and exists
        for tool_name in tool_functions:
            assert hasattr(app.server, tool_name), f"{tool_name} function missing"
            tool_function = getattr(app.server, tool_name)
            assert tool_function.__doc__ is not None, f"{tool_name} missing docstring"
            assert len(tool_function.__doc__.strip()) > 10, f"{tool_name} has insufficient docstring"
    
    def test_prompt_functions_exist(self):
        """Test that prompt functions exist in the server module."""
        # Import the server module directly
        import app.server
        
        # List of expected prompt functions
        expected_prompts = [
            "create_automation",
            "debug_automation",
            "troubleshoot_entity"
        ]
        
        # Check that each expected prompt function exists
        for prompt_name in expected_prompts:
            assert hasattr(app.server, prompt_name)
            assert callable(getattr(app.server, prompt_name))
            
    @pytest.mark.asyncio
    async def test_search_entities_resource(self):
        """Test the search_entities_tool function"""
        from app.server import search_entities_tool
        
        # Mock the get_entities function with test data
        mock_entities = [
            {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room Light", "brightness": 255}},
            {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Kitchen Light"}}
        ]
        
        with patch("app.server.get_entities", return_value=mock_entities) as mock_get:
            # Test search with a valid query
            result = await search_entities_tool(query="living")
            
            # Verify the function was called with the right parameters including lean format
            mock_get.assert_called_once_with(search_query="living", limit=20, lean=True)
            
            # Check that the result contains the expected entity data
            assert result["count"] == 2
            assert any(e["entity_id"] == "light.living_room" for e in result["results"])
            assert result["query"] == "living"
            
            # Check that domain counts are included
            assert "domains" in result
            assert "light" in result["domains"]
            
            # Test with empty query (returns all entities instead of error)
            result = await search_entities_tool(query="")
            assert "error" not in result
            assert result["count"] > 0
            assert "all entities (no filtering)" in result["query"]
            
            # Test that simplified representation includes domain-specific attributes
            result = await search_entities_tool(query="living")
            assert any("brightness" in e for e in result["results"])
            
            # Test with custom limit as an integer
            mock_get.reset_mock()
            result = await search_entities_tool(query="light", limit=5)
            mock_get.assert_called_once_with(search_query="light", limit=5, lean=True)
            
            # Test with a different limit to ensure it's respected
            mock_get.reset_mock()
            result = await search_entities_tool(query="light", limit=10)
            mock_get.assert_called_once_with(search_query="light", limit=10, lean=True)
            
    @pytest.mark.asyncio
    async def test_domain_summary_tool(self):
        """Test the domain_summary_tool function"""
        from app.server import domain_summary_tool
        
        # Mock the summarize_domain function
        mock_summary = {
            "domain": "light",
            "total_count": 2,
            "state_distribution": {"on": 1, "off": 1},
            "examples": {
                "on": [{"entity_id": "light.living_room", "friendly_name": "Living Room Light"}],
                "off": [{"entity_id": "light.kitchen", "friendly_name": "Kitchen Light"}]
            },
            "common_attributes": [("friendly_name", 2), ("brightness", 1)]
        }
        
        with patch("app.server.summarize_domain", return_value=mock_summary) as mock_summarize:
            # Test the function
            result = await domain_summary_tool(domain="light", example_limit=3)
            
            # Verify the function was called with the right parameters
            mock_summarize.assert_called_once_with("light", 3)
            
            # Check that the result matches the mock data
            assert result == mock_summary
            
    @pytest.mark.asyncio        
    async def test_get_entity_with_field_filtering(self):
        """Test the get_entity function with field filtering"""
        from app.server import get_entity
        
        # Mock entity data
        mock_entity = {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {
                "friendly_name": "Living Room Light",
                "brightness": 255,
                "color_temp": 370
            }
        }
        
        # Mock filtered entity data
        mock_filtered = {
            "entity_id": "light.living_room",
            "state": "on"
        }
        
        # Set up mock for get_entity_state to handle different calls
        with patch("app.server.get_entity_state") as mock_get_state:
            # Configure mock to return different responses based on parameters
            mock_get_state.return_value = mock_filtered
            
            # Test with field filtering
            result = await get_entity(entity_id="light.living_room", fields=["state"])
            
            # Verify the function call with fields parameter
            mock_get_state.assert_called_with("light.living_room", fields=["state"])
            assert result == mock_filtered
            
            # Test with detailed=True
            mock_get_state.reset_mock()
            mock_get_state.return_value = mock_entity
            result = await get_entity(entity_id="light.living_room", detailed=True)
            
            # Verify the function call with detailed parameter
            mock_get_state.assert_called_with("light.living_room", lean=False)
            assert result == mock_entity
            
            # Test default lean mode
            mock_get_state.reset_mock()
            mock_get_state.return_value = mock_filtered
            result = await get_entity(entity_id="light.living_room")
            
            # Verify the function call with lean=True parameter
            mock_get_state.assert_called_with("light.living_room", lean=True)
            assert result == mock_filtered

    @pytest.mark.asyncio
    async def test_query_entities_basic(self):
        """Test basic entity query with template."""
        from app.server import query_entities

        # Mock template result - now returns entity IDs (N+1 approach)
        mock_entity_ids = ["light.living_room", "light.kitchen"]

        # Mock get_entity_state to return full state for each entity
        async def mock_get_state(entity_id, lean=False):
            states = {
                "light.living_room": {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room", "brightness": 255}},
                "light.kitchen": {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen", "brightness": 128}}
            }
            return states.get(entity_id, {"error": "not found"})

        with patch("app.server.render_template", return_value=mock_entity_ids) as mock_render:
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.light | selectattr('state', 'eq', 'on') | list }}"
                )

                # Verify render_template was called with transformed template (extracts entity_ids)
                mock_render.assert_called_once_with("{{ states.light | selectattr('state', 'eq', 'on') | map(attribute='entity_id') | list | to_json }}")

                # Check result structure
                assert isinstance(result, dict)
                assert result["count"] == 2
                assert result["total_matched"] == 2
                assert result["truncated"] is False
                assert "entities" in result
                assert len(result["entities"]) == 2

    @pytest.mark.asyncio
    async def test_query_entities_with_limit(self):
        """Test query with limit applied."""
        from app.server import query_entities

        # Mock 100 entity IDs
        mock_entity_ids = [f"sensor.test_{i}" for i in range(100)]

        # Mock get_entity_state to return full state for each entity
        async def mock_get_state(entity_id, lean=False):
            # Extract index from entity_id like "sensor.test_42"
            idx = int(entity_id.split("_")[-1])
            return {"entity_id": entity_id, "state": str(idx), "attributes": {"friendly_name": f"Test {idx}"}}

        with patch("app.server.render_template", return_value=mock_entity_ids):
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.sensor | list }}",
                    limit=10
                )

                # Check that limit is respected
                assert result["count"] == 10
                assert result["total_matched"] == 100
                assert result["truncated"] is True
                assert len(result["entities"]) == 10

    @pytest.mark.asyncio
    async def test_query_entities_lean_format(self):
        """Test lean output format with domain-specific attributes."""
        from app.server import query_entities

        mock_entity_ids = ["light.test"]

        # Mock get_entity_state returning full state (lean formatting applied by query_entities)
        async def mock_get_state(entity_id, lean=False):
            return {
                "entity_id": "light.test",
                "state": "on",
                "attributes": {
                    "friendly_name": "Test Light",
                    "brightness": 255,
                    "color_temp": 370,
                    "supported_features": 63,
                    "extra_attr": "should_not_appear"
                }
            }

        with patch("app.server.render_template", return_value=mock_entity_ids):
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.light | list }}",
                    lean=True,
                    compact=False
                )

                # Check lean format includes domain-specific attributes
                entity = result["entities"][0]
                assert entity["entity_id"] == "light.test"
                assert entity["state"] == "on"
                assert entity["friendly_name"] == "Test Light"
                assert entity["brightness"] == 255  # Domain-specific for light
                # extra_attr should not appear in lean mode
                assert "extra_attr" not in entity

    @pytest.mark.asyncio
    async def test_query_entities_compact_format(self):
        """Test compact output format."""
        from app.server import query_entities

        mock_entity_ids = ["light.test"]

        async def mock_get_state(entity_id, lean=False):
            return {
                "entity_id": "light.test",
                "state": "on",
                "attributes": {
                    "friendly_name": "Test Light",
                    "brightness": 255,
                    "color_temp": 370
                }
            }

        with patch("app.server.render_template", return_value=mock_entity_ids):
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.light | list }}",
                    compact=True
                )

                # Check compact format has only essential fields
                entity = result["entities"][0]
                assert entity["entity_id"] == "light.test"
                assert entity["state"] == "on"
                assert entity["friendly_name"] == "Test Light"
                # Should NOT have any other attributes
                assert "brightness" not in entity
                assert "color_temp" not in entity

    @pytest.mark.asyncio
    async def test_query_entities_template_error(self):
        """Test error handling when template fails."""
        from app.server import query_entities

        with patch("app.server.render_template", return_value={"error": "Template syntax error"}):
            result = await query_entities(
                template="{{ invalid_syntax"
            )

            # Check error response structure
            assert result["count"] == 0
            assert result["total_matched"] == 0
            assert result["truncated"] is False
            assert result["entities"] == []
            assert "error" in result
            assert "Template syntax error" in result["error"]

    @pytest.mark.asyncio
    async def test_query_entities_non_list_result(self):
        """Test error handling when template returns non-JSON-parseable string."""
        from app.server import query_entities

        # Template returns a string that's not valid JSON
        with patch("app.server.render_template", return_value="not a list"):
            result = await query_entities(
                template="{{ 'not a list' }}"
            )

            # Check error response - with N+1 approach we get a JSON parse error
            assert result["count"] == 0
            assert result["total_matched"] == 0
            assert result["entities"] == []
            assert "error" in result
            assert "Failed to parse entity IDs as JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_query_entities_non_list_type(self):
        """Test error handling when render_template returns wrong type (e.g., int)."""
        from app.server import query_entities

        # Template returns an int instead of a list
        with patch("app.server.render_template", return_value=42):
            result = await query_entities(
                template="{{ 42 }}"
            )

            # Check error response
            assert result["count"] == 0
            assert result["total_matched"] == 0
            assert result["entities"] == []
            assert "error" in result
            assert "must return a list" in result["error"]

    @pytest.mark.asyncio
    async def test_query_entities_empty_result(self):
        """Test handling of empty result from template."""
        from app.server import query_entities

        with patch("app.server.render_template", return_value=[]):
            # No need to mock get_entity_state since empty list means no calls
            result = await query_entities(
                template="{{ states.nonexistent | list }}"
            )

            # Check empty result structure
            assert result["count"] == 0
            assert result["total_matched"] == 0
            assert result["truncated"] is False
            assert result["entities"] == []
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_query_entities_malformed_entity(self):
        """Test handling of malformed entries in entity_id list (e.g., None values)."""
        from app.server import query_entities

        # Entity ID list with malformed entry (None) - this can happen with bad templates
        mock_entity_ids = [
            None,  # Malformed - should be skipped
            "light.valid"
        ]

        async def mock_get_state(entity_id, lean=False):
            return {"entity_id": entity_id, "state": "on", "attributes": {"friendly_name": "Valid"}}

        with patch("app.server.render_template", return_value=mock_entity_ids):
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.light | list }}",
                    lean=True
                )

                # Should handle gracefully - None entry should be skipped
                assert isinstance(result, dict)
                assert "error" not in result
                # Only the valid entity should be returned
                assert result["count"] == 1
                assert result["total_matched"] == 2  # Total includes malformed
                assert result["entities"][0]["entity_id"] == "light.valid"

    @pytest.mark.asyncio
    async def test_query_entities_json_string_result(self):
        """Test handling when HA returns entity IDs as JSON string (actual API behavior)."""
        from app.server import query_entities

        # HA's /api/template actually returns a JSON string, not a parsed list
        mock_json_string = '["light.living_room", "light.kitchen"]'

        async def mock_get_state(entity_id, lean=False):
            states = {
                "light.living_room": {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room"}},
                "light.kitchen": {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Kitchen"}}
            }
            return states.get(entity_id, {"error": "not found"})

        with patch("app.server.render_template", return_value=mock_json_string):
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.light | list }}"
                )

                assert isinstance(result, dict)
                assert "error" not in result
                assert result["count"] == 2
                assert result["total_matched"] == 2
                assert result["entities"][0]["entity_id"] == "light.living_room"
                assert result["entities"][1]["entity_id"] == "light.kitchen"

    @pytest.mark.asyncio
    async def test_query_entities_entity_not_found(self):
        """Test handling when get_entity_state returns an error for an entity."""
        from app.server import query_entities

        mock_entity_ids = ["light.exists", "light.deleted"]

        async def mock_get_state(entity_id, lean=False):
            if entity_id == "light.exists":
                return {"entity_id": "light.exists", "state": "on", "attributes": {"friendly_name": "Exists"}}
            else:
                return {"error": "Entity not found"}

        with patch("app.server.render_template", return_value=mock_entity_ids):
            with patch("app.server.get_entity_state", side_effect=mock_get_state):
                result = await query_entities(
                    template="{{ states.light | list }}"
                )

                # Entity with error should be skipped
                assert result["count"] == 1
                assert result["total_matched"] == 2
                assert result["entities"][0]["entity_id"] == "light.exists"