from pathlib import Path

from deskscribe.settings import AppSettings, SettingsStore, default_settings_path


def test_default_settings_path_uses_home_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_settings_path() == (
        tmp_path / ".cache" / "deskscribe" / "settings.json"
    )


def test_default_settings_path_honors_xdg_cache_home(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cache_home = tmp_path / "xdg-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    assert default_settings_path() == cache_home / "deskscribe" / "settings.json"


def test_empty_xdg_cache_home_uses_home_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", "")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_settings_path() == (
        tmp_path / ".cache" / "deskscribe" / "settings.json"
    )


def test_settings_store_round_trip(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    store = SettingsStore(settings_path)
    expected = AppSettings(
        output_dir=r"C:\records",
        model_path=r"C:\models\faster-whisper-small",
        desktop_device_id="desktop-id",
        microphone_device_id="microphone-id",
        beam_size=3,
        caption_seconds=10,
        cpu_threads=6,
        prompt_context_characters=500,
    )

    store.save(expected)

    assert store.load() == expected


def test_settings_store_returns_defaults_for_missing_file(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "missing.json")

    assert store.load() == AppSettings()


def test_settings_store_returns_defaults_for_malformed_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{broken", encoding="utf-8")

    assert SettingsStore(settings_path).load() == AppSettings()


def test_legacy_folder_only_settings_load_with_empty_device_ids(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"output_dir": "output", "model_path": "model"}',
        encoding="utf-8",
    )

    assert SettingsStore(settings_path).load() == AppSettings("output", "model")


def test_invalid_advanced_settings_fall_back_to_defaults(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"beam_size": 0, "caption_seconds": "fast", '
        '"cpu_threads": 1000, "prompt_context_characters": -1}',
        encoding="utf-8",
    )

    settings = SettingsStore(settings_path).load()

    assert settings.beam_size == 1
    assert settings.caption_seconds == 15
    assert settings.cpu_threads == 8
    assert settings.prompt_context_characters == 300
