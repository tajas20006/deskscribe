import wave
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from deskscribe.output import (
    build_output_paths,
    normalize_title,
    open_file,
    save_transcript,
    save_wave,
)


def test_blank_title_uses_required_default_name(tmp_path: Path) -> None:
    paths = build_output_paths(
        tmp_path,
        " \t",
        datetime(2026, 7, 31, 9, 8, 7, tzinfo=UTC),
    )

    assert paths.transcript.name == "20260731-090807_名称未設定.txt"
    assert paths.audio.name == "20260731-090807_名称未設定.wav"


def test_output_paths_do_not_overwrite_an_existing_recording(tmp_path: Path) -> None:
    recorded_at = datetime(2026, 7, 31, 9, 8, 7, tzinfo=UTC)
    existing = tmp_path / "20260731-090807_会議.txt"
    existing.write_text("既存の録音\n", encoding="utf-8")

    paths = build_output_paths(tmp_path, "会議", recorded_at)

    assert paths.transcript.name == "20260731-090807_会議_2.txt"
    assert paths.audio.name == "20260731-090807_会議_2.wav"
    assert existing.read_text(encoding="utf-8") == "既存の録音\n"


def test_title_is_safe_for_cross_platform_filenames() -> None:
    assert normalize_title(' 会議: A/B? "確認" ') == "会議_ A_B_ _確認_"


def test_save_transcript_writes_utf8_text(tmp_path: Path) -> None:
    path = tmp_path / "result.txt"

    save_transcript(path, "日本語の文字起こし")

    assert path.read_text(encoding="utf-8") == "日本語の文字起こし\n"


def test_save_wave_writes_mono_pcm16(tmp_path: Path) -> None:
    path = tmp_path / "audio.wav"

    save_wave(path, np.array([-1.0, 0.0, 1.0], dtype=np.float32), 16_000)

    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16_000
        assert wav.getnframes() == 3


def test_open_file_uses_the_windows_default_application(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "transcript.txt"
    path.touch()
    opened: list[str] = []
    monkeypatch.setattr("deskscribe.output.sys.platform", "win32")
    monkeypatch.setattr(
        "deskscribe.output.os.startfile",
        lambda value: opened.append(value),
    )

    open_file(path)

    assert opened == [str(path)]
