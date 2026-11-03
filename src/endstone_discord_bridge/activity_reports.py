"""Complete, private activity reports with Discord-safe pages and downloads."""

import csv
import gzip
import io
from pathlib import PurePath

import discord


def _chunks(text, limit):
    """Split at line boundaries where possible, preserving every character."""
    while len(text) > limit:
        end = text.rfind("\n", 0, limit + 1)
        end = end + 1 if end >= 0 else limit
        yield text[:end]
        text = text[end:]
    if text:
        yield text


def report_pages(embeds):
    pages = []
    for source in embeds:
        def new_page():
            page = discord.Embed(title=source.title, color=source.color, timestamp=source.timestamp)
            return page

        page = new_page()
        descriptions = list(_chunks(discord.utils.escape_mentions(source.description or ""), 3500))
        for i, description in enumerate(descriptions):
            page.description = description
            if i < len(descriptions) - 1:
                pages.append(page)
                page = new_page()
        for field in source.fields:
            for value in _chunks(discord.utils.escape_mentions(field.value), 1000):
                if len(page.fields) >= 20 or len(page) + len(field.name) + len(value) > 5500:
                    pages.append(page)
                    page = new_page()
                page.add_field(name=field.name, value=value, inline=False)
        if page.fields or page.description or not source.fields:
            pages.append(page)
    return pages


def report_files(name, data, file_limit):
    """Compress or split at complete text/CSV records; never drop report rows."""
    if len(data) <= file_limit:
        return [discord.File(io.BytesIO(data), filename=name)]
    compressed = gzip.compress(data, mtime=0)
    if len(compressed) <= file_limit:
        return [discord.File(io.BytesIO(compressed), filename=name + ".gz")]
    if name.endswith(".csv"):
        rows = iter(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))
        def encode(row):
            output = io.StringIO(newline="")
            csv.writer(output).writerow(row)
            return output.getvalue().encode("utf-8")
        header = b"\xef\xbb\xbf" + encode(next(rows))
        records = (encode(row) for row in rows)
    else:
        header = b""
        records = (line.encode("utf-8") for line in data.decode("utf-8-sig").splitlines(keepends=True))
    if len(header) > file_limit:
        raise ValueError("The report header exceeds Discord's attachment limit.")
    parts, current = [], bytearray(header)
    for record in records:
        if len(header) + len(record) > file_limit:
            raise ValueError("A report record exceeds Discord's attachment limit.")
        if len(current) + len(record) > file_limit:
            parts.append(bytes(current))
            current = bytearray(header)
        current.extend(record)
    parts.append(bytes(current))
    path = PurePath(name)
    return [discord.File(io.BytesIO(part), filename=f"{path.stem}.part{i:03d}{path.suffix}")
            for i, part in enumerate(parts, 1)]


class ActivityReportView(discord.ui.View):
    def __init__(self, pages, files, owner_id):
        super().__init__(timeout=840)
        self.pages = pages
        self.file_data = [(f.filename, f.fp.getvalue()) for f in files]
        self.owner_id = owner_id
        self.index = 0
        self.page_count = max(len(pages), (len(files) + 9) // 10)
        self._update_buttons()

    def _update_buttons(self):
        self.first.disabled = self.previous.disabled = self.index == 0
        self.next.disabled = self.last.disabled = self.index == self.page_count - 1
        self.position.label = f"{self.index + 1} / {self.page_count}"

    def embed(self):
        page = self.pages[min(self.index, len(self.pages) - 1)].copy()
        footer = f"Page {self.index + 1}/{self.page_count} · Full report attached · Activity uses retained records"
        if len(self.file_data) > 10:
            footer += " · More download files on later pages"
        page.set_footer(text=footer)
        return page

    def files(self):
        batch = min(self.index, max(0, (len(self.file_data) - 1) // 10))
        return [discord.File(io.BytesIO(data), filename=name) for name, data in self.file_data[batch * 10:batch * 10 + 10]]

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Run the command to open your own private report.", ephemeral=True)
        return False

    async def _move(self, interaction, index):
        self.index = max(0, min(index, self.page_count - 1))
        self._update_buttons()
        kwargs = {"attachments": self.files()} if len(self.file_data) > 10 else {}
        await interaction.response.edit_message(embed=self.embed(), view=self,
                                                allowed_mentions=discord.AllowedMentions.none(), **kwargs)

    @discord.ui.button(label="First")
    async def first(self, interaction, button):
        await self._move(interaction, 0)

    @discord.ui.button(label="Previous")
    async def previous(self, interaction, button):
        await self._move(interaction, self.index - 1)

    @discord.ui.button(label="1 / 1", disabled=True)
    async def position(self, interaction, button):
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        await self._move(interaction, self.index + 1)

    @discord.ui.button(label="Last")
    async def last(self, interaction, button):
        await self._move(interaction, self.page_count - 1)


async def send_report(interaction, embeds, *, files=None, filename="activity_report.txt"):
    if isinstance(embeds, discord.Embed):
        embeds = [embeds]
    if files is None:
        lines = []
        for embed in embeds:
            lines.extend([embed.title or "", embed.description or ""])
            for field in embed.fields:
                lines.extend([field.name, field.value, ""])
        limit = getattr(interaction, "filesize_limit", None) or getattr(interaction.guild, "filesize_limit", 8000000)
        files = report_files(filename, "\n".join(lines).encode("utf-8"), limit)
    pages = report_pages(embeds)
    view = ActivityReportView(pages, files, getattr(getattr(interaction, "user", None), "id", None))
    await interaction.followup.send(embed=view.embed(), files=view.files(),
                                    view=view if view.page_count > 1 else None, ephemeral=True,
                                    allowed_mentions=discord.AllowedMentions.none())
