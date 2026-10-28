"""Read-only role reports over the bridge's existing activity records."""

import csv
import heapq
import io
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class RoleMember:
    discord_id: str
    username: str
    display_name: str
    aliases: tuple[str, ...] = ()


@dataclass
class MemberActivity:
    member: RoleMember
    minecraft_names: tuple[str, ...] = ()
    minecraft_uuids: tuple[str, ...] = ()
    match: str = "no match"
    notes: str = ""
    discord_events: int = 0
    minecraft_events: int = 0
    messages: int = 0
    voice_events: int = 0
    joins: int = 0
    leaves: int = 0
    last_discord: float = 0
    last_minecraft: float = 0

    @property
    def total_events(self):
        return self.discord_events + self.minecraft_events


@dataclass
class RoleActivityReport:
    rows: list[MemberActivity]
    days: int
    generated_at: float
    logs: list[tuple] = field(default_factory=list)
    log_count: int = 0


def _name(value):
    # Preserve spaces and punctuation: removing them can merge different players.
    return value.strip().casefold()


def build_role_report(members, role_member_ids, discord_activity, minecraft_activity,
                      admin_links=(), linked_accounts=None, *, days=30, now=None,
                      include_logs=False, max_log_rows=10000):
    """Build shared log indexes; resolve stable links before name matches.

    ``members`` includes the entire guild so a duplicate nickname outside the role
    cannot silently give its Minecraft activity to someone inside the role.
    Inputs are snapshots; no links or saved activity are changed by this report.
    """
    if not 1 <= days <= 90 or max_log_rows < 1:
        raise ValueError("Use 1–90 days and a positive log limit")
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    members = {str(m.discord_id): m for m in members}
    rows = {str(uid): MemberActivity(members[str(uid)]) for uid in role_member_ids
            if str(uid) in members}
    owners = defaultdict(set)
    methods = defaultdict(set)
    explicit_members = set()
    latest_names = {}
    names_to_uuids = defaultdict(set)

    def add_link(uuid, uid, method, name=""):
        uuid, uid = str(uuid), str(uid)
        if not uuid or not uid:
            return
        owners[uuid].add(uid)
        methods[uuid].add(method)
        explicit_members.add(uid)
        if name:
            latest_names.setdefault(uuid, (0, name))

    for uuid, uid in (linked_accounts or {}).items():
        add_link(uuid, uid, "verified link")
    for link in admin_links:
        add_link(link.minecraft_uuid, link.discord_id, "admin link", link.minecraft_username)
    for event in minecraft_activity:
        if event.timestamp > now:
            continue
        uuid = str(event.player_uuid)
        names_to_uuids[_name(event.player_name)].add(uuid)
        if event.timestamp >= latest_names.get(uuid, (-1, ""))[0]:
            latest_names[uuid] = (event.timestamp, event.player_name)

    assignments = {}
    row_uuids = defaultdict(set)
    row_methods = defaultdict(set)
    warnings = defaultdict(set)
    for uuid, ids in owners.items():
        if len(ids) != 1:
            for uid in ids & rows.keys():
                warnings[uid].add("Conflicting account links; disputed player excluded")
            continue
        uid = next(iter(ids))
        if uid in rows:
            assignments[uuid] = uid
            row_uuids[uid].add(uuid)
            row_methods[uid].update(methods[uuid])

    candidates = {}
    claimants = defaultdict(set)
    for uid, member in members.items():
        uuids = set()
        for alias in (member.username, member.display_name, *member.aliases):
            if alias and _name(alias):
                uuids.update(names_to_uuids.get(_name(alias), ()))
        candidates[uid] = uuids
        for uuid in uuids:
            claimants[uuid].add(uid)
    for uid in rows:
        if uid in explicit_members:
            continue
        uuids = candidates.get(uid, set())
        if not uuids:
            continue
        if len(uuids) != 1 or any(len(claimants[u]) != 1 for u in uuids):
            warnings[uid].add("Ambiguous name; use /link_accounts to confirm")
            continue
        uuid = next(iter(uuids))
        if uuid in owners:
            warnings[uid].add("Matching name belongs to an account linked elsewhere")
            continue
        assignments[uuid] = uid
        row_uuids[uid].add(uuid)
        row_methods[uid].add("name match (unverified)")

    for uid, row in rows.items():
        row.minecraft_uuids = tuple(sorted(row_uuids[uid]))
        row.minecraft_names = tuple(latest_names.get(u, (0, u))[1] for u in row.minecraft_uuids)
        row.match = ", ".join(sorted(row_methods[uid])) or "no match"
        row.notes = "; ".join(sorted(warnings[uid]))

    report = RoleActivityReport(list(rows.values()), days, now)
    log_heap = []

    def record(row, event, platform):
        report.log_count += 1
        if not include_logs:
            return
        log = (utc_timestamp(event.timestamp), row.member.discord_id,
               row.member.display_name, platform,
               getattr(event, "player_name", ""), getattr(event, "player_uuid", ""),
               event.event_type, getattr(event, "channel_name", "") or getattr(event, "world", "") or "",
               getattr(event, "coordinates", "") or "", row.match if platform == "minecraft" else "Discord ID")
        item = (event.timestamp, report.log_count, log)
        if len(log_heap) < max_log_rows:
            heapq.heappush(log_heap, item)
        elif item[:2] > log_heap[0][:2]:
            heapq.heapreplace(log_heap, item)

    for event in discord_activity:
        row = rows.get(str(event.user_id))
        if row is None or event.timestamp > now:
            continue
        row.last_discord = max(row.last_discord, event.timestamp)
        if event.timestamp < cutoff:
            continue
        row.discord_events += 1
        row.messages += event.event_type == "message"
        row.voice_events += event.event_type in ("voice_join", "voice_leave")
        record(row, event, "discord")
    for event in minecraft_activity:
        uid = assignments.get(str(event.player_uuid))
        if uid is None or event.timestamp > now:
            continue
        row = rows[uid]
        row.last_minecraft = max(row.last_minecraft, event.timestamp)
        if event.timestamp < cutoff:
            continue
        row.minecraft_events += 1
        row.joins += event.event_type == "join"
        row.leaves += event.event_type == "leave"
        record(row, event, "minecraft")
    report.rows.sort(key=lambda r: (-r.total_events, r.member.display_name.casefold(), r.member.discord_id))
    report.logs = [item[2] for item in sorted(log_heap, reverse=True)]
    return report


def utc_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else ""


def _csv_bytes(headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        # Names are user-controlled; keep spreadsheet exports as text.
        writer.writerow("'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                        else value for value in row)
    return output.getvalue().encode("utf-8-sig")


def summary_csv(report):
    return _csv_bytes(
        ("discord_id", "username", "display_name", "minecraft_names", "minecraft_uuids", "match", "notes",
         "discord_events", "minecraft_events", "messages", "voice_events", "minecraft_joins", "minecraft_leaves",
         "last_discord_utc", "last_minecraft_utc"),
        ((r.member.discord_id, r.member.username, r.member.display_name, "; ".join(r.minecraft_names),
          "; ".join(r.minecraft_uuids), r.match, r.notes, r.discord_events, r.minecraft_events, r.messages,
          r.voice_events, r.joins, r.leaves, utc_timestamp(r.last_discord), utc_timestamp(r.last_minecraft))
         for r in report.rows),
    )


def logs_csv(report):
    return _csv_bytes(
        ("timestamp_utc", "discord_id", "display_name", "platform", "player_name", "player_uuid", "event_type",
         "channel_or_world", "coordinates", "match"), report.logs,
    )
