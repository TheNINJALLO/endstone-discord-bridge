import asyncio
import gzip
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from endstone_discord_bridge.activity_tracker import DiscordActivityEntry
from endstone_discord_bridge.cogs.role_activity import RoleActivityCommands
from endstone_discord_bridge.role_activity import RoleMember, build_role_report


def setup_command(fail=False):
    role = SimpleNamespace(id=10, name="Staff", guild=SimpleNamespace(id=100))
    inside = SimpleNamespace(id=1, name="Alex", display_name="Alex", nick=None, global_name=None, roles=[role])
    outside = SimpleNamespace(id=2, name="Other", display_name="Other", nick=None, global_name=None, roles=[])
    calls = []

    async def fetch_members(**kwargs):
        calls.append(kwargs)
        yield inside
        if fail:
            raise discord.ClientException("Members intent is not enabled")
        yield outside

    guild = SimpleNamespace(id=100, filesize_limit=8000000, members=[], fetch_members=fetch_members)
    plugin = SimpleNamespace(server=object(), logger=Mock(), linked=SimpleNamespace(links={}),
                             activity_tracker=SimpleNamespace(discord_activity=[], minecraft_activity=[], admin_links=[]),
                             config=SimpleNamespace(activity=SimpleNamespace(enabled=True)))
    bot = SimpleNamespace(plugin=plugin, _is_primary_guild=lambda g: g.id == 100)
    cog = RoleActivityCommands(bot)
    interaction = SimpleNamespace(guild=guild, response=SimpleNamespace(defer=AsyncMock()),
                                  followup=SimpleNamespace(send=AsyncMock()))
    return cog, interaction, role, calls


def invoke(cog, interaction, role, **kwargs):
    asyncio.run(RoleActivityCommands.role_activity.callback(cog, interaction, role, **kwargs))


def test_command_fetches_complete_membership_and_sends_private_reports():
    cog, interaction, role, calls = setup_command()
    invoke(cog, interaction, role, include_logs=True)
    assert calls == [{"limit": None}]
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    sent = interaction.followup.send.call_args.kwargs
    assert sent["ephemeral"] is True
    assert "1 current role members" in sent["embed"].description
    assert [f.filename for f in sent["files"]] == ["role_10_activity.csv", "role_10_logs.csv"]
    assert not sent["allowed_mentions"].everyone
    assert not sent["allowed_mentions"].users


def test_partial_member_fetch_failure_does_not_send_partial_report():
    cog, interaction, role, _ = setup_command(fail=True)
    invoke(cog, interaction, role)
    assert "Server Members Intent" in interaction.followup.send.call_args.args[0]
    assert "files" not in interaction.followup.send.call_args.kwargs


def test_other_guild_is_rejected_before_fetching_logs():
    cog, interaction, role, calls = setup_command()
    role.guild.id = 999
    invoke(cog, interaction, role)
    assert calls == []
    assert "configured Discord server" in interaction.followup.send.call_args.args[0]


def test_paused_tracking_still_allows_searching_saved_logs():
    cog, interaction, role, _ = setup_command()
    cog.plugin.config.activity.enabled = False
    invoke(cog, interaction, role)
    assert any(field.name == "Tracking paused" for field in interaction.followup.send.call_args.kwargs["embed"].fields)


def test_command_requires_admin_and_is_guild_only():
    command = RoleActivityCommands.role_activity
    assert command.guild_only
    user = Mock(spec=discord.Member)
    user.guild_permissions = SimpleNamespace(administrator=False)
    user.roles = []
    interaction = SimpleNamespace(guild=object(), user=user,
                                  client=SimpleNamespace(plugin_config=SimpleNamespace(discord=SimpleNamespace(admin_role_ids=[5]))))
    with pytest.raises(discord.app_commands.CheckFailure):
        asyncio.run(command.checks[0](interaction))
    user.roles = [SimpleNamespace(id=5)]
    assert asyncio.run(command.checks[0](interaction)) is True
    user.guild_permissions.administrator = True
    user.roles = []
    assert asyncio.run(command.checks[0](interaction)) is True


def test_large_csv_is_compressed_without_losing_members():
    members = [RoleMember(str(i), "RepeatedName", "RepeatedName") for i in range(50)]
    result, files = RoleActivityCommands._make_report(members, [m.discord_id for m in members], [], [], [], {},
                                                     30, False, 1000, 10)
    assert len(result.rows) == 50
    assert files[0].filename.endswith(".csv.gz")
    assert len(gzip.decompress(files[0].fp.getvalue()).decode("utf-8-sig").splitlines()) == 51


def test_impossibly_small_attachment_limit_reports_error():
    with pytest.raises(ValueError, match="attachment limit"):
        RoleActivityCommands._make_report([], [], [], [], [], {}, 30, False, 5, 10)


def test_embed_stays_within_discord_limits_and_does_not_ping_names():
    members = [RoleMember(str(i), "user", "@everyone" + "*" * 1000) for i in range(20)]
    events = [DiscordActivityEntry(str(i), "old", "message", 100) for i in range(20)]
    result = build_role_report(members, [m.discord_id for m in members], events, [], now=101)
    embed = RoleActivityCommands._report_embed(SimpleNamespace(name="x" * 500), result, False)
    assert len(embed.title) <= 256
    assert all(len(f.value) <= 1024 for f in embed.fields)
    assert len(embed) <= 6000
    assert "@everyone" not in embed.fields[0].value
