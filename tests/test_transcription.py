import sys
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import numpy as np
import pytest

from deskscribe.transcription import FasterWhisperTranscriber


class Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisperModel:
    calls: ClassVar[list[tuple[str, dict[str, object]]]] = []
    transcription_calls: ClassVar[list[dict[str, object]]] = []

    def __init__(self, path: str, **kwargs: object) -> None:
        self.calls.append((path, kwargs))

    def transcribe(self, audio: np.ndarray, **kwargs: object):
        assert audio.dtype == np.float32
        self.transcription_calls.append(kwargs)
        return iter([Segment(" こんにちは"), Segment(" 世界 ")]), object()


def test_transcriber_loads_only_a_local_model(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    for filename in ("model.bin", "config.json", "tokenizer.json"):
        (model_dir / filename).touch()
    fake_faster_whisper = ModuleType("faster_whisper")
    fake_faster_whisper.WhisperModel = FakeWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)
    transcriber = FasterWhisperTranscriber(model_dir)

    transcriber.load()
    text = transcriber.transcribe(np.zeros(16_000, dtype=np.float32))

    path, kwargs = FakeWhisperModel.calls[-1]
    assert path == str(model_dir)
    assert kwargs["local_files_only"] is True
    assert kwargs["cpu_threads"] == 8
    assert FakeWhisperModel.transcription_calls[-1]["beam_size"] == 1
    assert text == "こんにちは 世界"


def test_transcriber_load_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    for filename in ("model.bin", "config.json", "tokenizer.json"):
        (model_dir / filename).touch()
    FakeWhisperModel.calls.clear()
    fake_faster_whisper = ModuleType("faster_whisper")
    fake_faster_whisper.WhisperModel = FakeWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)
    transcriber = FasterWhisperTranscriber(model_dir)

    transcriber.load()
    transcriber.load()

    assert len(FakeWhisperModel.calls) == 1


def test_transcriber_rejects_model_that_could_need_online_tokenizer(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.bin").touch()
    (model_dir / "config.json").touch()
    transcriber = FasterWhisperTranscriber(model_dir)

    with pytest.raises(ValueError, match="tokenizer.json"):
        transcriber.load()
