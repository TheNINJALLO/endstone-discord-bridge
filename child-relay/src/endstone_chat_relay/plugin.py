"""
Endstone Chat Relay — Discord Transport
Lightweight plugin for child servers: relays local MC chat to/from
a shared Discord bridge_relay channel. No ports needed.
"""
import asyncio
import threading
from typing import Optional

import discord

from endstone.plugin import Plugin
from endstone.command import Command, CommandSender
from endstone.event import event_handler, PlayerChatEvent, PlayerJoinEvent, PlayerQuitEvent
from endstone import Player

from .config import RelayConfig


class ChatRelayPlugin(Plugin):
    api_version = "0.11"

    name = "ChatRelay"
    version = "1.2.2"
    description = "Relay chat between child servers and the main bridge via Discord."

    commands = {
        "relay": {
            "description": "Show relay connection status.",
            "usages": ["/relay"],
            "permissions": ["endstone_chat_relay.relay"],
        },
        "relayreload": {
            "description": "Reload the chat relay config and reconnect.",
            "usages": ["/relayreload"],
            "permissions": ["endstone_chat_relay.reload"],
        },
    }

    permissions = {
        "endstone_chat_relay.relay": {
            "description": "Check relay connection status.",
            "default": True,
        },
        "endstone_chat_relay.reload": {
            "description": "Reload relay config and reconnect.",
            "default": True,
        },
    }

    # ---- lifecycle ----

    def on_enable(self):
        cfg_path = self.data_folder / "config.toml"
        self._cfg = RelayConfig.load(cfg_path)
        self._bot: Optional[discord.Client] = None
        self._bot_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._connected = False
        self._stopping = False

        if not self._cfg.token:
            self.logger.warning("No Discord bot token set in config.toml — relay will NOT function.")
        else:
            self._start_bot_thread()

        self.register_events(self)
        self.logger.info(
            f"Chat Relay enabled — server name: '{self._cfg.server_name}', "
            f"relay_channel: {self._cfg.relay_channel}"
        )

    def on_disable(self):
        self.logger.info("Shutting down Chat Relay…")
        self._stopping = True
        if self._bot and self._bot_loop and not self._bot_loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._bot.close(), self._bot_loop)
        if self._bot_thread and self._bot_thread.is_alive():
            self._bot_thread.join(timeout=5)
        self._connected = False

    # ---- Discord bot thread ----

    def _start_bot_thread(self):
        """Start the Discord bot on a daemon thread."""

        intents = discord.Intents.default()
        intents.message_content = True

        plugin = self  # capture for closures

        class RelayClient(discord.Client):
            async def on_ready(inner_self):
                plugin._connected = True
                plugin.logger.info(
                    f"Chat Relay bot connected as {inner_self.user} — "
                    f"watching channel {plugin._cfg.relay_channel}"
                )

            async def on_message(inner_self, message: discord.Message):
                # Only care about the relay channel
                if message.channel.id != int(plugin._cfg.relay_channel):
                    return
                # Only process RELAY embeds from other bots
                if not message.author.bot:
                    return
                if not message.embeds:
                    return
                e = message.embeds[0]
                if not (e.footer and e.footer.text and e.footer.text == "RELAY"):
                    return

                server_name = (e.author.name or "?") if e.author else "?"
                player = e.title or "?"
                body = e.description or ""

                if not body:
                    return

                # Don't echo our own server's messages back
                if server_name == plugin._cfg.server_name:
                    return

                # Broadcast to local MC
                def _broadcast():
                    try:
                        if server_name == "Discord":
                            # Discord user message
                            plugin.server.broadcast_message(
                                f"<§9Discord§r:{player}> {body}"
                            )
                        else:
                            # Another MC server's player message
                            plugin.server.broadcast_message(
                                f"[§b{server_name}§r] <{player}> {body}"
                            )
                    except Exception as exc:
                        plugin.logger.error(f"Failed to broadcast relay message: {exc}")

                plugin.server.scheduler.run_task(plugin, _broadcast, delay=0)

        def _run():
            self._bot_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._bot_loop)
            self._bot = RelayClient(intents=intents)
            try:
                self._bot_loop.run_until_complete(self._bot.start(self._cfg.token))
            except (RuntimeError, asyncio.CancelledError):
                pass  # expected during shutdown/reload

        self._bot_thread = threading.Thread(target=_run, name="ChatRelayBotThread", daemon=True)
        self._bot_thread.start()

    # ---- send chat to Discord relay channel ----

    def _send_to_relay(self, player_name: str, message: str):
        """Send a local MC chat message to the bridge_relay channel as a RELAY embed."""
        if not self._bot or not self._bot_loop or self._bot_loop.is_closed():
            return

        async def _send():
            try:
                await self._bot.wait_until_ready()
                ch_id = int(self._cfg.relay_channel or 0)
                if not ch_id:
                    return
                ch = self._bot.get_channel(ch_id)
                if ch is None:
                    ch = await self._bot.fetch_channel(ch_id)
                if ch:
                    embed = discord.Embed(
                        title=player_name,
                        description=message,
                        color=0x2ECC71,
                    )
                    embed.set_author(name=self._cfg.server_name)
                    embed.set_footer(text="RELAY")
                    await ch.send(embed=embed)
            except Exception as e:
                self.logger.error(f"Failed to send relay embed: {e}")

        asyncio.run_coroutine_threadsafe(_send(), self._bot_loop)

    def _send_join_leave(self, player_name: str, event_type: str):
        """Send a join or leave notification to the bridge_relay channel as an embed."""
        if not self._bot or not self._bot_loop or self._bot_loop.is_closed():
            return

        async def _send():
            try:
                await self._bot.wait_until_ready()
                ch_id = int(self._cfg.relay_channel or 0)
                if not ch_id:
                    return
                ch = self._bot.get_channel(ch_id)
                if ch is None:
                    ch = await self._bot.fetch_channel(ch_id)
                if ch:
                    color = 0x2ECC71 if event_type == "join" else 0xF59E0B
                    footer_text = f"RELAY_{event_type.upper()}"
                    embed = discord.Embed(
                        title=player_name,
                        description=event_type,
                        color=color,
                    )
                    embed.set_author(name=self._cfg.server_name)
                    embed.set_footer(text=footer_text)
                    await ch.send(embed=embed)
                    self.logger.info(f"Sent relay {event_type} embed for {player_name} to Discord")
            except Exception as e:
                self.logger.error(f"Failed to send relay {event_type} embed: {e}")

        asyncio.run_coroutine_threadsafe(_send(), self._bot_loop)

    # ---- MC events ----

    @event_handler
    def on_player_chat(self, event: PlayerChatEvent):
        msg = event.message
        name = event.player.name
        # Skip command prefixes
        stripped = msg.strip()
        if stripped.startswith("/") or stripped.startswith("-") or stripped.startswith(";"):
            return
        self._send_to_relay(name, msg)

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent):
        name = event.player.name
        self.logger.info(f"Player {name} joined the server.")
        if self._cfg.relay_joins:
            self._send_join_leave(name, "join")
        else:
            self.logger.info("relay_joins is disabled in config, skipping relay.")

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent):
        name = event.player.name
        self.logger.info(f"Player {name} left the server.")
        if self._cfg.relay_leaves:
            self._send_join_leave(name, "leave")
        else:
            self.logger.info("relay_leaves is disabled in config, skipping relay.")

    # ---- commands ----

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name == "relay":
            if self._connected:
                sender.send_message(
                    f"§a✔ Connected to Discord relay as §e{self._cfg.server_name}§a\n"
                    f"§7Channel: {self._cfg.relay_channel}"
                )
            else:
                sender.send_message(
                    f"§c✘ Not connected to Discord relay\n"
                    f"§7Channel: {self._cfg.relay_channel}\n"
                    f"§7Server name: {self._cfg.server_name}"
                )
            return True

        if command.name == "relayreload":
            if isinstance(sender, Player) and not sender.is_op:
                sender.send_message("§cYou must be an operator to use this command.")
                return True
            try:
                cfg_path = self.data_folder / "config.toml"
                self._cfg = RelayConfig.load(cfg_path)
                sender.send_message(
                    f"§aRelay config reloaded. Reconnecting as §e{self._cfg.server_name}§a\n"
                    f"§7Channel: {self._cfg.relay_channel}"
                )
                self.logger.info(f"Config reloaded by {getattr(sender, 'name', 'console')}")
                # Restart the bot thread
                self._stopping = True
                if self._bot and self._bot_loop and not self._bot_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(self._bot.close(), self._bot_loop)
                if self._bot_thread and self._bot_thread.is_alive():
                    self._bot_thread.join(timeout=3)
                self._connected = False
                self._stopping = False
                if self._cfg.token:
                    self._start_bot_thread()
            except Exception as e:
                sender.send_message(f"§cReload failed: {e}")
                self.logger.error(f"Config reload failed: {e}")
            return True

        return False
