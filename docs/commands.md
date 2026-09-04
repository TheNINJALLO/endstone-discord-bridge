# Command Guide

This guide covers every command registered by the main Discord Bridge plugin and
the optional child-server Chat Relay plugin.

## Access and syntax

- `<value>` means the option is required.
- `[value]` means the option is optional.
- **Public** Discord commands can be used by any Discord member who can use
  application commands.
- **Admin** Discord commands require Discord's Administrator permission or a role
  listed in `[discord].admin_role_ids`.
- **Allowlist admin** commands accept the same admin access plus roles listed in
  `[discord].allowlist_role_ids`.
- Discord slash commands provide option prompts, so enter each value in the
  option Discord displays rather than typing angle or square brackets.

## Main-server Minecraft commands

These commands are entered in Minecraft chat or the Endstone console.

| Command | Access | What it does | How to use |
|---|---|---|---|
| `/link` | Player; `endstone_discord_bridge.link` | Creates a six-character, time-limited code that links the player's Minecraft identity to Discord. | Run `/link` in Minecraft, then run `/verify <code>` in Discord before the code expires. |
| `/bridgereload` | Operator or console; `endstone_discord_bridge.reload` | Reloads the main bridge's `config.toml` without restarting Endstone. This applies changes such as `[features].bridge_relay`. | Edit the configuration, save it, then run `/bridgereload`. |

## Public Discord commands

| Command | What it does | How to use |
|---|---|---|
| `/verify <code>` | Completes account linking with a code created by Minecraft's `/link`. The response is private. | Example: `/verify code:ABC123`. |
| `/whoami` | Shows the Minecraft UUID linked to your Discord account. The response is private. | Run `/whoami`. |
| `/list` | Lists online Minecraft players. By default the result is sent by DM; set `[features].list_dm_default = false` to answer in the channel instead. | Run `/list`. |
| `/tps` | Shows the server's current TPS and MSPT when those metrics are available. The response is private. | Run `/tps`. |

## Discord server and player administration

Unless a row says **Allowlist admin**, every command in this section requires
**Admin** access.

| Command | Access | What it does | How to use |
|---|---|---|---|
| `/inventory <player>` | Admin | Takes a live, read-only snapshot of an online player's main inventory, armor, offhand, and Ender Chest. Online names autocomplete. Empty slots are omitted, long results are paginated, and every response is ephemeral in the channel where the command was run. | Example: `/inventory player:Builder`. The target must be online. |
| `/execute <command_string>` | Admin | Dispatches a command as the Minecraft server console and records the action in the configured audit channel. | Example: `/execute command_string:summon pig 0 70 0`. Do not include a leading slash. |
| `/execute_when_online <player> <command_string> [notify_message]` | Admin | Runs a console command immediately if the player is online, or queues it until they join. `{player}` in the command is replaced with the supplied player name. | Example: `/execute_when_online player:Alex command_string:give {player} diamond 1 notify_message:You received a diamond!`. |
| `/kick <player> [reason]` | Admin | Kicks a player with an optional reason. | Example: `/kick player:Alex reason:Please reconnect`. |
| `/ban <player> [reason]` | Admin | Attempts to ban a player; if the server's ban command is unavailable, it falls back to a kick marked as banned. | Example: `/ban player:Alex reason:Griefing`. |
| `/unban <player>` | Admin | Attempts both the `pardon` and `unban` command forms. | Example: `/unban player:Alex`. |
| `/allowlist_add <player>` | Allowlist admin | Adds a player using the server's `allowlist` command, with `whitelist` as a compatibility fallback. | Example: `/allowlist_add player:Alex`. |
| `/allowlist_remove <player>` | Allowlist admin | Removes a player from the allowlist/whitelist. | Example: `/allowlist_remove player:Alex`. |
| `/allowlist_on` | Admin | Enables the allowlist/whitelist. | Run `/allowlist_on`. |
| `/allowlist_off` | Admin | Disables the allowlist/whitelist. | Run `/allowlist_off`. |
| `/allowlist_list` | Admin | Requests the allowlist/whitelist list. The actual list is printed to the Minecraft server console. | Run `/allowlist_list`, then check the server console. |
| `/mute <player>` | Admin | Soft-mutes a player inside the bridge plugin so their Minecraft chat events are cancelled. | Example: `/mute player:Alex`. |
| `/unmute <player>` | Admin | Removes a bridge soft-mute. | Example: `/unmute player:Alex`. |
| `/pay <action> <player> <amount>` | Admin | Adds or removes a score from the objective configured by `[economy].scoreboard_objective`. If the player is offline, the operation is queued until they join. | Choose `add` or `remove`. Example: `/pay action:add player:Alex amount:100`. |
| `/config_reload` | Admin | Reloads the main bridge's `config.toml` and refreshes components that retain configuration references. | Edit and save `config.toml`, then run `/config_reload`. |

The bridge's soft-mute list and offline operation queues are held in memory and
do not survive a plugin or server restart.

## Discord queue administration

