from endstone_discord_bridge.inventory_view import format_inventory_pages, snapshot_player_inventory


class FakeMeta:
    has_display_name = True
    display_name = "§6Named Blade"
    has_damage = True
    damage = 7
    enchants = {"sharpness": 5}


class FakeItem:
    def __init__(self, item_type, amount=1, meta=None):
        self.type = item_type
        self.amount = amount
        self.item_meta = meta


class FakeInventory:
    def __init__(self, items, size=None):
        self._items = items
        self.size = len(items) if size is None else size
        self.helmet = None
        self.chestplate = None
        self.leggings = None
        self.boots = None
        self.item_in_off_hand = None

    def get_item(self, slot):
        return self._items[slot] if slot < len(self._items) else None


class FakePlayer:
    name = "Builder"

    def __init__(self):
        self.inventory = FakeInventory(
            [FakeItem("minecraft:diamond_sword", meta=FakeMeta()), None], size=36
        )
        self.inventory.helmet = FakeItem("minecraft:diamond_helmet")
        self.inventory.item_in_off_hand = FakeItem("minecraft:shield")
        self.ender_chest = FakeInventory([FakeItem("minecraft:diamond", 64)], size=27)


def test_snapshot_includes_all_player_inventory_sections():
    snapshot = snapshot_player_inventory(FakePlayer())

    assert snapshot["player"] == "Builder"
    assert snapshot["main"][0] == {
        "slot": 0,
        "type": "minecraft:diamond_sword",
        "amount": 1,
        "name": "Named Blade",
        "damage": 7,
        "enchantments": [("sharpness", 5)],
    }
    assert snapshot["equipment"][0]["slot"] == "Helmet"
    assert snapshot["offhand"][0]["type"] == "minecraft:shield"
    assert snapshot["ender_chest"][0]["amount"] == 64


def test_formatted_pages_stay_within_discord_description_limit():
    snapshot = snapshot_player_inventory(FakePlayer())
    pages = format_inventory_pages(snapshot, max_chars=180)

    assert len(pages) > 1
    assert all(len(page) <= 180 for page in pages)
    assert any("minecraft:diamond_sword" in page for page in pages)
    assert any("Ender Chest" in page for page in pages)
