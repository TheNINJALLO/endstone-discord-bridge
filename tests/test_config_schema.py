from endstone_discord_bridge.config_schema import BridgeConfig, is_bridge_relay_enabled


def test_bridge_relay_defaults_to_enabled_for_existing_configs(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[discord]\ntoken = ''\n", encoding="utf-8")

    assert BridgeConfig.load(path).features.bridge_relay is True


def test_bridge_relay_can_be_disabled(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[features]\nbridge_relay = false\n", encoding="utf-8")

    assert BridgeConfig.load(path).features.bridge_relay is False


def test_bridge_relay_requires_feature_and_channel():
    config = BridgeConfig()
    config.channels.bridge_relay = 123
    assert is_bridge_relay_enabled(config) is True

    config.features.bridge_relay = False
    assert is_bridge_relay_enabled(config) is False

    config.features.bridge_relay = True
    config.channels.bridge_relay = 0
    assert is_bridge_relay_enabled(config) is False
