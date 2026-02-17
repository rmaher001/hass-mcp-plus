"""WebSocket API communication with Home Assistant."""

import asyncio
import json
import logging
import ssl
from typing import Dict, Any

import websockets

from app.config import HA_URL, HA_TOKEN, HA_VERIFY_SSL
from app.hass.client import _rate_limiter

logger = logging.getLogger(__name__)


async def call_websocket_api(message_type: str, **kwargs) -> Dict[str, Any]:
    """
    Call Home Assistant WebSocket API.

    Args:
        message_type: The WebSocket message type (e.g., 'recorder/statistics_during_period')
        **kwargs: Additional parameters for the message

    Returns:
        The response from Home Assistant
    """
    # Convert HTTP URL to WebSocket URL
    ws_url = HA_URL.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/websocket"

    # Use SSL context for secure WebSocket connections
    ssl_context = None
    if ws_url.startswith("wss://"):
        ssl_context = ssl.create_default_context()
        if not HA_VERIFY_SSL:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    try:
        # Apply rate limiting before making connection
        await _rate_limiter.acquire()
        async with websockets.connect(ws_url, ssl=ssl_context, max_size=16 * 1024 * 1024) as websocket:
            # Wait for auth required message
            auth_msg = await websocket.recv()
            auth_data = json.loads(auth_msg)

            if auth_data.get("type") == "auth_required":
                # Send authentication
                await websocket.send(json.dumps({
                    "type": "auth",
                    "access_token": HA_TOKEN
                }))

                # Wait for auth result
                auth_result = await websocket.recv()
                auth_result_data = json.loads(auth_result)

                if auth_result_data.get("type") != "auth_ok":
                    logger.error("WebSocket authentication failed: %s", auth_result_data)
                    raise Exception("WebSocket authentication failed")

                # Now send the actual request
                message_id = 1
                message = {
                    "id": message_id,
                    "type": message_type,
                    **kwargs
                }

                await websocket.send(json.dumps(message))

                # Wait for response
                response = await websocket.recv()
                response_data = json.loads(response)

                # Check for success
                if response_data.get("success") is False:
                    error = response_data.get("error", {})
                    logger.error("WebSocket API error: %s", error.get("message", "Unknown error"))
                    raise Exception("WebSocket API request failed")

                return response_data.get("result", {})
            else:
                logger.error("Unexpected WebSocket auth message: %s", auth_data)
                raise Exception("Unexpected WebSocket auth message")

    except ssl.SSLError as e:
        logger.error("SSL/TLS error connecting to Home Assistant at %s: %s", ws_url, e)
        raise Exception("SSL certificate error connecting to Home Assistant")
    except websockets.exceptions.InvalidURI as e:
        logger.error("Invalid WebSocket URI: %s", ws_url)
        raise Exception("Invalid WebSocket URI")
    except websockets.exceptions.ConnectionClosed as e:
        logger.error("WebSocket connection closed unexpectedly: %s - %s", e.code, e.reason)
        raise Exception("WebSocket connection closed unexpectedly")
    except websockets.exceptions.WebSocketException as e:
        logger.error("WebSocket connection error to %s: %s", ws_url, e)
        raise Exception("WebSocket connection failed")
    except json.JSONDecodeError as e:
        logger.error("Failed to parse WebSocket response: %s", e)
        raise Exception("Invalid response from Home Assistant")
    except asyncio.TimeoutError:
        logger.error("WebSocket connection to %s timed out", ws_url)
        raise Exception("WebSocket connection timed out")
    except ConnectionRefusedError:
        logger.error("Connection refused to %s", ws_url)
        raise Exception("Connection refused: Home Assistant not reachable")
    except OSError as e:
        logger.error("Network error connecting to %s: %s", ws_url, e)
        raise Exception("Network error connecting to Home Assistant")
    except Exception as e:
        logger.error("WebSocket API error: %s", e)
        raise Exception("WebSocket API communication error")
