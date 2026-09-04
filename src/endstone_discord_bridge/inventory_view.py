"""Safe, Discord-friendly snapshots of online Endstone player inventories."""

from __future__ import annotations

import re
from typing import Any


_MINECRAFT_FORMAT = re.compile(r"\u00a7[0-9A-FK-OR]", re.IGNORECASE)


def _clean_text(value: Any, limit: int = 120) -> str:
    text = _MINECRAFT_FORMAT.sub("", str(value or "")).replace("`", "'")
    text = " ".join(text.split())
    return text[:limit]


def _item_snapshot(item: Any) -> dict[str, Any] | None:
    """Convert an ItemStack to primitives while still on the server thread."""
    if item is None:
        return None

    try:
        item_type = str(item.type)
    except Exception:
        return None
    if not item_type or item_type == "minecraft:air":
        return None

    try:
        amount = max(1, int(item.amount))
    except Exception:
        amount = 1

    result: dict[str, Any] = {"type": _clean_text(item_type), "amount": amount}
    try:
        meta = item.item_meta
    except Exception:
        meta = None

    if meta is not None:
        try:
            if meta.has_display_name:
                display_name = _clean_text(meta.display_name)
                if display_name:
                    result["name"] = display_name
        except Exception:
            pass

        try:
            if meta.has_damage:
                result["damage"] = max(0, int(meta.damage))
        except Exception:
            pass

        try:
            enchantments = []
            for enchantment, level in dict(meta.enchants or {}).items():
                enchantment_id = _clean_text(getattr(enchantment, "id", enchantment), 60)
                enchantments.append((enchantment_id, int(level)))
            if enchantments:
                result["enchantments"] = enchantments
        except Exception:
            pass

    return result


def _inventory_entries(inventory: Any) -> tuple[int, list[dict[str, Any]]]:
    try:
        size = max(0, int(inventory.size))
    except Exception:
        size = 0

    entries = []
    for slot in range(size):
        try:
            item = _item_snapshot(inventory.get_item(slot))
        except Exception:
            item = None
        if item is not None:
            entries.append({"slot": slot, **item})
    return size, entries


def snapshot_player_inventory(player: Any) -> dict[str, Any]:
    """Capture main, equipment, offhand, and Ender Chest inventory sections."""
    inventory = player.inventory
    main_size, main = _inventory_entries(inventory)

    equipment = []
    for label, attribute in (
        ("Helmet", "helmet"),
        ("Chestplate", "chestplate"),
        ("Leggings", "leggings"),
        ("Boots", "boots"),
    ):
        try:
            item = _item_snapshot(getattr(inventory, attribute, None))
        except Exception:
            item = None
        if item is not None:
            equipment.append({"slot": label, **item})

    try:
        offhand_item = _item_snapshot(inventory.item_in_off_hand)
    except Exception:
        offhand_item = None
    offhand = [{"slot": "Offhand", **offhand_item}] if offhand_item else []

    try:
        ender_size, ender_chest = _inventory_entries(player.ender_chest)
    except Exception:
        ender_size, ender_chest = 0, []

    return {
        "player": _clean_text(getattr(player, "name", "Unknown"), 80),
        "main_size": main_size,
        "main": main,
        "equipment": equipment,
        "offhand": offhand,
        "ender_size": ender_size,
        "ender_chest": ender_chest,
    }


def _format_item(entry: dict[str, Any]) -> str:
    item_type = entry["type"]
    line = f"`{entry['slot']}` **{entry['amount']}×** `{item_type}`"
    if entry.get("name"):
        line += f" — {entry['name']}"
    details = []
    if "damage" in entry:
        details.append(f"damage {entry['damage']}")
    if entry.get("enchantments"):
        details.extend(f"{name} {level}" for name, level in entry["enchantments"])
    if details:
        line += f" _({', '.join(details)})_"
    return line[:300]


def format_inventory_pages(snapshot: dict[str, Any], max_chars: int = 3500) -> list[str]:
    """Format a snapshot into embed-description-sized pages."""
    sections = (
        (f"Main Inventory ({len(snapshot['main'])}/{snapshot['main_size']} slots)", snapshot["main"]),
        ("Equipment", snapshot["equipment"]),
        ("Offhand", snapshot["offhand"]),
        (f"Ender Chest ({len(snapshot['ender_chest'])}/{snapshot['ender_size']} slots)", snapshot["ender_chest"]),
    )

    pages: list[str] = []
    current = ""
    for heading, entries in sections:
        lines = [_format_item(entry) for entry in entries] or ["_Empty_"]
        block_lines = [f"**{heading}**", *lines]
        for line in block_lines:
            line = line[:max_chars]
            candidate = f"{current}\n{line}" if current else line
            if current and len(candidate) > max_chars:
                pages.append(current.rstrip())
                current = line
            else:
                current = candidate
        if current and len(current) < max_chars:
            current += "\n"

    if current.strip():
        pages.append(current.rstrip())
    return pages or ["_Inventory is empty._"]
