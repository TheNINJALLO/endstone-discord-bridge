# endstone-chat-relay

Lightweight chat relay plugin for child servers in a multi-server Endstone network. Connects to the primary server's relay hub via WebSocket and exchanges chat messages.

## Setup

1. **Install** on each child server:
   ```
   pip install ./child-relay
   ```

2. **Start the server once** to generate `config.toml` in the plugin's data folder.

3. **Edit `config.toml`:**
   ```toml
   [relay]
   hub_address = "ws://YOUR_HUB_IP:8765"
   server_name = "Zoo"
   secret = "your-shared-secret"
   ```

4. **Restart the server.** Check the console for `Connected to relay hub as 'Zoo'`.

## Commands

| Command | Description |
|---------|-------------|
| `/relay` | Shows connection status to the relay hub |

## Requirements

- The primary server must be running **endstone-discord-bridge** with `[relay_hub]` enabled.
- All servers must use the **same `secret`** value.
- The hub's WebSocket port (default `8765`) must be reachable from child servers.
