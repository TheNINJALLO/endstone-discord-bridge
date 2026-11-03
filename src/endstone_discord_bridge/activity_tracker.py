import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class DiscordActivityEntry:
    """Single Discord activity event"""
    user_id: str
    username: str
    event_type: str  # "join", "leave", "message", "voice_join", "voice_leave"
    timestamp: float
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MinecraftActivityEntry:
    """Single Minecraft activity event"""
    player_name: str
    player_uuid: str
    event_type: str  # "join", "leave"
    timestamp: float
    world: Optional[str] = None
    coordinates: Optional[str] = None


@dataclass
class ActivityStats:
    """Activity statistics for a time period"""
    total_events: int = 0
    unique_users: int = 0
    joins: int = 0
    leaves: int = 0
    messages: int = 0
    voice_activity: int = 0
    most_active_users: List[Dict[str, Any]] = field(default_factory=list)
    daily_breakdown: Dict[str, int] = field(default_factory=dict)
    all_users: List[Dict[str, Any]] = field(default_factory=list)  # All users with activity data
    inactive_users: List[Dict[str, Any]] = field(default_factory=list)  # Users with no recent activity


@dataclass
class AdminLinkEntry:
    """Admin-created link between Discord and Minecraft accounts"""
    discord_id: str
    discord_username: str
    minecraft_uuid: str
    minecraft_username: str
    linked_by: str  # Admin who created the link
    linked_at: float  # Timestamp
    notes: str = ""


