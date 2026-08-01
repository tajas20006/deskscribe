"""Local transcript and optional audio file output."""

import os
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

DEFAULT_TITLE = "名称未設定"
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class OutputPaths:
    transcript: Path
    audio: Path


def normalize_title(title: str) -> str:
    """Return a cross-platform safe title or the required default."""
    normalized = _UNSAFE_FILENAME_CHARS.sub("_", title.strip())
    normalized = normalized.rstrip(" .")
    return normalized[:80] or DEFAULT_TITLE


def build_output_paths(
    output_dir: Path,
    title: str,
    recorded_at: datetime,
) -> OutputPaths:
    basename = f"{recorded_at:%Y%m%d-%H%M%S}_{normalize_title(title)}"
    output_dir = Path(output_dir)
    sequence = 1
    while True:
        suffix = "" if sequence == 1 else f"_{sequence}"
        paths = OutputPaths(
            transcript=output_dir / f"{basename}{suffix}.txt",
            audio=output_dir / f"{basename}{suffix}.wav",
        )
        if not paths.transcript.exists() and not paths.audio.exists():
            return paths
        sequence += 1


def save_transcript(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{text.rstrip()}\n", encoding="utf-8")


def open_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def save_wave(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
