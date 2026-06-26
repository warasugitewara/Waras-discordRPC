import json

from config.store import DEFAULT_CONFIG, ConfigStore, Secrets, resolve_bind


def test_resolve_bind_local_returns_loopback():
    assert resolve_bind({"network_mode": "local", "bind": "10.0.0.1"}) == "127.0.0.1"


def test_resolve_bind_lan_returns_all_interfaces():
    assert resolve_bind({"network_mode": "lan", "bind": "10.0.0.1"}) == "0.0.0.0"


def test_resolve_bind_custom_returns_configured_bind():
    assert resolve_bind({"network_mode": "custom", "bind": "10.0.0.5"}) == "10.0.0.5"


def test_resolve_bind_unknown_or_missing_defaults_to_loopback():
    assert resolve_bind({}) == "127.0.0.1"
    assert resolve_bind({"network_mode": "weird"}) == "127.0.0.1"


def test_secrets_save_roundtrip_and_preserves_other_keys(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER_KEY=keepme\nBRIDGE_TOKEN=old\n", encoding="utf-8")

    Secrets.save(env_path, bridge_token="newtoken", discord_client_id="12345")

    monkeypatch.delenv("BRIDGE_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
    monkeypatch.delenv("OTHER_KEY", raising=False)
    secrets = Secrets.load(env_path)
    assert secrets.bridge_token == "newtoken"
    assert secrets.discord_client_id == "12345"
    # 既存の無関係キーは保持される
    assert "OTHER_KEY=keepme" in env_path.read_text(encoding="utf-8")


def test_secrets_save_creates_file_when_missing(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    Secrets.save(env_path, bridge_token="t", discord_client_id="9")

    monkeypatch.delenv("BRIDGE_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
    secrets = Secrets.load(env_path)
    assert secrets.bridge_token == "t"
    assert secrets.discord_client_id == "9"


def test_migrate_converts_legacy_twingate_to_custom(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 1, "network_mode": "twingate"}), encoding="utf-8")

    config = ConfigStore(path).load()

    assert config["network_mode"] == "custom"


def test_load_returns_default_when_missing(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    assert store.load() == DEFAULT_CONFIG


def test_save_then_load_roundtrip(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    config = store.load()
    config["bind"] = "10.0.0.5"
    config["sources"]["phone-music"] = {
        "name": "Phone",
        "enabled": True,
        "priority": 1,
        "pinned": False,
    }
    store.save(config)

    reloaded = store.load()
    assert reloaded["bind"] == "10.0.0.5"
    assert reloaded["sources"]["phone-music"]["priority"] == 1


def test_migrate_fills_missing_fields(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": 1, "bind": "0.0.0.0"}), encoding="utf-8")

    config = ConfigStore(path).load()

    assert config["bind"] == "0.0.0.0"
    assert config["ttl_seconds"] == DEFAULT_CONFIG["ttl_seconds"]


def test_secrets_load_from_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("BRIDGE_TOKEN=abc123\nDISCORD_CLIENT_ID=999\n", encoding="utf-8")
    monkeypatch.delenv("BRIDGE_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)

    secrets = Secrets.load(env_path)

    assert secrets.bridge_token == "abc123"
    assert secrets.discord_client_id == "999"
