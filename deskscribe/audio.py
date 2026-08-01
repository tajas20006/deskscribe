"""Audio device discovery, capture, metering, and two-source mixing."""

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from threading import Event, Lock, Thread
from types import ModuleType
from typing import Any, ClassVar, Protocol

import numpy as np

DESKTOP = "desktop"
MICROPHONE = "microphone"


class AudioCaptureError(RuntimeError):
    """Identify which selected audio source could not be captured."""

    def __init__(self, source: str, device_id: str, cause: Exception) -> None:
        label = {
            DESKTOP: "デスクトップ音声",
            MICROPHONE: "マイク音声",
        }.get(source, source)
        detail = str(cause).strip() or type(cause).__name__
        super().__init__(f"{label}の取得を開始できませんでした: {detail}")
        self.source = source
        self.device_id = device_id
        self.cause = cause


@dataclass(frozen=True)
class DeviceInfo:
    id: str
    name: str


@dataclass(frozen=True)
class AudioDevices:
    desktop: list[DeviceInfo]
    microphones: list[DeviceInfo]


class SoundCardBackend(Protocol):
    def all_microphones(self, include_loopback: bool): ...

    def get_microphone(self, id: str, include_loopback: bool): ...


class SoundCardDeviceProvider:
    def __init__(self, backend: SoundCardBackend | ModuleType | None = None) -> None:
        if backend is None:
            import soundcard

            backend = soundcard
        self._backend = backend

    def list_devices(self) -> AudioDevices:
        desktop: list[DeviceInfo] = []
        microphones: list[DeviceInfo] = []
        for device in self._backend.all_microphones(include_loopback=True):
            info = DeviceInfo(str(device.id), str(device.name))
            if device.isloopback:
                desktop.append(info)
            else:
                microphones.append(info)
        return AudioDevices(desktop=desktop, microphones=microphones)


def to_mono(block: np.ndarray) -> np.ndarray:
    values = np.asarray(block, dtype=np.float32)
    if values.ndim == 1:
        return values
    if values.ndim != 2:
        raise ValueError("音声データは1次元または2次元である必要があります。")
    return values.mean(axis=1, dtype=np.float32)


def meter_level(block: np.ndarray) -> float:
    mono = to_mono(block)
    if mono.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float32))))
    if rms <= 0:
        return 0.0
    decibels = 20 * np.log10(rms)
    return float(np.clip((decibels + 60) / 60, 0.0, 1.0))