class ActivityTracker:
    """Tracks and stores Discord and Minecraft activity data"""

    def __init__(self, data_folder: Path, config=None):
        self.data_folder = data_folder
        self.discord_file = data_folder / "discord.json"
        self.minecraft_file = data_folder / "server.json"
        self.admin_links_file = data_folder / "admin_links.json"
        self.config = config

        # In-memory storage (loaded from files)
        self.discord_activity: List[DiscordActivityEntry] = []
        self.minecraft_activity: List[MinecraftActivityEntry] = []
        self.admin_links: List[AdminLinkEntry] = []

        # Load existing data
        self.load_data()
    
    def load_data(self):
        """Load activity data from JSON files"""
        try:
            if self.discord_file.exists():
                with open(self.discord_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.discord_activity = [
                        DiscordActivityEntry(**entry) for entry in data.get('activity', [])
                    ]
        except Exception as e:
            print(f"Error loading Discord activity data: {e}")
            self.discord_activity = []

        try:
            if self.minecraft_file.exists():
                with open(self.minecraft_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.minecraft_activity = [
                        MinecraftActivityEntry(**entry) for entry in data.get('activity', [])
                    ]
        except Exception as e:
            print(f"Error loading Minecraft activity data: {e}")
            self.minecraft_activity = []

        try:
            if self.admin_links_file.exists():
                with open(self.admin_links_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.admin_links = [
                        AdminLinkEntry(**entry) for entry in data.get('links', [])
                    ]
        except Exception as e:
            print(f"Error loading admin links data: {e}")
            self.admin_links = []
    
    def save_data(self):
        """Save activity data to JSON files"""
        try:
            # Save Discord activity
            discord_data = {
                'last_updated': time.time(),
                'activity': [asdict(entry) for entry in self.discord_activity]
            }
            with open(self.discord_file, 'w', encoding='utf-8') as f:
                json.dump(discord_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving Discord activity data: {e}")

        try:
            # Save Minecraft activity
            minecraft_data = {
                'last_updated': time.time(),
                'activity': [asdict(entry) for entry in self.minecraft_activity]
            }
            with open(self.minecraft_file, 'w', encoding='utf-8') as f:
                json.dump(minecraft_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving Minecraft activity data: {e}")

        try:
            # Save admin links
            links_data = {
                'last_updated': time.time(),
                'links': [asdict(entry) for entry in self.admin_links]
            }
            with open(self.admin_links_file, 'w', encoding='utf-8') as f:
                json.dump(links_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving admin links data: {e}")
    
    def add_discord_activity(self, user_id: str, username: str, event_type: str, 
                           channel_id: Optional[str] = None, channel_name: Optional[str] = None,
                           additional_data: Optional[Dict[str, Any]] = None):
        """Add a Discord activity entry"""
        entry = DiscordActivityEntry(
            user_id=str(user_id),
            username=username,
            event_type=event_type,
            timestamp=time.time(),
            channel_id=str(channel_id) if channel_id else None,
            channel_name=channel_name,
            additional_data=additional_data or {}
        )
        self.discord_activity.append(entry)
        self._cleanup_old_entries()
        self.save_data()
    
    def add_minecraft_activity(self, player_name: str, player_uuid: str, event_type: str,
                             world: Optional[str] = None, coordinates: Optional[str] = None):
        """Add a Minecraft activity entry"""
        entry = MinecraftActivityEntry(
            player_name=player_name,
            player_uuid=str(player_uuid),
            event_type=event_type,
            timestamp=time.time(),
            world=world,
            coordinates=coordinates
        )
        self.minecraft_activity.append(entry)
        self._cleanup_old_entries()
        self.save_data()
    
    def _cleanup_old_entries(self, max_days: Optional[int] = None):
        """Remove entries older than max_days to prevent file bloat"""
        if max_days is None:
            max_days = getattr(getattr(self.config, 'activity', None), 'cleanup_days', 90) if self.config else 90
        cutoff_time = time.time() - (max_days * 24 * 60 * 60)
        
        self.discord_activity = [
            entry for entry in self.discord_activity 
            if entry.timestamp > cutoff_time
        ]
        
        self.minecraft_activity = [
            entry for entry in self.minecraft_activity 
            if entry.timestamp > cutoff_time
        ]
    
    def get_discord_stats(self, days: int) -> ActivityStats:
        """Get Discord activity statistics for the specified number of days"""
        now = time.time()
        cutoff_time = now - (days * 24 * 60 * 60)
        recent_activity = [
            entry for entry in self.discord_activity 
            if cutoff_time < entry.timestamp <= now
        ]
        
        return self._calculate_discord_stats(recent_activity, days)
    
    def get_minecraft_stats(self, days: int) -> ActivityStats:
        """Get Minecraft activity statistics for the specified number of days"""
        now = time.time()
        cutoff_time = now - (days * 24 * 60 * 60)
        recent_activity = [
            entry for entry in self.minecraft_activity 
            if cutoff_time < entry.timestamp <= now
        ]
        
        return self._calculate_minecraft_stats(recent_activity, days)
    
    def _calculate_discord_stats(self, activity: List[DiscordActivityEntry], days: int) -> ActivityStats:
        """Calculate statistics for Discord activity"""
        stats = ActivityStats()
        stats.total_events = len(activity)
        
        if not activity:
            return stats
        
        # Count unique users
        unique_users = set(entry.user_id for entry in activity)
        stats.unique_users = len(unique_users)
        
        # Count event types
        for entry in activity:
            if entry.event_type == "join":
                stats.joins += 1
            elif entry.event_type == "leave":
                stats.leaves += 1
            elif entry.event_type == "message":
                stats.messages += 1
            elif entry.event_type in ["voice_join", "voice_leave"]:
                stats.voice_activity += 1
        
        # Calculate most active users
        user_activity = {}
        for entry in activity:
            user_activity[entry.user_id] = user_activity.get(entry.user_id, 0) + 1
        
        # Enhanced most active users with linked account info
        enhanced_users = []
        names = {entry.user_id: entry.username for entry in sorted(activity, key=lambda e: e.timestamp)}
        for user_id, count in sorted(user_activity.items(), key=lambda x: x[1], reverse=True):
            username = names[user_id]
            link = self.get_admin_link_by_discord(user_id)
            user_data = {
                "user_id": user_id,
                "username": username,
                "count": count,
                "is_linked": link is not None,
                "minecraft_username": link.minecraft_username if link else None
            }
            enhanced_users.append(user_data)

        stats.most_active_users = enhanced_users
        
        # Daily breakdown
        stats.daily_breakdown = self._get_daily_breakdown(activity, days)
        
        return stats
    
    def _calculate_minecraft_stats(self, activity: List[MinecraftActivityEntry], days: int) -> ActivityStats:
        """Calculate statistics for Minecraft activity"""
        stats = ActivityStats()
        stats.total_events = len(activity)
        
        if not activity:
            return stats
        
        # Count unique players
        unique_players = set(entry.player_uuid for entry in activity)
        stats.unique_users = len(unique_players)
        
        # Count event types
        for entry in activity:
            if entry.event_type == "join":
                stats.joins += 1
            elif entry.event_type == "leave":
                stats.leaves += 1
        
        # Calculate most active players
        player_activity = {}
        for entry in activity:
            player_activity[entry.player_uuid] = player_activity.get(entry.player_uuid, 0) + 1
        
        # Enhanced most active players with linked account info
        enhanced_players = []
        names = {entry.player_uuid: entry.player_name for entry in sorted(activity, key=lambda e: e.timestamp)}
        for player_uuid, count in sorted(player_activity.items(), key=lambda x: x[1], reverse=True):
            username = names[player_uuid]
            link = self.get_admin_link_by_minecraft(player_uuid)
            player_data = {
                "user_id": player_uuid,
                "username": username,
                "count": count,
                "is_linked": link is not None,
                "discord_username": link.discord_username if link else None
            }
            enhanced_players.append(player_data)

        stats.most_active_users = enhanced_players
        
        # Daily breakdown
        stats.daily_breakdown = self._get_daily_breakdown(activity, days)
        
        return stats
    
    def _get_latest_username(self, user_id: str, activity: List[DiscordActivityEntry]) -> str:
        """Get the most recent username for a Discord user"""
        for entry in reversed(activity):
            if entry.user_id == user_id:
                return entry.username
        return "Unknown"
    
    def _get_latest_player_name(self, player_uuid: str, activity: List[MinecraftActivityEntry]) -> str:
        """Get the most recent player name for a Minecraft player"""
        for entry in reversed(activity):
            if entry.player_uuid == player_uuid:
                return entry.player_name
        return "Unknown"
    
    def _get_daily_breakdown(self, activity: List, days: int) -> Dict[str, int]:
        """Get daily breakdown of activity"""
        daily_counts = {}
        now = datetime.fromtimestamp(time.time(), timezone.utc)
        
        # Initialize all days with 0
        # A rolling N-day window can cover parts of N+1 UTC calendar days.
        for i in range(days + 1):
            date = now - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            daily_counts[date_str] = 0
        
        # Count activity per day
        for entry in activity:
            entry_date = datetime.fromtimestamp(entry.timestamp, timezone.utc)
            date_str = entry_date.strftime("%Y-%m-%d")
            if date_str in daily_counts:
                daily_counts[date_str] += 1
        
        return daily_counts

    # Admin linking methods
    def add_admin_link(self, discord_id: str, discord_username: str, minecraft_uuid: str,
                      minecraft_username: str, linked_by: str, notes: str = "") -> bool:
        """Add an admin-created link between Discord and Minecraft accounts"""
        # Check if link already exists
        for link in self.admin_links:
            if link.discord_id == str(discord_id) or link.minecraft_uuid == str(minecraft_uuid):
                return False  # Link already exists

        link = AdminLinkEntry(
            discord_id=str(discord_id),
            discord_username=discord_username,
            minecraft_uuid=str(minecraft_uuid),
            minecraft_username=minecraft_username,
            linked_by=linked_by,
            linked_at=time.time(),
            notes=notes
        )
        self.admin_links.append(link)
        self.save_data()
        return True

    def remove_admin_link(self, discord_id: str = None, minecraft_uuid: str = None) -> bool:
        """Remove an admin link by Discord ID or Minecraft UUID"""
        for i, link in enumerate(self.admin_links):
            if (discord_id and link.discord_id == str(discord_id)) or \
               (minecraft_uuid and link.minecraft_uuid == str(minecraft_uuid)):
                self.admin_links.pop(i)
                self.save_data()
                return True
        return False

    def get_admin_link_by_discord(self, discord_id: str) -> Optional[AdminLinkEntry]:
        """Get admin link by Discord ID"""
        for link in self.admin_links:
            if link.discord_id == str(discord_id):
                return link
        return None

    def get_admin_link_by_minecraft(self, minecraft_uuid: str) -> Optional[AdminLinkEntry]:
        """Get admin link by Minecraft UUID"""
        for link in self.admin_links:
            if link.minecraft_uuid == str(minecraft_uuid):
                return link
        return None

    def get_all_admin_links(self) -> List[AdminLinkEntry]:
        """Get all admin links"""
        return self.admin_links.copy()

    def get_comprehensive_member_list(self, days=30, *, discord_members=(), linked_accounts=None, platform="both"):
        """Include the complete guild roster, known players and accounts without events.

        No saved activity is distinct from a measured number of inactive days.
        Platform filters determine both recent activity and last seen.
        """
        now = time.time()
        cutoff = now - days * 86400
        discord_members = tuple(discord_members)
        all_members = {}
        owners = {}
        for uuid, uid in (linked_accounts or {}).items():
            owners.setdefault(str(uuid), set()).add(str(uid))
        for link in self.admin_links:
            owners.setdefault(str(link.minecraft_uuid), set()).add(str(link.discord_id))
        links = {uuid: next(iter(ids)) for uuid, ids in owners.items() if len(ids) == 1}

        def member(key, uid=None, uuid=None):
            if key not in all_members:
                all_members[key] = {
                    'discord_id': uid, 'discord_username': None,
                    'minecraft_uuid': uuid, 'minecraft_username': None,
                    'last_discord_activity': None, 'last_minecraft_activity': None,
                    'discord_events_recent': 0, 'minecraft_events_recent': 0,
                    'total_discord_events': 0, 'total_minecraft_events': 0,
                    'is_linked': False, 'link_type': None,
                    'days_since_last_activity': None,
                    'discord_active_days': set(), 'minecraft_active_days': set(),
                }
            return all_members[key]

        for current in discord_members:
            uid = str(current.id)
            member(uid, uid=uid)['discord_username'] = current.name
        for uuid, uid in links.items():
            row = member(uid, uid=uid)
            row['minecraft_uuid'] = uuid
            row['is_linked'] = True
            row['link_type'] = 'account link'
        for link in self.admin_links:
            if links.get(str(link.minecraft_uuid)) == str(link.discord_id):
                row = member(str(link.discord_id), uid=str(link.discord_id))
                row['discord_username'] = row['discord_username'] or link.discord_username
                row['minecraft_username'] = link.minecraft_username

        for entry in self.discord_activity:
            if entry.timestamp > now:
                continue
            uid = str(entry.user_id)
            row = member(uid, uid=uid)
            if entry.timestamp >= (row['last_discord_activity'] or 0):
                row['discord_username'] = entry.username
                row['last_discord_activity'] = entry.timestamp
            row['total_discord_events'] += 1
            row['discord_events_recent'] += entry.timestamp > cutoff
            if entry.timestamp > cutoff:
                row['discord_active_days'].add(datetime.fromtimestamp(entry.timestamp, timezone.utc).date())
        for entry in self.minecraft_activity:
            if entry.timestamp > now:
                continue
            uuid = str(entry.player_uuid)
            uid = links.get(uuid)
            row = member(uid or f"mc_{uuid}", uid=uid, uuid=uuid)
            row['minecraft_uuid'] = row['minecraft_uuid'] or uuid
            if entry.timestamp >= (row['last_minecraft_activity'] or 0):
                row['minecraft_username'] = entry.player_name
                row['last_minecraft_activity'] = entry.timestamp
            row['total_minecraft_events'] += 1
            row['minecraft_events_recent'] += entry.timestamp > cutoff
            if entry.timestamp > cutoff:
                row['minecraft_active_days'].add(datetime.fromtimestamp(entry.timestamp, timezone.utc).date())

        # Prefer the current Discord name to historical event names.
        for current in discord_members:
            all_members[str(current.id)]['discord_username'] = current.name
        active, inactive = [], []
        for row in all_members.values():
            if platform == "discord" and not row['discord_id']:
                continue
            if platform == "minecraft" and not row['minecraft_uuid']:
                continue
            timestamps = []
            recent = 0
            for source in ("discord", "minecraft") if platform == "both" else (platform,):
                timestamps.append(row[f'last_{source}_activity'] or 0)
                recent += row[f'{source}_events_recent']
            last = max(timestamps)
            row['days_since_last_activity'] = int((now - last) / 86400) if last else None
            sources = ('discord', 'minecraft') if platform == 'both' else (platform,)
            row['active_days_count'] = len(set().union(*(row[f'{source}_active_days'] for source in sources)))
            del row['discord_active_days'], row['minecraft_active_days']
            (active if recent else inactive).append(row)
        order = lambda row: (row['days_since_last_activity'] is None,
                             row['days_since_last_activity'] or 0,
                             (row['discord_username'] or row['minecraft_username'] or '').casefold())
        active.sort(key=order)
        inactive.sort(key=order)
        rows = active + inactive
        return {
            'active_members': active, 'inactive_members': inactive,
            'total_members': len(rows), 'active_count': len(active), 'inactive_count': len(inactive),
            'linked_count': sum(row['is_linked'] for row in rows),
            'discord_only': sum(bool(row['discord_id'] and not row['minecraft_uuid']) for row in rows),
            'minecraft_only': sum(bool(row['minecraft_uuid'] and not row['discord_id']) for row in rows),
            'analysis_period_days': days,
            'platform': platform,
        }

    def get_detailed_daily_activity(self, days: int = 30) -> Dict[str, Any]:
        """Get detailed daily activity breakdown for all players"""
        now = time.time()
        cutoff_time = now - (days * 24 * 60 * 60)

        # Get recent activity
        recent_discord = [e for e in self.discord_activity if cutoff_time < e.timestamp <= now]
        recent_minecraft = [e for e in self.minecraft_activity if cutoff_time < e.timestamp <= now]

        # Initialize daily data structure
        daily_data = {}
        for i in range(days + 1):
            date = datetime.fromtimestamp(now, timezone.utc) - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            daily_data[date_str] = {
                'discord_users': {},
                'minecraft_players': {},
                'total_discord_events': 0,
                'total_minecraft_events': 0,
                'unique_discord_users': set(),
                'unique_minecraft_players': set()
            }

        # Process Discord activity
        for entry in recent_discord:
            entry_date = datetime.fromtimestamp(entry.timestamp, timezone.utc)
            date_str = entry_date.strftime("%Y-%m-%d")

            if date_str in daily_data:
                user_id = entry.user_id
                username = entry.username

                if user_id not in daily_data[date_str]['discord_users']:
                    daily_data[date_str]['discord_users'][user_id] = {
                        'username': username,
                        'events': 0,
                        'joins': 0,
                        'leaves': 0,
                        'messages': 0,
                        'voice_activity': 0
                    }

                daily_data[date_str]['discord_users'][user_id]['events'] += 1
                daily_data[date_str]['discord_users'][user_id]['username'] = username  # Update to latest
                daily_data[date_str]['total_discord_events'] += 1
                daily_data[date_str]['unique_discord_users'].add(user_id)

                # Count event types
                if entry.event_type == "join":
                    daily_data[date_str]['discord_users'][user_id]['joins'] += 1
                elif entry.event_type == "leave":
                    daily_data[date_str]['discord_users'][user_id]['leaves'] += 1
                elif entry.event_type == "message":
                    daily_data[date_str]['discord_users'][user_id]['messages'] += 1
                elif entry.event_type in ["voice_join", "voice_leave"]:
                    daily_data[date_str]['discord_users'][user_id]['voice_activity'] += 1

        # Process Minecraft activity
        for entry in recent_minecraft:
            entry_date = datetime.fromtimestamp(entry.timestamp, timezone.utc)
            date_str = entry_date.strftime("%Y-%m-%d")

            if date_str in daily_data:
                player_uuid = entry.player_uuid
                player_name = entry.player_name

                if player_uuid not in daily_data[date_str]['minecraft_players']:
                    daily_data[date_str]['minecraft_players'][player_uuid] = {
                        'username': player_name,
                        'events': 0,
                        'joins': 0,
                        'leaves': 0,
                        'sessions': 0
                    }

                daily_data[date_str]['minecraft_players'][player_uuid]['events'] += 1
                daily_data[date_str]['minecraft_players'][player_uuid]['username'] = player_name  # Update to latest
                daily_data[date_str]['total_minecraft_events'] += 1
                daily_data[date_str]['unique_minecraft_players'].add(player_uuid)

                # Count event types
                if entry.event_type == "join":
                    daily_data[date_str]['minecraft_players'][player_uuid]['joins'] += 1
                elif entry.event_type == "leave":
                    daily_data[date_str]['minecraft_players'][player_uuid]['leaves'] += 1

        # Convert sets to counts for JSON serialization
        for date_data in daily_data.values():
            date_data['unique_discord_users'] = len(date_data['unique_discord_users'])
            date_data['unique_minecraft_players'] = len(date_data['unique_minecraft_players'])

        return daily_data
