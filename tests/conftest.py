from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_settings_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
