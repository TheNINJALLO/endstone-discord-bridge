import asyncio
import csv
import gzip
import io
import random
import string
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from endstone_discord_bridge.activity_reports import ActivityReportView, report_files, report_pages
from endstone_discord_bridge.activity_tracker import (
    ActivityTracker, AdminLinkEntry, DiscordActivityEntry, MinecraftActivityEntry,
)
from endstone_discord_bridge.cogs.activity import ActivityCommands
from endstone_discord_bridge.cogs.role_activity import RoleActivityCommands
from endstone_discord_bridge.role_activity import RoleMember, build_role_report


NOW = 1800000000


def test_rankings_do_not_drop_users_beyond_top_ten(tmp_path):
    tracker = ActivityTracker(tmp_path)
    discord_events = [DiscordActivityEntry(str(i), f"Discord{i}", "message", NOW) for i in range(250)]
    minecraft_events = [MinecraftActivityEntry(f"Player{i}", str(i), "join", NOW) for i in range(250)]
    assert len(tracker._calculate_discord_stats(discord_events, 30).most_active_users) == 250
    assert len(tracker._calculate_minecraft_stats(minecraft_events, 30).most_active_users) == 250


def test_complete_roster_includes_never_active_and_linked_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: NOW)
    tracker = ActivityTracker(tmp_path)
    tracker.discord_activity = [
        DiscordActivityEntry("recent", "Historical", "message", NOW - 10),
        DiscordActivityEntry("old", "Old", "message", NOW - 30 * 86400 - 1),
    ]
    tracker.admin_links = [AdminLinkEntry("linked", "Linked", "player", "Player", "admin", NOW)]
    tracker.minecraft_activity = [MinecraftActivityEntry("Player", "player", "join", NOW - 10)]
    roster = [SimpleNamespace(id="recent", name="Current"), SimpleNamespace(id="never", name="Never")]
    data = tracker.get_comprehensive_member_list(30, discord_members=roster, linked_accounts={"unused": "verified"})
    active = {row['discord_id']: row for row in data['active_members']}
    inactive = {row['discord_id']: row for row in data['inactive_members']}
    assert set(active) == {"recent", "linked"}
    assert active['recent']['discord_username'] == "Current"
    assert active['linked']['minecraft_events_recent'] == 1
    assert set(inactive) == {"old", "never", "verified"}
    assert inactive['old']['discord_events_recent'] == 0
    assert inactive['never']['days_since_last_activity'] is None
    assert inactive['verified']['is_linked'] is True


def test_platform_inactivity_does_not_use_activity_from_other_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: NOW)
    tracker = ActivityTracker(tmp_path)
    tracker.discord_activity = [DiscordActivityEntry("1", "Discord", "message", NOW - 45 * 86400)]
    tracker.minecraft_activity = [MinecraftActivityEntry("Player", "uuid", "join", NOW - 1)]
    discord_data = tracker.get_comprehensive_member_list(30, linked_accounts={"uuid": "1"}, platform="discord")
    minecraft_data = tracker.get_comprehensive_member_list(30, linked_accounts={"uuid": "1"}, platform="minecraft")
    assert discord_data['inactive_members'][0]['days_since_last_activity'] == 45
    assert minecraft_data['active_members'][0]['minecraft_events_recent'] == 1


def test_rolling_window_keeps_the_oldest_partial_calendar_day(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: NOW)
    tracker = ActivityTracker(tmp_path)
    tracker.discord_activity = [DiscordActivityEntry("1", "User", "message", NOW - 7 * 86400 + 1)]
    stats = tracker.get_discord_stats(7)
    daily = tracker.get_detailed_daily_activity(7)
    assert stats.total_events == sum(stats.daily_breakdown.values()) == 1
    assert sum(day['total_discord_events'] for day in daily.values()) == 1


