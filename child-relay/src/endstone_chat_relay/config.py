"""Chat-relay plugin configuration — Discord transport."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RelayConfig:
    token: str = ""                      # Discord bot token
    relay_channel: int = 0               # bridge_relay channel ID
    server_name: str = "Child Server"    # Tag shown on messages
    relay_joins: bool = True             # Send player join events to Discord
    relay_leaves: bool = True            # Send player quit/leave events to Discord

    # ---- persistence ----
    @staticmethod
    def load(path: Path) -> "RelayConfig":
        if not path.exists():
            cfg = RelayConfig()
            cfg.save(path)
            return cfg
        raw = tomllib.loads(path.read_text("utf-8"))
        sec = raw.get("relay", {})
        return RelayConfig(
            token=str(sec.get("token", "")),
            relay_channel=int(sec.get("relay_channel", 0)),
            server_name=str(sec.get("server_name", "Child Server")),
            relay_joins=bool(sec.get("relay_joins", True)),
            relay_leaves=bool(sec.get("relay_leaves", True)),
        )

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "[relay]",
            f'token = "{self.token}"',
            f"relay_channel = {self.relay_channel}",
            f'server_name = "{self.server_name}"',
            f"relay_joins = {str(self.relay_joins).lower()}",
            f"relay_leaves = {str(self.relay_leaves).lower()}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
