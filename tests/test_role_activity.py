import csv
import io
import json

import pytest

from endstone_discord_bridge.activity_tracker import ActivityTracker, AdminLinkEntry, DiscordActivityEntry, MinecraftActivityEntry
from endstone_discord_bridge.role_activity import RoleMember, build_role_report, logs_csv, summary_csv


NOW = 1800000000


def member(uid="1", name="Alex", **kwargs):
    return RoleMember(uid, kwargs.pop("username", name), name, **kwargs)


def mc(name="Alex", uuid="player-a", event="join", timestamp=NOW - 10):
    return MinecraftActivityEntry(name, uuid, event, timestamp)


def dc(uid="1", event="message", timestamp=NOW - 10):
    return DiscordActivityEntry(uid, "old nickname", event, timestamp)


def link(uid="1", uuid="player-a", name="Old Name"):
    return AdminLinkEntry(uid, "Discord", uuid, name, "admin", NOW - 100)


def report(members=None, selected=("1",), discord=(), minecraft=(), **kwargs):
    return build_role_report(members or [member()], selected, discord, minecraft, now=NOW, **kwargs)


def csv_rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def test_existing_saved_logs_work_without_waiting_for_new_events(tmp_path):
    (tmp_path / "server.json").write_text(json.dumps({"activity": [
        {"player_name": "alex", "player_uuid": "player-a", "event_type": "join", "timestamp": NOW - 10}
    ]}))
    (tmp_path / "discord.json").write_text(json.dumps({"activity": [
        {"user_id": "1", "username": "Old Nickname", "event_type": "message", "timestamp": NOW - 5}
    ]}))
    tracker = ActivityTracker(tmp_path)
    result = report([member(), member("2", "Offline"), member("3", "Outside role")], ("1", "2"),
                    tracker.discord_activity, tracker.minecraft_activity)
    rows = {r.member.discord_id: r for r in result.rows}
    assert set(rows) == {"1", "2"}
    assert rows["1"].minecraft_events == rows["1"].discord_events == 1
    assert rows["1"].match == "name match (unverified)"
    assert rows["2"].total_events == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["discord.json", "server.json"]


@pytest.mark.parametrize("aliases,username,display", [
    ((), "aLeX", "Different"), ((), "different", "Alex"), ((" Alex ",), "different", "Other")
])
def test_current_username_display_and_nickname_aliases(aliases, username, display):
    result = report([member(name=display, username=username, aliases=aliases)], minecraft=[mc("alex")])
    assert result.rows[0].minecraft_events == 1


def test_name_matching_does_not_strip_punctuation_or_spaces():
    result = report([member(name="Alex Smith")], minecraft=[mc("AlexSmith"), mc("[VIP]Alex Smith", "b")])
    assert result.rows[0].minecraft_events == 0


@pytest.mark.parametrize("kwargs,expected", [
    ({"linked_accounts": {"player-a": "1"}}, "verified link"),
    ({"admin_links": [link()]}, "admin link"),
])
def test_explicit_links_survive_renames_and_use_latest_recorded_name(kwargs, expected):
    events = [mc("New Name", timestamp=NOW - 1), mc("Old Name", timestamp=NOW - 100)]
    result = report(minecraft=events, **kwargs)
    row = result.rows[0]
    assert row.minecraft_events == 2
    assert row.minecraft_names == ("New Name",)
    assert row.match == expected


def test_links_with_no_recorded_activity_still_appear():
    row = report(admin_links=[link(name="Player")]).rows[0]
    assert row.minecraft_names == ("Player",)
    assert row.match == "admin link"
    assert row.total_events == 0


@pytest.mark.parametrize("outside_linked", [False, True])
def test_duplicate_nickname_outside_role_is_ambiguous(outside_linked):
    kwargs = {"linked_accounts": {"another-player": "2"}} if outside_linked else {}
    result = report([member(), member("2", "Alex")], minecraft=[mc()], **kwargs)
    assert result.rows[0].minecraft_events == 0
    assert "Ambiguous" in result.rows[0].notes


def test_reused_minecraft_name_is_not_guessed():
    result = report(minecraft=[mc(uuid="old-uuid"), mc(uuid="new-uuid")])
    assert result.rows[0].minecraft_events == 0
    assert "Ambiguous" in result.rows[0].notes


def test_cannot_claim_player_linked_to_someone_outside_the_role():
    result = report(minecraft=[mc()], linked_accounts={"player-a": "outsider"})
    assert result.rows[0].minecraft_events == 0
    assert "linked elsewhere" in result.rows[0].notes


def test_conflicting_admin_and_verified_links_exclude_disputed_player():
    result = report(minecraft=[mc()], admin_links=[link()], linked_accounts={"player-a": "2"})
    assert result.rows[0].minecraft_events == 0
    assert "Conflicting account links" in result.rows[0].notes


def test_linked_member_does_not_also_claim_an_unlinked_namesake():
    result = report(minecraft=[mc(), mc("Real Player", "real")], linked_accounts={"real": "1"})
    assert result.rows[0].minecraft_events == 1
    assert result.rows[0].minecraft_names == ("Real Player",)


def test_multiple_confirmed_accounts_are_counted_once_each():
    result = report(minecraft=[mc(), mc("Other", "other")], linked_accounts={"player-a": "1", "other": "1"},
                    admin_links=[link()])
    assert result.rows[0].minecraft_events == 2
    assert result.rows[0].minecraft_uuids == ("other", "player-a")


def test_date_window_counts_and_last_seen_use_retained_records():
    old = NOW - 8 * 86400
    result = report(discord=[dc(timestamp=old), dc(event="voice_join"), dc(timestamp=NOW + 1)],
                    minecraft=[mc(timestamp=old)], days=7)
    row = result.rows[0]
    assert row.discord_events == row.voice_events == 1
    assert row.messages == row.minecraft_events == 0
    assert row.last_minecraft == old
    assert row.last_discord == NOW - 10


def test_logs_are_role_filtered_and_newest_first_with_explicit_limit():
    result = report(discord=[dc(timestamp=NOW - 2), dc("outsider"), dc(timestamp=NOW - 1)],
                    minecraft=[mc(timestamp=NOW - 3)], include_logs=True, max_log_rows=2)
    assert result.log_count == 3
    assert len(result.logs) == 2
    assert all(log[1] == "1" for log in result.logs)
    assert result.logs[0][0] > result.logs[1][0]
    assert len(csv_rows(logs_csv(result))) == 2


def test_new_role_selection_excludes_former_member_history():
    result = report([member(), member("2", "Current")], ("2",), discord=[dc(), dc("2")], include_logs=True)
    assert [r.member.discord_id for r in result.rows] == ["2"]
    assert result.log_count == 1


def test_csv_preserves_names_and_marks_formula_cells_as_text():
    result = report([member(name='=HYPERLINK("bad")\n,Name')], discord=[dc()])
    row = csv_rows(summary_csv(result))[0]
    assert row["display_name"] == '\'=HYPERLINK("bad")\n,Name'
    assert row["discord_events"] == "1"


def test_empty_role_returns_valid_header_only_report():
    result = report(selected=(), discord=[dc()], minecraft=[mc()], include_logs=True)
    assert result.rows == result.logs == []
    assert csv_rows(summary_csv(result)) == []


@pytest.mark.parametrize("days", [0, 91])
def test_invalid_windows_are_rejected(days):
    with pytest.raises(ValueError):
        report(days=days)