def test_role_logs_have_no_default_ten_thousand_record_limit():
    members = [RoleMember("1", "User", "User")]
    events = [DiscordActivityEntry("1", "User", "message", NOW - i) for i in range(10025)]
    report = build_role_report(members, ["1"], events, [], now=NOW, include_logs=True)
    assert len(report.logs) == report.log_count == 10025
    assert report.logs[0][0] > report.logs[-1][0]


def test_large_csv_is_split_at_complete_records_with_no_lost_names():
    rng = random.Random(42)
    members = [RoleMember(str(i), "".join(rng.choices(string.ascii_letters, k=50)),
                          f'Name {i}, "Quoted"\nSecond line') for i in range(180)]
    report, files = RoleActivityCommands._make_report(members, [m.discord_id for m in members], [], [], [], {},
                                                     30, False, 1400, 123)
    assert len(report.rows) == 180
    assert len(files) > 1
    rows = []
    for file in files:
        content = file.fp.getvalue()
        assert len(content) <= 1400
        rows.extend(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    assert {row['discord_id'] for row in rows} == {str(i) for i in range(180)}
    assert {row['display_name'] for row in rows} == {m.display_name for m in members}
    assert all(row['activity_status'] == 'inactive' for row in rows)


def test_oversized_fields_are_paginated_without_losing_characters():
    text = "\n".join(f"Member {i} " + "x" * 300 for i in range(250))
    source = discord.Embed(title="Members", description="Complete list")
    source.add_field(name="Active", value=text)
    pages = report_pages([source])
    assert len(pages) > 5
    assert "".join(field.value for page in pages for field in page.fields) == text
    for page in pages:
        assert len(page) < 5800
        assert len(page.fields) <= 25
        assert all(len(field.value) <= 1024 for field in page.fields)


def test_page_buttons_reach_last_entry_and_preserve_downloads():
    async def run():
        pages = [discord.Embed(title=f"Page {i}") for i in range(8)]
        files = report_files("report.txt", b"Every entry", 8000000)
        view = ActivityReportView(pages, files, 123)
        interaction = SimpleNamespace(user=SimpleNamespace(id=123), response=SimpleNamespace(edit_message=AsyncMock()))
        assert await view.interaction_check(interaction)
        assert view.first.disabled and view.previous.disabled
        await view.last.callback(interaction)
        assert view.index == 7
        assert view.last.disabled and view.next.disabled
        assert interaction.response.edit_message.call_args.kwargs['embed'].title == 'Page 7'
        assert 'attachments' not in interaction.response.edit_message.call_args.kwargs
        await view.first.callback(interaction)
        await view.next.callback(interaction)
        assert view.index == 1
        view.stop()
    asyncio.run(run())


def test_all_download_batches_are_reachable_when_more_than_ten_files():
    async def run():
        files = [discord.File(io.BytesIO(f"Entry {i}".encode()), filename=f"part{i}.txt") for i in range(24)]
        view = ActivityReportView([discord.Embed(title="Report")], files, 1)
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
        names = {file.filename for file in view.files()}
        for index in range(1, view.page_count):
            await view._move(interaction, index)
            names.update(file.filename for file in interaction.response.edit_message.call_args.kwargs['attachments'])
        assert names == {f"part{i}.txt" for i in range(24)}
        view.stop()
    asyncio.run(run())


def setup_commands(tmp_path, *, fail=False):
    now = time.time()
    tracker = ActivityTracker(tmp_path)
    tracker.discord_activity = [DiscordActivityEntry(str(i), f"DiscordUser_{i:03d}", "message", now - 100)
                                for i in range(60)]
    tracker.discord_activity += [DiscordActivityEntry(str(i), f"DiscordUser_{i:03d}", "message", now - 45 * 86400)
                                 for i in range(60, 85)]
    tracker.minecraft_activity = [MinecraftActivityEntry(f"MinecraftPlayer_{i:03d}", f"uuid{i}", "join", now - 100)
                                  for i in range(60)]
    calls = []

    async def fetch_members(**kwargs):
        calls.append(kwargs)
        for i in range(110):
            yield SimpleNamespace(id=i, name=f"DiscordUser_{i:03d}")
            if fail:
                raise discord.ClientException("Incomplete membership")

    plugin = SimpleNamespace(server=object(), logger=Mock(), activity_tracker=tracker,
                             linked=SimpleNamespace(links={}))
    bot = SimpleNamespace(plugin=plugin, _is_primary_guild=lambda guild: guild.id == 1)
    interaction = SimpleNamespace(guild=SimpleNamespace(id=1, filesize_limit=8000000, fetch_members=fetch_members),
                                  user=SimpleNamespace(id=123), response=SimpleNamespace(defer=AsyncMock()),
                                  followup=SimpleNamespace(send=AsyncMock()))
    return ActivityCommands(bot), interaction, calls


def attachment_text(sent):
    parts = []
    for file in sent['files']:
        data = file.fp.getvalue()
        if file.filename.endswith('.gz'):
            data = gzip.decompress(data)
        parts.append(data.decode('utf-8-sig'))
    return "\n".join(parts)


@pytest.mark.parametrize('command,kwargs,expected', [
    ('activity', {'platform': 'discord', 'days': 30}, ['DiscordUser_059', 'DiscordUser_084', 'DiscordUser_109']),
    ('activity', {'platform': 'minecraft', 'days': 30}, ['MinecraftPlayer_059']),
    ('activity_export', {'platform': 'discord', 'days': 30}, ['DiscordUser_059', 'DiscordUser_109']),
    ('activity_export', {'platform': 'minecraft', 'days': 30}, ['MinecraftPlayer_059']),
    ('members', {'days': 30}, ['DiscordUser_059', 'DiscordUser_109', 'MinecraftPlayer_059']),
    ('members', {'days': 30, 'show_inactive': True}, ['DiscordUser_059', 'DiscordUser_109']),
    ('inactive_members', {'min_days': 30}, ['DiscordUser_060', 'DiscordUser_084', 'DiscordUser_109']),
    ('export_inactive', {'min_days': 30}, ['DiscordUser_060', 'DiscordUser_084', 'DiscordUser_109']),
    ('inactivity_summary', {}, ['DiscordUser_060', 'DiscordUser_084', 'DiscordUser_109']),
    ('unified_activity', {'days': 30}, ['DiscordUser_059', 'DiscordUser_109', 'MinecraftPlayer_059']),
    ('daily_activity', {'days': 30}, ['DiscordUser_059', 'DiscordUser_109', 'MinecraftPlayer_059']),
    ('player_activity', {'player_name': 'DiscordUser_059', 'days': 30}, ['DiscordUser_059']),
    ('all_players_activity', {'days': 30}, ['DiscordUser_059', 'DiscordUser_109', 'MinecraftPlayer_059']),
    ('all_players_activity', {'days': 30, 'sort_by': 'name'}, ['DiscordUser_059', 'DiscordUser_109']),
    ('all_players_activity', {'days': 30, 'sort_by': 'last_seen'}, ['DiscordUser_059', 'DiscordUser_109']),
])
def test_commands_return_complete_downloads_and_safe_private_pages(tmp_path, command, kwargs, expected):
    cog, interaction, calls = setup_commands(tmp_path)
    asyncio.run(getattr(ActivityCommands, command).callback(cog, interaction, **kwargs))
    cog.plugin.logger.error.assert_not_called()
    interaction.followup.send.assert_awaited_once()
    sent = interaction.followup.send.call_args.kwargs
    assert sent['ephemeral'] is True
    assert sent['allowed_mentions'].users is False
    text = attachment_text(sent)
    assert all(name in text for name in expected)
    if command != 'player_activity':
        assert calls == [{'limit': None}]
    view = sent['view']
    for page in view.pages if view else [sent['embed']]:
        assert len(page) <= 6000
        assert all(len(field.value) <= 1024 for field in page.fields)
    if view:
        page_text = "\n".join((page.description or "") + "\n" + "\n".join(f.value for f in page.fields)
                              for page in view.pages)
        assert all(name in page_text for name in expected)
        view.stop()


def test_failed_member_fetch_never_publishes_partial_activity_lists(tmp_path):
    cog, interaction, calls = setup_commands(tmp_path, fail=True)
    asyncio.run(ActivityCommands.members.callback(cog, interaction, days=30))
    assert calls == [{'limit': None}]
    interaction.followup.send.assert_awaited_once()
    assert "Server Members Intent" in interaction.followup.send.call_args.args[0]
    assert 'files' not in interaction.followup.send.call_args.kwargs


def test_linked_account_lists_and_unified_report_include_links_after_twenty(tmp_path):
    cog, interaction, _ = setup_commands(tmp_path)
    cog.plugin.activity_tracker.admin_links = [
        AdminLinkEntry(str(i), f"DiscordUser_{i:03d}", f"uuid{i}", f"MinecraftPlayer_{i:03d}", "admin", NOW)
        for i in range(60)
    ]
    asyncio.run(ActivityCommands.linked_accounts.callback(cog, interaction))
    sent = interaction.followup.send.call_args.kwargs
    assert all(f"MinecraftPlayer_{i:03d}" in attachment_text(sent) for i in range(60))
    if sent['view']:
        sent['view'].stop()
    interaction.followup.send.reset_mock()
    asyncio.run(ActivityCommands.unified_activity.callback(cog, interaction, days=30))
    sent = interaction.followup.send.call_args.kwargs
    text = attachment_text(sent)
    linked_section = text.split('Active Linked Accounts', 1)[1].split('Engagement Insights', 1)[0]
    assert all(f"MinecraftPlayer_{i:03d}" in linked_section for i in range(60))
    assert '**Discord Activity:** 50.0%' in text
    assert '**Minecraft Activity:** 50.0%' in text
    sent['view'].stop()


def test_inactivity_summary_includes_complete_seven_day_list(tmp_path):
    cog, interaction, _ = setup_commands(tmp_path)
    cog.plugin.activity_tracker.discord_activity.append(
        DiscordActivityEntry("sevenday", "SevenDayOnly", "message", time.time() - 10 * 86400))
    asyncio.run(ActivityCommands.inactivity_summary.callback(cog, interaction))
    sent = interaction.followup.send.call_args.kwargs
    text = attachment_text(sent)
    seven = text.split('Inactive for 7+ Days / No Saved Activity', 1)[1].split('Inactive for 14+', 1)[0]
    thirty = text.split('Inactive for 30+ Days / No Saved Activity', 1)[1]
    assert 'SevenDayOnly' in seven
    assert 'SevenDayOnly' not in thirty
    assert 'DiscordUser_109' in thirty
    assert 'No saved activity' in thirty
    sent['view'].stop()


def test_never_recorded_minecraft_account_is_not_excluded_by_name_filter(tmp_path):
    cog, interaction, _ = setup_commands(tmp_path)
    cog.plugin.linked.links = {'never-seen-uuid': '109'}
    asyncio.run(ActivityCommands.inactive_members.callback(cog, interaction, min_days=30, platform='minecraft'))
    cog.plugin.logger.error.assert_not_called()
    sent = interaction.followup.send.call_args.kwargs
    text = attachment_text(sent)
    assert 'never-seen-uuid' in text and 'No saved activity' in text


def test_empty_logs_still_show_every_current_member(tmp_path):
    cog, interaction, _ = setup_commands(tmp_path)
    cog.plugin.activity_tracker.discord_activity.clear()
    cog.plugin.activity_tracker.minecraft_activity.clear()
    asyncio.run(ActivityCommands.activity.callback(cog, interaction, platform='discord', days=30))
    cog.plugin.logger.error.assert_not_called()
    sent = interaction.followup.send.call_args.kwargs
    text = attachment_text(sent)
    assert all(f'DiscordUser_{i:03d}' in text for i in range(110))
    assert 'No saved activity' in text
    sent['view'].stop()