| Command | What it does | How to use |
|---|---|---|
| `/view_queues` | Shows a private summary of pending offline score and console-command operations. | Run `/view_queues`. |
| `/view_player_queue <player>` | Shows the queued operations for one player, including notification summaries. | Example: `/view_player_queue player:Alex`. |
| `/clear_player_queue <player>` | Removes all pending score and console-command operations for one player. | Example: `/clear_player_queue player:Alex`. |

## Discord grief-monitoring administration

| Command | What it does | How to use |
|---|---|---|
| `/grief_toggle <feature> <state>` | Turns all grief monitoring or one tracker on/off. `feature` is `all`, `block_break`, `block_place`, or `container_access`; `state` is `on` or `off`. Changes are in memory only. | Example: `/grief_toggle feature:container_access state:off`. Update `config.toml` too if the change should survive a restart. |
| `/grief_status` | Shows whether grief monitoring is enabled and summarizes active trackers, cooldown, and configured monitored types. | Run `/grief_status`. |

The older `/grief_stats`, `/grief_player`, and `/grief_location` commands are not
registered. Grief events are still delivered to their configured Discord
channels when monitoring is enabled.

## Discord activity and account administration

All commands in this section require **Admin** access and respond privately.
For commands with a `days` option, Discord limits the selection to `7`, `14`, or
`30` unless a different range is stated.

| Command | What it does | How to use |
|---|---|---|
| `/activity <platform> <days>` | Shows aggregate activity statistics for `discord` or `minecraft`. | Example: `/activity platform:minecraft days:7`. |
| `/activity_export <platform> <days>` | Exports Discord or Minecraft activity statistics as a downloadable text file. | Example: `/activity_export platform:discord days:30`. |
| `/members [days] [show_inactive]` | Shows a comprehensive member report. Defaults to `30` days and hides inactive members. | Example: `/members days:14 show_inactive:true`. |
| `/link_accounts <discord_user> <minecraft_username> [notes]` | Administratively links a Discord member to a Minecraft username, with optional notes. | Example: `/link_accounts discord_user:@Alex minecraft_username:Alex notes:Verified by staff`. |
| `/unlink_accounts [discord_user] [minecraft_username]` | Removes an administrative account link. At least one of the two identifying options is required. | Example: `/unlink_accounts discord_user:@Alex`. |
| `/linked_accounts` | Lists all administratively linked Discord and Minecraft accounts. | Run `/linked_accounts`. |
| `/inactive_members [min_days] [platform]` | Lists members inactive for at least the specified number of days. `min_days` defaults to `30` and must be between `1` and `365`; `platform` is `discord`, `minecraft`, or `both`. | Example: `/inactive_members min_days:60 platform:both`. |
| `/export_inactive [min_days] [format_type]` | Exports inactive members as a text file. Defaults to `60` days; format is `discord_ids`, `minecraft_names`, or `detailed`. | Example: `/export_inactive min_days:90 format_type:discord_ids`. |
| `/inactivity_summary [platform]` | Summarizes inactivity at 7-, 14-, and 30-day thresholds for `discord`, `minecraft`, or `both`. | Example: `/inactivity_summary platform:both`. |
| `/unified_activity <days>` | Combines Discord and Minecraft activity and highlights linked accounts. | Example: `/unified_activity days:30`. |
| `/daily_activity [days] [show_details]` | Shows a day-by-day activity report. Defaults to `14` days with detailed pages enabled. | Example: `/daily_activity days:7 show_details:false`. |
| `/player_activity <player_name> [days]` | Shows activity for one Discord username or Minecraft player name. Defaults to `14` days. | Example: `/player_activity player_name:Alex days:30`. |
| `/all_players_activity [platform] [days] [sort_by]` | Produces a paginated report for all players. Defaults to `both`, `14` days, sorted by `activity`; sorting can also use `name` or `last_seen`. | Example: `/all_players_activity platform:minecraft days:30 sort_by:last_seen`. |

## Child-server Chat Relay commands

These commands exist only when the optional `endstone-chat-relay` wheel is
installed on a child Minecraft server.

| Command | Access | What it does | How to use |
|---|---|---|---|
| `/relay` | `endstone_chat_relay.relay` | Shows whether the child plugin is connected, plus its configured server name and Discord relay channel. | Run `/relay` in Minecraft or from the console. |
| `/relayreload` | Operator or console; `endstone_chat_relay.reload` | Reloads the child relay's `config.toml`, shuts down its current Discord connection, and reconnects with the new settings. | Edit the child plugin configuration, save it, then run `/relayreload`. |

## Common workflows

### Link a player account

1. The player runs `/link` in Minecraft.
2. The player copies the generated code.
3. The player runs `/verify code:<code>` in Discord before it expires.
4. The player can confirm the link with `/whoami`.

### Inspect an online inventory privately

1. In the desired Discord channel, run `/inventory`.
2. Select an online player from autocomplete.
3. Only the command user sees the paginated live inventory response.

### Disable the Discord-channel multi-server bridge

Set the feature switch in the main server's `config.toml`, then reload:

```toml
[features]
bridge_relay = false
```

Run `/config_reload` in Discord or `/bridgereload` in Minecraft/the console. The
normal Minecraft ↔ Discord chat channel remains enabled.
