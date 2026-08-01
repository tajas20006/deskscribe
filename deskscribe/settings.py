"""Persistent per-user GUI settings."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BEAM_SIZE = 1
DEFAULT_CAPTION_SECONDS = 15
DEFAULT_CPU_THREADS = 8
DEFAULT_PROMPT_CONTEXT_CHARACTERS = 300


@dataclass(frozen=True)
class AppSettings:
    output_dir: str = ""
    model_path: str = ""
    desktop_device_id: str = ""
    microphone_device_id: str = ""
    beam_size: int = DEFAULT_BEAM_SIZE
    caption_seconds: int = DEFAULT_CAPTION_SECONDS
    cpu_threads: int = DEFAULT_CPU_THREADS
    prompt_context_characters: int = DEFAULT_PROMPT_CONTEXT_CHARACTERS


def default_settings_path() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    if cache_home:
        return Path(cache_home) / "deskscribe" / "settings.json"
    return Path.home() / ".cache" / "deskscribe" / "settings.json"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> AppSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError, TypeError:
            return AppSettings()
        if not isinstance(data, dict):
            return AppSettings()
        output_dir = data.get("output_dir", "")
        model_path = data.get("model_path", "")
        desktop_device_id = data.get("desktop_device_id", "")
        microphone_device_id = data.get("microphone_device_id", "")
        return AppSettings(
            output_dir=output_dir if isinstance(output_dir, str) else "",
            model_path=model_path if isinstance(model_path, str) else "",
            desktop_device_id=(
                desktop_device_id if isinstance(desktop_device_id, str) else ""
            ),
            microphone_device_id=(
                microphone_device_id if isinstance(microphone_device_id, str) else ""
            ),
            beam_size=self._bounded_int(
                data,
                "beam_size",
                DEFAULT_BEAM_SIZE,
                minimum=1,
                maximum=10,
            ),
            caption_seconds=self._bounded_int(
                data,
                "caption_seconds",
                DEFAULT_CAPTION_SECONDS,
                minimum=1,
                maximum=30,
            ),
            cpu_threads=self._bounded_int(
                data,
                "cpu_threads",
                DEFAULT_CPU_THREADS,
                minimum=1,
                maximum=64,
            ),
            prompt_context_characters=self._bounded_int(
                data,
                "prompt_context_characters",
                DEFAULT_PROMPT_CONTEXT_CHARACTERS,
                minimum=0,
                maximum=4000,
            ),
        )

    @staticmethod
    def _bounded_int(
        data: dict[str, object],
        key: str,
        default: int,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return value if minimum <= value <= maximum else default

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
