"""Offline-only faster-whisper adapter."""

from pathlib import Path
from typing import Any

import numpy as np


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_path: Path,
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = "ja",
        beam_size: int = 1,
        cpu_threads: int = 8,
    ) -> None:
        self.model_path = Path(model_path)
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self._model: Any = None

    def load(self) -> None:
        if self._model is not None:
            return
        self._validate_local_model()
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            str(self.model_path),
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            local_files_only=True,
        )

    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str:
        if self._model is None:
            raise RuntimeError("文字起こしモデルが読み込まれていません。")
        segments, _ = self._model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
            condition_on_previous_text=True,
            initial_prompt=prompt or None,
        )
        return "".join(segment.text for segment in segments).strip()

    def _validate_local_model(self) -> None:
        if not self.model_path.is_dir():
            raise ValueError("ローカルモデルのディレクトリが存在しません。")
        required = ("model.bin", "config.json", "tokenizer.json")
        missing = [name for name in required if not (self.model_path / name).is_file()]
        if missing:
            raise ValueError(
                "ローカルモデルに必要なファイルがありません: " + ", ".join(missing)
            )
