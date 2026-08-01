import wave
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from deskscribe.session import (
    RecordingConfig,
    RecordingSession,
    format_transcript_line,
)


class FakeCapture:
    def __init__(self) -> None:
        self.callback: Callable[[str, np.ndarray], None] | None = None

    def start(
        self,
        desktop_device_id: str,
        microphone_device_id: str,
        callback: Callable[[str, np.ndarray], None],
        error_callback: Callable[[Exception], None],
    ) -> None:
        assert desktop_device_id == "desktop"
        assert microphone_device_id == "microphone"
        self.callback = callback

    def stop(self) -> None:
        pass

    def emit(self, source: str, samples: np.ndarray) -> None:
        assert self.callback is not None
        self.callback(source, samples)


class FakeTranscriber:
    def __init__(self) -> None:
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str:
        assert self.loaded
        return "自動抽出"


def test_transcript_line_contains_wall_clock_range() -> None:
    recorded_at = datetime(2026, 7, 31, 10, 45, 39, tzinfo=UTC)

    line = format_transcript_line(recorded_at, 0, 5, "テスト発言")

    assert line == "[10:45:39 - 10:45:44] テスト発言"


def test_recording_session_saves_corrected_text_without_audio_by_default(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.bin").touch()
    capture = FakeCapture()
    captions: list[str] = []
    meters: list[tuple[str, float]] = []
    config = RecordingConfig(
        output_dir=tmp_path,
        model_path=model_dir,
        desktop_device_id="desktop",
        microphone_device_id="microphone",
        title="議事録",
        replacement_rules=[("自動抽出", "DeskScribe")],
        sample_rate=4,
        caption_seconds=1,
    )
    session = RecordingSession(
        config,
        capture,
        FakeTranscriber(),
        on_caption=captions.append,
        on_meter=lambda source, level: meters.append((source, level)),
        now=lambda: datetime(2026, 7, 31, 10, 20, 30, tzinfo=UTC),
    )

    session.start()
    capture.emit("desktop", np.ones(4, dtype=np.float32))
    capture.emit("microphone", np.zeros(4, dtype=np.float32))
    result = session.stop()

    assert result.transcript_path.name == "20260731-102030_議事録.txt"
    assert result.audio_path is None
    expected = "[10:20:30 - 10:20:31] DeskScribe"
    assert result.transcript_path.read_text(encoding="utf-8") == f"{expected}\n"
    assert captions[-1] == "[10:20:30 - 10:20:31] 自動抽出"
    assert {source for source, _ in meters} == {"desktop", "microphone"}
    assert not (tmp_path / "20260731-102030_議事録.wav").exists()


def test_recording_config_rejects_missing_devices(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    config = RecordingConfig(output_dir=tmp_path, model_path=model_dir)

    errors = config.validation_errors()

    assert "デスクトップ音声デバイス" in "\n".join(errors)
    assert "マイク音声デバイス" in "\n".join(errors)


def test_recording_config_uses_speed_oriented_defaults(tmp_path: Path) -> None:
    config = RecordingConfig(output_dir=tmp_path, model_path=tmp_path)

    assert config.caption_seconds == 15
    assert config.prompt_context_characters == 300


def test_recording_session_saves_audio_when_enabled(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    capture = FakeCapture()
    config = RecordingConfig(
        output_dir=tmp_path,
        model_path=model_dir,
        desktop_device_id="desktop",
        microphone_device_id="microphone",
        save_audio=True,
        sample_rate=4,
        caption_seconds=1,
    )
    session = RecordingSession(
        config,
        capture,
        FakeTranscriber(),
        now=lambda: datetime(2026, 7, 31, 10, 20, 30, tzinfo=UTC),
    )

    session.start()
    capture.emit("desktop", np.ones(4, dtype=np.float32))
    capture.emit("microphone", np.zeros(4, dtype=np.float32))
    result = session.stop()

    assert result.audio_path is not None
    with wave.open(str(result.audio_path), "rb") as wav:
        assert wav.getframerate() == 4
        assert wav.getnframes() == 4


def test_recording_session_captions_when_one_source_stalls(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    capture = FakeCapture()
    captions: list[str] = []
    config = RecordingConfig(
        output_dir=tmp_path,
        model_path=model_dir,
        desktop_device_id="desktop",
        microphone_device_id="microphone",
        sample_rate=4,
        caption_seconds=1,
    )
    session = RecordingSession(
        config,
        capture,
        FakeTranscriber(),
        on_caption=captions.append,
        now=lambda: datetime(2026, 7, 31, 10, 20, 30, tzinfo=UTC),
    )

    session.start()
    capture.emit("desktop", np.ones(6, dtype=np.float32))
    session.stop()

    assert captions == [
        "[10:20:30 - 10:20:31] 自動抽出",
        "[10:20:30 - 10:20:31] 自動抽出\n[10:20:31 - 10:20:31] 自動抽出",
    ]


class SilentTranscriber(FakeTranscriber):
    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str:
        assert self.loaded
        return ""


def test_empty_recognition_does_not_add_a_timestamp_line(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    capture = FakeCapture()
    config = RecordingConfig(
        output_dir=tmp_path,
        model_path=model_dir,
        desktop_device_id="desktop",
        microphone_device_id="microphone",
        sample_rate=4,
        caption_seconds=1,
    )
    session = RecordingSession(config, capture, SilentTranscriber())

    session.start()
    capture.emit("desktop", np.ones(4, dtype=np.float32))
    capture.emit("microphone", np.zeros(4, dtype=np.float32))
    result = session.stop()

    assert result.text == ""
    assert result.transcript_path.read_text(encoding="utf-8") == "\n"


class FailingStartCapture(FakeCapture):
    def __init__(self) -> None:
        super().__init__()
        self.stop_calls = 0

    def start(
        self,
        desktop_device_id: str,
        microphone_device_id: str,
        callback: Callable[[str, np.ndarray], None],
        error_callback: Callable[[Exception], None],
    ) -> None:
        super().start(
            desktop_device_id,
            microphone_device_id,
            callback,
            error_callback,
        )
        raise RuntimeError("capture startup failed")

    def stop(self) -> None:
        self.stop_calls += 1


def test_recording_start_failure_cleans_up_capture_and_timing_state(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    capture = FailingStartCapture()
    clock = [10.0]
    config = RecordingConfig(
        output_dir=tmp_path,
        model_path=model_dir,
        desktop_device_id="desktop",
        microphone_device_id="microphone",
    )
    session = RecordingSession(
        config,
        capture,
        FakeTranscriber(),
        monotonic=lambda: clock[0],
    )

    with pytest.raises(RuntimeError, match="capture startup failed"):
        session.start()
    clock[0] = 15.0

    assert capture.stop_calls == 1
    assert session.elapsed_seconds == 0


def test_recording_session_can_be_reused_without_previous_recording_state(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    capture = FakeCapture()
    recorded_times = iter(
        (
            datetime(2026, 7, 31, 10, 20, 30, tzinfo=UTC),
            datetime(2026, 7, 31, 10, 20, 31, tzinfo=UTC),
        )
    )
    config = RecordingConfig(
        output_dir=tmp_path,
        model_path=model_dir,
        desktop_device_id="desktop",
        microphone_device_id="microphone",
        save_audio=True,
        sample_rate=4,
        caption_seconds=1,
    )
    session = RecordingSession(
        config,
        capture,
        FakeTranscriber(),
        now=lambda: next(recorded_times),
    )

    session.start()
    capture.emit("desktop", np.ones(4, dtype=np.float32))
    capture.emit("microphone", np.zeros(4, dtype=np.float32))
    session.stop()

    session.start()
    capture.emit("desktop", np.ones(4, dtype=np.float32))
    capture.emit("microphone", np.zeros(4, dtype=np.float32))
    second = session.stop()

    assert second.text == "[10:20:31 - 10:20:32] 自動抽出"
    assert second.audio_path is not None
    with wave.open(str(second.audio_path), "rb") as wav:
        assert wav.getnframes() == 4