def resample_mono(
    block: np.ndarray,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("サンプルレートは正の整数である必要があります。")
    mono = to_mono(block)
    if mono.size == 0 or source_rate == target_rate:
        return mono.astype(np.float32, copy=False)
    target_size = max(1, round(mono.size * target_rate / source_rate))
    if mono.size == 1:
        return np.full(target_size, mono[0], dtype=np.float32)
    source_positions = np.arange(mono.size, dtype=np.float64)
    target_positions = np.linspace(0, mono.size - 1, target_size)
    return np.interp(target_positions, source_positions, mono).astype(np.float32)


def mix_audio(desktop: np.ndarray, microphone: np.ndarray) -> np.ndarray:
    left = to_mono(desktop)
    right = to_mono(microphone)
    length = max(left.size, right.size)
    if length == 0:
        return np.empty(0, dtype=np.float32)
    left_padded = np.pad(left, (0, length - left.size))
    right_padded = np.pad(right, (0, length - right.size))
    return np.clip(left_padded + right_padded, -1.0, 1.0).astype(np.float32)


class DualSourceBuffer:
    """Synchronize independently captured desktop and microphone samples."""

    def __init__(
        self,
        chunk_samples: int,
        max_skew_samples: int | None = None,
    ) -> None:
        if chunk_samples <= 0:
            raise ValueError("chunk_samples must be positive")
        if max_skew_samples is None:
            max_skew_samples = chunk_samples // 2
        if max_skew_samples < 0:
            raise ValueError("max_skew_samples must not be negative")
        self._chunk_samples = chunk_samples
        self._max_skew_samples = max_skew_samples
        self._buffers = {
            DESKTOP: np.empty(0, dtype=np.float32),
            MICROPHONE: np.empty(0, dtype=np.float32),
        }
        self._lock = Lock()

    def push(self, source: str, samples: np.ndarray) -> list[np.ndarray]:
        if source not in self._buffers:
            raise ValueError(f"不明な音声ソースです: {source}")
        mono = to_mono(samples)
        completed: list[np.ndarray] = []
        with self._lock:
            self._buffers[source] = np.concatenate((self._buffers[source], mono))
            while all(
                buffer.size >= self._chunk_samples for buffer in self._buffers.values()
            ):
                desktop = self._take(DESKTOP, self._chunk_samples)
                microphone = self._take(MICROPHONE, self._chunk_samples)
                completed.append(mix_audio(desktop, microphone))
            leading_source = max(
                self._buffers,
                key=lambda current: self._buffers[current].size,
            )
            if (
                self._buffers[leading_source].size
                >= self._chunk_samples + self._max_skew_samples
            ):
                lagging_source = MICROPHONE if leading_source == DESKTOP else DESKTOP
                leading = self._take(leading_source, self._chunk_samples)
                lagging_length = min(
                    self._chunk_samples,
                    self._buffers[lagging_source].size,
                )
                lagging = self._take(lagging_source, lagging_length)
                if leading_source == DESKTOP:
                    completed.append(mix_audio(leading, lagging))
                else:
                    completed.append(mix_audio(lagging, leading))
        return completed

    def flush(self) -> np.ndarray:
        with self._lock:
            desktop = self._buffers[DESKTOP]
            microphone = self._buffers[MICROPHONE]
            self._buffers = {
                DESKTOP: np.empty(0, dtype=np.float32),
                MICROPHONE: np.empty(0, dtype=np.float32),
            }
        return mix_audio(desktop, microphone)

    def _take(self, source: str, length: int) -> np.ndarray:
        selected = self._buffers[source][:length]
        self._buffers[source] = self._buffers[source][length:]
        return selected


AudioCallback = Callable[[str, np.ndarray], None]
ErrorCallback = Callable[[Exception], None]
MicrophoneCallback = Callable[[np.ndarray], None]


class MicrophoneFallback(Protocol):
    def capture(
        self,
        device_name: str,
        sample_rate: int,
        block_frames: int,
        stop_event: Event,
        callback: MicrophoneCallback,
    ) -> None: ...


class PortAudioMicrophoneCapture:
    """Capture microphones through sounddevice when SoundCard cannot open them."""

    _preferred_host_apis: ClassVar[dict[str, str]] = {}
    _preference_lock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        backend: Any = None,
        first_block_timeout: float = 1.0,
    ) -> None:
        if first_block_timeout <= 0:
            raise ValueError("first_block_timeout must be positive")
        self._backend = backend
        self._first_block_timeout = first_block_timeout

    def capture(
        self,
        device_name: str,
        sample_rate: int,
        block_frames: int,
        stop_event: Event,
        callback: MicrophoneCallback,
    ) -> None:
        backend = self._backend
        if backend is None:
            import sounddevice

            backend = sounddevice

        candidates = self._candidate_devices(backend, device_name)
        if not candidates:
            raise RuntimeError(
                f"PortAudioに対応する入力デバイスがありません: {device_name}"
            )

        preference_key = self._normalized_name(device_name)
        with self._preference_lock:
            preferred_host_api = self._preferred_host_apis.get(preference_key)
        if preferred_host_api is not None:
            candidates.sort(
                key=lambda candidate: candidate[2] == preferred_host_api,
                reverse=True,
            )

        failures: list[str] = []
        for device_index, device, host_api_name in candidates:
            native_rate = max(1, round(float(device["default_samplerate"])))
            native_frames = max(
                1,
                round(block_frames * native_rate / sample_rate),
            )
            stream_options: dict[str, Any] = {}
            if host_api_name == "Windows WASAPI" and hasattr(
                backend,
                "WasapiSettings",
            ):
                stream_options["extra_settings"] = backend.WasapiSettings(
                    auto_convert=True
                )
            first_block = Event()
            callback_errors: list[Exception] = []

            def on_audio(
                block: np.ndarray,
                _frames: int,
                _time_info: Any,
                _status: Any,
                _native_rate: int = native_rate,
                _callback_errors: list[Exception] = callback_errors,
                _first_block: Event = first_block,
            ) -> None:
                try:
                    callback(resample_mono(block.copy(), _native_rate, sample_rate))
                except Exception as error:  # noqa: BLE001 - callback boundary
                    _callback_errors.append(error)
                finally:
                    _first_block.set()

            try:
                with backend.InputStream(
                    device=device_index,
                    samplerate=native_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=native_frames,
                    callback=on_audio,
                    **stream_options,
                ):
                    if not first_block.wait(self._first_block_timeout):
                        failures.append(f"{host_api_name}: 音声データが届きません")
                        continue
                    if callback_errors:
                        raise callback_errors[0]
                    with self._preference_lock:
                        self._preferred_host_apis[preference_key] = host_api_name
                    while not stop_event.wait(0.1):
                        if callback_errors:
                            raise callback_errors[0]
                    if callback_errors:
                        raise callback_errors[0]
                return
            except Exception as error:  # noqa: BLE001 - PortAudio errors vary by API
                failures.append(f"{host_api_name}: {error}")

        detail = " / ".join(failures)
        raise RuntimeError(f"PortAudioでマイクを開けませんでした: {detail}")

    @staticmethod
    def _candidate_devices(
        backend: Any,
        selected_name: str,
    ) -> list[tuple[int, Any, str]]:
        target = PortAudioMicrophoneCapture._normalized_name(selected_name)
        host_apis = backend.query_hostapis()
        candidates: list[tuple[float, int, int, Any, str]] = []
        host_priority = {
            "MME": 3,
            "Windows DirectSound": 2,
            "Windows WASAPI": 1,
            "Windows WDM-KS": 0,
        }
        for index, device in enumerate(backend.query_devices()):
            if int(device["max_input_channels"]) < 1:
                continue
            candidate = PortAudioMicrophoneCapture._normalized_name(device["name"])
            similarity = SequenceMatcher(None, target, candidate).ratio()
            if target in candidate or candidate in target:
                similarity = max(similarity, 0.9)
            if similarity < 0.45:
                continue
            host_api_name = str(host_apis[int(device["hostapi"])]["name"])
            candidates.append(
                (
                    similarity,
                    host_priority.get(host_api_name, -1),
                    index,
                    device,
                    host_api_name,
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            (index, device, host_api_name)
            for _similarity, _priority, index, device, host_api_name in candidates
        ]

    @staticmethod
    def _normalized_name(name: str) -> str:
        return "".join(
            character for character in name.casefold() if character.isalnum()
        )


class SoundCardCapture:
    """Capture a loopback input and microphone on independent threads."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        block_frames: int = 1_600,
        backend: SoundCardBackend | ModuleType | None = None,
        microphone_fallback: MicrophoneFallback | None = None,
    ) -> None:
        if backend is None:
            import soundcard

            backend = soundcard
        self._backend = backend
        self._sample_rate = sample_rate
        self._block_frames = block_frames
        self._stop_event = Event()
        self._threads: list[Thread] = []
        self._microphone_fallback = (
            microphone_fallback
            if microphone_fallback is not None
            else PortAudioMicrophoneCapture()
        )

    def start(
        self,
        desktop_device_id: str,
        microphone_device_id: str,
        callback: AudioCallback,
        error_callback: ErrorCallback,
    ) -> None:
        if self._threads:
            raise RuntimeError("音声キャプチャは既に実行中です。")
        self._stop_event.clear()
        for source, device_id in (
            (DESKTOP, desktop_device_id),
            (MICROPHONE, microphone_device_id),
        ):
            thread = Thread(
                target=self._capture,
                args=(source, device_id, callback, error_callback),
                name=f"capture-{source}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        if self._threads:
            names = ", ".join(thread.name for thread in self._threads)
            raise RuntimeError(f"音声キャプチャを停止できませんでした: {names}")

    def _capture(
        self,
        source: str,
        device_id: str,
        callback: AudioCallback,
        error_callback: ErrorCallback,
    ) -> None:
        device = None
        try:
            device = self._backend.get_microphone(
                device_id,
                include_loopback=True,
            )
            if source == MICROPHONE and "loop120" in str(device.name).casefold():
                self._capture_with_microphone_fallback(
                    source,
                    device_id,
                    str(device.name),
                    callback,
                    error_callback,
                )
                return
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="^data discontinuity in recording$",
                    category=RuntimeWarning,
                )
                with device.recorder(
                    samplerate=self._sample_rate,
                    blocksize=self._block_frames * 2,
                ) as recorder:
                    while not self._stop_event.is_set():
                        block = recorder.record(numframes=self._block_frames)
                        callback(source, to_mono(block))
        except AssertionError as soundcard_error:
            if source != MICROPHONE:
                error_callback(AudioCaptureError(source, device_id, soundcard_error))
                return
            self._capture_with_microphone_fallback(
                source,
                device_id,
                str(device.name) if device is not None else device_id,
                callback,
                error_callback,
            )
        except Exception as error:  # noqa: BLE001 - native backend errors vary
            error_callback(AudioCaptureError(source, device_id, error))

    def _capture_with_microphone_fallback(
        self,
        source: str,
        device_id: str,
        device_name: str,
        callback: AudioCallback,
        error_callback: ErrorCallback,
    ) -> None:
        try:
            self._microphone_fallback.capture(
                device_name,
                self._sample_rate,
                self._block_frames,
                self._stop_event,
                lambda samples: callback(source, samples),
            )
        except Exception as fallback_error:  # noqa: BLE001
            error_callback(AudioCaptureError(source, device_id, fallback_error))
