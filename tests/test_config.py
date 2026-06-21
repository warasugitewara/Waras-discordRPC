import json

from config.store import DEFAULT_CONFIG, ConfigStore, Secrets


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
