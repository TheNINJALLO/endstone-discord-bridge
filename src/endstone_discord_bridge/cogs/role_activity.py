import asyncio
import gzip
import io

import discord
from discord import app_commands

from ..role_activity import RoleMember, build_role_report, logs_csv, summary_csv
from ..util import MinecraftCogBase, admin_only


class RoleActivityCommands(MinecraftCogBase):
    """Cross-reference today's role membership with already recorded activity."""

    @app_commands.command(name="role_activity", description="Search saved activity for current members of a Discord role")
    @app_commands.guild_only()
    @admin_only()
    @app_commands.describe(
        role="Role whose current members should be included",
        days="Days of saved activity to search (1–90, default 30)",
        include_logs="Also attach the latest matching event records (up to 10,000)",
    )
    async def role_activity(self, interaction: discord.Interaction, role: discord.Role,
                            days: app_commands.Range[int, 1, 90] = 30, include_logs: bool = False):
        await self.safe_defer(interaction, ephemeral=True)
        guild = interaction.guild
        if guild is None or role.guild.id != guild.id or not self.bot._is_primary_guild(guild):
            await interaction.followup.send("Choose a role in the bridge's configured Discord server.", ephemeral=True)
            return
        try:
            # Fetch every page rather than assuming the member cache is complete.
            async def fetch_members():
                members, selected = [], []
                async for member in guild.fetch_members(limit=None):
                    uid = str(member.id)
                    members.append(RoleMember(uid, member.name, member.display_name,
                                              tuple(n for n in (member.nick, member.global_name) if n)))
                    if any(r.id == role.id for r in member.roles):
                        selected.append(uid)
                return members, selected

            members, selected = await asyncio.wait_for(fetch_members(), timeout=90)
            tracker = self.plugin.activity_tracker
            report, files = await asyncio.to_thread(
                self._make_report, members, selected, tuple(tracker.discord_activity),
                tuple(tracker.minecraft_activity), tuple(tracker.admin_links),
                dict(self.plugin.linked.links), days, include_logs,
                getattr(interaction, "filesize_limit", guild.filesize_limit), role.id,
            )
            embed = self._report_embed(role, report, include_logs)
            if not self.plugin.config.activity.enabled:
                embed.add_field(name="Tracking paused", value="Activity tracking is disabled; this report uses saved records.",
                                inline=False)
            await interaction.followup.send(embed=embed, files=files, ephemeral=True,
                                            allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.ClientException):
            await interaction.followup.send(
                "Unable to read the complete role membership. Enable Server Members Intent for the bot "
                "in the Discord Developer Portal, then restart the bridge.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("Fetching the complete member list timed out. Please retry shortly.", ephemeral=True)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception as exc:
            self.plugin.logger.error(f"Error generating role activity report: {exc}")
            await interaction.followup.send("Unable to generate the role activity report. Check the server logs.", ephemeral=True)

    @staticmethod
    def _make_report(members, selected, discord_events, minecraft_events, admin_links,
                     linked_accounts, days, include_logs, file_limit, role_id):
        report = build_role_report(members, selected, discord_events, minecraft_events, admin_links,
                                   linked_accounts, days=days, include_logs=include_logs)
        attachments = [(f"role_{role_id}_activity.csv", summary_csv(report))]
        if include_logs:
            attachments.append((f"role_{role_id}_logs.csv", logs_csv(report)))
        files = []
        for name, data in attachments:
            if len(data) > file_limit:
                data = gzip.compress(data, mtime=0)
                name += ".gz"
            if len(data) > file_limit:
                raise ValueError("The report exceeds Discord's attachment limit. Choose a shorter period or a smaller role.")
            files.append(discord.File(io.BytesIO(data), filename=name))
        return report, files

    @staticmethod
    def _report_embed(role, report, include_logs):
        active = sum(r.total_events > 0 for r in report.rows)
        embed = discord.Embed(title=f"Role activity: {role.name}"[:256], color=0x5865F2,
                              timestamp=discord.utils.utcnow())
        embed.description = (
            f"**{len(report.rows):,} current role members** · {report.days} days\n"
            f"**{active:,}** with matching activity · **{len(report.rows) - active:,}** with no matching events\n"
            f"**{sum(r.discord_events for r in report.rows):,}** Discord events · "
            f"**{sum(r.minecraft_events for r in report.rows):,}** Minecraft events\n\n"
            "The CSV includes every current role member, counts, matching method and last recorded activity. "
            "Account links take priority; name matches are unverified. Ambiguous names are flagged."
        )
        if report.rows:
            preview = []
            for row in report.rows[:8]:
                name = discord.utils.escape_markdown(discord.utils.escape_mentions(row.member.display_name[:60]))
                preview.append(f"**{name}** — Discord {row.discord_events:,} · Minecraft {row.minecraft_events:,}"
                               + (" · review match" if row.notes else ""))
            embed.add_field(name="Member preview", value="\n".join(preview)[:1024], inline=False)
        if include_logs:
            embed.add_field(name="Matching event log", value=f"{len(report.logs):,} of {report.log_count:,} records attached, newest first.",
                            inline=False)
        embed.set_footer(text="Current role membership, including offline members. Activity is limited to retained bridge logs.")
        return embed
