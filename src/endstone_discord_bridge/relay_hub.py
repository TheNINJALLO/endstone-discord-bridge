"""
WebSocket relay hub for multi-server chat.

Runs a WS server on a daemon thread. Child servers connect, authenticate
with a shared secret, and exchange chat messages through the hub.

Protocol (JSON):
  Child -> Hub:  {"type":"auth","server":"Zoo","secret":"..."}
  Hub -> Child:  {"type":"auth_ok"} | {"type":"auth_fail","reason":"..."}
  Child -> Hub:  {"type":"chat","player":"Steve","message":"hello"}
  Hub -> Child:  {"type":"chat","server":"Main Server","player":"Alex","message":"hi"}
  Hub -> Child:  {"type":"discord","user":"DiscordUser","message":"hey"}
"""

import asyncio
import json
import logging
import threading
from typing import Optional, Dict, Callable

try:
    import websockets
    import websockets.server
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class RelayHub:
    """WebSocket server that manages child server connections and message routing."""

    def __init__(self, port: int, secret: str, server_name: str, logger: logging.Logger):
        self.port = port
        self.secret = secret
        self.server_name = server_name
        self.logger = logger

        # ws -> server_name (only after auth)
        self._clients: Dict = {}
        # All connected websockets (including pre-auth)
        self._all_ws: set = set()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None

        # Callbacks set by the plugin
        self.on_child_chat: Optional[Callable] = None      # (server_name, player, message)
        self.on_child_connect: Optional[Callable] = None    # (server_name)
        self.on_child_disconnect: Optional[Callable] = None # (server_name)

    # ---- public API (called from main thread) ----

    def start(self):
        """Start the WS server on a daemon thread."""
        if not HAS_WEBSOCKETS:
            self.logger.error(
                "relay_hub: 'websockets' package not installed. "
                "Install with: pip install websockets"
            )
            return

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._serve())

        self._thread = threading.Thread(target=_run, name="RelayHubThread", daemon=True)
        self._thread.start()
        self.logger.info(f"Relay hub starting on port {self.port}")

    def stop(self):
        """Shut down the WS server."""
        if self._server:
            self._server.close()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.logger.info("Relay hub stopped.")

    def broadcast_to_children(self, data: dict, exclude_server: Optional[str] = None):
        """Send a JSON message to all authenticated children (except exclude_server)."""
        if not self._loop or not self._clients:
            return
        raw = json.dumps(data)
        for ws, name in list(self._clients.items()):
            if name == exclude_server:
                continue
            try:
                asyncio.run_coroutine_threadsafe(ws.send(raw), self._loop)
            except Exception as e:
                self.logger.debug(f"relay_hub: failed to send to {name}: {e}")

    @property
    def connected_servers(self) -> list[str]:
        """Return list of connected child server names."""
        return list(self._clients.values())

    # ---- internal WS server ----

    async def _serve(self):
        try:
            self._server = await websockets.serve(
                self._handler,
                "0.0.0.0",
                self.port,
                ping_interval=30,
                ping_timeout=10,
            )
            self.logger.info(f"Relay hub listening on 0.0.0.0:{self.port}")
            await self._server.wait_closed()
        except Exception as e:
            self.logger.error(f"Relay hub server error: {e}")

    async def _handler(self, ws):
        self._all_ws.add(ws)
        server_name = None
        try:
            # First message must be auth
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
            except asyncio.TimeoutError:
                await ws.send(json.dumps({"type": "auth_fail", "reason": "auth timeout"}))
                return
            except Exception:
                await ws.send(json.dumps({"type": "auth_fail", "reason": "invalid message"}))
                return

            if msg.get("type") != "auth":
                await ws.send(json.dumps({"type": "auth_fail", "reason": "first message must be auth"}))
                return

            if msg.get("secret") != self.secret:
                await ws.send(json.dumps({"type": "auth_fail", "reason": "bad secret"}))
                self.logger.warning(f"Relay hub: auth failed from {ws.remote_address}")
                return

            server_name = msg.get("server", "Unknown")
            self._clients[ws] = server_name
            await ws.send(json.dumps({"type": "auth_ok"}))
            self.logger.info(f"Relay hub: child server '{server_name}' connected from {ws.remote_address}")

            if self.on_child_connect:
                try:
                    self.on_child_connect(server_name)
                except Exception as e:
                    self.logger.debug(f"on_child_connect callback error: {e}")

            # Main message loop
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    if msg_type == "chat":
                        player = msg.get("player", "?")
                        message = msg.get("message", "")
                        if not message:
                            continue

                        # Notify the plugin (which will broadcast to MC + Discord + other children)
                        if self.on_child_chat:
                            try:
                                self.on_child_chat(server_name, player, message)
                            except Exception as e:
                                self.logger.error(f"on_child_chat callback error: {e}")

                except json.JSONDecodeError:
                    self.logger.debug(f"Relay hub: invalid JSON from {server_name}")
                except Exception as e:
                    self.logger.error(f"Relay hub: error processing message from {server_name}: {e}")

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.logger.error(f"Relay hub: connection error: {e}")
        finally:
            self._all_ws.discard(ws)
            if ws in self._clients:
                del self._clients[ws]
            if server_name:
                self.logger.info(f"Relay hub: child server '{server_name}' disconnected")
                if self.on_child_disconnect:
                    try:
                        self.on_child_disconnect(server_name)
                    except Exception as e:
                        self.logger.debug(f"on_child_disconnect callback error: {e}")
