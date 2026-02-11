import os
import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import httpx

# Add app directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock environment variables before imports
@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables to prevent tests from using real credentials."""
    with patch.dict(os.environ, {
        "HA_URL": "http://localhost:8123",
        "HA_TOKEN": "mock_token_for_tests"
    }):
        yield

# Mock httpx client
@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client for testing."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    
    # Create a mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = AsyncMock(return_value={})
    mock_response.raise_for_status = MagicMock()
    mock_response.text = ""
    
    # Set up methods to return the mock response
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.delete = AsyncMock(return_value=mock_response)
    
    # Create a patched httpx.AsyncClient constructor
    with patch('httpx.AsyncClient', return_value=mock_client):
        yield mock_client

# Patch get_client in every submodule that imports it
# (patching app.hass.get_client only patches the re-export in __init__.py)
_GET_CLIENT_MODULES = [
    'app.hass.entities',
    'app.hass.services',
    'app.hass.history',
    'app.hass.logging_ha',
    'app.hass.summary',
    'app.hass.templates',
]

@pytest.fixture(autouse=True)
def mock_get_client(mock_httpx_client):
    """Mock the get_client function in all submodules that use it."""
    from contextlib import ExitStack
    with ExitStack() as stack:
        for mod in _GET_CLIENT_MODULES:
            stack.enter_context(patch(f'{mod}.get_client', return_value=mock_httpx_client))
        # Also keep the __init__.py re-export patched for any code using it
        stack.enter_context(patch('app.hass.get_client', return_value=mock_httpx_client))
        yield mock_httpx_client

# Mock HA session
@pytest.fixture
def mock_hass_session():
    """Create a mock Home Assistant session."""
    mock_session = MagicMock()
    
    # Mock common methods
    mock_session.get = MagicMock()
    mock_session.post = MagicMock()
    mock_session.delete = MagicMock()
    
    # Configure default returns
    mock_session.get.return_value.__aenter__.return_value.status = 200
    mock_session.get.return_value.__aenter__.return_value.json = MagicMock(return_value={})
    
    mock_session.post.return_value.__aenter__.return_value.status = 200
    mock_session.post.return_value.__aenter__.return_value.json = MagicMock(return_value={})
    
    mock_session.delete.return_value.__aenter__.return_value.status = 200
    mock_session.delete.return_value.__aenter__.return_value.json = MagicMock(return_value={})
    
    return mock_session

# Mock config
@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return {
        "hass_url": "http://localhost:8123",
        "hass_token": "mock_token",
        "config_dir": "/tmp/hass-mcp-plus-test/config",
        "log_level": "INFO"
    }