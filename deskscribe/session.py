"""Recording and transcription session orchestration."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from typing import Protocol

import numpy as np

from deskscribe.audio import (
    DESKTOP,
    MICROPHONE,
    DualSourceBuffer,
    meter_level,
)
from deskscribe.output import (
    OutputPaths,
    build_output_paths,
    save_transcript,
    save_wave,
)
from deskscribe.text import apply_replacements


class Capture(Protocol):
    def start(
        self,
        desktop_device_id: str,
        microphone_device_id: str,
        callback: Callable[[str, np.ndarray], None],
        error_callback: Callable[[Exception], None],
    ) -> None: ...

    def stop(self) -> None: ...


class Transcriber(Protocol):
    def load(self) -> None: ...

    def transcribe(self, audio: np.ndarray, prompt: str = "") -> str: ...


@dataclass
class RecordingConfig:
    output_dir: Path
    model_path: Path
    desktop_device_id: str = ""
    microphone_device_id: str = ""
    title: str = ""
    save_audio: bool = False
    replacement_rules: list[tuple[str, str]] = field(default_factory=list)
    sample_rate: int = 16_000
    caption_seconds: float = 15
    prompt_context_characters: int = 300

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.desktop_device_id:
            errors.append("デスクトップ音声デバイスを選択してください。")
        if not self.microphone_device_id:
            errors.append("マイク音声デバイスを選択してください。")
        if not Path(self.output_dir).is_dir():
            errors.append("保存先フォルダが存在しません。")
        if not Path(self.model_path).is_dir():
            errors.append("ローカルモデルのフォルダが存在しません。")
        if self.sample_rate <= 0:
            errors.append("サンプルレートは正の整数にしてください。")
        if self.caption_seconds <= 0:
            errors.append("ライブキャプション間隔は正の値にしてください。")
        if self.prompt_context_characters < 0:
            errors.append("過去文脈の文字数は0以上にしてください。")
        return errors


@dataclass(frozen=True)
class RecordingResult:
    transcript_path: Path
    audio_path: Path | None
    text: str


@dataclass(frozen=True)
class TimedAudioChunk:
    audio: np.ndarray
    start_seconds: float
    end_seconds: float


def format_transcript_line(
    recorded_at: datetime,
    start_seconds: float,
    end_seconds: float,
    text: str,
) -> str:
    start = recorded_at + timedelta(seconds=max(0.0, start_seconds))
    end = recorded_at + timedelta(seconds=max(start_seconds, end_seconds))
    return f"[{start:%H:%M:%S} - {end:%H:%M:%S}] {text}"


class RecordingSession:
    def __init__(
        self,
        config: RecordingConfig,
        capture: Capture,
        transcriber: Transcriber,
        *,
        on_caption: Callable[[str], None] = lambda _text: None,
        on_meter: Callable[[str, float], None] = lambda _source, _level: None,
        on_error: Callable[[Exception], None] = lambda _error: None,
        now: Callable[[], datetime] = datetime.now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._capture = capture
        self._transcriber = transcriber
        self._on_caption = on_caption
        self._on_meter = on_meter
        self._on_error = on_error
        self._now = now
        self._monotonic = monotonic
        self._lock = Lock()
        self._audio_lock = Lock()
        self._active = False
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        """Initialize state that belongs to one recording run."""
        self._buffer = DualSourceBuffer(
            round(self.config.sample_rate * self.config.caption_seconds),
            max_skew_samples=round(self.config.sample_rate * 0.5),
        )
        self._queue: Queue[TimedAudioChunk | None] = Queue()
        self._worker: Thread | None = None
        self._captions: list[str] = []
        self._recognized_texts: list[str] = []
        self._recognized_chunks: list[tuple[TimedAudioChunk, str]] = []
        self._recorded_chunks: list[np.ndarray] = []
        self._queued_samples = 0
        self._recorded_at: datetime | None = None
        self._started_at: float | None = None

    @property
    def elapsed_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, self._monotonic() - self._started_at)

    def start(self) -> None:
        if self._active:
            raise RuntimeError("録音は既に開始されています。")
        errors = self.config.validation_errors()
        if errors:
            raise ValueError("\n".join(errors))
        self._transcriber.load()
        self._reset_run_state()
        self._recorded_at = self._now()
        self._started_at = self._monotonic()
        self._worker = Thread(
            target=self._transcription_worker,
            name="transcription",
            daemon=True,
        )
        self._worker.start()
        try:
            self._capture.start(
                self.config.desktop_device_id,
                self.config.microphone_device_id,
                self._on_audio,
                self._handle_error,
            )
        except Exception as start_error:
            try:
                self._capture.stop()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve start error
                start_error.add_note(
                    f"キャプチャの後片付けにも失敗しました: {cleanup_error}"
                )
            self._stop_transcription_worker()
            self._recorded_at = None
            self._started_at = None
            raise
        self._active = True

    def stop(self) -> RecordingResult:
        if not self._active:
            raise RuntimeError("録音は開始されていません。")
        self._capture.stop()
        final_chunk = self._buffer.flush()
        if final_chunk.size:
            self._enqueue(final_chunk)
        self._stop_transcription_worker()
        self._active = False

        corrected_text = self._build_corrected_transcript()
        assert self._recorded_at is not None
        paths = build_output_paths(
            self.config.output_dir,
            self.config.title,
            self._recorded_at,
        )
        save_transcript(paths.transcript, corrected_text)
        audio_path = self._save_audio_if_requested(paths)
        return RecordingResult(paths.transcript, audio_path, corrected_text)

    def _on_audio(self, source: str, samples: np.ndarray) -> None:
        if source not in (DESKTOP, MICROPHONE):
            self._handle_error(ValueError(f"不明な音声ソースです: {source}"))
            return
        self._on_meter(source, meter_level(samples))
        with self._audio_lock:
            for chunk in self._buffer.push(source, samples):
                self._enqueue(chunk)

    def _enqueue(self, chunk: np.ndarray) -> None:
        start_seconds = self._queued_samples / self.config.sample_rate
        self._queued_samples += chunk.size
        end_seconds = self._queued_samples / self.config.sample_rate
        with self._lock:
            self._recorded_chunks.append(chunk)
        self._queue.put(TimedAudioChunk(chunk, start_seconds, end_seconds))

    def _transcription_worker(self) -> None:
        while True:
            chunk = self._queue.get()
            try:
                if chunk is None:
                    return
                history = "\n".join(self._recognized_texts)
                context_length = self.config.prompt_context_characters
                prompt = history[-context_length:] if context_length else ""
                text = self._transcriber.transcribe(chunk.audio, prompt=prompt)
                if text:
                    self._recognized_texts.append(text)
                    self._recognized_chunks.append((chunk, text))
                    assert self._recorded_at is not None
                    self._captions.append(
                        format_transcript_line(
                            self._recorded_at,
                            chunk.start_seconds,
                            chunk.end_seconds,
                            text,
                        )
                    )
                    self._on_caption("\n".join(self._captions))
            except Exception as error:  # noqa: BLE001 - model errors are reported
                self._handle_error(error)
            finally:
                self._queue.task_done()

    def _build_corrected_transcript(self) -> str:
        assert self._recorded_at is not None
        return "\n".join(
            format_transcript_line(
                self._recorded_at,
                chunk.start_seconds,
                chunk.end_seconds,
                apply_replacements(text, self.config.replacement_rules),
            )
            for chunk, text in self._recognized_chunks
        )

    def _stop_transcription_worker(self) -> None:
        self._queue.put(None)
        if self._worker is not None:
            self._worker.join()
            self._worker = None

    def _save_audio_if_requested(self, paths: OutputPaths) -> Path | None:
        if not self.config.save_audio:
            return None
        with self._lock:
            chunks = list(self._recorded_chunks)
        samples = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)
        save_wave(paths.audio, samples, self.config.sample_rate)
        return paths.audio

    def _handle_error(self, error: Exception) -> None:
        self._on_error(error)
